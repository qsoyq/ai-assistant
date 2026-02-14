import logging
import subprocess
import time
from pathlib import Path

import typer
from watchfiles import Change
from watchfiles import watch as watch_changes

from ai_assistant.commands import default_invoke_without_command

helptext = """
监听文件变化并执行命令
"""

cmd = typer.Typer(help=helptext)


def add_default_invoke():
    for _cmd in (cmd,):
        _cmd.callback(invoke_without_command=True)(default_invoke_without_command)


add_default_invoke()


@cmd.command()
def watch(
    target: Path = typer.Argument(
        ...,
        help="监听目标（文件或目录）",
        exists=True,
        file_okay=True,
        dir_okay=True,
        resolve_path=True,
    ),
    run_cmd: str = typer.Argument(..., help="检测到变化后执行的 shell 命令"),
    interval: float = typer.Option(0.2, "-i", "--interval", help="事件轮询步长（秒）"),
    debounce: float = typer.Option(0.5, "-d", "--debounce", help="两次触发的最短间隔（秒）"),
    run_on_start: bool = typer.Option(False, "--run-on-start", help="启动时先执行一次命令"),
):
    """监听文件变化并执行命令"""
    logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s")

    target = target.expanduser()
    if not target.exists():
        raise typer.BadParameter(f"目标不存在: {target}")

    watch_path = target if target.is_dir() else target.parent
    target_resolved = target.resolve()
    target_is_dir = target.is_dir()
    last_trigger_at = 0.0

    if run_on_start:
        typer.echo(f"[startup] 执行命令: {run_cmd}")
        p = subprocess.run(run_cmd, shell=True, check=False, capture_output=True, text=True)
        typer.echo(f"[exit_code] {p.returncode}")
        typer.echo(f"[stdout] {p.stdout}")
        typer.echo(f"[stderr] {p.stderr}")

        last_trigger_at = time.time()

    typer.echo(f"开始监听: {target}")
    typer.echo(f"触发命令: {run_cmd}")
    typer.echo("按 Ctrl+C 退出")

    try:
        for changes in watch_changes(watch_path, recursive=True, debounce=0, step=int(interval * 1000)):
            if not changes:
                continue

            if target_is_dir:
                related_changes = changes
            else:
                related_changes = {(change, path) for change, path in changes if Path(path).resolve() == target_resolved}

            if not related_changes:
                continue

            now = time.time()
            if now - last_trigger_at < debounce:
                continue

            action_names = sorted({change.name.lower() for change, _ in related_changes if isinstance(change, Change)})
            typer.echo(f"[changed] {target} ({', '.join(action_names)})")
            p = subprocess.run(run_cmd, shell=True, check=False, capture_output=True, text=True)
            typer.echo(f"[exit_code] {p.returncode}")
            typer.echo(f"[stdout] {p.stdout}")
            typer.echo(f"[stderr] {p.stderr}")

            last_trigger_at = now
    except KeyboardInterrupt:
        typer.echo("\n已停止监听")


if __name__ == "__main__":
    cmd()
