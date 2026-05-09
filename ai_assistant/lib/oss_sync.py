"""阿里云 OSS 同步与传输底层逻辑。"""

from __future__ import annotations

import dataclasses
import os
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import Callable, Literal

import oss2

OSS_PREFIX = "oss:"
META_MTIME_KEY = "x-oss-meta-mtime"


@dataclasses.dataclass
class OssConfig:
    access_key_id: str
    access_key_secret: str
    endpoint: str
    bucket_name: str
    security_token: str | None = None

    @classmethod
    def resolve(
        cls,
        access_key_id: str | None = None,
        access_key_secret: str | None = None,
        endpoint: str | None = None,
        region: str | None = None,
        bucket_name: str | None = None,
        security_token: str | None = None,
    ) -> "OssConfig":
        ak = access_key_id or os.environ.get("OSS_ACCESS_KEY_ID")
        sk = access_key_secret or os.environ.get("OSS_ACCESS_KEY_SECRET")
        ep = endpoint or os.environ.get("OSS_ENDPOINT")
        rg = region or os.environ.get("OSS_REGION")
        bk = bucket_name or os.environ.get("OSS_BUCKET")
        st = security_token or os.environ.get("OSS_SESSION_TOKEN")

        if not ep and rg:
            normalized = rg if rg.startswith("oss-") else f"oss-{rg}"
            ep = f"https://{normalized}.aliyuncs.com"

        missing: list[str] = []
        if not ak:
            missing.append("OSS_ACCESS_KEY_ID")
        if not sk:
            missing.append("OSS_ACCESS_KEY_SECRET")
        if not ep:
            missing.append("OSS_ENDPOINT 或 OSS_REGION")
        if not bk:
            missing.append("OSS_BUCKET")
        if missing:
            raise RuntimeError(f"OSS 配置缺失: {', '.join(missing)}")

        assert ak and sk and ep and bk
        return cls(ak, sk, ep, bk, st)


def build_bucket(cfg: OssConfig) -> oss2.Bucket:
    if cfg.security_token:
        auth = oss2.StsAuth(cfg.access_key_id, cfg.access_key_secret, cfg.security_token)
    else:
        auth = oss2.Auth(cfg.access_key_id, cfg.access_key_secret)
    return oss2.Bucket(auth, cfg.endpoint, cfg.bucket_name)


def parse_oss_path(path: str) -> tuple[bool, str | None, str]:
    """返回 (是否为 OSS 路径, URI 显式带的 bucket | None, 剥离前缀后的 key 前缀)。

    支持两种形式:
    - ``oss:prefix/``       → ``(True, None, "prefix/")``  使用 --bucket / OSS_BUCKET
    - ``oss://bucket/path`` → ``(True, "bucket", "path")`` URI 内含 bucket
    - ``oss://bucket``      → ``(True, "bucket", "")``     根前缀
    本地路径               → ``(False, None, path)``      原样返回
    """
    if path.startswith("oss://"):
        rest = path[len("oss://") :]
        if "/" in rest:
            bucket, prefix = rest.split("/", 1)
        else:
            bucket, prefix = rest, ""
    elif path.startswith(OSS_PREFIX):
        bucket = None
        prefix = path[len(OSS_PREFIX) :]
    else:
        return False, None, path
    return True, bucket, prefix.lstrip("/")


@dataclasses.dataclass
class SyncItem:
    action: Literal["upload", "download", "delete-local", "delete-remote"]
    rel: str
    size: int
    local_path: Path | None = None
    oss_key: str | None = None
    reason: str = ""  # 触发本次操作的原因, 用于 dry-run 显示


@dataclasses.dataclass
class SyncPlan:
    direction: Literal["up", "down"]
    items: list[SyncItem]
    truncated: bool = False  # 是否被 max_files 截断
    total_before_cap: int = 0


def _walk_local(root: Path) -> dict[str, tuple[int, float]]:
    out: dict[str, tuple[int, float]] = {}
    if not root.exists():
        return out
    if root.is_file():
        st = root.stat()
        out[root.name] = (st.st_size, st.st_mtime)
        return out
    for p in root.rglob("*"):
        if p.is_file():
            rel = str(p.relative_to(root)).replace(os.sep, "/")
            st = p.stat()
            out[rel] = (st.st_size, st.st_mtime)
    return out


def _walk_oss(bucket: oss2.Bucket, prefix: str) -> dict[str, tuple[int, float]]:
    """返回 {相对 key: (size, server_last_modified_epoch)}.

    服务端 Last-Modified 在列举响应里就有, 不需额外 head_object.
    """
    out: dict[str, tuple[int, float]] = {}
    norm = prefix
    if norm and not norm.endswith("/"):
        norm = norm + "/"
    for obj in oss2.ObjectIteratorV2(bucket, prefix=norm):
        key = obj.key
        if key.endswith("/"):
            continue
        rel = key[len(norm) :] if norm else key
        out[rel] = (obj.size, float(obj.last_modified))
    return out


