"""Artifact download and gated platform adapters; never launches Cindy."""

from __future__ import annotations

import os
import plistlib
import shutil
import stat
import subprocess
import uuid
import zipfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable
from urllib.parse import urlsplit

import typer

from .archive import claim_path, safe_member
from .common import (
    ARCH_HELP,
    CHANNEL_HELP,
    MODE_HELP,
    PLATFORM_HELP,
    RELEASE_REGION_HELP,
    SOURCE_HELP,
    Channel,
    CindyError,
    Mode,
    ReleaseRegion,
    Source,
    confirm,
    emit,
    guarded,
)
from .download import download_file
from .paths import (
    app_data,
    check_space,
    disjoint,
    exists,
    host_platform,
    identity,
    is_link,
    native_arch,
    normalize_arch,
    normalize_platform,
    private_dir,
    root_path,
    safe_id,
)
from .procs import require_stopped
from .releases import Artifact, Releases
from .schema import highest_migration, schema_versions
from .signing import actual_version, verify_mac
from .state import State
from .state import sha256 as file_sha256
from .transaction import Transaction


def extract_portable(archive: Path, target: Path) -> None:
    """Exercise the portable archive boundary without executing any PE file."""
    private_dir(target)
    with zipfile.ZipFile(archive) as source:
        infos = source.infolist()
        if len(infos) > 100_000 or sum(info.file_size for info in infos) > 8 * 1024**3:
            raise CindyError("ZIP 超过解包限制。", 4)
        seen = set()
        spellings: dict[str, str] = {}
        paths: dict[str, bool] = {}
        for item in infos:
            name = item.filename.replace("\\", "/").rstrip("/")
            canonical = claim_path(name, spellings)
            kind = (item.external_attr >> 16) & 0o170000
            if canonical in seen or kind not in {0, stat.S_IFREG, stat.S_IFDIR} or item.flag_bits & 1:
                raise CindyError("ZIP 有重复路径、链接、特殊文件或加密项。", 4)
            seen.add(canonical)
            paths[name] = item.is_dir()
        for name in paths:
            if any(paths.get(parent.as_posix()) is False for parent in Path(name).parents if parent.as_posix() != "."):
                raise CindyError("ZIP 成员祖先不是目录。", 4)
        for item in infos:
            path = target / item.filename.replace("\\", "/").rstrip("/")
            path.parent.mkdir(parents=True, mode=0o700, exist_ok=True)
            if item.is_dir():
                path.mkdir(mode=0o700, exist_ok=True)
            else:
                with source.open(item) as content, path.open("xb") as output:
                    shutil.copyfileobj(content, output, length=1024**2)
                path.chmod(0o600)


def default_destination(artifact: Artifact, identifier: str) -> Path:
    home = Path.home()
    if artifact.platform == "darwin":
        return home / "Applications/Cindy Versions" / identifier / "Cindy.app"
    if artifact.platform == "win32":
        return Path(os.environ.get("LOCALAPPDATA", str(home / "AppData/Local"))) / "Programs/Cindy Versions" / identifier
    return home / ".local/opt/cindy-versions" / identifier


def install_layout(target: Path, state: State) -> None:
    disjoint(target, state.home)
    disjoint(target, state.runtime)
    for name in ("Cindy", "CindyGlobal", "CindyDev"):
        disjoint(target, app_data() / name)
    for record in state.records("profiles").values():
        disjoint(target, Path(record["path"]))


