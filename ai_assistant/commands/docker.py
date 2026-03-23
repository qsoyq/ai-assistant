import json
import os
from dataclasses import dataclass
from pathlib import Path, PurePosixPath

import docker
import typer
from docker.errors import ContainerError, DockerException, ImageNotFound
from rich.console import Console
from rich.markdown import Markdown

from ai_assistant.commands import default_invoke_without_command

_DAEMON_LOG_ROOT = PurePosixPath("/var/lib/docker/containers")
_DEFAULT_HELPER_IMAGE = "alpine:3.20"
_CONSOLE = Console()

helptext = """
Docker 相关工具
"""

cmd = typer.Typer(help=helptext)


def add_default_invoke():
    for _cmd in (cmd,):
        _cmd.callback(invoke_without_command=True)(default_invoke_without_command)


add_default_invoke()


@dataclass(frozen=True)
class ContainerLogTarget:
    id: str
    short_id: str
    name: str
    log_path: str

    @property
    def display_name(self) -> str:
        return f"{self.name} ({self.short_id})"


def _normalize_container_name(name: str) -> str:
    return name.lstrip("/")


def _docker_config_dir() -> Path:
    docker_config = os.environ.get("DOCKER_CONFIG")
    if docker_config:
        return Path(docker_config)
    return Path.home() / ".docker"


def _get_current_docker_context(config_dir: Path | None = None) -> str | None:
    docker_config_dir = config_dir or _docker_config_dir()
    config_path = docker_config_dir / "config.json"
    if not config_path.is_file():
        return None

    try:
        config_data = json.loads(config_path.read_text())
    except (OSError, json.JSONDecodeError):
        return None

    current_context = config_data.get("currentContext")
    if not isinstance(current_context, str) or not current_context or current_context == "default":
        return None

    return current_context


def _get_docker_context_host(config_dir: Path | None = None) -> str | None:
    docker_config_dir = config_dir or _docker_config_dir()
    current_context = _get_current_docker_context(docker_config_dir)
    if not current_context:
        return None

    meta_root = docker_config_dir / "contexts" / "meta"
    if not meta_root.is_dir():
        return None

    for metadata_path in meta_root.glob("*/meta.json"):
        try:
            metadata = json.loads(metadata_path.read_text())
        except (OSError, json.JSONDecodeError):
            continue

        if metadata.get("Name") != current_context:
            continue

        endpoint = metadata.get("Endpoints", {}).get("docker", {})
        host = endpoint.get("Host")
        if isinstance(host, str) and host:
            return host

    return None


def create_docker_client() -> docker.DockerClient:
    if os.environ.get("DOCKER_HOST"):
        return docker.from_env()

    context_host = _get_docker_context_host()
    if context_host:
        return docker.DockerClient(base_url=context_host)

    return docker.from_env()


def list_container_log_targets(client: docker.DockerClient) -> list[ContainerLogTarget]:
    targets: list[ContainerLogTarget] = []

    for container in client.containers.list(all=True):
        details = client.api.inspect_container(container.id)
        targets.append(
            ContainerLogTarget(
                id=container.id,
                short_id=container.short_id,
                name=_normalize_container_name(details.get("Name") or container.name or container.short_id),
                log_path=details.get("LogPath") or "",
            )
        )

    return targets


def select_container_targets(targets: list[ContainerLogTarget], selector: str) -> list[ContainerLogTarget]:
    if selector == "*":
        return list(targets)

    matches = [target for target in targets if selector in {target.name, target.id, target.short_id}]
    if not matches:
        raise typer.BadParameter(f"未找到容器: {selector}。请传入精确容器名称、完整/短 ID，或 `*`。")

    if len(matches) > 1:
        matched_names = ", ".join(target.display_name for target in matches)
        raise typer.BadParameter(f"匹配到多个容器: {matched_names}。请改用完整容器 ID。")

    return matches


