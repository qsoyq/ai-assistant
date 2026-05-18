import os
import re
import subprocess
import sys
import tarfile
import tempfile
from datetime import datetime
from pathlib import Path

import httpx
import rich
import tomlkit
import typer
from rich.table import Table

from ai_assistant.commands import make_typer

helptext = """
生成、查看、校验、安装 realm (https://github.com/zhboner/realm) TCP/UDP 中继。

子命令:

- generate: 渲染配置 TOML, 默认打印到 stdout, 可用 --output 写入文件。
- show:     读取并展示已有配置 (endpoints 表格 + log/network 块)。
- validate: 解析 TOML 并校验关键字段, 失败时打印具体路径并以非零退出。
- install:  从 GitHub releases 下载 realm 二进制并解压到 --prefix, 仅 Linux 可用。

show / validate 未传路径时, 按 ./config.toml -> /etc/realm/config.toml 顺序解析。
"""

cmd = make_typer(helptext)

DEFAULT_CONFIG_CANDIDATES = [Path("./config.toml"), Path("/etc/realm/config.toml")]
VALID_LOG_LEVELS = {"off", "error", "warn", "info", "debug", "trace"}
HOST_PORT_RE = re.compile(r"^.+:\d{1,5}$")

REALM_REPO = "zhboner/realm"
REALM_LATEST_API = f"https://api.github.com/repos/{REALM_REPO}/releases/latest"
REALM_DOWNLOAD_TMPL = f"https://github.com/{REALM_REPO}/releases/download/{{tag}}/realm-{{arch}}-unknown-linux-gnu.tar.gz"
SUPPORTED_ARCHES = {"x86_64", "aarch64"}


def _now() -> str:
    return datetime.now().strftime(r"%Y-%m-%d %H:%M:%S")


def _echo(msg: str) -> None:
    rich.print(f"[{_now()}] {msg}")


def _parse_ports(listen_port: str) -> list[int]:
    ports: list[int] = []
    for token in listen_port.split(","):
        token = token.strip()
        if token.isdigit():
            ports.append(int(token))
            continue
        if token.count("-") == 1:
            start, end = token.split("-")
            start, end = start.strip(), end.strip()
            if start.isdigit() and end.isdigit():
                ports.extend(range(int(start), int(end) + 1))
                continue
        raise typer.BadParameter(f"无法解析端口片段: {token!r}")
    if not ports:
        raise typer.BadParameter("解析后端口列表为空")
    return ports


def _resolve_config(path: Path | None) -> Path:
    if path is not None:
        if not path.exists():
            _echo(f"配置文件不存在: {path}")
            raise typer.Exit(1)
        return path
    for candidate in DEFAULT_CONFIG_CANDIDATES:
        if candidate.exists():
            return candidate
    tried = ", ".join(str(p) for p in DEFAULT_CONFIG_CANDIDATES)
    _echo(f"未找到配置文件, 按顺序查找了: {tried}")
    raise typer.Exit(1)


@cmd.command()
def generate(
    log_level: str = typer.Option("off", help="日志级别, off/error/warn/info/debug/trace"),
    log_output: str = typer.Option("/var/log/realm.log", help="日志输出路径"),
    no_tcp: bool = typer.Option(False, help="禁用 TCP 转发"),
    use_udp: bool = typer.Option(True, help="启用 UDP 转发"),
    listen_host: str = typer.Option("[::0]", help="本地监听主机地址"),
    listen_port: str = typer.Option("443", help="本地监听端口, 支持单端口或范围, 如 443,8110-8113"),
    remote_host: str = typer.Option("127.0.0.1", help="远程主机地址"),
    remote_port: str = typer.Option("443", help="远程主机端口"),
    output: str = typer.Option("-", help="配置输出路径, 默认 - 输出到 stdout"),
):
    """生成 realm 配置 TOML。"""
    local_ports = _parse_ports(listen_port)
    endpoints = [{"listen": f"{listen_host}:{port}", "remote": f"{remote_host}:{remote_port}"} for port in local_ports]
    config = {
        "log": {"level": log_level, "output": log_output},
        "network": {"no_tcp": no_tcp, "use_udp": use_udp},
        "endpoints": endpoints,
    }
    text = tomlkit.dumps(config)
    if output == "-":
        print(text, end="")
        return
    path = Path(output).expanduser()
    if path.is_dir():
        _echo(f"输出路径不可以是目录: {path}")
        raise typer.Exit(2)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text)
    _echo(f"已写入: {path}")