def install_mac(artifact: Artifact, package: Path, target: Path, identifier: str, state: State, *, replace: bool = False, check: Callable[[], None] = require_stopped) -> dict[str, Any]:
    install_layout(target, state)
    check()
    if target.suffix != ".app":
        raise CindyError("macOS --dest 必须指向完整 .app 路径。", 2)
    records = state.records("installs")
    if identifier in records and records[identifier]["path"] != str(target):
        raise CindyError("同一安装 ID 已登记到另一路径。", 2)
    if any(record["path"] == str(target) and key != identifier for key, record in records.items()):
        raise CindyError("目标已被另一安装 ID 登记。", 2)
    if exists(target):
        if not replace:
            record = records.get(identifier)
            if record and record.get("sha256") == artifact.sha256 and identity(target) == record.get("directory_id"):
                verify_mac(target, artifact.region, artifact.version, artifact.arch)
                return dict(record)
            raise CindyError("目标已存在，需要 --replace。", 2)
        verify_mac(target, artifact.region)
    target.parent.mkdir(parents=True, mode=0o700, exist_ok=True)
    check_space(target.parent, max(package.stat().st_size * 4, 1024**3))
    record = {
        "id": identifier,
        "install_uuid": uuid.uuid4().hex,
        "region": artifact.region,
        "platform": artifact.platform,
        "arch": artifact.arch,
        "mode": artifact.mode,
        "path": str(target),
        "version": artifact.version,
        "selector": artifact.selector,
        "channel": artifact.channel,
        "sha256": artifact.sha256,
        "verification": "sha256+signature" if artifact.sha256 else "signature-only",
        "source_url": artifact.url,
        "digest_source": artifact.digest_source,
        "installed_at": datetime.now(timezone.utc).isoformat(),
    }
    tx = Transaction(state, target, operation="install", metadata={"install": record})
    mount = tx.wrapper / "mount"
    private_dir(mount)
    tx.data["mountpoint"] = str(mount)
    tx.save("preparing")
    attached = False
    try:
        snapshot = tx.wrapper / "source.dmg"
        if is_link(package) or not package.is_file():
            raise CindyError("安装包不是普通文件。", 4)
        shutil.copyfile(package, snapshot)
        snapshot.chmod(0o600)
        if artifact.sha256 and file_sha256(snapshot) != artifact.sha256:
            raise CindyError("安装前私有快照摘要不匹配。", 4)
        result = subprocess.run(
            ["/usr/bin/hdiutil", "attach", "-readonly", "-nobrowse", "-noautoopen", "-plist", "-mountpoint", str(mount), str(snapshot)], capture_output=True, timeout=120, check=False
        )
        if result.returncode:
            raise CindyError("DMG 只读挂载失败。", 4)
        attached = True
        information = plistlib.loads(result.stdout)
        entities = information.get("system-entities", [])
        device = next((entity.get("dev-entry") for entity in entities if entity.get("mount-point") == str(mount)), None)
        if not device:
            raise CindyError("无法取得本次挂载设备标识。", 6)
        tx.data["mount_device"] = device
        tx.save("preparing")
        apps = [path for path in mount.glob("*.app") if path.is_dir() and not is_link(path)]
        if len(apps) != 1:
            raise CindyError("DMG 根目录必须只有一个非链接 app。", 4)
        info = verify_mac(apps[0], artifact.region, artifact.version, artifact.arch)
        copied = subprocess.run(["/usr/bin/ditto", str(apps[0]), str(tx.new)], capture_output=True, timeout=600, check=False)
        if copied.returncode:
            raise CindyError("复制 app 失败，旧安装保持不变。")
        verify_mac(tx.new, artifact.region, artifact.version, artifact.arch)
        record["exe"] = str(target / "Contents/MacOS" / info["exe"])
        tx.data["metadata"]["install"] = record
        # Detach before activation/cleanup: never recurse into a mounted image.
        detached = subprocess.run(["/usr/bin/hdiutil", "detach", device], capture_output=True, timeout=120, check=False)
        if detached.returncode:
            raise CindyError("DMG 卸载失败，保留事务供 recover 处理。", 6)
        attached = False
        tx.activate(check)
        return record
    except BaseException:
        if attached:
            detached = subprocess.run(["/usr/bin/hdiutil", "detach", str(mount)], capture_output=True, timeout=120, check=False)
            attached = detached.returncode != 0
        if not attached:
            try:
                check()
                tx.recover()
            except BaseException:
                pass
        raise


