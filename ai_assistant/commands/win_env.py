"""Manage Windows environment variables via direct registry access."""

from __future__ import annotations

import json
import os
import sys
from datetime import datetime
from enum import Enum
from pathlib import Path

import typer

from ai_assistant.commands import make_typer

helptext = """
查看/添加/修改 Windows 环境变量, 直接读写注册表 (HKCU / HKLM)。

子命令:
  list       列出环境变量
  get        查看单个变量
  set        新增或修改变量 (添加 + 修改合并)
  unset      删除变量
  path       专用 PATH 操作 (add / remove / show), 内置去重和 REG_EXPAND_SZ 处理

写入流程:
  1. 写注册表 (HKCU\\Environment 或 HKLM\\...\\Session Manager\\Environment)
  2. 同步更新当前 Python 进程的 os.environ
  3. 广播 WM_SETTINGCHANGE, 通知 Explorer 派生的新进程刷新

已知限制:
  - 已运行的 cmd / PowerShell / IDE 不会自动刷新, 需重新打开
  - --scope system 需要管理员权限
  - 仅支持 Windows
"""

cmd = make_typer(helptext)
path_app = typer.Typer(help="PATH 专用操作 (add / remove / show)")
cmd.add_typer(path_app, name="path")


# ---------------------------------------------------------------------------
# Enums
# ---------------------------------------------------------------------------
class Scope(str, Enum):
    user = "user"
    system = "system"
    process = "process"
    all_ = "all"


class WriteScope(str, Enum):
    user = "user"
    system = "system"


class PathScope(str, Enum):
    user = "user"
    system = "system"
    effective = "effective"


class RegTypeOpt(str, Enum):
    sz = "sz"
    expand = "expand"


# Windows registry value type constants. Hardcoded so this module imports on
# non-Windows hosts without pulling in winreg.
REG_SZ = 1
REG_EXPAND_SZ = 2

_USER_SUBKEY = r"Environment"
_SYSTEM_SUBKEY = r"SYSTEM\CurrentControlSet\Control\Session Manager\Environment"

# PATH-style names that should default to REG_EXPAND_SZ when newly created.
_EXPAND_BY_DEFAULT = {"PATH", "PATHEXT", "PSMODULEPATH", "TEMP", "TMP"}


# ---------------------------------------------------------------------------
# Platform guard
# ---------------------------------------------------------------------------
def _ensure_windows() -> None:
    if sys.platform != "win32":
        typer.echo("win-env 仅支持 Windows", err=True)
        raise typer.Exit(1)


# ---------------------------------------------------------------------------
# Backup
# ---------------------------------------------------------------------------
def default_backup_dir() -> Path:
    if sys.platform == "win32":
        base = os.environ.get("LOCALAPPDATA") or str(Path.home() / "AppData" / "Local")
        return Path(base) / "ai-assistant" / "win-env-backup"
    return Path.home() / ".ai-assistant" / "win-env-backup"


def write_path_backup(scope: WriteScope, value: str, backup_dir: Path) -> Path:
    backup_dir.mkdir(parents=True, exist_ok=True)
    ts = datetime.now().strftime("%Y%m%d-%H%M%S")
    out = backup_dir / f"PATH-{scope.value}-{ts}.txt"
    out.write_text(value, encoding="utf-8")
    return out


# ---------------------------------------------------------------------------
# Pure helpers (cross-platform testable)
# ---------------------------------------------------------------------------
def split_path(value: str) -> list[str]:
    """Split a Windows PATH-style string. Always uses ';' (PATH is Windows-only)."""
    return [p for p in value.split(";") if p]


def join_path(entries: list[str]) -> str:
    return ";".join(entries)


def _path_key(entry: str) -> str:
    """Windows-style normalization that works on any host: case-insensitive,
    forward and back slashes equivalent, trailing separator ignored.

    Deliberately NOT using os.path.normcase/normpath because those are no-ops
    on POSIX, which would make pure helpers behave differently per host.
    """
    return entry.replace("/", "\\").rstrip("\\").lower()