def _head_meta_mtime(bucket: oss2.Bucket, key: str) -> float | None:
    try:
        meta = bucket.head_object(key)
        v = meta.headers.get(META_MTIME_KEY)
        if v:
            return float(v)
    except oss2.exceptions.OssError:
        return None
    return None


def compute_sync_plan(
    bucket: oss2.Bucket,
    src: str,
    dst: str,
    delete: bool = False,
    force: bool = False,
    max_files: int | None = None,
) -> SyncPlan:
    src_is_oss, src_uri_bucket, src_path = parse_oss_path(src)
    dst_is_oss, dst_uri_bucket, dst_path = parse_oss_path(dst)

    if src_is_oss == dst_is_oss:
        raise ValueError("sync 必须一端是本地路径、另一端是 oss: 路径")

    for uri_bucket, label in ((src_uri_bucket, "源"), (dst_uri_bucket, "目标")):
        if uri_bucket and uri_bucket != bucket.bucket_name:
            raise ValueError(f"{label} URI 指定的 bucket={uri_bucket!r} 与当前配置 bucket={bucket.bucket_name!r} 不一致")

    if src_is_oss:
        return _plan_download(bucket, src_path, Path(dst_path), delete, force, max_files)
    return _plan_upload(bucket, Path(src_path), dst_path, delete, force, max_files)


def _plan_upload(
    bucket: oss2.Bucket,
    local_root: Path,
    oss_prefix: str,
    delete: bool,
    force: bool,
    max_files: int | None,
) -> SyncPlan:
    local_files = _walk_local(local_root)
    remote_files = _walk_oss(bucket, oss_prefix)
    norm_prefix = oss_prefix if not oss_prefix or oss_prefix.endswith("/") else oss_prefix + "/"

    items: list[SyncItem] = []

    for rel, (size, mtime) in sorted(local_files.items()):
        oss_key = norm_prefix + rel
        if force:
            items.append(SyncItem("upload", rel, size, local_root / rel, oss_key, reason="force"))
            continue
        if rel not in remote_files:
            items.append(SyncItem("upload", rel, size, local_root / rel, oss_key, reason="new"))
            continue
        remote_size, remote_lm = remote_files[rel]
        if remote_size != size:
            items.append(SyncItem("upload", rel, size, local_root / rel, oss_key, reason="size-changed"))
            continue
        meta_mtime = _head_meta_mtime(bucket, oss_key)
        if meta_mtime is not None:
            if abs(meta_mtime - mtime) > 1.0:
                items.append(SyncItem("upload", rel, size, local_root / rel, oss_key, reason="mtime-changed"))
            continue
        # 远端没有 x-oss-meta-mtime (非本 CLI 上传过的对象), 回退到 ossutil 风格:
        # 比较本地 mtime 与服务端 Last-Modified, 仅当本地明显更新时才上传.
        if mtime > remote_lm + 1.0:
            items.append(SyncItem("upload", rel, size, local_root / rel, oss_key, reason="local-newer"))

    if delete:
        for rel, (size, _lm) in sorted(remote_files.items()):
            if rel not in local_files:
                items.append(SyncItem("delete-remote", rel, size, None, norm_prefix + rel, reason="extra-on-remote"))

    total = len(items)
    truncated = False
    if max_files is not None and total > max_files:
        items = items[:max_files]
        truncated = True

    return SyncPlan("up", items, truncated, total)


def _plan_download(
    bucket: oss2.Bucket,
    oss_prefix: str,
    local_root: Path,
    delete: bool,
    force: bool,
    max_files: int | None,
) -> SyncPlan:
    local_files = _walk_local(local_root)
    remote_files = _walk_oss(bucket, oss_prefix)
    norm_prefix = oss_prefix if not oss_prefix or oss_prefix.endswith("/") else oss_prefix + "/"

    items: list[SyncItem] = []

    for rel, (size, remote_lm) in sorted(remote_files.items()):
        local_path = local_root / rel
        oss_key = norm_prefix + rel
        if force:
            items.append(SyncItem("download", rel, size, local_path, oss_key, reason="force"))
            continue
        if rel not in local_files:
            items.append(SyncItem("download", rel, size, local_path, oss_key, reason="new"))
            continue
        local_size, local_mtime = local_files[rel]
        if local_size != size:
            items.append(SyncItem("download", rel, size, local_path, oss_key, reason="size-changed"))
            continue
        meta_mtime = _head_meta_mtime(bucket, oss_key)
        if meta_mtime is not None:
            if abs(meta_mtime - local_mtime) > 1.0:
                items.append(SyncItem("download", rel, size, local_path, oss_key, reason="mtime-changed"))
            continue
        # 远端没有 x-oss-meta-mtime, 回退: 仅当服务端 Last-Modified 明显更新时下载.
        if remote_lm > local_mtime + 1.0:
            items.append(SyncItem("download", rel, size, local_path, oss_key, reason="remote-newer"))

    if delete:
        for rel, (size, _mtime) in sorted(local_files.items()):
            if rel not in remote_files:
                items.append(SyncItem("delete-local", rel, size, local_root / rel, None, reason="extra-on-local"))

    total = len(items)
    truncated = False
    if max_files is not None and total > max_files:
        items = items[:max_files]
        truncated = True

    return SyncPlan("down", items, truncated, total)