@guarded
def install(
    region: ReleaseRegion = typer.Option(..., help=f"{RELEASE_REGION_HELP} 必须显式指定。"),
    channel: Channel | None = typer.Option(None, help=CHANNEL_HELP),
    version: str = typer.Option("latest", help="版本：latest（默认）、X.Y.Z、vX.Y.Z、X.Y.Z-beta；显式版本不能与 channel 合用。"),
    platform: str | None = typer.Option(None, help=PLATFORM_HELP),
    arch: str | None = typer.Option(None, help=ARCH_HELP),
    dest: Path | None = typer.Option(None, help="安装目标：macOS 为完整 .app 路径，其他平台为独立目录；不改变 userData。"),
    identifier: str | None = typer.Option(None, "--id", help="安装 ID，默认区域-版本-平台-架构-模式。"),
    mode: Mode = typer.Option(Mode.auto, help=MODE_HELP),
    source: Source = typer.Option(Source.cdn, help=SOURCE_HELP),
    sha256: str | None = typer.Option(None, help="用户提供的可信整包 SHA-256；不能用 Setup.exe 摘要验证 ZIP。"),
    require_sha256: bool = typer.Option(False, help="强制可信摘要，与 allow-signature-only 互斥。"),
    allow_signature_only: bool = typer.Option(False, help="仅本机 macOS dmg：无摘要时显式允许完整签名校验，不放行摘要不符。"),
    download_only: bool = typer.Option(False, help="只下载并验证摘要，可指定其他平台；不执行或安装。"),
    output_dir: Path | None = typer.Option(None, help="download-only 的输出目录，默认私有下载缓存。"),
    register_desktop: bool = typer.Option(False, help="Linux 桌面/协议注册；未通过实机门禁，当前拒绝执行。"),
    replace: bool = typer.Option(False, help="允许替换同区域、已核验归属的程序，不修改用户数据。"),
    yes: bool = typer.Option(False, "--yes", help="跳过确认，不跳过身份、停止或平台门禁。"),
) -> None:
    """解析并校验指定地区客户端；支持 --dest 独立目录安装，不自动启动。"""
    chosen_platform = normalize_platform(platform) if platform else host_platform()
    chosen_arch = normalize_arch(arch) if arch else native_arch()
    if allow_signature_only and (require_sha256 or download_only or chosen_platform != "darwin"):
        raise CindyError("signature-only 仅用于本机 macOS 安装，不能与 require-sha256/download-only 合用。", 2)
    if download_only and any((dest, identifier, replace, register_desktop)):
        raise CindyError("download-only 不能与 dest/id/replace/register-desktop 合用。", 2)
    if output_dir and not download_only:
        raise CindyError("output-dir 只适用于 download-only。", 2)
    if not download_only and (chosen_platform, chosen_arch) != (host_platform(), native_arch()):
        raise CindyError("跨平台或架构只允许 download-only。", 2)
    if register_desktop and chosen_platform != "linux":
        raise CindyError("register-desktop 只适用于 Linux。", 2)
    if not download_only and chosen_platform != "darwin":
        raise CindyError("Windows/Linux 安装、卸载与桌面集成尚未通过隔离实机门禁；仅开放 releases 和 download-only，不执行安装器。", 5)
    state = State()
    with state.lock():
        resolver = Releases(state)
        for origin in resolver.custom_sources:
            typer.echo(f"警告：使用自定义来源 {origin}；仍要求可信产物校验。", err=True)
        artifact = resolver.resolve(
            region.value,
            chosen_platform,
            chosen_arch,
            version=version,
            channel=channel.value if channel else None,
            mode=mode.value,
            source=source.value,
            manual_sha256=sha256,
            signature_only=allow_signature_only,
        )
        identifier = safe_id(identifier or f"{artifact.region}-{artifact.version}-{artifact.platform}-{artifact.arch}-{artifact.mode}")
        target = root_path(dest or default_destination(artifact, identifier))
        if not download_only:
            install_layout(target, state)
            if not confirm(
                f"安装 {artifact.region} {artifact.version} 至 {target}；模式 {artifact.mode}，校验来源 {artifact.digest_source}。两区共用协议和部分共享数据，分目录不保证运行时完全隔离；启动后可能自动升级。",
                yes,
            ):
                return
            require_stopped()
        directory = root_path(output_dir) if output_dir else state.home / "downloads" / artifact.region / f"{artifact.platform}-{artifact.arch}" / artifact.kind / (artifact.sha256 or uuid.uuid4().hex)
        filename = Path(urlsplit(artifact.url).path).name
        if not filename:
            raise CindyError("下载 URL 缺少文件名。", 4)
        safe_member(filename)
        package = download_file(artifact.url, directory / filename, artifact.sha256, size=artifact.size, origins=resolver.origins)
        if download_only:
            emit({"path": package, "artifact": artifact.to_dict(), "signature": "not-checked"})
            return
        record = install_mac(artifact, package, target, identifier, state, replace=replace)
        emit(record)
        maximum = highest_migration(target / "Contents/Resources")
        schemas = schema_versions(app_data() / ("Cindy" if region.value == "cn" else "CindyGlobal"))
        typer.echo(f"schema 序号初筛：数据库 {schemas}，客户端最大迁移 {maximum}；非兼容保证。")
        if maximum is not None and any(value is not None and value > maximum for value in schemas.values()):
            typer.echo("现有库较新，此客户端会拒绝打开；请先备份再 reset。", err=True)


