"""Cold profile snapshots, recoverable replacement, and explicit retention."""

from __future__ import annotations

import os
import shutil
from functools import partial
from pathlib import Path
from typing import Any, Callable

import typer

from .archive import create_backup, inventory, read_header, verify_backup
from .common import (
    COMPRESSION_HELP,
    MAX_BYTES,
    MAX_ENTRIES,
    REGION_HELP,
    CindyError,
    Compression,
    Region,
    confirm,
    emit,
    guarded,
    tty_required,
)
from .paths import (
    Profile,
    app_data,
    check_space,
    discovered_profiles,
    disjoint,
    host_platform,
    identity,
    is_link,
    keychain_identity,
    native_arch,
    profile_for,
    root_path,
)
from .picker import choose_many, choose_one
from .procs import require_stopped, running_state
from .schema import highest_migration, schema_versions
from .state import State, index_update, read_json, sha256
from .transaction import Observer, Transaction, pending_transactions, remove_owned

cmd = typer.Typer(help="Cindy profile 冷备份、校验、全量覆盖恢复及备份清理。", rich_markup_mode=None)


def candidates(directory: Path, region: str | None = None, *, include_partial: bool = False) -> list[dict[str, Any]]:
    result: list[dict[str, Any]] = []
    if not directory.is_dir():
        return result
    for path in directory.glob("cindy-*.tar*"):
        partial = include_partial and path.name.endswith(".partial")
        if is_link(path) or not path.is_file() or (not partial and not path.name.endswith((".tar", ".tar.gz", ".tar.zst"))):
            continue
        try:
            if partial:
                record = read_json(path.with_name(f"{path.name}.json"))
                if record.get("file_id") != identity(path) or record.get("path") != str(path):
                    continue
                from .archive import validate_header

                header = validate_header(record.get("header"))
            else:
                header = read_header(path)
            if region and header["profile"]["region"] != region:
                continue
            disabled = "" if (header["profile"]["platform"], header["profile"]["arch"]) == (host_platform(), native_arch()) else "平台或原生架构不同"
            result.append(
                {
                    "path": str(path),
                    "header": header,
                    "disabled": disabled,
                    "partial": partial,
                    "file_id": identity(path),
                    "display": f"{header['created_at']} {header['profile']['region']} {header['profile']['name']} {path.stat().st_size} B {header.get('compression')} [{header['kind']}] {header['label']} {'[partial]' if partial else ''}",
                }
            )
        except (CindyError, OSError) as exc:
            result.append({"path": str(path), "header": {}, "display": path.name, "disabled": str(exc)})
    return sorted(result, key=lambda item: item["header"].get("created_at", ""), reverse=True)


def validate_layout(profile: Profile, state: State, output: Path | None = None) -> None:
    path = Path(profile.path)
    disjoint(path, state.home)
    disjoint(path, state.runtime)
    if output is not None:
        disjoint(path, output)
        root_path(output)
    for record in state.records("installs").values():
        disjoint(path, Path(record["path"]))


def profile_check(profile: Profile, state: State, check: Callable[[], None]) -> Callable[[], None]:
    if check is require_stopped:
        paths = [Path(profile.path), *(Path(record["path"]) for record in state.records("profiles").values())]
        return partial(require_stopped, paths)
    return check


def backup_profile(profile: Profile, state: State, *, output: Path | None = None, check: Callable[[], None] = require_stopped, **options: Any) -> tuple[Path, dict[str, Any]]:
    validate_layout(profile, state, output)
    check = profile_check(profile, state, check)
    check()
    path, header = create_backup(profile, output or state.backups, check=check, **options)
    check()
    state.register_profile(profile.to_dict())
    return path, header


