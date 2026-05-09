"""阿里云 OSS 子命令: 对象 CRUD + 签名 URL + 同步。"""

from __future__ import annotations

import functools
import inspect
import sys
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

import oss2
import rich
import typer
from rich.console import Console
from rich.progress import (
    BarColumn,
    DownloadColumn,
    Progress,
    TaskID,
    TextColumn,
    TimeRemainingColumn,
    TransferSpeedColumn,
)
from rich.table import Table

from ai_assistant.commands import version_callback
from ai_assistant.lib.oss_sync import (
    META_MTIME_KEY,
    OssConfig,
    SyncPlan,
    TransferEvent,
    build_bucket,
    compute_sync_plan,
    execute_sync,
    parse_oss_path,
)

helptext = """
阿里云 OSS 工具集

支持对象上传/下载/列举/删除/查看, 预签名 URL, 以及目录同步.

鉴权信息从环境变量或命令行选项读取, 命令行优先:

    OSS_ACCESS_KEY_ID, OSS_ACCESS_KEY_SECRET, OSS_ENDPOINT (或 OSS_REGION),
    OSS_BUCKET, OSS_SESSION_TOKEN (可选, 用于 STS).
"""

cmd = typer.Typer(help=helptext)
console = Console()


# 全局鉴权选项: 同时挂在 root callback 和每个子命令上, 因此选项可放在子命令前后任意位置.
AUTH_OPTIONS: dict[str, Any] = {
    "access_key_id": typer.Option(None, "--access-key-id", envvar="OSS_ACCESS_KEY_ID", help="AccessKey ID"),
    "access_key_secret": typer.Option(None, "--access-key-secret", envvar="OSS_ACCESS_KEY_SECRET", help="AccessKey Secret"),
    "endpoint": typer.Option(None, "--endpoint", envvar="OSS_ENDPOINT", help="OSS endpoint, 如 https://oss-cn-hangzhou.aliyuncs.com"),
    "region": typer.Option(None, "--region", envvar="OSS_REGION", help="OSS 区域, 如 cn-hangzhou; 与 --endpoint 二选一"),
    "bucket_name": typer.Option(None, "--bucket", envvar="OSS_BUCKET", help="Bucket 名称"),
    "security_token": typer.Option(None, "--security-token", envvar="OSS_SESSION_TOKEN", help="STS 临时凭证 Token, 可选"),
}


def _root_callback(
    ctx: typer.Context,
    _: bool = typer.Option(False, "--version", "-v", "-V", callback=version_callback),
    access_key_id: Optional[str] = AUTH_OPTIONS["access_key_id"],
    access_key_secret: Optional[str] = AUTH_OPTIONS["access_key_secret"],
    endpoint: Optional[str] = AUTH_OPTIONS["endpoint"],
    region: Optional[str] = AUTH_OPTIONS["region"],
    bucket_name: Optional[str] = AUTH_OPTIONS["bucket_name"],
    security_token: Optional[str] = AUTH_OPTIONS["security_token"],
) -> None:
    ctx.ensure_object(dict)
    ctx.obj["config_kwargs"] = {
        "access_key_id": access_key_id,
        "access_key_secret": access_key_secret,
        "endpoint": endpoint,
        "region": region,
        "bucket_name": bucket_name,
        "security_token": security_token,
    }


cmd.callback(invoke_without_command=True)(_root_callback)


def with_auth(fn):
    """给子命令注入与 root callback 同名的鉴权选项, 子命令传入的值覆盖 root.

    typer 通过函数签名生成命令行参数, 这里用 inspect.Signature 把鉴权 KEYWORD_ONLY
    参数追加到原函数签名末尾, 再让 wrapper 把这些参数从 kwargs 中 pop 出来合并到 ctx.obj.
    """
    sig = inspect.signature(fn)
    extra = [inspect.Parameter(name, inspect.Parameter.KEYWORD_ONLY, default=default, annotation=Optional[str]) for name, default in AUTH_OPTIONS.items()]
    new_sig = sig.replace(parameters=list(sig.parameters.values()) + extra)

    @functools.wraps(fn)
    def wrapper(*args, **kwargs):
        auth = {k: kwargs.pop(k) for k in AUTH_OPTIONS}
        ctx: typer.Context | None = kwargs.get("ctx")
        if ctx is not None:
            ctx.ensure_object(dict)
            base = ctx.obj.get("config_kwargs", {})
            ctx.obj["config_kwargs"] = {k: (auth[k] if auth[k] is not None else base.get(k)) for k in auth}
        return fn(*args, **kwargs)

    wrapper.__signature__ = new_sig  # type: ignore[attr-defined]
    return wrapper