@cmd.command()
def show(
    path: Path = typer.Argument(None, help="配置路径, 留空时按 ./config.toml -> /etc/realm/config.toml 顺序查找"),
):
    """展示已有 realm 配置。"""
    config_path = _resolve_config(path)
    try:
        doc = tomlkit.parse(config_path.read_text())
    except Exception as e:
        _echo(f"TOML 解析失败: {config_path} ({e})")
        raise typer.Exit(1)

    _echo(f"从 {config_path} 读取")

    log = doc.get("log") or {}
    network = doc.get("network") or {}
    rich.print(f"[bold]log[/bold]      level={log.get('level')!r} output={log.get('output')!r}")
    rich.print(f"[bold]network[/bold]  no_tcp={network.get('no_tcp')!r} use_udp={network.get('use_udp')!r}")

    endpoints = doc.get("endpoints") or []
    table = Table(title=f"endpoints ({len(endpoints)})")
    table.add_column("#", justify="right")
    table.add_column("listen")
    table.add_column("remote")
    for i, ep in enumerate(endpoints):
        table.add_row(str(i), str(ep.get("listen", "")), str(ep.get("remote", "")))
    rich.print(table)


@cmd.command()
def validate(
    path: Path = typer.Argument(None, help="配置路径, 留空时按 ./config.toml -> /etc/realm/config.toml 顺序查找"),
):
    """校验配置文件结构, 失败时打印字段路径并以非零退出。"""
    config_path = _resolve_config(path)
    try:
        doc = tomlkit.parse(config_path.read_text())
    except Exception as e:
        _echo(f"TOML 解析失败: {config_path} ({e})")
        raise typer.Exit(1)

    errors: list[str] = []

    log = doc.get("log")
    if not isinstance(log, dict):
        errors.append("log: 缺失或不是 table")
    else:
        level = log.get("level")
        if level not in VALID_LOG_LEVELS:
            errors.append(f"log.level: 非法值 {level!r}, 允许 {sorted(VALID_LOG_LEVELS)}")
        output = log.get("output")
        if not isinstance(output, str) or not output:
            errors.append("log.output: 必须是非空字符串")

    network = doc.get("network")
    if not isinstance(network, dict):
        errors.append("network: 缺失或不是 table")
    else:
        if not isinstance(network.get("no_tcp"), bool):
            errors.append("network.no_tcp: 必须是 bool")
        if not isinstance(network.get("use_udp"), bool):
            errors.append("network.use_udp: 必须是 bool")

    endpoints = doc.get("endpoints")
    if not isinstance(endpoints, list) or not endpoints:
        errors.append("endpoints: 必须是非空数组")
    else:
        for i, ep in enumerate(endpoints):
            if not isinstance(ep, dict):
                errors.append(f"endpoints[{i}]: 不是 table")
                continue
            listen = ep.get("listen")
            remote = ep.get("remote")
            if not isinstance(listen, str) or not HOST_PORT_RE.match(listen):
                errors.append(f"endpoints[{i}].listen: 必须是 host:port 字符串, 当前 {listen!r}")
            if not isinstance(remote, str) or not HOST_PORT_RE.match(remote):
                errors.append(f"endpoints[{i}].remote: 必须是 host:port 字符串, 当前 {remote!r}")

    if errors:
        _echo(f"校验失败: {config_path}")
        for err in errors:
            rich.print(f"  - {err}")
        raise typer.Exit(1)
    _echo(f"校验通过: {config_path}")


def _resolve_latest_tag() -> str:
    try:
        resp = httpx.get(REALM_LATEST_API, timeout=15, follow_redirects=True)
        resp.raise_for_status()
        tag = resp.json().get("tag_name")
    except Exception as e:
        _echo(f"获取最新版本失败: {e}")
        _echo("请显式指定 --version, 例如: --version v2.9.3")
        raise typer.Exit(1)
    if not isinstance(tag, str) or not tag:
        _echo("GitHub API 返回缺少 tag_name 字段")
        raise typer.Exit(1)
    return tag


