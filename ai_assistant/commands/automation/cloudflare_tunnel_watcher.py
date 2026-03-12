import os
import subprocess
import time
from dataclasses import dataclass
from enum import Enum

import requests
import typer

from ai_assistant.commands import default_invoke_without_command

helptext = """
监听 Cloudflare Tunnel 连接状态变化并执行命令
"""

cmd = typer.Typer(help=helptext)


def add_default_invoke():
    for _cmd in (cmd,):
        _cmd.callback(invoke_without_command=True)(default_invoke_without_command)


add_default_invoke()


class TunnelStatus(str, Enum):
    READY = "ready"
    NOT_READY = "not_ready"
    UNREACHABLE = "unreachable"


@dataclass(frozen=True)
class TunnelState:
    metrics_url: str
    status: TunnelStatus
    status_code: int
    detail: str

    @property
    def is_healthy(self) -> bool:
        return self.status == TunnelStatus.READY


def fetch_tunnel_state(metrics_url: str, timeout: float) -> TunnelState:
    try:
        ready_url = f"{metrics_url.rstrip('/')}/ready"
        response = requests.get(ready_url, timeout=timeout)
        if response.status_code == 200:
            return TunnelState(
                metrics_url=metrics_url,
                status=TunnelStatus.READY,
                status_code=response.status_code,
                detail=response.text.strip(),
            )
        return TunnelState(
            metrics_url=metrics_url,
            status=TunnelStatus.NOT_READY,
            status_code=response.status_code,
            detail=response.text.strip(),
        )
    except requests.ConnectionError:
        return TunnelState(
            metrics_url=metrics_url,
            status=TunnelStatus.UNREACHABLE,
            status_code=0,
            detail="无法连接到 cloudflared metrics 端点",
        )
    except requests.Timeout:
        return TunnelState(
            metrics_url=metrics_url,
            status=TunnelStatus.UNREACHABLE,
            status_code=0,
            detail="连接 cloudflared metrics 端点超时",
        )


def run_shell_command(run_cmd: str, state: TunnelState) -> None:
    env = os.environ.copy()
    env.update(
        {
            "CF_TUNNEL_METRICS_URL": state.metrics_url,
            "CF_TUNNEL_STATUS": state.status.value,
            "CF_TUNNEL_STATUS_CODE": str(state.status_code),
            "CF_TUNNEL_DETAIL": state.detail,
            "CF_TUNNEL_IS_HEALTHY": str(state.is_healthy).lower(),
        }
    )

    typer.echo(f"[run] {run_cmd}")
    p = subprocess.run(run_cmd, shell=True, check=False, capture_output=True, text=True, env=env)
    typer.echo(f"[exit_code] {p.returncode}")
    typer.echo(f"[stdout] {p.stdout}")
    typer.echo(f"[stderr] {p.stderr}")


@cmd.command()
def watch(
    run_cmd: str = typer.Argument(..., help="检测到状态变化后执行的 shell 命令"),
    metrics_url: str = typer.Option("http://127.0.0.1:20241", "--metrics-url", "-m", help="cloudflared metrics 端点地址"),
    interval: float = typer.Option(30, "-i", "--interval", help="轮询间隔（秒）", min=1),
    request_timeout: float = typer.Option(5.0, "--request-timeout", help="请求超时时间（秒）", min=1),
    run_on_start: bool = typer.Option(False, "--run-on-start", help="启动时立即执行一次命令"),
    run_on_unhealthy: bool = typer.Option(False, "--run-on-unhealthy", help="仅在状态变为不健康时执行命令（默认任何状态变化都执行）"),
):
    """监听 Cloudflare Tunnel 连接状态变化并执行命令

    通过轮询 cloudflared 的 metrics 端点 `/ready` 来检测隧道连接状态。
    cloudflared 默认在 `127.0.0.1:20241` 暴露 metrics 服务，
    可通过 `cloudflared --metrics` 参数自定义地址。

    传递给执行命令子进程的环境变量:
    - `CF_TUNNEL_METRICS_URL`: metrics 端点地址
    - `CF_TUNNEL_STATUS`: 当前状态 (`ready`, `not_ready`, `unreachable`)
    - `CF_TUNNEL_STATUS_CODE`: HTTP 状态码（不可达时为 `0`）
    - `CF_TUNNEL_DETAIL`: 状态详情
    - `CF_TUNNEL_IS_HEALTHY`: 是否健康 (`true` / `false`)

    示例:
    - 监听状态变化:
            ai-assistant-cf-tunnel-watcher watch 'echo "status=$CF_TUNNEL_STATUS"' --run-on-start
    - 自定义 metrics 地址:
            ai-assistant-cf-tunnel-watcher watch 'echo "$CF_TUNNEL_STATUS"' -m http://127.0.0.1:12345
    - 启动时立即执行:
            ai-assistant-cf-tunnel-watcher watch 'notify.sh' --run-on-start
    - 仅在不健康时执行:
            ai-assistant-cf-tunnel-watcher watch 'alert.sh' --run-on-unhealthy
    - 调整轮询间隔:
            ai-assistant-cf-tunnel-watcher watch 'your-command' --interval 10
    """
    typer.echo(f"开始监听 Cloudflare Tunnel 状态: {metrics_url}")
    typer.echo(f"轮询间隔: {interval} 秒")
    typer.echo(f"触发命令: {run_cmd}")
    if run_on_unhealthy:
        typer.echo("触发模式: 仅不健康时执行")
    else:
        typer.echo("触发模式: 任何状态变化时执行")
    typer.echo("按 Ctrl+C 退出")

    current_state = fetch_tunnel_state(metrics_url, timeout=request_timeout)
    typer.echo(f"[current] status={current_state.status.value} code={current_state.status_code} detail={current_state.detail}")

    if run_on_start:
        run_shell_command(run_cmd, current_state)

    try:
        while True:
            time.sleep(interval)

            next_state = fetch_tunnel_state(metrics_url, timeout=request_timeout)

            if next_state.status == current_state.status:
                typer.echo(f"[no_change] status={next_state.status.value}")
                continue

            typer.echo(f"[changed] {current_state.status.value} -> {next_state.status.value}")
            typer.echo(f"[detail] {next_state.detail}")

            should_run = True
            if run_on_unhealthy and next_state.is_healthy:
                should_run = False
                typer.echo("[skip] 新状态为健康，跳过命令执行")

            if should_run:
                run_shell_command(run_cmd, next_state)

            current_state = next_state
    except KeyboardInterrupt:
        typer.echo("\n已停止监听")


if __name__ == "__main__":
    cmd()
