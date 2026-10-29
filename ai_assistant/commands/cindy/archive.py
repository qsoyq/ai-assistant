"""Self-contained, bounded PAX snapshots with per-file integrity records."""

from __future__ import annotations

import gzip
import hashlib
import importlib
import importlib.metadata
import io
import json
import math
import os
import re
import stat
import tarfile
import unicodedata
import uuid
from contextlib import ExitStack, contextmanager
from datetime import datetime, timezone
from pathlib import Path, PurePosixPath, PureWindowsPath
from typing import Any, BinaryIO, Callable, Iterator, cast

from .common import MAX_BYTES, MAX_ENTRIES, CindyError
from .paths import (
    RESERVED,
    Profile,
    check_space,
    disjoint,
    exists,
    identity,
    is_link,
    private_dir,
    root_path,
)
from .schema import schema_versions
from .state import atomic_json, index_update, read_json, sync_dir

HEADER = "cindy-backup.json"
TAIL = "cindy-files.jsonl"
RUNTIME = {"SingletonLock", "SingletonSocket", "SingletonCookie", "lockfile"}
CACHES = {"Cache", "Code Cache", "GPUCache", "DawnGraphiteCache", "DawnWebGPUCache"}
META_LIMIT = 64 * 1024**2


class SafeTarInfo(tarfile.TarInfo):
    def _proc_member(self, archive: tarfile.TarFile) -> tarfile.TarInfo:
        if self.type in {tarfile.XHDTYPE, tarfile.XGLTYPE, tarfile.GNUTYPE_LONGNAME, tarfile.GNUTYPE_LONGLINK} and self.size > 1024**2:
            raise CindyError("PAX/长文件名元数据超过上限。", 4)
        if self.type == tarfile.GNUTYPE_SPARSE:
            raise CindyError("不支持 sparse 成员。", 4)
        processor = cast(Callable[[tarfile.TarInfo, tarfile.TarFile], tarfile.TarInfo], getattr(tarfile.TarInfo, "_proc_member"))
        return processor(self, archive)


def json_bytes(value: Any) -> bytes:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")


def safe_member(name: str) -> str:
    if not name or len(name.encode("utf-8")) > 4096 or "\\" in name or ":" in name or name.startswith("/") or any(ord(c) < 32 for c in name):
        raise CindyError(f"不安全的归档成员路径：{name!r}", 4)
    parts = name.split("/")
    if any(part in {"", ".", ".."} or part.rstrip(" .") != part or part.split(".")[0].upper() in RESERVED for part in parts):
        raise CindyError(f"不安全的归档成员路径：{name!r}", 4)
    return unicodedata.normalize("NFC", name).casefold()


def claim_path(name: str, spellings: dict[str, str]) -> str:
    canonical = safe_member(name)
    parts = name.split("/")
    for count in range(1, len(parts) + 1):
        prefix = "/".join(parts[:count])
        key = unicodedata.normalize("NFC", prefix).casefold()
        if key in spellings and spellings[key] != prefix:
            raise CindyError("归档路径祖先有大小写或 Unicode 规范化冲突。", 4)
        spellings[key] = prefix
    return canonical


def fingerprint(path: Path) -> tuple[int, ...]:
    value = path.lstat()
    return value.st_dev, value.st_ino, value.st_mode, value.st_size, value.st_mtime_ns, value.st_ctime_ns


def inventory(root: Path, *, exclude_caches: bool = False, include_updates: bool = False) -> dict[str, tuple[int, ...]]:
    result: dict[str, tuple[int, ...]] = {}

    def walk(directory: Path) -> None:
        with os.scandir(directory) as entries:
            for item in sorted(entries, key=lambda entry: entry.name):
                path = Path(item.path)
                name = path.relative_to(root).as_posix()
                top = name.split("/")[0]
                if top in RUNTIME or (exclude_caches and top in CACHES) or (top == "updates" and "/" in name and not include_updates):
                    continue
                safe_member(name)
                info = path.lstat()
                if getattr(info, "st_reparse_tag", 0):
                    raise CindyError("Windows reparse point 归档尚未通过实机门禁。", 5)
                if not (stat.S_ISDIR(info.st_mode) or stat.S_ISREG(info.st_mode) or stat.S_ISLNK(info.st_mode)):
                    raise CindyError(f"不支持特殊文件：{name}", 4)
                result[name] = fingerprint(path)
                if stat.S_ISDIR(info.st_mode):
                    if os.path.ismount(path):
                        raise CindyError(f"Profile 内有挂载点，拒绝跨卷遍历：{name}", 4)
                    walk(path)

    walk(root)
    return result