def _resolve_oss_key(ctx: typer.Context, raw: str) -> str:
    """归一化 OSS 参数, 支持三种写法:

    - ``key/path``                裸 key, 原样返回
    - ``oss:key/path``            带前缀, 剥离后返回
    - ``oss://bucket/key/path``   URI 含 bucket: 当前无 bucket 时作为 fallback,
                                  已有 bucket 时校验一致, 不一致直接退出.

    必须在 ``_get_bucket`` 之前调用, 否则 URI 里的 bucket 来不及参与配置解析.
    """
    _is_oss, uri_bucket, key = parse_oss_path(raw)
    if uri_bucket:
        cfg = ctx.obj["config_kwargs"]
        existing = cfg.get("bucket_name")
        if not existing:
            cfg["bucket_name"] = uri_bucket
        elif existing != uri_bucket:
            typer.echo(
                f"URI 指定的 bucket={uri_bucket!r} 与当前配置 bucket={existing!r} 不一致",
                err=True,
            )
            raise typer.Exit(1)
    return key


def _get_bucket(ctx: typer.Context) -> oss2.Bucket:
    if "bucket" in ctx.obj:
        return ctx.obj["bucket"]
    try:
        cfg = OssConfig.resolve(**ctx.obj["config_kwargs"])
    except RuntimeError as exc:
        typer.echo(str(exc), err=True)
        typer.echo("提示: 设置环境变量 OSS_ACCESS_KEY_ID / OSS_ACCESS_KEY_SECRET / OSS_ENDPOINT / OSS_BUCKET", err=True)
        raise typer.Exit(1)
    bucket = build_bucket(cfg)
    ctx.obj["bucket"] = bucket
    ctx.obj["cfg"] = cfg
    return bucket


def _humanize_bytes(n: int) -> str:
    for unit in ("B", "KB", "MB", "GB", "TB"):
        if n < 1024:
            return f"{n:.1f}{unit}" if unit != "B" else f"{n}{unit}"
        n /= 1024  # type: ignore[assignment]
    return f"{n:.1f}PB"


def _progress_columns() -> list:
    return [
        TextColumn("[progress.description]{task.description}"),
        BarColumn(),
        DownloadColumn(),
        TransferSpeedColumn(),
        TimeRemainingColumn(),
    ]


# ---------- upload ----------


@cmd.command()
@with_auth
def upload(
    ctx: typer.Context,
    local_path: Path = typer.Argument(..., help="本地文件路径"),
    oss_key: str = typer.Argument(..., help="OSS 对象 key"),
    force: bool = typer.Option(False, "-f", "--force", help="目标已存在时仍上传 (覆盖)"),
) -> None:
    """上传单个文件到 OSS, 大文件自动分片续传."""
    if not local_path.exists() or not local_path.is_file():
        typer.echo(f"文件不存在或不是普通文件: {local_path}", err=True)
        raise typer.Exit(1)

    oss_key = _resolve_oss_key(ctx, oss_key)
    bucket = _get_bucket(ctx)

    if not force:
        try:
            if bucket.object_exists(oss_key):
                typer.echo(f"目标已存在: {oss_key} (使用 -f 强制覆盖)", err=True)
                raise typer.Exit(1)
        except oss2.exceptions.OssError as exc:
            typer.echo(f"检查目标存在性失败: {exc}", err=True)
            raise typer.Exit(1)

    size = local_path.stat().st_size
    mtime = local_path.stat().st_mtime
    headers = {META_MTIME_KEY: str(mtime)}

    with Progress(*_progress_columns(), console=console) as progress:
        task = progress.add_task(f"upload {oss_key}", total=size)

        def cb(consumed: int, total: int) -> None:
            progress.update(task, completed=consumed, total=total or size)

        if size <= 5 * 1024 * 1024:
            bucket.put_object_from_file(oss_key, str(local_path), headers=headers, progress_callback=cb)
        else:
            oss2.resumable_upload(bucket, oss_key, str(local_path), headers=headers, progress_callback=cb, num_threads=1)

    rich.print(f"[green]✓[/green] 已上传 {local_path} → {oss_key} ({_humanize_bytes(size)})")