def dedup_path(entries: list[str]) -> list[str]:
    """Stable dedup by normcase + normpath."""
    seen: set[str] = set()
    out: list[str] = []
    for e in entries:
        key = _path_key(e)
        if key not in seen:
            seen.add(key)
            out.append(e)
    return out


def path_contains(entries: list[str], target: str) -> bool:
    key = _path_key(target)
    return any(_path_key(e) == key for e in entries)


def path_remove(entries: list[str], target: str) -> list[str]:
    key = _path_key(target)
    return [e for e in entries if _path_key(e) != key]


def render_path_diff(old_entries: list[str], new_entries: list[str]) -> str:
    old_keys = {_path_key(e): e for e in old_entries}
    new_keys = {_path_key(e): e for e in new_entries}
    added = [new_keys[k] for k in new_keys if k not in old_keys]
    removed = [old_keys[k] for k in old_keys if k not in new_keys]
    if not added and not removed:
        return "(no change)"
    lines: list[str] = []
    for e in added:
        lines.append(f"+ {e}")
    for e in removed:
        lines.append(f"- {e}")
    return "\n".join(lines)


def reg_type_label(reg_type: int) -> str:
    return {REG_SZ: "REG_SZ", REG_EXPAND_SZ: "REG_EXPAND_SZ"}.get(reg_type, f"REG_TYPE({reg_type})")


def resolve_reg_type(name: str, requested: RegTypeOpt | None, existing: int | None) -> int:
    """Pick the registry value type for a write.

    Precedence: explicit --type > existing type (preserve on update) >
    default-expand list (PATH/PATHEXT/...) > REG_SZ.
    """
    if requested is RegTypeOpt.sz:
        return REG_SZ
    if requested is RegTypeOpt.expand:
        return REG_EXPAND_SZ
    if existing is not None:
        return existing
    if name.upper() in _EXPAND_BY_DEFAULT:
        return REG_EXPAND_SZ
    return REG_SZ


# ---------------------------------------------------------------------------
# Registry primitives (Windows only; winreg/ctypes imported inside functions)
# ---------------------------------------------------------------------------
def _scope_root_subkey(scope: WriteScope | Scope | str) -> tuple[int, str]:
    if sys.platform != "win32":
        raise RuntimeError("winreg unavailable on non-Windows host")
    import winreg

    s = scope.value if isinstance(scope, Enum) else scope
    if s == "user":
        return winreg.HKEY_CURRENT_USER, _USER_SUBKEY
    if s == "system":
        return winreg.HKEY_LOCAL_MACHINE, _SYSTEM_SUBKEY
    raise ValueError(f"unsupported scope for registry: {scope!r}")


def read_var(scope: WriteScope | Scope | str, name: str) -> tuple[str, int] | None:
    if sys.platform != "win32":
        raise RuntimeError("winreg unavailable on non-Windows host")
    import winreg

    root, subkey = _scope_root_subkey(scope)
    try:
        with winreg.OpenKey(root, subkey, 0, winreg.KEY_READ) as key:
            try:
                value, reg_type = winreg.QueryValueEx(key, name)
                return str(value), int(reg_type)
            except FileNotFoundError:
                return None
    except FileNotFoundError:
        return None


def list_vars(scope: WriteScope | Scope | str) -> dict[str, tuple[str, int]]:
    if sys.platform != "win32":
        raise RuntimeError("winreg unavailable on non-Windows host")
    import winreg

    root, subkey = _scope_root_subkey(scope)
    out: dict[str, tuple[str, int]] = {}
    try:
        with winreg.OpenKey(root, subkey, 0, winreg.KEY_READ) as key:
            i = 0
            while True:
                try:
                    name, value, reg_type = winreg.EnumValue(key, i)
                except OSError:
                    break
                out[str(name)] = (str(value), int(reg_type))
                i += 1
    except FileNotFoundError:
        pass
    return out