def zstd_module() -> Any:
    for module in ("zstandard", "compression.zstd"):
        try:
            return importlib.import_module(module)
        except ImportError:
            pass
    raise CindyError("需要 zstd 解码能力，请安装 ai-assistant[cindy] 或使用 Python 3.14。", 2)


@contextmanager
def archive_stream(raw: BinaryIO, mode: str, compression: str | None = None) -> Iterator[BinaryIO]:
    with ExitStack() as stack:
        if mode == "r":
            magic = raw.read(4)
            raw.seek(0)
            compression = "gzip" if magic.startswith(b"\x1f\x8b") else ("zstd" if magic == b"\x28\xb5\x2f\xfd" else "none")
        stream: Any
        if compression == "gzip":
            stream = stack.enter_context(gzip.GzipFile(fileobj=raw, mode=f"{mode}b", compresslevel=1))
        elif compression == "zstd":
            module = zstd_module()
            if module.__name__ == "zstandard":
                if mode == "r":
                    stream = stack.enter_context(module.ZstdDecompressor(max_window_size=128 * 1024**2).stream_reader(raw, closefd=False))
                else:
                    stream = stack.enter_context(module.ZstdCompressor(level=3, threads=2, write_checksum=True).stream_writer(raw, closefd=False))
            else:
                if mode == "r":
                    stream = stack.enter_context(module.ZstdFile(raw, "rb", options={module.DecompressionParameter.window_log_max: 27}))
                else:
                    stream = stack.enter_context(
                        module.ZstdFile(raw, "wb", options={module.CompressionParameter.compression_level: 3, module.CompressionParameter.checksum_flag: 1, module.CompressionParameter.nb_workers: 2})
                    )
        else:
            stream = raw
        try:
            yield stream
        except Exception as exc:
            if type(exc).__module__.startswith(("zstandard", "compression.zstd")) or isinstance(exc, gzip.BadGzipFile):
                raise CindyError("压缩流损坏或解码窗口超过限制。", 4) from exc
            raise


def validate_header(value: Any) -> dict[str, Any]:
    if not isinstance(value, dict) or value.get("format") != "ai-assistant.cindy-backup" or value.get("format_version") != 1:
        raise CindyError("不是受支持的 Cindy 备份格式。", 4)
    profile = value.get("profile")
    if not isinstance(profile, dict) or set(profile) != set(Profile.__dataclass_fields__) or any(not isinstance(profile.get(key), str) for key in Profile.__dataclass_fields__):
        raise CindyError("备份 Profile 清单损坏。", 4)
    if profile["keychain_identity"] not in {"absent", "Cindy", "CindyDev"}:
        raise CindyError("归档钥匙串身份标记无法识别。", 4)
    if profile["region"] not in {"cn", "global", "dev"} or profile["kind"] not in {"main", "isolated", "custom"}:
        raise CindyError("备份区域或 Profile 类型无效。", 4)
    source_path = PureWindowsPath(profile["path"]) if profile["platform"] == "win32" else PurePosixPath(profile["path"])
    if profile["platform"] not in {"darwin", "win32", "linux"} or profile["arch"] not in {"x64", "arm64"} or not source_path.is_absolute():
        raise CindyError("备份平台或来源路径无效。", 4)
    schemas = value.get("schema")
    if not isinstance(schemas, dict) or any(
        not isinstance(name, str) or "/" in name or "\\" in name or (version is not None and (type(version) is not int or version < 0)) for name, version in schemas.items()
    ):
        raise CindyError("归档 schema 元数据无效。", 4)
    for key in ("entries", "bytes"):
        if type(value.get(key)) is not int or value[key] < 0:
            raise CindyError("备份计数无效。", 4)
    for key in ("backup_id", "created_at", "kind", "label"):
        if not isinstance(value.get(key), str):
            raise CindyError(f"备份缺少字段：{key}", 4)
    if value["kind"] not in {"manual", "pre-restore", "pre-reset"}:
        raise CindyError("未知备份类型。", 4)
    return value