def resolve_target(header: dict[str, Any], state: State, target: Path | None, allow_relocate: bool) -> Profile:
    original = Profile(**header["profile"])
    if (original.platform, original.arch) != (host_platform(), native_arch()):
        raise CindyError("禁止跨平台或跨原生架构恢复。", 2)
    if bool(target) != allow_relocate:
        raise CindyError("--target 与 --allow-relocate 必须同时指定。", 2)
    path = target or Path(original.path)
    if not target and not path.is_dir() and not path.parent.is_dir():
        raise CindyError("来源路径在本机不可定位，请明确指定 --target 和 --allow-relocate。", 2)
    profile = profile_for(path, original.region)
    if profile.kind != original.kind:
        raise CindyError("禁止在 main、isolated、custom 之间迁移。", 2)
    if not target and original.kind != "custom" and Path(original.app_data).resolve() != app_data().resolve():
        raise CindyError("本机 appData 已变化，迁移须明确指定目标。", 2)
    if keychain_identity(path) != "absent" and keychain_identity(path) != original.keychain_identity:
        raise CindyError("目标钥匙串身份与归档不同，拒绝恢复。", 2)
    if profile.kind == "custom" and path.is_dir() and any(path.iterdir()):
        known = state.records("profiles").get(original.profile_key)
        if str(path.resolve()) != original.path or not known or known["path"] != str(path.resolve()):
            raise CindyError("非空 custom 目标未登记为此来源 Profile。", 2)
    return profile


def compatibility_report(profile: Profile, state: State, schemas: dict[str, int | None]) -> list[dict[str, Any]]:
    from .signing import actual_version

    result = []
    for identifier, record in state.records("installs").items():
        if record["region"] != profile.region:
            continue
        installed = Path(record["path"])
        resources = installed / "Contents/Resources" if record["platform"] == "darwin" else installed / "resources"
        if record["platform"] == "linux":
            resources = installed / "current/resources"
        maximum = highest_migration(resources)
        too_old = maximum is not None and any(value is not None and value > maximum for value in schemas.values())
        result.append(
            {
                "id": identifier,
                "actual_version": actual_version(installed, record["platform"]),
                "max_schema": maximum,
                "screening": "库版本超前，客户端会拒绝打开" if too_old else ("unknown" if maximum is None else "序号初筛未发现超前，非兼容保证"),
            }
        )
    return result


def copy_shared(source: Path, new: Path) -> None:
    for item in list(new.iterdir()):
        if item.name.startswith("shared-"):
            remove_owned(item)
    if source.is_dir():
        for item in source.iterdir():
            if item.name.startswith("shared-"):
                target = new / item.name
                if is_link(item):
                    target.symlink_to(os.readlink(item))
                elif item.is_dir():
                    shutil.copytree(item, target, symlinks=True)
                elif item.is_file():
                    shutil.copy2(item, target)
                else:
                    raise CindyError("shared 中存在特殊文件。", 4)
                verify_copy(item, target)


def verify_copy(source: Path, target: Path) -> None:
    if is_link(source):
        matches = is_link(target) and os.readlink(source) == os.readlink(target)
    elif source.is_file():
        matches = target.is_file() and not is_link(target) and sha256(source) == sha256(target)
    else:
        matches = target.is_dir() and not is_link(target) and {p.name for p in source.iterdir()} == {p.name for p in target.iterdir()}
        if matches:
            for child in source.iterdir():
                verify_copy(child, target / child.name)
    if not matches:
        raise CindyError("shared 副本校验失败，当前目录保持不变。", 4)