@guarded
def releases(
    region: ReleaseRegion | None = typer.Option(None, help=f"{RELEASE_REGION_HELP} 默认查询两区。"),
    platform: str | None = typer.Option(None, help=PLATFORM_HELP),
    arch: str | None = typer.Option(None, help=ARCH_HELP),
    limit: int = typer.Option(20, min=1, max=1000, help="历史版本条目上限。"),
    as_json: bool = typer.Option(False, "--json", help="输出单个版本化 JSON 对象。"),
) -> None:
    """查询两区各渠道当前版本及 GitHub 历史产物，不执行安装。"""
    state = State()
    with state.lock(recover=True):
        resolver = Releases(state)
        for origin in resolver.custom_sources:
            typer.echo(f"警告：使用自定义来源 {origin}。", err=True)
        result = resolver.listing([region.value] if region else ["cn", "global"], normalize_platform(platform) if platform else host_platform(), normalize_arch(arch) if arch else native_arch(), limit)
    emit(result, as_json)


@guarded
def installs(as_json: bool = typer.Option(False, "--json", help="输出单个版本化 JSON 对象。")) -> None:
    """只读列出安装登记与磁盘实际版本，不运行客户端。"""
    state = State()
    result = []
    for record in state.records("installs").values():
        path = Path(record["path"])
        actual = actual_version(path, record["platform"])
        result.append({**record, "actual_version": actual, "status": "missing" if not path.exists() else ("unknown" if actual is None else ("drift" if actual != record["version"] else "installed"))})
    emit({"installs": result, "active": state.active()}, as_json)


@guarded
def uninstall(
    identifier: str = typer.Argument(..., help="已登记安装 ID；不接受任意目录作为删除授权。"),
    yes: bool = typer.Option(False, "--yes", help="跳过卸载确认，不删除 userData。"),
) -> None:
    """卸载已登记程序；所有模式均保留用户数据与外部文件。"""
    state = State()
    with state.lock():
        record = state.records("installs").get(safe_id(identifier))
        if not record:
            raise CindyError("没有对应安装登记。", 5)
        if record["platform"] != "darwin" or host_platform() != "darwin":
            raise CindyError("该平台卸载尚未通过实机门禁，拒绝自动执行。", 5)
        path = root_path(Path(record["path"]))
        install_layout(path, state)
        if identity(path) != record.get("directory_id"):
            raise CindyError("安装目录身份已变化，拒绝依据陈旧登记删除。", 6)
        verify_mac(path, record["region"])
        if not confirm(f"卸载程序 {path}；不删除 userData 或共享数据。", yes):
            return
        require_stopped()
        tx = Transaction(state, path, operation="uninstall", metadata={"uninstall": identifier})
        tx.activate_delete(require_stopped)
        typer.echo("程序已卸载，用户数据未修改。")