def write_var(scope: WriteScope, name: str, value: str, reg_type: int) -> None:
    if sys.platform != "win32":
        raise RuntimeError("winreg unavailable on non-Windows host")
    import winreg

    root, subkey = _scope_root_subkey(scope)
    try:
        with winreg.OpenKey(root, subkey, 0, winreg.KEY_SET_VALUE) as key:
            winreg.SetValueEx(key, name, 0, reg_type, value)
    except PermissionError as exc:
        if scope is WriteScope.system:
            raise typer.Exit(_perm_denied("写入系统级环境变量需要管理员权限")) from exc
        raise


def delete_var(scope: WriteScope, name: str) -> bool:
    if sys.platform != "win32":
        raise RuntimeError("winreg unavailable on non-Windows host")
    import winreg

    root, subkey = _scope_root_subkey(scope)
    try:
        with winreg.OpenKey(root, subkey, 0, winreg.KEY_SET_VALUE) as key:
            try:
                winreg.DeleteValue(key, name)
                return True
            except FileNotFoundError:
                return False
    except PermissionError as exc:
        if scope is WriteScope.system:
            raise typer.Exit(_perm_denied("删除系统级环境变量需要管理员权限")) from exc
        raise
    except FileNotFoundError:
        return False


def broadcast_setting_change() -> None:
    """Tell Explorer (and listening apps) to reload env vars."""
    import ctypes

    HWND_BROADCAST = 0xFFFF
    WM_SETTINGCHANGE = 0x001A
    SMTO_ABORTIFHUNG = 0x0002
    result = ctypes.c_long()
    ctypes.windll.user32.SendMessageTimeoutW(  # type: ignore[attr-defined]
        HWND_BROADCAST,
        WM_SETTINGCHANGE,
        0,
        "Environment",
        SMTO_ABORTIFHUNG,
        5000,
        ctypes.byref(result),
    )


def _perm_denied(msg: str) -> int:
    typer.echo(f"{msg} (请以管理员身份重新运行)", err=True)
    return 2


# ---------------------------------------------------------------------------
# CLI: list / get / set / unset
# ---------------------------------------------------------------------------
@cmd.command("list")
def list_cmd(
    scope: Scope = typer.Option(Scope.user, "--scope", "-s", help="user / system / process / all"),
    json_out: bool = typer.Option(False, "--json", help="JSON 输出"),
) -> None:
    """列出环境变量。"""
    _ensure_windows()
    data = _collect(scope)
    if json_out:
        typer.echo(json.dumps(data, ensure_ascii=False, indent=2, sort_keys=True))
        return
    for s, items in data.items():
        if scope is not Scope.all_ and s != scope.value:
            continue
        typer.echo(f"[{s}]  ({len(items)} vars)")
        for name in sorted(items, key=str.lower):
            entry = items[name]
            value = entry["value"] if isinstance(entry, dict) else entry
            typer.echo(f"  {name} = {value}")


@cmd.command("get")
def get_cmd(
    name: str = typer.Argument(..., help="变量名"),
    scope: Scope = typer.Option(Scope.all_, "--scope", "-s"),
    json_out: bool = typer.Option(False, "--json"),
) -> None:
    """查看变量值。默认 --scope all 同时打印 user / system / process 三个源。"""
    _ensure_windows()
    rows: dict[str, dict[str, str] | None] = {}
    if scope in (Scope.user, Scope.all_):
        rows["user"] = _entry_dict(read_var(WriteScope.user, name))
    if scope in (Scope.system, Scope.all_):
        rows["system"] = _entry_dict(read_var(WriteScope.system, name))
    if scope in (Scope.process, Scope.all_):
        v = os.environ.get(name)
        rows["process"] = {"value": v, "type": "process"} if v is not None else None

    if json_out:
        typer.echo(json.dumps(rows, ensure_ascii=False, indent=2))
        return
    for s, row in rows.items():
        if row is None:
            typer.echo(f"[{s}] (unset)")
        else:
            typer.echo(f"[{s}] {row.get('type', '')}\n  {row['value']}")