def _download(url: str, dest: Path) -> None:
    try:
        with httpx.stream("GET", url, timeout=60, follow_redirects=True) as resp:
            resp.raise_for_status()
            with dest.open("wb") as fp:
                for chunk in resp.iter_bytes(chunk_size=64 * 1024):
                    fp.write(chunk)
    except Exception as e:
        _echo(f"下载失败: {url} ({e})")
        raise typer.Exit(1)


def _extract_realm(tarball: Path, prefix: Path) -> Path:
    with tarfile.open(tarball, "r:gz") as tar:
        members = [m for m in tar.getmembers() if m.isfile() and Path(m.name).name == "realm"]
        if not members:
            _echo(f"压缩包中未找到 realm 二进制: {tarball}")
            raise typer.Exit(1)
        member = members[0]
        target = prefix / "realm"
        src = tar.extractfile(member)
        if src is None:
            _echo("解压失败: 无法读取 realm 文件流")
            raise typer.Exit(1)
        with src:
            target.write_bytes(src.read())
    target.chmod(0o755)
    return target


@cmd.command()
def install(
    version: str = typer.Option("latest", help="realm 版本标签, latest 自动解析 GitHub 最新; 显式形如 v2.9.3"),
    arch: str = typer.Option("x86_64", help=f"CPU 架构, 可选 {sorted(SUPPORTED_ARCHES)}"),
    prefix: Path = typer.Option(Path("/usr/local/bin"), help="二进制安装目录"),
    force: bool = typer.Option(False, help="目标已存在时覆盖"),
    dry_run: bool = typer.Option(False, help="只打印将执行的步骤, 不下载也不写盘"),
):
    """从 GitHub releases 下载 realm 二进制并安装到 --prefix (仅 Linux)。"""
    if sys.platform != "linux":
        _echo(f"install 仅支持 Linux, 当前平台 {sys.platform}; 请在 Linux 机器上执行")
        raise typer.Exit(1)
    if arch not in SUPPORTED_ARCHES:
        _echo(f"不支持的架构: {arch!r}, 允许 {sorted(SUPPORTED_ARCHES)}")
        raise typer.Exit(2)

    tag = _resolve_latest_tag() if version == "latest" else version
    url = REALM_DOWNLOAD_TMPL.format(tag=tag, arch=arch)
    target = prefix / "realm"

    _echo(f"版本:   {tag}")
    _echo(f"架构:   {arch}")
    _echo(f"下载:   {url}")
    _echo(f"目标:   {target}")

    if target.exists() and not force:
        _echo(f"已存在 {target}, 加 --force 覆盖, 或先手动删除")
        raise typer.Exit(1)

    if dry_run:
        _echo("dry-run: 跳过下载与写盘")
        return

    if not prefix.exists():
        _echo(f"目录不存在: {prefix}")
        raise typer.Exit(1)
    if not os.access(prefix, os.W_OK):
        _echo(f"无写入权限: {prefix} (用 sudo 重试, 或换 --prefix 到可写目录)")
        raise typer.Exit(1)

    with tempfile.TemporaryDirectory(prefix="realm-install-") as tmpdir:
        tarball = Path(tmpdir) / "realm.tar.gz"
        _echo("下载中...")
        _download(url, tarball)
        _echo(f"已下载 {tarball.stat().st_size} 字节, 解压中...")
        binary = _extract_realm(tarball, prefix)

    _echo(f"已安装: {binary}")

    try:
        out = subprocess.run([str(target), "-v"], capture_output=True, text=True, timeout=10)
    except Exception as e:
        _echo(f"校验失败: 无法执行 {target} -v ({e})")
        raise typer.Exit(1)
    version_line = (out.stdout or out.stderr).strip().splitlines()[0] if (out.stdout or out.stderr) else ""
    _echo(f"校验: {version_line or '(无输出)'}")


if __name__ == "__main__":
    cmd()