def get_single_container(client: docker.DockerClient, selector: str) -> docker.models.containers.Container:
    targets = list_container_log_targets(client)
    matches = select_container_targets(targets, selector)
    if len(matches) != 1:
        raise typer.BadParameter("该命令仅支持单个容器，请传入精确容器名称或容器 ID。")
    return client.containers.get(matches[0].id)


def list_joinable_networks(client: docker.DockerClient) -> list[docker.models.networks.Network]:
    return [network for network in client.networks.list() if network.name not in {"host", "none"}]


def connect_container_to_all_networks(
    client: docker.DockerClient,
    container: docker.models.containers.Container,
) -> tuple[list[str], list[str]]:
    container.reload()
    connected_network_names = set(container.attrs.get("NetworkSettings", {}).get("Networks", {}))
    connected: list[str] = []
    skipped: list[str] = []

    for network in list_joinable_networks(client):
        if network.name in connected_network_names:
            skipped.append(network.name)
            continue

        try:
            network.connect(container)
            connected.append(network.name)
        except DockerException as exc:
            raise RuntimeError(f"将容器 `{container.name}` 加入网络 `{network.name}` 失败: {exc}") from exc

    return connected, skipped


def print_markdown(message: str) -> None:
    _CONSOLE.print(Markdown(message))


def truncate_log_file(log_path: str) -> None:
    path = Path(log_path)
    if not path.is_absolute():
        raise RuntimeError(f"日志路径不是绝对路径: {log_path}")
    if not path.exists():
        raise RuntimeError(f"日志文件不存在: {log_path}")
    if not path.is_file():
        raise RuntimeError(f"日志路径不是文件: {log_path}")

    with path.open("r+b") as file:
        file.truncate(0)


def can_clear_with_helper_container(log_path: str) -> bool:
    path = PurePosixPath(log_path)
    if not path.is_absolute():
        return False

    try:
        path.relative_to(_DAEMON_LOG_ROOT)
    except ValueError:
        return False

    return True


def clear_logs_with_helper_container(
    client: docker.DockerClient,
    targets: list[ContainerLogTarget],
    helper_image: str,
) -> None:
    log_paths = [target.log_path for target in targets]
    command = ["sh", "-ceu", 'for file in "$@"; do : > "$file"; done', "sh", *log_paths]
    volumes = {str(_DAEMON_LOG_ROOT): {"bind": str(_DAEMON_LOG_ROOT), "mode": "rw"}}

    try:
        client.containers.run(helper_image, command=command, remove=True, volumes=volumes)
    except ImageNotFound:
        client.images.pull(helper_image)
        client.containers.run(helper_image, command=command, remove=True, volumes=volumes)
    except ContainerError as exc:
        stderr = exc.stderr.decode("utf-8", errors="ignore") if isinstance(exc.stderr, bytes) else str(exc.stderr or "")
        raise RuntimeError(f"辅助容器清空日志失败: {stderr.strip() or exc}") from exc


def clear_container_logs(
    client: docker.DockerClient,
    targets: list[ContainerLogTarget],
    helper_image: str = _DEFAULT_HELPER_IMAGE,
) -> None:
    helper_targets: list[ContainerLogTarget] = []
    failures: list[str] = []

    for target in targets:
        if not target.log_path:
            failures.append(f"{target.display_name}: Docker 未返回日志路径，可能正在使用不支持清空的日志驱动")
            continue

        try:
            truncate_log_file(target.log_path)
        except OSError:
            if can_clear_with_helper_container(target.log_path):
                helper_targets.append(target)
                continue
            failures.append(f"{target.display_name}: 无法直接访问日志文件 `{target.log_path}`")
        except RuntimeError as exc:
            if can_clear_with_helper_container(target.log_path):
                helper_targets.append(target)
                continue
            failures.append(f"{target.display_name}: {exc}")

    if helper_targets:
        try:
            clear_logs_with_helper_container(client, helper_targets, helper_image=helper_image)
        except (DockerException, RuntimeError) as exc:
            helper_names = ", ".join(target.display_name for target in helper_targets)
            failures.append(f"{helper_names}: {exc}")

    if failures:
        failure_text = "\n".join(f"- {message}" for message in failures)
        raise RuntimeError(f"以下容器日志清空失败:\n{failure_text}")


