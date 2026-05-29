import shutil
import subprocess

import rich
import typer
from rich.table import Table

from ai_assistant.commands import make_typer

helptext = """
管理通过 `uv tool` 安装的 CLI 工具。

子命令:
- upgrade-all: 列出所有 uv tool 工具, 逐个执行 upgrade, 逐条打印结果并汇总。
"""

cmd = make_typer(helptext)


def _ensure_uv() -> None:
    if not shutil.which("uv"):
        typer.echo("uv not found in PATH, install from https://docs.astral.sh/uv/", err=True)
        raise typer.Exit(1)


def _list_tools() -> list[str]:
    p = subprocess.run(["uv", "tool", "list"], capture_output=True, text=True)
    if p.returncode != 0:
        typer.echo(p.stderr.strip() or "uv tool list failed", err=True)
        raise typer.Exit(p.returncode)
    tools: list[str] = []
    for line in p.stdout.splitlines():
        if not line or line.startswith(("-", " ", "\t")):
            continue
        tools.append(line.split()[0])
    return tools


def _summarize(output: str) -> str:
    for line in reversed(output.splitlines()):
        stripped = line.strip()
        if stripped:
            return stripped
    return "(no output)"


@cmd.command("upgrade-all")
def upgrade_all(
    dry_run: bool = typer.Option(False, "--dry-run", help="只列出会被升级的工具, 不执行"),
    prerelease: str = typer.Option("", "--prerelease", help="透传 uv tool upgrade --prerelease 的取值, 例如 allow / if-necessary / explicit"),
    reinstall: bool = typer.Option(False, "--reinstall", help="透传 uv tool upgrade --reinstall, 强制重装"),
):
    """升级所有通过 uv tool 安装的工具, 逐个执行并汇总结果。"""
    _ensure_uv()
    tools = _list_tools()
    if not tools:
        rich.print("[yellow]uv tool list 为空, 无可升级工具。[/yellow]")
        return

    rich.print(f"待处理 {len(tools)} 个工具: {', '.join(tools)}")
    if dry_run:
        rich.print("[cyan]dry-run: 跳过实际升级。[/cyan]")
        return

    results: list[tuple[str, bool, str]] = []
    for name in tools:
        args = ["uv", "tool", "upgrade", name]
        if prerelease:
            args += ["--prerelease", prerelease]
        if reinstall:
            args += ["--reinstall"]
        rich.print(f"\n[bold]→ {name}[/bold]")
        p = subprocess.run(args, capture_output=True, text=True)
        combined = (p.stderr or "") + (p.stdout or "")
        for line in combined.splitlines():
            rich.print(f"  {line}")
        results.append((name, p.returncode == 0, _summarize(combined)))

    table = Table(title="upgrade summary")
    table.add_column("status", justify="center")
    table.add_column("tool")
    table.add_column("result")
    ok = 0
    for name, success, summary in results:
        if success:
            ok += 1
            table.add_row("[green]✓[/green]", name, summary)
        else:
            table.add_row("[red]✗[/red]", name, summary)
    rich.print()
    rich.print(table)
    rich.print(f"\n总计: {ok}/{len(results)} 成功")
    if ok != len(results):
        raise typer.Exit(1)


if __name__ == "__main__":
    cmd()