# ---------- download ----------


@cmd.command()
@with_auth
def download(
    ctx: typer.Context,
    oss_key: str = typer.Argument(..., help="OSS 对象 key"),
    local_path: Path = typer.Argument(..., help="本地保存路径"),
    force: bool = typer.Option(False, "-f", "--force", help="本地已存在时仍下载 (覆盖)"),
) -> None:
    """从 OSS 下载单个文件, 大文件自动分片续传."""
    oss_key = _resolve_oss_key(ctx, oss_key)
    bucket = _get_bucket(ctx)

    if local_path.exists() and not force:
        typer.echo(f"本地路径已存在: {local_path} (使用 -f 强制覆盖)", err=True)
        raise typer.Exit(1)

    try:
        meta = bucket.head_object(oss_key)
    except oss2.exceptions.NoSuchKey:
        typer.echo(f"对象不存在: {oss_key}", err=True)
        raise typer.Exit(1)

    size = meta.content_length
    local_path.parent.mkdir(parents=True, exist_ok=True)

    with Progress(*_progress_columns(), console=console) as progress:
        task = progress.add_task(f"download {oss_key}", total=size)

        def cb(consumed: int, total: int) -> None:
            progress.update(task, completed=consumed, total=total or size)

        if size <= 5 * 1024 * 1024:
            bucket.get_object_to_file(oss_key, str(local_path), progress_callback=cb)
        else:
            oss2.resumable_download(bucket, oss_key, str(local_path), progress_callback=cb, num_threads=1)

    rich.print(f"[green]✓[/green] 已下载 {oss_key} → {local_path} ({_humanize_bytes(size)})")


# ---------- ls ----------


@cmd.command(name="ls")
@with_auth
def list_objects(
    ctx: typer.Context,
    prefix: str = typer.Argument("", help="对象 key 前缀"),
    recursive: bool = typer.Option(False, "-r", "--recursive", help="递归列举所有层级"),
    limit: int = typer.Option(100, "-n", "--limit", help="最多返回多少条, 0 表示无限"),
    long: bool = typer.Option(False, "-l", "--long", help="显示大小、修改时间、存储类型"),
) -> None:
    """列举 OSS 对象."""
    prefix = _resolve_oss_key(ctx, prefix)
    bucket = _get_bucket(ctx)
    delimiter = "" if recursive else "/"

    if long:
        table = Table(show_header=True, header_style="bold")
        table.add_column("Size", justify="right")
        table.add_column("Modified")
        table.add_column("Storage")
        table.add_column("Key")
        count = 0
        for obj in oss2.ObjectIteratorV2(bucket, prefix=prefix, delimiter=delimiter):
            if obj.is_prefix():
                table.add_row("-", "-", "-", f"[blue]{obj.key}[/blue]")
            else:
                mtime = datetime.fromtimestamp(obj.last_modified, tz=timezone.utc).strftime("%Y-%m-%d %H:%M:%S")
                table.add_row(_humanize_bytes(obj.size), mtime, obj.storage_class or "-", obj.key)
            count += 1
            if limit and count >= limit:
                break
        console.print(table)
        rich.print(f"[dim]列出 {count} 项[/dim]")
    else:
        count = 0
        for obj in oss2.ObjectIteratorV2(bucket, prefix=prefix, delimiter=delimiter):
            print(obj.key)
            count += 1
            if limit and count >= limit:
                break


# ---------- rm ----------