def replace_profile(
    profile: Profile,
    state: State,
    *,
    archive: Path | None = None,
    include_shared: bool = False,
    pre_backup: bool = True,
    check: Callable[[], None] = require_stopped,
    observer: Observer | None = None,
    max_bytes: int = MAX_BYTES,
    max_entries: int = MAX_ENTRIES,
) -> str:
    validate_layout(profile, state)
    check = profile_check(profile, state, check)
    target = Path(profile.path)
    check()
    if archive:
        disjoint(target, archive)
        archived_profile = read_header(archive)["profile"]
        if (archived_profile["region"], archived_profile["kind"], archived_profile["platform"], archived_profile["arch"]) != (profile.region, profile.kind, profile.platform, profile.arch):
            raise CindyError("归档与目标 Profile 身份不兼容。", 2)
    if include_shared and not (profile.region == "cn" and profile.kind == "main" and archive):
        raise CindyError("--include-shared 仅适用于 cn 主目录备份恢复到 cn 主目录。", 2)
    if archive is None and not target.is_dir():
        raise CindyError("待清空的 Profile 不存在。")
    before = inventory(target, include_updates=True) if target.is_dir() else None
    size = sum(row[3] for row in (before or {}).values())
    amount = size + (read_header(archive)["bytes"] if archive else 0)
    check_space(target.parent, amount)
    tx = Transaction(state, target, operation="restore" if archive else "reset", observer=observer, metadata={"profile": profile.to_dict()})
    try:
        if pre_backup and target.is_dir():
            path, _ = backup_profile(profile, state, kind="pre-restore" if archive else "pre-reset", transaction_id=tx.id, check=check, max_bytes=max_bytes, max_entries=max_entries)
            tx.data["metadata"]["pre_backup"] = str(path)
            tx.save("preparing")
        if archive:
            verify_backup(archive, destination=tx.new, max_bytes=max_bytes, max_entries=max_entries)
            if keychain_identity(tx.new) != archived_profile["keychain_identity"]:
                raise CindyError("归档标记内容与 Profile 身份声明不同。", 4)
        if profile.region == "cn" and profile.kind == "main" and not include_shared:
            copy_shared(target, tx.new)
        if before is not None and inventory(target, include_updates=True) != before:
            raise CindyError("准备期间当前 Profile 发生变化。", 6)
        tx.activate(check)
    except BaseException as exc:
        recovered = False
        try:
            check()
            tx.recover()
            recovered = True
        except BaseException:
            pass
        if not isinstance(exc, (KeyboardInterrupt, SystemExit)):
            if not recovered:
                raise CindyError(f"事务未收尾，数据现场已保留；请执行 cindy recover：{tx.id}", 6) from exc
            if tx.data["new_id"] is not None and identity(target) == tx.data["new_id"]:
                raise CindyError(f"目录已提交并收尾，但执行期间发生错误，请检查结果：{target}", 6) from exc
        raise
    return "Profile 已恢复。" if archive else "Profile 数据已清空；共享目录及外部数据未清空。"


@cmd.command("backup")
@guarded
def backup(
    region: Region | None = typer.Option(None, help=f"{REGION_HELP} 不提供 path 时必填，有 path 时可推断。"),
    path: Path | None = typer.Option(None, help="明确选择的 Profile 目录，不能为链接。"),
    output_dir: Path | None = typer.Option(None, help="私有备份目录；默认状态目录下 backups，不能位于源内或 Git 工作区。"),
    label: str = typer.Option("", help="备份标签，最多 80 字且不能含控制字符。"),
    compress: Compression = typer.Option(Compression.auto, help=COMPRESSION_HELP),
    exclude_caches: bool = typer.Option(False, help="排除已知顶层浏览器缓存，不排除任意同名子目录。"),
    include_update_cache: bool = typer.Option(False, help="包含已下载更新；恢复后可能立即触发升级。"),
    max_bytes: int = typer.Option(MAX_BYTES, min=1, help="未压缩数据上限（字节），默认 100 GiB。"),
    max_entries: int = typer.Option(MAX_ENTRIES, min=1, help="成员数上限，默认 200000。"),
) -> None:
    """在所有 Cindy 退出后创建并完整校验私有备份。"""
    state = State()
    profile = profile_for(path, region.value if region else None)
    with state.lock():
        destination, header = backup_profile(
            profile,
            state,
            output=output_dir,
            label=label,
            compression=compress.value,
            exclude_caches=exclude_caches,
            include_updates=include_update_cache,
            max_bytes=max_bytes,
            max_entries=max_entries,
        )
    emit({"path": destination, "entries": header["entries"], "bytes": header["bytes"]})


