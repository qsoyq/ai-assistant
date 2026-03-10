import subprocess
import time

import typer

from ai_assistant.commands import default_invoke_without_command

helptext = """
监听 Docker 镜像更新并执行命令
"""

cmd = typer.Typer(help=helptext)


def add_default_invoke():
    for _cmd in (cmd,):
        _cmd.callback(invoke_without_command=True)(default_invoke_without_command)


add_default_invoke()


@cmd.command()
def watch(
    image: str = typer.Argument(..., help="监听的 Docker 镜像，例如 nginx:latest"),
    run_cmd: str = typer.Argument(..., help="检测到变化后执行的 shell 命令"),
    interval: float = typer.Option(30.0, "-i", "--interval", min=1.0, help="轮询间隔（秒）"),
    docker_timeout: float = typer.Option(300.0, "--docker-timeout", min=1.0, help="单次 Docker 命令超时时间（秒）"),
    run_on_start: bool = typer.Option(False, "--run-on-start", help="启动时先执行一次命令"),
    trigger_on_initial_pull: bool = typer.Option(False, "--trigger-on-initial-pull", help="首次拉取到镜像时也触发命令"),
):
    """监听 Docker 镜像更新并执行命令"""

    def run_shell_command(command: str) -> None:
        typer.echo(f"[run] {command}")
        process = subprocess.run(command, shell=True, check=False, capture_output=True, text=True)
        typer.echo(f"[exit_code] {process.returncode}")
        typer.echo(f"[stdout] {process.stdout}")
        typer.echo(f"[stderr] {process.stderr}")

    def run_docker_command(args: list[str]) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            ["docker", *args],
            check=False,
            capture_output=True,
            text=True,
            timeout=docker_timeout,
        )

    def inspect_image_id() -> str | None:
        process = run_docker_command(["image", "inspect", "--format", "{{.Id}}", image])
        if process.returncode != 0:
            return None
        return process.stdout.strip() or None

    def pull_image() -> tuple[bool, str]:
        try:
            process = run_docker_command(["pull", image])
        except subprocess.TimeoutExpired:
            return False, f"docker pull 超时（>{docker_timeout} 秒）"

        output = "\n".join(part for part in (process.stdout.strip(), process.stderr.strip()) if part).strip()
        if process.returncode != 0:
            return False, output or "docker pull 执行失败"
        return True, output

    last_image_id = inspect_image_id()

    if run_on_start:
        typer.echo("[startup] 启动时执行命令")
        run_shell_command(run_cmd)

    typer.echo(f"开始监听镜像: {image}")
    typer.echo(f"触发命令: {run_cmd}")
    typer.echo(f"当前镜像 ID: {last_image_id or '<未拉取>'}")
    typer.echo(f"轮询间隔: {interval} 秒")
    typer.echo("按 Ctrl+C 退出")

    try:
        while True:
            success, pull_output = pull_image()
            if not success:
                typer.echo(f"[docker_pull_failed] {pull_output}")
                time.sleep(interval)
                continue

            current_image_id = inspect_image_id()
            if current_image_id is None:
                typer.echo("[inspect_failed] 拉取完成后仍无法获取镜像 ID")
                time.sleep(interval)
                continue

            if last_image_id is None:
                typer.echo(f"[pulled] {image}")
                if pull_output:
                    typer.echo(f"[docker] {pull_output}")
                if trigger_on_initial_pull:
                    typer.echo("[trigger] 首次拉取到镜像，执行命令")
                    run_shell_command(run_cmd)
                last_image_id = current_image_id
                time.sleep(interval)
                continue

            if current_image_id != last_image_id:
                typer.echo(f"[updated] {image}")
                typer.echo(f"[old_image_id] {last_image_id}")
                typer.echo(f"[new_image_id] {current_image_id}")
                if pull_output:
                    typer.echo(f"[docker] {pull_output}")
                run_shell_command(run_cmd)
                last_image_id = current_image_id
            else:
                typer.echo(f"[no_change] {image}")

            time.sleep(interval)
    except KeyboardInterrupt:
        typer.echo("\n已停止监听")


if __name__ == "__main__":
    cmd()