@cmd.command()
@with_auth
def rm(
    ctx: typer.Context,
    keys: list[str] = typer.Argument(..., help="OSS 对象 key, 可多个"),
    yes: bool = typer.Option(False, "-y", "--yes", help="跳过确认"),
    recursive: bool = typer.Option(False, "-r", "--recursive", help="按前缀递归删除"),
) -> None:
    """删除 OSS 对象, 支持多个 key 或前缀递归."""
    keys = [_resolve_oss_key(ctx, k) for k in keys]
    bucket = _get_bucket(ctx)

    targets: list[str] = []
    if recursive:
        for prefix in keys:
            for obj in oss2.ObjectIteratorV2(bucket, prefix=prefix):
                targets.append(obj.key)
    else:
        targets = list(keys)

    if not targets:
        typer.echo("没有匹配的对象", err=True)
        raise typer.Exit(0)

    rich.print(f"将删除 [red]{len(targets)}[/red] 个对象:")
    for k in targets[:20]:
        print(f"  {k}")
    if len(targets) > 20:
        print(f"  ... (省略 {len(targets) - 20} 项)")

    if not yes:
        confirm = typer.confirm("确认删除?")
        if not confirm:
            raise typer.Exit(1)

    for i in range(0, len(targets), 1000):
        batch = targets[i : i + 1000]
        bucket.batch_delete_objects(batch)

    rich.print(f"[green]✓[/green] 已删除 {len(targets)} 个对象")


# ---------- stat ----------


@cmd.command()
@with_auth
def stat(ctx: typer.Context, oss_key: str = typer.Argument(..., help="OSS 对象 key")) -> None:
    """查看 OSS 对象元数据."""
    oss_key = _resolve_oss_key(ctx, oss_key)
    bucket = _get_bucket(ctx)
    try:
        meta = bucket.head_object(oss_key)
    except oss2.exceptions.NoSuchKey:
        typer.echo(f"对象不存在: {oss_key}", err=True)
        raise typer.Exit(1)

    table = Table(show_header=False, box=None)
    table.add_column("Key", style="cyan")
    table.add_column("Value")
    table.add_row("Key", oss_key)
    table.add_row("Size", f"{meta.content_length} ({_humanize_bytes(meta.content_length)})")
    table.add_row("ETag", meta.etag)
    table.add_row("Content-Type", meta.content_type or "-")
    table.add_row("Last-Modified", meta.headers.get("Last-Modified", "-"))
    table.add_row("Storage-Class", meta.headers.get("x-oss-storage-class", "-"))
    if META_MTIME_KEY in meta.headers:
        table.add_row("Meta-Mtime", meta.headers[META_MTIME_KEY])
    console.print(table)


# ---------- cat ----------


@cmd.command()
@with_auth
def cat(
    ctx: typer.Context,
    oss_key: str = typer.Argument(..., help="OSS 对象 key"),
    max_size: int = typer.Option(1024 * 1024, "--max-size", help="允许打印的最大字节数, 防止误打印巨大文件"),
) -> None:
    """打印 OSS 对象内容到 stdout (受 --max-size 限制)."""
    oss_key = _resolve_oss_key(ctx, oss_key)
    bucket = _get_bucket(ctx)
    try:
        meta = bucket.head_object(oss_key)
    except oss2.exceptions.NoSuchKey:
        typer.echo(f"对象不存在: {oss_key}", err=True)
        raise typer.Exit(1)

    if meta.content_length > max_size:
        typer.echo(
            f"对象大小 {_humanize_bytes(meta.content_length)} 超过 --max-size {_humanize_bytes(max_size)}, 拒绝打印",
            err=True,
        )
        raise typer.Exit(1)

    result = bucket.get_object(oss_key)
    sys.stdout.buffer.write(result.read())


# ---------- sign ----------


@cmd.command()
@with_auth
def sign(
    ctx: typer.Context,
    oss_key: str = typer.Argument(..., help="OSS 对象 key"),
    expires: int = typer.Option(3600, "-e", "--expires", help="URL 有效期, 秒"),
    method: str = typer.Option("GET", "-m", "--method", help="HTTP 方法 (GET / PUT)"),
) -> None:
    """生成预签名 URL, 直接打印到 stdout."""
    oss_key = _resolve_oss_key(ctx, oss_key)
    bucket = _get_bucket(ctx)
    method_upper = method.upper()
    if method_upper not in ("GET", "PUT"):
        typer.echo(f"不支持的方法: {method}", err=True)
        raise typer.Exit(1)
    url = bucket.sign_url(method_upper, oss_key, expires, slash_safe=True)
    print(url)