@cmd.command("verify")
@guarded
def verify(
    archive: Path = typer.Argument(..., help="需要完整验证的归档文件；不依赖索引也能校验正文。"),
    max_bytes: int = typer.Option(MAX_BYTES, min=1, help="未压缩数据上限（字节）。"),
    max_entries: int = typer.Option(MAX_ENTRIES, min=1, help="归档成员上限。"),
) -> None:
    """完整读取并校验内容摘要、结构、计数及压缩校验和。"""
    with State().lock(recover=True):
        emit(verify_backup(archive, max_bytes=max_bytes, max_entries=max_entries))


@cmd.command("restore")
@guarded
def restore(
    archive: Path | None = typer.Argument(None, help="可信归档；不提供时必须通过 TTY 选择。"),
    backup_dir: Path | None = typer.Option(None, help="候选备份目录，不是恢复目标。"),
    region: Region | None = typer.Option(None, help=f"{REGION_HELP} 未提供时不过滤；显式归档时作为区域断言。"),
    target: Path | None = typer.Option(None, help="显式迁移目标，必须同时传 allow-relocate；不能跨 Profile 类型。"),
    allow_relocate: bool = typer.Option(False, help="允许明确迁移；不改写链接、数据库路径或钥匙串标记。"),
    include_shared: bool = typer.Option(False, help="仅 cn 主目录：使用归档内 shared，可能影响其他区域。"),
    no_pre_backup: bool = typer.Option(False, help="跳过当前数据的自动备份，不跳过完整校验与事务。"),
    yes: bool = typer.Option(False, "--yes", help="显式归档时跳过确认；交互选择模式忽略。"),
    max_bytes: int = typer.Option(MAX_BYTES, min=1, help="未压缩数据上限（字节）。"),
    max_entries: int = typer.Option(MAX_ENTRIES, min=1, help="归档成员上限。"),
) -> None:
    """全量覆盖一个同区域、同平台、同原生架构的 Profile。"""
    state = State()
    if archive is None:
        tty_required()
        status, _ = running_state(discovered_profiles())
        typer.echo(f"Cindy 运行状态：{status}")
        chosen = choose_one(candidates(backup_dir or state.backups, region.value if region else None))
        if chosen is None:
            typer.echo("已取消，未做任何更改。")
            return
        archive = Path(chosen["path"])
        if yes:
            typer.echo("选择模式忽略 --yes。")
        yes = False
    header = read_header(archive)
    if region and header["profile"]["region"] != region.value:
        raise CindyError("归档区域与 --region 不一致。", 2)
    profile = resolve_target(header, state, target, allow_relocate)
    emit({"客户端兼容初筛": compatibility_report(profile, state, header.get("schema", {})), "排除缓存": header.get("exclude_caches"), "包含更新包": header.get("include_update_cache")})
    if not confirm(
        f"覆盖 {profile.path}\n来源：{header['profile']['path']}\n自动备份：{not no_pre_backup}；归档 shared：{include_shared}；schema={header.get('schema')}（仅初筛）。绝对路径不重写，登录态可能失效。",
        yes,
    ):
        return
    with state.lock():
        profile = resolve_target(header, state, target, allow_relocate)
        typer.echo(replace_profile(profile, state, archive=archive, include_shared=include_shared, pre_backup=not no_pre_backup, max_bytes=max_bytes, max_entries=max_entries))