@cmd.command("set")
def set_cmd(
    name: str = typer.Argument(..., help="变量名"),
    value: str = typer.Argument(..., help="变量值"),
    scope: WriteScope = typer.Option(WriteScope.user, "--scope", "-s"),
    type_: RegTypeOpt | None = typer.Option(None, "--type", help="sz | expand; 不传时沿用现值或自动推断"),
    dry_run: bool = typer.Option(False, "--dry-run"),
) -> None:
    """新增或修改变量 (覆盖写入)。"""
    _ensure_windows()
    existing = read_var(scope, name)
    old_value = existing[0] if existing else None
    old_type = existing[1] if existing else None
    new_type = resolve_reg_type(name, type_, old_type)

    typer.echo(f"scope: {scope.value}    name: {name}    type: {reg_type_label(new_type)}")
    typer.echo(f"OLD: {old_value!r}")
    typer.echo(f"NEW: {value!r}")
    if dry_run:
        typer.echo("(dry-run, 未写入)")
        return

    write_var(scope, name, value, new_type)
    os.environ[name] = value
    broadcast_setting_change()
    typer.echo("写入完成。已广播 WM_SETTINGCHANGE。")
    typer.echo("提示: 已打开的 cmd / PowerShell / IDE 不会自动刷新, 需重新打开。")


@cmd.command("unset")
def unset_cmd(
    name: str = typer.Argument(..., help="变量名"),
    scope: WriteScope = typer.Option(WriteScope.user, "--scope", "-s"),
    dry_run: bool = typer.Option(False, "--dry-run"),
) -> None:
    """删除变量。"""
    _ensure_windows()
    existing = read_var(scope, name)
    if existing is None:
        typer.echo(f"[{scope.value}] {name} 不存在, 无需删除。")
        return
    typer.echo(f"scope: {scope.value}    name: {name}    OLD: {existing[0]!r}")
    if dry_run:
        typer.echo("(dry-run, 未删除)")
        return
    delete_var(scope, name)
    os.environ.pop(name, None)
    broadcast_setting_change()
    typer.echo("删除完成。")


# ---------------------------------------------------------------------------
# CLI: path show / add / remove
# ---------------------------------------------------------------------------
@path_app.command("show")
def path_show(
    scope: PathScope = typer.Option(PathScope.effective, "--scope", "-s"),
) -> None:
    """显示 PATH 各 entry。effective = 当前进程实际生效的 PATH。"""
    _ensure_windows()
    if scope is PathScope.effective:
        entries = split_path(os.environ.get("PATH", ""))
    else:
        existing = read_var(WriteScope(scope.value), "PATH")
        entries = split_path(existing[0]) if existing else []
    for e in entries:
        typer.echo(e)