@cmd.command("log-clear")
def log_clear(
    container: str = typer.Argument(..., help="精确容器名称、完整/短容器 ID，或 `*` 表示全部容器"),
    helper_image: str = typer.Option(_DEFAULT_HELPER_IMAGE, "--helper-image", help="无法直接访问日志文件时使用的辅助镜像"),
):
    """清空指定容器的日志

    使用示例:
    - `ai-assistant docker log-clear web`
    - `ai-assistant docker log-clear 1234567890ab`
    - `ai-assistant docker log-clear '*'`
    - `ai-assistant docker log-clear web --helper-image alpine:3.20`

    - 传入容器名称时，按精确名称匹配
    - 传入容器 ID 时，支持完整 ID 或短 ID 精确匹配
    - 传入 `*` 时，清空所有容器日志

    优先直接清空 Docker 返回的 `LogPath`；
    如果当前环境无法直接访问日志文件，会回退到临时辅助容器执行清理，
    以兼容 Docker Desktop 等 daemon 文件系统不直接暴露给当前机器的场景。

    `--helper-image` 需要包含可用的 shell，用于在辅助容器内截断日志文件。
    """

    client: docker.DockerClient | None = None
    try:
        client = create_docker_client()
        targets = list_container_log_targets(client)
        selected_targets = select_container_targets(targets, container)
        if not selected_targets:
            typer.echo("未找到可清空日志的容器")
            raise typer.Exit(code=1)

        clear_container_logs(client, selected_targets, helper_image=helper_image)

        for target in selected_targets:
            typer.echo(f"已清空日志: {target.display_name}")
        typer.echo(f"完成，共处理 {len(selected_targets)} 个容器")
    except typer.BadParameter as exc:
        typer.echo(f"参数错误: {exc}", err=True)
        raise typer.Exit(code=1) from exc
    except DockerException as exc:
        typer.echo(f"Docker 连接或执行失败: {exc}", err=True)
        raise typer.Exit(code=1) from exc
    except RuntimeError as exc:
        typer.echo(str(exc), err=True)
        raise typer.Exit(code=1) from exc
    finally:
        if client is not None:
            client.close()


@cmd.command("network-connect-all")
def network_connect_all(
    container: str = typer.Argument(..., help="精确容器名称、完整容器 ID 或短容器 ID"),
):
    """将指定容器加入到全部普通 Docker 网络中

    使用示例:
    - `ai-assistant docker network-connect-all web`
    - `ai-assistant docker network-connect-all 1234567890ab`

    说明:
    - 会遍历当前 Docker 上的全部网络
    - 已连接的网络会自动跳过
    - `host` 和 `none` 属于特殊网络，默认不处理
    """

    client: docker.DockerClient | None = None
    try:
        client = create_docker_client()
        target_container = get_single_container(client, container)
        connected, skipped = connect_container_to_all_networks(client, target_container)

        if connected:
            connected_items = "\n".join(f"- `{network}`" for network in connected)
            print_markdown(f"已加入网络:\n{connected_items}")
        if skipped:
            skipped_items = "\n".join(f"- `{network}`" for network in skipped)
            print_markdown(f"已跳过网络:\n{skipped_items}")
        if not connected and not skipped:
            typer.echo("未发现可加入的普通 Docker 网络")
            raise typer.Exit(code=1)

        typer.echo(f"完成，容器 {target_container.name} 新加入 {len(connected)} 个网络，跳过 {len(skipped)} 个网络")
    except typer.BadParameter as exc:
        typer.echo(f"参数错误: {exc}", err=True)
        raise typer.Exit(code=1) from exc
    except DockerException as exc:
        typer.echo(f"Docker 连接或执行失败: {exc}", err=True)
        raise typer.Exit(code=1) from exc
    except RuntimeError as exc:
        typer.echo(str(exc), err=True)
        raise typer.Exit(code=1) from exc
    finally:
        if client is not None:
            client.close()


if __name__ == "__main__":
    cmd()
