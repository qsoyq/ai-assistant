"""Import Bash-compatible shell exports into Windows environment variables."""

from __future__ import annotations

import os
import sys
from pathlib import Path

import typer

from ai_assistant.commands import version_callback, win_env
from ai_assistant.commands._lazy import print_extras_hint
from ai_assistant.lib.shell_env import ShellEnvError, evaluate_exports, parse_initial_env

helptext = """
使用 Bashkit 执行 Shell 文件, 将导出的环境变量写入 Windows。

采用 Bash 语义, 不保证 Zsh 专有语法兼容。不会继承当前进程环境;
可通过 --env 显式提供初始变量。源目录只读映射, 网络及宿主命令不启用。
脚本在 errexit 模式下执行; 非零退出、stderr 输出或超时会中止导入。
默认跳过 PATH, 多行值保持原样, 使用 REG_SZ 覆盖同名变量。
--dry-run 仍执行脚本, 但不写入 Windows。输出不包含变量值或脚本日志。
仅支持 Windows; --scope system 需要管理员权限。
"""

app = typer.Typer(help=helptext)


@app.command(name="shell-env-to-win", help=helptext)
def import_cmd(
    file: Path = typer.Argument(..., exists=True, dir_okay=False, readable=True, help="UTF-8 编码的 Bash 兼容 Shell 文件"),
    scope: win_env.WriteScope = typer.Option(win_env.WriteScope.user, "--scope", "-s", help="user / system"),
    dry_run: bool = typer.Option(False, "--dry-run", help="执行并预览, 不写入 Windows"),
    env: list[str] | None = typer.Option(None, "--env", help="初始变量 NAME=VALUE, 可重复指定"),
    include_path: bool = typer.Option(False, "--include-path", help="允许按原值覆盖 PATH, 不转换路径"),
    _: bool = typer.Option(False, "--version", "-v", "-V", callback=version_callback, is_eager=True),
) -> None:
    if sys.platform != "win32":
        typer.echo("shell-env-to-win 仅支持 Windows", err=True)
        raise typer.Exit(1)
    try:
        exports = evaluate_exports(file, parse_initial_env(env or []))
    except ImportError as exc:
        print_extras_hint(command_label="shell-env-to-win", entry_invocation="ai-assistant shell-env-to-win", extra="shell-env", exc=exc)
        raise typer.Exit(1) from None
    except ShellEnvError as exc:
        typer.echo(str(exc), err=True)
        raise typer.Exit(1) from None

    if not include_path:
        for name in list(exports):
            if name.upper() == "PATH":
                exports.pop(name)
                typer.echo("Skipped PATH (use --include-path to import it verbatim).")
    if not exports:
        typer.echo("No new or changed exported variables to import.")
        return

    try:
        existing = {name: win_env.read_var(scope, name) for name in exports}
    except OSError:
        typer.echo("Cannot read the target Windows environment; no variables imported.", err=True)
        raise typer.Exit(1) from None
    for name, value in exports.items():
        action = "update" if existing[name] is not None else "add"
        typer.echo(f"[{scope.value}] {action} {name}: {len(value)} characters, REG_SZ")
    if dry_run:
        typer.echo(f"dry-run: {len(exports)} variables; no Windows writes.")
        return

    written: list[str] = []
    failed = False
    exit_code = 1
    try:
        for name, value in exports.items():
            win_env.write_var(scope, name, value, win_env.REG_SZ)
            written.append(name)
            os.environ[name] = value
    except (OSError, ValueError, typer.Exit) as exc:
        failed = True
        exit_code = exc.exit_code if isinstance(exc, typer.Exit) else 1
        typer.echo(f"Import failed at {name}; {len(written)} registry writes completed. No rollback performed.", err=True)
    finally:
        if written:
            try:
                win_env.broadcast_setting_change()
            except Exception:
                failed = True
                typer.echo("Variables were written, but the environment refresh notification failed.", err=True)
    if failed:
        if written:
            typer.echo("Written variables: " + ", ".join(written), err=True)
        raise typer.Exit(exit_code)
    typer.echo(f"Imported {len(written)} variables. Reopen terminals and applications to use the updated environment.")


cmd = typer.main.get_command(app)