@cmd.command("reset")
@guarded
def reset(
    region: Region | None = typer.Option(None, help=f"{REGION_HELP} 无 path 时必填，有 path 时可推断。"),
    path: Path | None = typer.Option(None, help="明确选择的 Profile 目录。"),
    no_backup: bool = typer.Option(False, help="不自动备份，丢失数据后不能撤销。"),
    yes: bool = typer.Option(False, "--yes", help="跳过清空确认，不跳过停止检查。"),
) -> None:
    """先完整备份，再以可恢复事务清空 Profile；cn shared 默认保留。"""
    state = State()
    profile = profile_for(path, region.value if region else None)
    if not confirm(f"清空 {profile.path}；自动备份：{not no_backup}。共享与外部数据保留。", yes):
        return
    with state.lock():
        typer.echo(replace_profile(profile, state, pre_backup=not no_backup))


@cmd.command("list")
@guarded
def list_data(as_json: bool = typer.Option(False, "--json", help="输出单个版本化 JSON 对象。")) -> None:
    """只读列出 Profile、默认备份与待恢复事务。"""
    state = State()
    paths = {str(path) for path in discovered_profiles()}
    paths.update(record["path"] for record in state.records("profiles").values())
    profiles = []
    for raw in sorted(paths):
        path = Path(raw)
        status, reasons = running_state([path])
        profiles.append(
            {
                "path": raw,
                "exists": path.is_dir(),
                "running": status,
                "reasons": reasons,
                "empty_profile": path.is_dir() and not any(not item.name.startswith("shared-") for item in path.iterdir()),
                "schema": schema_versions(path) if status == "stopped" and path.is_dir() and not is_link(path) else "unknown",
            }
        )
    emit({"profiles": profiles, "backups": candidates(state.backups), "journals": [str(path) for path in state.journals.glob("*.json")], "active": state.active()}, as_json)


def delete_backups(items: list[dict[str, Any]], directory: Path) -> None:
    failures = []
    for item in items:
        path = Path(item["path"])
        try:
            if path.parent.resolve() != directory.resolve() or is_link(path) or not path.is_file() or identity(path) != item["file_id"]:
                raise CindyError("备份已变化或路径不安全。", 6)
            if item.get("partial"):
                sidecar = path.with_name(f"{path.name}.json")
                saved = read_json(sidecar)
                if saved.get("file_id") != identity(path) or saved.get("header") != item["header"]:
                    raise CindyError("partial 归属记录已变化。", 6)
                path.unlink()
                sidecar.unlink()
            else:
                if read_header(path) != item["header"]:
                    raise CindyError("备份已变化。", 6)
                path.unlink()
                index_update(directory, path, None)
        except (OSError, CindyError) as exc:
            failures.append(f"{path.name}: {exc}")
    if failures:
        raise CindyError(f"部分删除失败：{'；'.join(failures)}")


@cmd.command("prune")
@guarded
def prune(
    backup_dir: Path | None = typer.Option(None, help="清理范围，仅第一层备份。"),
    region: Region | None = typer.Option(None, help=f"{REGION_HELP} 默认全部区域，按 profile 分组。"),
    keep: int = typer.Option(5, min=1, help="每个 Profile 至少保留的最新备份数。"),
    yes: bool = typer.Option(False, "--yes", help="跳过确认；仍保护最近自动备份。"),
) -> None:
    """按 Profile 保留最新 N 份与最近撤销点，保留项损坏时拒绝删除。"""
    state = State()
    directory = root_path(backup_dir or state.backups)
    with state.lock():
        groups: dict[str, list[dict[str, Any]]] = {}
        for item in candidates(directory, region.value if region else None):
            if item["header"]:
                groups.setdefault(item["header"]["profile"]["profile_key"], []).append(item)
        protected = set(state.records("undo").values())
        doomed: list[dict[str, Any]] = []
        for group in groups.values():
            retained = [item for index, item in enumerate(group) if index < keep or item["path"] in protected]
            for item in retained:
                verify_backup(Path(item["path"]))
            doomed.extend(item for item in group if item not in retained)
        if doomed and confirm(f"删除 {len(doomed)} 份旧备份：\n" + "\n".join(item["display"] for item in doomed), yes):
            delete_backups(doomed, directory)
        elif not doomed:
            typer.echo("没有需要清理的备份。")


