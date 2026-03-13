import os
import subprocess
import time
from dataclasses import dataclass
from datetime import datetime

import requests
import typer

from ai_assistant.commands import default_invoke_without_command

helptext = """
监听 Docker Hub 镜像最新推送并执行命令
"""

cmd = typer.Typer(help=helptext)


def add_default_invoke():
    for _cmd in (cmd,):
        _cmd.callback(invoke_without_command=True)(default_invoke_without_command)


add_default_invoke()


@dataclass(frozen=True)
class DockerHubTagState:
    namespace: str
    repository: str
    tag: str
    digest: str
    last_updated: str

    @property
    def image(self) -> str:
        return f"{self.namespace}/{self.repository}"

    @property
    def image_with_tag(self) -> str:
        return f"{self.image}:{self.tag}"


def parse_image(image: str) -> tuple[str, str]:
    parts = [part for part in image.strip().split("/") if part]
    if len(parts) == 1:
        return "library", parts[0]
    if len(parts) == 2:
        return parts[0], parts[1]

    raise typer.BadParameter("镜像名称格式不正确，应为 `repo` 或 `namespace/repo`")


def fetch_latest_tag_state(namespace: str, repository: str, timeout: float) -> DockerHubTagState:
    response = requests.get(
        f"https://hub.docker.com/v2/namespaces/{namespace}/repositories/{repository}/tags",
        params={"page_size": "1", "ordering": "last_updated"},
        timeout=timeout,
    )
    response.raise_for_status()

    payload = response.json()
    results = payload.get("results") or []
    if not results:
        raise RuntimeError(f"未找到镜像标签: {namespace}/{repository}")

    latest = results[0]
    images = latest.get("images") or []
    digest = next((item.get("digest") for item in images if item.get("digest")), "")

    return DockerHubTagState(
        namespace=namespace,
        repository=repository,
        tag=latest["name"],
        digest=digest,
        last_updated=latest["last_updated"],
    )


def fetch_fixed_tag_state(namespace: str, repository: str, tag: str, timeout: float) -> DockerHubTagState:
    response = requests.get(
        f"https://hub.docker.com/v2/namespaces/{namespace}/repositories/{repository}/tags/{tag}",
        timeout=timeout,
    )
    response.raise_for_status()

    payload = response.json()
    images = payload.get("images") or []
    digest = next((item.get("digest") for item in images if item.get("digest")), "")

    return DockerHubTagState(
        namespace=namespace,
        repository=repository,
        tag=payload["name"],
        digest=digest,
        last_updated=payload["last_updated"],
    )


def run_shell_command(run_cmd: str, state: DockerHubTagState) -> None:
    env = os.environ.copy()
    env.update(
        {
            "DOCKERHUB_IMAGE": state.image,
            "DOCKERHUB_TAG": state.tag,
            "DOCKERHUB_IMAGE_WITH_TAG": state.image_with_tag,
            "DOCKERHUB_DIGEST": state.digest,
            "DOCKERHUB_LAST_UPDATED": state.last_updated,
        }
    )

    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    typer.echo(f"{now} [run] {run_cmd}")
    p = subprocess.run(run_cmd, shell=True, check=False, capture_output=True, text=True, env=env)
    typer.echo(f"{now} [exit_code] {p.returncode}")
    typer.echo(f"{now} [stdout] {p.stdout}")
    typer.echo(f"{now} [stderr] {p.stderr}")


@cmd.command()
def watch(
    image: str = typer.Argument(..., help="Docker Hub 镜像名，如 `nginx` 或 `library/nginx`"),
    run_cmd: str = typer.Argument(..., help="检测到新镜像推送后执行的 shell 命令"),
    tag: str | None = typer.Option(None, "--tag", help="固定监听某个 tag，例如 `latest`"),
    interval: float = typer.Option(300, "-i", "--interval", help="轮询间隔（秒）", min=1),
    request_timeout: float = typer.Option(10.0, "--request-timeout", help="请求 Docker Hub API 的超时时间（秒）", min=1),
    run_on_start: bool = typer.Option(False, "--run-on-start", help="启动时立即执行一次命令"),
):
    """监听 Docker Hub 镜像最新推送或指定 tag 的变化并执行命令

    传递给执行命令子进程的环境变量:
    - `DOCKERHUB_IMAGE`: 镜像名，例如 `library/nginx`
    - `DOCKERHUB_TAG`: 当前 tag，例如 `latest`
    - `DOCKERHUB_IMAGE_WITH_TAG`: 带 tag 的镜像名，例如 `library/nginx:latest`
    - `DOCKERHUB_DIGEST`: 当前镜像摘要，例如 `sha256:...`
    - `DOCKERHUB_LAST_UPDATED`: Docker Hub 返回的最近更新时间

    示例:
    - 监听镜像最近推送:
            ai-assistant-docker-hub-runner watch nginx 'echo "$DOCKERHUB_IMAGE_WITH_TAG"'
    - 监听镜像最近推送并立即执行:
            ai-assistant-docker-hub-runner watch nginx 'echo "$DOCKERHUB_IMAGE_WITH_TAG"' --run-on-start
    - 只监听固定 tag:
            ai-assistant-docker-hub-runner watch nginx 'echo "$DOCKERHUB_DIGEST"' --tag latest
    - 只监听固定 tag 并立即执行:
            ai-assistant-docker-hub-runner watch nginx 'echo "$DOCKERHUB_DIGEST"' --tag latest --run-on-start
    - 调整轮询和请求超时:
            ai-assistant-docker-hub-runner watch nginx 'your-command' --interval 30 --request-timeout 5
    """
    namespace, repository = parse_image(image)

    def fetch_state() -> DockerHubTagState:
        if tag is None:
            return fetch_latest_tag_state(namespace, repository, timeout=request_timeout)
        return fetch_fixed_tag_state(namespace, repository, tag, timeout=request_timeout)

    typer.echo(f"开始监听 Docker Hub 镜像: {namespace}/{repository}")
    if tag is None:
        typer.echo("监听模式: 最新推送")
    else:
        typer.echo(f"监听模式: 固定 tag ({tag})")
    typer.echo(f"轮询间隔: {interval} 秒")
    typer.echo(f"触发命令: {run_cmd}")
    typer.echo("按 Ctrl+C 退出")

    try:
        current_state = fetch_state()
    except Exception as exc:
        raise typer.BadParameter(f"初始化获取镜像信息失败: {exc}") from exc

    typer.echo(f"[current] {current_state.image_with_tag} @ {current_state.last_updated}")

    if run_on_start:
        run_shell_command(run_cmd, current_state)

    try:
        while True:
            time.sleep(interval)

            now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

            try:
                next_state = fetch_state()
            except Exception as exc:
                typer.echo(f"{now} [error] 拉取 Docker Hub 信息失败: {exc}")
                continue

            if next_state == current_state:
                typer.echo(f"{now} [no_change] {next_state.image_with_tag} @ {next_state.last_updated}")
                continue

            typer.echo(f"{now} [updated] {current_state.image_with_tag} -> {next_state.image_with_tag}")
            typer.echo(f"{now} [digest] {current_state.digest or '-'} -> {next_state.digest or '-'}")
            typer.echo(f"{now} [last_updated] {current_state.last_updated} -> {next_state.last_updated}")
            run_shell_command(run_cmd, next_state)
            current_state = next_state
    except KeyboardInterrupt:
        typer.echo("\n已停止监听")


if __name__ == "__main__":
    cmd()