def read_member(archive: tarfile.TarFile, member: tarfile.TarInfo, limit: int) -> bytes:
    if not member.isfile() or member.size > limit or member.size < 0:
        raise CindyError("归档元数据超过限制或类型无效。", 4)
    stream = archive.extractfile(member)
    if stream is None:
        raise CindyError("归档成员不可读。", 4)
    with stream:
        return stream.read(limit + 1)


def read_header(path: Path) -> dict[str, Any]:
    try:
        with path.open("rb") as raw, archive_stream(raw, "r") as stream, tarfile.open(fileobj=stream, mode="r|", bufsize=512, tarinfo=SafeTarInfo) as archive:
            member = archive.next()
            if member is None or member.name != HEADER:
                raise CindyError("归档首成员必须为 cindy-backup.json。", 4)
            return validate_header(json.loads(read_member(archive, member, 1024**2)))
    except (tarfile.TarError, EOFError, UnicodeError, ValueError) as exc:
        raise CindyError("归档头损坏。", 4) from exc


def add_bytes(archive: tarfile.TarFile, name: str, data: bytes) -> None:
    member = tarfile.TarInfo(name)
    member.size = len(data)
    member.mode = 0o600
    archive.addfile(member, io.BytesIO(data))


class HashReader:
    def __init__(self, stream: BinaryIO):
        self.stream = stream
        self.digest = hashlib.sha256()

    def read(self, size: int = -1) -> bytes:
        data = self.stream.read(size)
        self.digest.update(data)
        return data


def create_backup(
    profile: Profile,
    output: Path,
    *,
    compression: str = "auto",
    label: str = "",
    kind: str = "manual",
    transaction_id: str | None = None,
    exclude_caches: bool = False,
    include_updates: bool = False,
    max_bytes: int = MAX_BYTES,
    max_entries: int = MAX_ENTRIES,
    check: Callable[[], None] | None = None,
) -> tuple[Path, dict[str, Any]]:
    root = root_path(Path(profile.path))
    output = root_path(output)
    disjoint(root, output)
    if not root.is_dir():
        raise CindyError(f"Profile 不存在：{root}")
    if len(label) > 80 or any(ord(c) < 32 for c in label):
        raise CindyError("label 最多 80 字且不能有控制字符。", 2)
    if compression == "auto":
        try:
            zstd_module()
            compression = "zstd"
        except CindyError:
            compression = "none"
    if compression not in {"none", "zstd", "gzip"}:
        raise CindyError("不支持的压缩格式。", 2)
    original_root_id = identity(root)
    before = inventory(root, exclude_caches=exclude_caches, include_updates=include_updates)
    total = sum(value[3] for value in before.values() if stat.S_ISREG(value[2]))
    if total > max_bytes or len(before) > max_entries:
        raise CindyError("Profile 超过容量或成员上限。", 4)
    private_dir(output)
    check_space(output, total + len(before) * 2048)
    identifier = uuid.uuid4().hex
    now = datetime.now(timezone.utc)
    header = {
        "format": "ai-assistant.cindy-backup",
        "format_version": 1,
        "backup_id": identifier,
        "created_at": now.isoformat(),
        "tool_version": importlib.metadata.version("ai-assistant"),
        "profile": profile.to_dict(),
        "entries": len(before),
        "bytes": total,
        "kind": kind,
        "transaction_id": transaction_id,
        "label": label,
        "compression": compression,
        "exclude_caches": exclude_caches,
        "include_update_cache": include_updates,
        "schema": schema_versions(root),
        "shared": [name for name in before if "/" not in name and name.startswith("shared-")],
    }
    suffix = {"none": ".tar", "zstd": ".tar.zst", "gzip": ".tar.gz"}[compression]
    slug = re.sub(r"[^A-Za-z0-9._-]+", "-", label).strip("-")[:40]
    path = output / f"cindy-{profile.region}-{now.strftime('%Y%m%dT%H%M%SZ')}-{identifier}{f'-{slug}' if slug else ''}{suffix}"
    partial = path.with_name(f"{path.name}.partial")
    records: list[dict[str, Any]] = []
    header_raw = json_bytes(header)
    partial_record = partial.with_name(f"{partial.name}.json")
    with os.fdopen(os.open(partial, os.O_RDWR | os.O_CREAT | os.O_EXCL, 0o600), "w+b") as raw:
        atomic_json(partial_record, {"header": header, "file_id": identity(partial), "path": str(partial)})
        with archive_stream(raw, "w", compression) as stream, tarfile.open(fileobj=stream, mode="w|", format=tarfile.PAX_FORMAT) as archive:
            add_bytes(archive, HEADER, header_raw)
            for name, expected in before.items():
                source = root / name
                if fingerprint(source) != expected:
                    raise CindyError("备份期间源树发生变化。", 6)
                member = tarfile.TarInfo(f"data/{name}")
                member.mode = stat.S_IMODE(expected[2]) & 0o777
                member.mtime = expected[4] / 1_000_000_000
                record: dict[str, Any] = {"path": name, "mode": member.mode, "mtime": member.mtime}
                if stat.S_ISLNK(expected[2]):
                    member.type = tarfile.SYMTYPE
                    member.linkname = os.readlink(source)
                    record.update(type="link", target=member.linkname)
                    archive.addfile(member)
                elif stat.S_ISDIR(expected[2]):
                    member.type = tarfile.DIRTYPE
                    record["type"] = "dir"
                    archive.addfile(member)
                else:
                    member.size = expected[3]
                    with os.fdopen(os.open(source, os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0)), "rb") as content:
                        reader = HashReader(content)
                        archive.addfile(member, reader)
                        record.update(type="file", bytes=member.size, sha256=reader.digest.hexdigest())
                        if content.read(1):
                            raise CindyError("备份期间文件增长。", 6)
                records.append(record)
            tail = b"\n".join([json_bytes({"header_sha256": hashlib.sha256(header_raw).hexdigest()}), *(json_bytes(row) for row in records)]) + b"\n"
            if len(tail) > META_LIMIT:
                raise CindyError("尾清单超过上限。", 4)
            add_bytes(archive, TAIL, tail)
        raw.flush()
        os.fsync(raw.fileno())
    verify_backup(partial, max_bytes=max_bytes, max_entries=max_entries, check_index=False)
    if identity(root) != original_root_id or inventory(root, exclude_caches=exclude_caches, include_updates=include_updates) != before:
        raise CindyError("备份期间源树发生变化，保留 partial，不发布。", 6)
    if check:
        check()
    os.rename(partial, path)
    partial_record.unlink(missing_ok=True)
    sync_dir(output)
    try:
        index_update(output, path, header)
    except OSError as exc:
        raise CindyError(f"归档已发布但索引写入失败：{path}", 6) from exc
    return path, header