# ---------- 执行同步 ----------


@dataclasses.dataclass
class TransferEvent:
    item: SyncItem
    consumed: int = 0
    total: int = 0
    done: bool = False
    error: BaseException | None = None


ProgressCb = Callable[[TransferEvent], None]


def _upload_one(bucket: oss2.Bucket, item: SyncItem, on_progress: ProgressCb | None) -> None:
    assert item.local_path is not None and item.oss_key is not None
    mtime_str = str(item.local_path.stat().st_mtime)
    headers = {META_MTIME_KEY: mtime_str}

    def cb(consumed: int, total: int) -> None:
        if on_progress:
            on_progress(TransferEvent(item, consumed, total))

    if item.size <= 5 * 1024 * 1024:
        bucket.put_object_from_file(item.oss_key, str(item.local_path), headers=headers, progress_callback=cb)
    else:
        oss2.resumable_upload(
            bucket,
            item.oss_key,
            str(item.local_path),
            headers=headers,
            progress_callback=cb,
            num_threads=1,
        )


def _download_one(bucket: oss2.Bucket, item: SyncItem, on_progress: ProgressCb | None) -> None:
    assert item.local_path is not None and item.oss_key is not None
    item.local_path.parent.mkdir(parents=True, exist_ok=True)

    def cb(consumed: int, total: int) -> None:
        if on_progress:
            on_progress(TransferEvent(item, consumed, total))

    if item.size <= 5 * 1024 * 1024:
        bucket.get_object_to_file(item.oss_key, str(item.local_path), progress_callback=cb)
    else:
        oss2.resumable_download(
            bucket,
            item.oss_key,
            str(item.local_path),
            progress_callback=cb,
            num_threads=1,
        )

    meta_mtime = _head_meta_mtime(bucket, item.oss_key)
    if meta_mtime is not None:
        os.utime(item.local_path, (time.time(), meta_mtime))


def _delete_remote(bucket: oss2.Bucket, item: SyncItem, on_progress: ProgressCb | None) -> None:
    assert item.oss_key is not None
    bucket.delete_object(item.oss_key)


def _delete_local(_bucket: oss2.Bucket, item: SyncItem, on_progress: ProgressCb | None) -> None:
    assert item.local_path is not None
    if item.local_path.exists():
        item.local_path.unlink()


_HANDLERS: dict[str, Callable[[oss2.Bucket, SyncItem, ProgressCb | None], None]] = {
    "upload": _upload_one,
    "download": _download_one,
    "delete-remote": _delete_remote,
    "delete-local": _delete_local,
}


@dataclasses.dataclass
class SyncResult:
    succeeded: list[SyncItem] = dataclasses.field(default_factory=list)
    failed: list[tuple[SyncItem, BaseException]] = dataclasses.field(default_factory=list)


def execute_sync(
    bucket: oss2.Bucket,
    plan: SyncPlan,
    workers: int = 4,
    on_progress: ProgressCb | None = None,
) -> SyncResult:
    result = SyncResult()
    if not plan.items:
        return result

    def run(item: SyncItem) -> tuple[SyncItem, BaseException | None]:
        try:
            handler = _HANDLERS[item.action]
            handler(bucket, item, on_progress)
            if on_progress:
                on_progress(TransferEvent(item, item.size, item.size, done=True))
            return item, None
        except BaseException as exc:  # noqa: BLE001
            if on_progress:
                on_progress(TransferEvent(item, 0, item.size, done=True, error=exc))
            return item, exc

    with ThreadPoolExecutor(max_workers=max(1, workers)) as pool:
        futures = [pool.submit(run, it) for it in plan.items]
        for fut in as_completed(futures):
            item, err = fut.result()
            if err is None:
                result.succeeded.append(item)
            else:
                result.failed.append((item, err))

    return result