@cmd.command("clear")
@guarded
def clear(
    backup_dir: Path | None = typer.Option(None, help="备份目录，只处理第一层普通文件。"),
    region: Region | None = typer.Option(None, help=f"{REGION_HELP} 默认全部区域。"),
    only_auto: bool = typer.Option(False, help="只删除 kind 为 pre-restore/pre-reset 的备份。"),
    keep_auto: bool = typer.Option(False, help="保留自动备份，与 only-auto 互斥。"),
    select: bool = typer.Option(False, help="逐项选择，而非选择范围内全部备份。"),
) -> None:
    """交互清空备份；必须输入 delete 加份数，不能用 --yes。"""
    tty_required()
    if only_auto and keep_auto:
        raise CindyError("only-auto 和 keep-auto 互斥。", 2)
    state = State()
    directory = root_path(backup_dir or state.backups)
    with state.lock():
        items = [item for item in candidates(directory, region.value if region else None, include_partial=True) if item["header"]]
        items = [item for item in items if not (only_auto and item["header"]["kind"] == "manual") and not (keep_auto and item["header"]["kind"] != "manual")]
        for item in items:
            item["disabled"] = ""
        chosen = choose_many(items) if select and items else items
        if not chosen:
            typer.echo("已取消或没有可清理的备份。")
            return
        typer.echo("\n".join(item["display"] for item in chosen))
        protected = set(state.records("undo").values())
        for item in chosen:
            profile_key = item["header"]["profile"]["profile_key"]
            if item["path"] in protected:
                typer.echo(f"警告：将删除最近一次操作的自动撤销备份：{item['path']}")
            if not any(other["header"]["profile"]["profile_key"] == profile_key and other not in chosen and not other.get("partial") for other in items):
                typer.echo(f"警告：该 Profile 在当前备份目录将没有完整备份：{item['header']['profile']['path']}")
        typer.echo(f"合计 {len(chosen)} 份，{sum(Path(item['path']).stat().st_size for item in chosen)} 字节。警告：可能删除某 Profile 的最后备份或最近自动撤销点，删除后无法撤销。")
        try:
            answer = typer.prompt(f"输入 delete {len(chosen)} 确认", default="", show_default=False)
        except (KeyboardInterrupt, typer.Abort):
            answer = ""
        if answer != f"delete {len(chosen)}":
            typer.echo("已取消，未做任何更改。")
            return
        delete_backups(chosen, directory)
        typer.echo(f"已删除 {len(chosen)} 份备份；无法确认归属的 partial 保留，不自动删除。")


def recover_transactions(yes: bool, *, data_only: bool) -> None:
    state = State()
    with state.lock(recover=True):
        transactions = pending_transactions(state)
        if data_only:
            transactions = [tx for tx in transactions if tx.data["operation"] in {"restore", "reset"}]
        if not transactions:
            typer.echo("没有待恢复事务。")
            return
        if not confirm("检查并恢复以下事务：\n" + "\n".join(f"{tx.id} {tx.data['phase']} {tx.target}" for tx in transactions), yes):
            return
        require_stopped()
        for tx in transactions:
            typer.echo(f"{tx.id}: {tx.recover()}")


@cmd.command("recover")
@guarded
def recover(yes: bool = typer.Option(False, "--yes", help="跳过数据事务收尾确认；遇到冲突仍拒绝。")) -> None:
    """收尾中断的恢复或清空；安装事务请使用 cindy recover。"""
    recover_transactions(yes, data_only=True)


@guarded
def recover_all(yes: bool = typer.Option(False, "--yes", help="跳过全部事务收尾确认；遇到冲突仍拒绝。")) -> None:
    """按文件身份收尾数据、安装和卸载事务，不覆盖外来目标。"""
    recover_transactions(yes, data_only=False)