# ---------- sync ----------


def _print_dry_run(plan: SyncPlan) -> None:
    if not plan.items and plan.total_before_cap == 0:
        rich.print("[green]目标与源已一致, 无需同步[/green]")
        return

    direction_label = "本地 → OSS" if plan.direction == "up" else "OSS → 本地"
    rich.print(f"[bold]同步方向:[/bold] {direction_label}")
    rich.print(f"[bold]待处理项:[/bold] {len(plan.items)}" + (f" (超出 max-files, 总 {plan.total_before_cap})" if plan.truncated else ""))

    table = Table(show_header=True, header_style="bold")
    table.add_column("Action")
    table.add_column("Size", justify="right")
    table.add_column("Cumulative", justify="right")
    table.add_column("Reason")
    table.add_column("Path")

    cumulative = 0
    upload_bytes = 0
    download_bytes = 0
    delete_count = 0
    reason_counts: dict[str, int] = {}
    for item in plan.items:
        action_color = {
            "upload": "green",
            "download": "cyan",
            "delete-remote": "red",
            "delete-local": "red",
        }.get(item.action, "white")
        reason_color = {
            "new": "green",
            "size-changed": "yellow",
            "mtime-changed": "yellow",
            "local-newer": "cyan",
            "remote-newer": "cyan",
            "force": "blue",
            "extra-on-remote": "red",
            "extra-on-local": "red",
        }.get(item.reason, "white")
        if item.action == "upload":
            upload_bytes += item.size
            cumulative += item.size
        elif item.action == "download":
            download_bytes += item.size
            cumulative += item.size
        else:
            delete_count += 1
        reason_counts[item.reason] = reason_counts.get(item.reason, 0) + 1
        table.add_row(
            f"[{action_color}]{item.action}[/{action_color}]",
            _humanize_bytes(item.size),
            _humanize_bytes(cumulative),
            f"[{reason_color}]{item.reason}[/{reason_color}]",
            item.rel,
        )
    console.print(table)

    rich.print(f"[bold]合计:[/bold] {len(plan.items)} 项, 总传输 {_humanize_bytes(cumulative)}")
    if upload_bytes:
        rich.print(f"  上传: {_humanize_bytes(upload_bytes)}")
    if download_bytes:
        rich.print(f"  下载: {_humanize_bytes(download_bytes)}")
    if delete_count:
        rich.print(f"  删除: {delete_count} 项")
    if reason_counts:
        rich.print("[bold]按原因:[/bold] " + ", ".join(f"{r}={n}" for r, n in sorted(reason_counts.items())))


def _run_sync_with_progress(bucket: oss2.Bucket, plan: SyncPlan, workers: int) -> None:
    total_bytes = sum(it.size for it in plan.items if it.action in ("upload", "download"))
    total_files = len(plan.items)

    progress = Progress(*_progress_columns(), console=console, transient=False)
    overall = progress.add_task(f"sync ({plan.direction})", total=total_bytes or 1)

    item_tasks: dict[int, TaskID] = {}
    item_consumed: dict[int, int] = {}
    bytes_done_overall = 0
    files_done = 0
    lock = threading.Lock()

    def on_progress(ev: TransferEvent) -> None:
        nonlocal bytes_done_overall, files_done
        item_id = id(ev.item)
        with lock:
            if ev.done:
                if item_id in item_tasks:
                    progress.remove_task(item_tasks.pop(item_id))
                files_done += 1
                if ev.error is None and ev.item.action in ("upload", "download"):
                    delta = ev.item.size - item_consumed.get(item_id, 0)
                    if delta > 0:
                        bytes_done_overall += delta
                        progress.update(overall, completed=bytes_done_overall)
                item_consumed.pop(item_id, None)
                progress.update(overall, description=f"sync ({plan.direction}) {files_done}/{total_files} files")
                return

            if ev.item.action not in ("upload", "download"):
                return

            if item_id not in item_tasks:
                label = f"{ev.item.action} {ev.item.rel}"
                item_tasks[item_id] = progress.add_task(label, total=ev.total or ev.item.size)

            prev = item_consumed.get(item_id, 0)
            delta = ev.consumed - prev
            if delta > 0:
                item_consumed[item_id] = ev.consumed
                bytes_done_overall += delta
                progress.update(item_tasks[item_id], completed=ev.consumed)
                progress.update(overall, completed=bytes_done_overall)

    with progress:
        result = execute_sync(bucket, plan, workers=workers, on_progress=on_progress)

    rich.print(f"[green]✓[/green] 完成 {len(result.succeeded)} 项")
    if result.failed:
        rich.print(f"[red]✗[/red] 失败 {len(result.failed)} 项:")
        for item, err in result.failed[:10]:
            rich.print(f"  [red]{item.action}[/red] {item.rel}: {err}")
        if len(result.failed) > 10:
            rich.print(f"  ... (省略 {len(result.failed) - 10} 项)")
        raise typer.Exit(1)