@path_app.command("add")
def path_add(
    entry: str = typer.Argument(..., help="要加入的目录"),
    scope: WriteScope = typer.Option(WriteScope.user, "--scope", "-s"),
    prepend: bool = typer.Option(False, "--prepend", help="加到最前; 默认追加到末尾"),
    backup_dir: Path | None = typer.Option(None, "--backup-dir", help="备份目录, 默认 %LOCALAPPDATA%/ai-assistant/win-env-backup"),
    dry_run: bool = typer.Option(False, "--dry-run"),
) -> None:
    """向 PATH 加入一个目录, 自动去重并保留 REG_EXPAND_SZ 类型。"""
    _ensure_windows()
    existing = read_var(scope, "PATH")
    old_value = existing[0] if existing else ""
    old_type = existing[1] if existing else REG_EXPAND_SZ
    old_entries = split_path(old_value)

    if path_contains(old_entries, entry):
        typer.echo(f"PATH 已包含 {entry!r}, 跳过 (位置不变)。")
        return

    new_entries = [entry, *old_entries] if prepend else [*old_entries, entry]
    new_entries = dedup_path(new_entries)
    new_value = join_path(new_entries)

    typer.echo(f"scope: {scope.value}    type: {reg_type_label(old_type)}")
    typer.echo(render_path_diff(old_entries, new_entries))

    if dry_run:
        bd = backup_dir or default_backup_dir()
        typer.echo(f"(dry-run; 实际写入时会备份到 {bd})")
        return

    bd = backup_dir or default_backup_dir()
    backup_file = write_path_backup(scope, old_value, bd)
    typer.echo(f"已备份原 PATH 到 {backup_file}")
    write_var(scope, "PATH", new_value, old_type)
    os.environ["PATH"] = new_value
    broadcast_setting_change()
    typer.echo("写入完成。已广播 WM_SETTINGCHANGE。")
    typer.echo("提示: 已打开的 cmd / PowerShell / IDE 不会自动刷新, 需重新打开。")


@path_app.command("remove")
def path_remove_cmd(
    entry: str = typer.Argument(..., help="要移除的目录"),
    scope: WriteScope = typer.Option(WriteScope.user, "--scope", "-s"),
    backup_dir: Path | None = typer.Option(None, "--backup-dir"),
    dry_run: bool = typer.Option(False, "--dry-run"),
) -> None:
    """从 PATH 移除一个目录 (大小写不敏感, normpath 比较)。"""
    _ensure_windows()
    existing = read_var(scope, "PATH")
    if existing is None:
        typer.echo(f"[{scope.value}] PATH 不存在, 无需移除。")
        return
    old_value, old_type = existing
    old_entries = split_path(old_value)

    if not path_contains(old_entries, entry):
        typer.echo(f"PATH 不含 {entry!r}, 跳过。")
        return

    new_entries = path_remove(old_entries, entry)
    new_value = join_path(new_entries)

    typer.echo(f"scope: {scope.value}    type: {reg_type_label(old_type)}")
    typer.echo(render_path_diff(old_entries, new_entries))

    if dry_run:
        bd = backup_dir or default_backup_dir()
        typer.echo(f"(dry-run; 实际写入时会备份到 {bd})")
        return

    bd = backup_dir or default_backup_dir()
    backup_file = write_path_backup(scope, old_value, bd)
    typer.echo(f"已备份原 PATH 到 {backup_file}")
    write_var(scope, "PATH", new_value, old_type)
    os.environ["PATH"] = new_value
    broadcast_setting_change()
    typer.echo("写入完成。已广播 WM_SETTINGCHANGE。")
    typer.echo("提示: 已打开的 cmd / PowerShell / IDE 不会自动刷新, 需重新打开。")


# ---------------------------------------------------------------------------
# Internal helpers for CLI rendering
# ---------------------------------------------------------------------------
def _entry_dict(entry: tuple[str, int] | None) -> dict[str, str] | None:
    if entry is None:
        return None
    value, reg_type = entry
    return {"value": value, "type": reg_type_label(reg_type)}


def _collect(scope: Scope) -> dict[str, dict[str, dict[str, str]]]:
    out: dict[str, dict[str, dict[str, str]]] = {}
    if scope in (Scope.user, Scope.all_):
        out["user"] = {n: {"value": v, "type": reg_type_label(t)} for n, (v, t) in list_vars(WriteScope.user).items()}
    if scope in (Scope.system, Scope.all_):
        out["system"] = {n: {"value": v, "type": reg_type_label(t)} for n, (v, t) in list_vars(WriteScope.system).items()}
    if scope in (Scope.process, Scope.all_):
        out["process"] = {n: {"value": v, "type": "process"} for n, v in os.environ.items()}
    return out


if __name__ == "__main__":
    cmd()