def verify_backup(path: Path, *, destination: Path | None = None, max_bytes: int = MAX_BYTES, max_entries: int = MAX_ENTRIES, check_index: bool = True) -> dict[str, Any]:
    if is_link(path) or not path.is_file():
        raise CindyError("归档必须是普通文件，不能是链接。", 4)
    if destination is not None:
        if exists(destination) and any(destination.iterdir()):
            raise CindyError("解包目标必须为空。", 4)
        private_dir(destination)
    try:
        with path.open("rb") as raw:
            before = os.fstat(raw.fileno())
            hasher = hashlib.sha256()
            while block := raw.read(1024**2):
                hasher.update(block)
            digest = hasher.hexdigest()
            raw.seek(0)
            with archive_stream(raw, "r") as stream, tarfile.open(fileobj=stream, mode="r|", bufsize=512, tarinfo=SafeTarInfo) as archive:
                first = archive.next()
                if first is None or first.name != HEADER:
                    raise CindyError("缺少归档首清单。", 4)
                header_raw = read_member(archive, first, 1024**2)
                header = validate_header(json.loads(header_raw))
                if header["bytes"] > max_bytes or header["entries"] > max_entries:
                    raise CindyError("归档声明超过容量限制。", 4)
                records: list[dict[str, Any]] = []
                seen: dict[str, str] = {}
                types: dict[str, str] = {}
                spellings: dict[str, str] = {}
                links = []
                directories = []
                total = 0
                got_tail = False
                while member := archive.next():
                    if member.name == TAIL:
                        tail_raw = read_member(archive, member, META_LIMIT)
                        if any(len(line) > 65536 for line in tail_raw.splitlines()):
                            raise CindyError("清单行超过上限。", 4)
                        tail = [json.loads(line) for line in tail_raw.splitlines()]
                        if not tail or tail[0] != {"header_sha256": hashlib.sha256(header_raw).hexdigest()} or tail[1:] != records:
                            raise CindyError("归档内容或尾清单摘要不一致。", 4)
                        if archive.next() is not None:
                            raise CindyError("尾清单之后存在额外成员。", 4)
                        got_tail = True
                        break
                    if not member.name.startswith("data/") or member.sparse is not None or any(key.startswith("GNU.sparse") for key in member.pax_headers):
                        raise CindyError("归档成员不在 data/ 或使用不支持的扩展。", 4)
                    name = member.name[5:].rstrip("/")
                    canonical = claim_path(name, spellings)
                    if canonical in seen:
                        raise CindyError("归档包含重复或规范化冲突路径。", 4)
                    seen[canonical] = name
                    if len(seen) > min(max_entries, header["entries"]):
                        raise CindyError("归档成员数超过声明或限制。", 4)
                    if member.mode & 0o7000 or member.size < 0 or not math.isfinite(member.mtime) or not (member.isdir() or member.isfile() or member.issym()):
                        raise CindyError("不支持的成员类型或权限。", 4)
                    kind = "dir" if member.isdir() else ("link" if member.issym() else "file")
                    types[name] = kind
                    if any(types.get(parent.as_posix()) in {"link", "file"} for parent in PurePosixPath(name).parents if parent.as_posix() != "."):
                        raise CindyError("成员祖先不是目录。", 4)
                    if kind != "dir" and any(previous.startswith(f"{name}/") for previous in types):
                        raise CindyError("成员覆盖已有目录或链接祖先。", 4)
                    record = {"path": name, "mode": member.mode, "mtime": member.mtime, "type": kind}
                    target = destination / name if destination is not None else None
                    if target is not None:
                        target.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
                    if kind == "file":
                        total += member.size
                        if total > min(max_bytes, header["bytes"]):
                            raise CindyError("归档展开大小超过声明或限制。", 4)
                        source = archive.extractfile(member)
                        if source is None:
                            raise CindyError("文件内容缺失。", 4)
                        hasher = hashlib.sha256()
                        remaining = member.size
                        with ExitStack() as stack:
                            stack.enter_context(source)
                            output = stack.enter_context(target.open("xb")) if target is not None else None
                            while remaining:
                                data = source.read(min(1024**2, remaining))
                                if not data:
                                    raise CindyError("归档截断。", 4)
                                hasher.update(data)
                                remaining -= len(data)
                                if output is not None:
                                    output.write(data)
                        record.update(bytes=member.size, sha256=hasher.hexdigest())
                        if target is not None:
                            target.chmod(member.mode & 0o777)
                            os.utime(target, (member.mtime, member.mtime))
                    elif kind == "link":
                        if len(member.linkname.encode()) > 4096 or "\x00" in member.linkname:
                            raise CindyError("链接目标无效。", 4)
                        record["target"] = member.linkname
                        links.append((target, member.linkname))
                    else:
                        if target is not None:
                            target.mkdir(mode=0o700, exist_ok=True)
                            directories.append((target, member))
                    records.append(record)
                if not got_tail or len(records) != header["entries"] or total != header["bytes"]:
                    raise CindyError("归档缺少尾清单或计数不一致。", 4)
                # Drain the decoder to validate gzip/zstd trailers, without allowing hidden payloads.
                padding = 0
                while block := stream.read(10240):
                    padding += len(block)
                    if padding > 10240 or block.strip(b"\x00"):
                        raise CindyError("归档结束后存在额外内容或过量填充。", 4)
            after = os.fstat(raw.fileno())
            if (before.st_ino, before.st_size, before.st_mtime_ns, before.st_ctime_ns) != (after.st_ino, after.st_size, after.st_mtime_ns, after.st_ctime_ns) or fingerprint(path)[:2] != (
                before.st_dev,
                before.st_ino,
            ):
                raise CindyError("读取期间归档被替换或修改。", 6)
            if check_index:
                expected = read_json(path.parent / "index.json").get("records", {}).get(path.name, {}).get("sha256")
                if expected and expected != digest:
                    raise CindyError("索引中的归档 SHA-256 不匹配。", 4)
            for target, link in links:
                if target is not None:
                    target.symlink_to(link)
            for target, member in reversed(directories):
                target.chmod(member.mode & 0o777)
                os.utime(target, (member.mtime, member.mtime))
            header["archive_sha256"] = digest
            return header
    except (tarfile.TarError, EOFError, UnicodeError, ValueError) as exc:
        raise CindyError("归档损坏或格式无效。", 4) from exc