@cmd.command()
@with_auth
def sync(
    ctx: typer.Context,
    src: str = typer.Argument(..., help="源路径, 本地路径或 oss:<prefix>/ 或 oss://<bucket>/<prefix>/"),
    dst: str = typer.Argument(..., help="目标路径, 本地路径或 oss:<prefix>/ 或 oss://<bucket>/<prefix>/"),
    delete: bool = typer.Option(False, "--delete", help="删除目标端不存在于源端的文件 (镜像同步)"),
    dry_run: bool = typer.Option(False, "--dry-run", help="只显示需要同步的文件列表, 不实际传输"),
    max_files: Optional[int] = typer.Option(None, "--max-files", help="本次最多同步多少个文件, 默认无限"),
    workers: int = typer.Option(4, "--workers", help="并发传输数"),
    force: bool = typer.Option(False, "-f", "--force", help="忽略 size/mtime 比较, 全部覆盖"),
) -> None:
    """目录同步: 本地 ↔ OSS, 默认按 size + x-oss-meta-mtime 比对.

    OSS 端两种写法等价 (URI 内的 bucket 必须与 --bucket / OSS_BUCKET 一致):

      oss:<prefix>/             从 --bucket 读取 bucket
      oss://<bucket>/<prefix>/  s3 风格, bucket 写在 URI 里

    使用示例:
      ai-assistant aliyun-oss sync ./dist/ oss:web/                  # 上传
      ai-assistant aliyun-oss sync ./dist/ oss://mybucket/web/       # 上传, 显式 bucket
      ai-assistant aliyun-oss sync oss:backup/ ./restore/            # 下载
      ai-assistant aliyun-oss sync ./dist/ oss:web/ --dry-run --max-files 50
    """
    src_is_oss, src_uri_bucket, _ = parse_oss_path(src)
    dst_is_oss, dst_uri_bucket, _ = parse_oss_path(dst)
    if src_is_oss == dst_is_oss:
        typer.echo("sync 必须一端是本地路径, 另一端用 oss:<prefix>/ 或 oss://<bucket>/<prefix>/", err=True)
        raise typer.Exit(1)

    # 如果配置里没指定 bucket, 但 URI 里写了, 用 URI 里的作为 fallback.
    uri_bucket = src_uri_bucket or dst_uri_bucket
    if uri_bucket and not ctx.obj["config_kwargs"].get("bucket_name"):
        ctx.obj["config_kwargs"]["bucket_name"] = uri_bucket

    bucket = _get_bucket(ctx)

    try:
        plan = compute_sync_plan(bucket, src, dst, delete=delete, force=force, max_files=max_files)
    except ValueError as exc:
        typer.echo(str(exc), err=True)
        raise typer.Exit(1)

    if dry_run:
        _print_dry_run(plan)
        return

    if not plan.items:
        rich.print("[green]目标与源已一致, 无需同步[/green]")
        return

    if plan.truncated:
        rich.print(f"[yellow]注意:[/yellow] 总待同步 {plan.total_before_cap} 项, 本次执行受 --max-files 限制为 {len(plan.items)} 项")

    _run_sync_with_progress(bucket, plan, workers=workers)


if __name__ == "__main__":
    cmd()
