import json
import os
import platform
import random
import shutil
import subprocess
from datetime import datetime
from pathlib import Path
from uuid import uuid4

import httpx
import typer

from ai_assistant.commands import make_typer

helptext = """
基于 Xray REALITY 协议生成服务端与客户端配置, 可选自动安装 xray 并启用 systemd 服务。

参考: https://github.com/XTLS/REALITY

子命令:

- build: 渲染 REALITY 服务端配置 / 客户端信息 / vless URL, 默认写入 /usr/local/etc/xray/。
  追加 `--dry-run` 仅打印, 不写盘 / 不安装 / 不操作 systemd; 适合在非 Linux 环境预览。

依赖说明:

- 自动公网 IP 探测使用 httpx 直连 cloudflare/cdn-cgi/trace, 网络不可达时请用 `--address` 显式指定。
- 自动安装 xray 仅支持 Debian / Ubuntu (apt-get) 与 RHEL / CentOS (yum), 失败可追加 `--skip-install` 自行安装。
- 启动服务依赖 systemd, 非 Linux 平台会自动跳过。
"""

cmd = make_typer(helptext)
DEFAULT_CONFIG_PATH = Path("/usr/local/etc/xray/config.json")
DEFAULT_CLIENT_INFO_PATH = Path("/usr/local/etc/xray/reclient.json")
DEFAULT_ACCESS_LOG = "/var/log/xray/access.log"
DEFAULT_ERROR_LOG = "/var/log/xray/error.log"
DEFAULT_SNI = "www.amazon.com"
DEFAULT_SHORT_IDS = "88"
DEFAULT_PORT = 443
XRAY_BINARY = "/usr/local/bin/xray"


def _build_config_template() -> dict:
    return {
        "log": {
            "loglevel": "warning",
        },
        "inbounds": [
            {
                "port": DEFAULT_PORT,
                "protocol": "vless",
                "tag": "vless_tls",
                "settings": {"clients": [{"id": "", "flow": "xtls-rprx-vision"}], "decryption": "none"},
                "streamSettings": {
                    "network": "tcp",
                    "security": "reality",
                    "realitySettings": {
                        "show": False,
                        "dest": f"{DEFAULT_SNI}:443",
                        "xver": 0,
                        "serverNames": [DEFAULT_SNI],
                        "privateKey": "",
                        "minClientVer": "",
                        "maxClientVer": "",
                        "maxTimeDiff": 0,
                        "shortIds": [DEFAULT_SHORT_IDS],
                        "limitFallbackUpload": {
                            "afterBytes": 0,
                            "bytesPerSec": 0,
                            "burstBytesPerSec": 0,
                        },
                        "limitFallbackDownload": {
                            "afterBytes": 0,
                            "bytesPerSec": 0,
                            "burstBytesPerSec": 0,
                        },
                    },
                },
                "sniffing": {"enabled": True, "destOverride": ["http", "tls", "quic"]},
            }
        ],
        "outbounds": [{"protocol": "freedom", "tag": "direct"}, {"protocol": "blackhole", "tag": "block"}],
        "routing": {"rules": [], "domainStrategy": "AsIs"},
    }


def _is_root() -> bool:
    geteuid = getattr(os, "geteuid", None)
    if geteuid is None:
        return False
    return bool(geteuid() == 0)


CLOUDFLARE_TRACE_URL = "http://www.cloudflare.com/cdn-cgi/trace"
TRACE_TIMEOUT_SECONDS = 5.0


def _trace_via_httpx(local_address: str) -> tuple[str | None, str | None]:
    """以指定本地地址族 (0.0.0.0 → IPv4, :: → IPv6) 请求 cloudflare trace, 返回 (公网 IP, 错误信息)。"""
    transport = httpx.HTTPTransport(local_address=local_address)
    try:
        with httpx.Client(transport=transport, timeout=TRACE_TIMEOUT_SECONDS) as client:
            response = client.get(CLOUDFLARE_TRACE_URL)
    except httpx.HTTPError as exc:
        return None, f"{type(exc).__name__}: {exc}"

    if response.status_code != 200:
        return None, f"HTTP {response.status_code}: {response.text.strip()}"

    parsed: dict[str, str] = {}
    for line in response.text.strip().split("\n"):
        if "=" in line:
            key, value = line.split("=", 1)
            parsed[key] = value
    return parsed.get("ip"), None


def _detect_public_address() -> str:
    addr_v4, err_v4 = _trace_via_httpx("0.0.0.0")
    if addr_v4:
        return addr_v4
    addr_v6, err_v6 = _trace_via_httpx("::")
    if addr_v6:
        return addr_v6

    typer.echo("公网 IP 探测失败, 请使用 `--address` 显式指定。", err=True)
    if err_v4:
        typer.echo(f"IPv4 探测错误: {err_v4}", err=True)
    if err_v6:
        typer.echo(f"IPv6 探测错误: {err_v6}", err=True)
    raise typer.Exit(code=2)


XRAY_INSTALLER_URL = "https://github.com/XTLS/Xray-install/raw/main/install-release.sh"


def _run_steps(steps: list[list[str]], failure_msg: str, exit_code: int) -> None:
    for step in steps:
        result = subprocess.run(step, check=False)
        if result.returncode != 0:
            typer.echo(f"{failure_msg} (失败命令: {' '.join(step)})", err=True)
            raise typer.Exit(code=exit_code)


def _install_xray(*, yes: bool) -> None:
    if Path("/usr/bin/apt-get").exists():
        prep_steps: list[list[str]] = [
            ["apt-get", "update", "-y"],
            ["apt-get", "upgrade", "-y"],
            ["apt-get", "install", "-y", "gawk", "curl"],
        ]
    else:
        prep_steps = [
            ["yum", "update", "-y"],
            ["yum", "upgrade", "-y"],
            ["yum", "install", "-y", "epel-release"],
            ["yum", "install", "-y", "gawk", "curl"],
        ]
    _run_steps(prep_steps, "安装基础依赖失败 (gawk / curl)。", exit_code=5)

    typer.echo(f"即将下载并以 root 身份执行第三方安装脚本: {XRAY_INSTALLER_URL}")
    typer.echo("脚本内容由 XTLS/Xray-install 上游维护, 本命令不做校验。")
    if not yes and not typer.confirm("继续安装 xray?", default=False):
        typer.echo("已取消 xray 安装, 可追加 --skip-install 自行安装。", err=True)
        raise typer.Exit(code=0)

    try:
        installer = httpx.get(XRAY_INSTALLER_URL, follow_redirects=True, timeout=30).text
    except httpx.HTTPError as exc:
        typer.echo(f"下载 xray 安装脚本失败: {exc}", err=True)
        raise typer.Exit(code=5) from exc

    result = subprocess.run(["bash", "-s", "@", "install"], input=installer, text=True, check=False)
    if result.returncode != 0:
        typer.echo("Xray 安装失败。", err=True)
        raise typer.Exit(code=5)


def _generate_x25519_keys() -> tuple[str, str]:
    if not Path(XRAY_BINARY).exists():
        typer.echo(
            f"未找到 xray 可执行文件: {XRAY_BINARY}。请先安装 xray, 或追加 `--public-key` / `--private-key` 显式提供密钥。",
            err=True,
        )
        raise typer.Exit(code=3)

    result = subprocess.run([XRAY_BINARY, "x25519"], capture_output=True, text=True, check=False)
    if result.returncode != 0:
        err = "\n".join(filter(None, [(result.stderr or "").strip(), (result.stdout or "").strip()]))
        typer.echo(f"生成 x25519 密钥失败:\n{err}", err=True)
        raise typer.Exit(code=3)

    lines = [line for line in (result.stdout or "").strip().split("\n") if line.strip()]
    if len(lines) < 2:
        typer.echo(f"无法解析 xray x25519 输出:\n{result.stdout}", err=True)
        raise typer.Exit(code=3)

    private_key = lines[0].split(" ")[-1].strip()
    public_key = lines[1].split(" ")[-1].strip()
    return private_key, public_key


def _enable_xray_service() -> None:
    _run_steps(
        [
            ["systemctl", "enable", "xray.service"],
            ["systemctl", "restart", "xray.service"],
        ],
        "启用并重启 xray.service 失败。",
        exit_code=6,
    )


def _build_limit_fallback_section() -> dict:
    after_bytes = random.randint(1024 * 1024 * 1, 1024 * 1024 * 4)
    bytes_per_sec = random.randint(int(1024 * 1024 * 1 / 8), int(1024 * 1024 * 2 / 8))
    burst_factor = random.randint(10, 20) / 10
    return {
        "afterBytes": after_bytes,
        "bytesPerSec": bytes_per_sec,
        "burstBytesPerSec": int(bytes_per_sec * burst_factor),
    }


def _backup_existing_file(path: Path) -> Path | None:
    if not path.exists():
        return None
    timestamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    backup_path = path.with_name(f"{path.name}.bak.{timestamp}")
    shutil.copy2(path, backup_path)
    return backup_path


def _format_vless_url(*, uuid: str, address: str, port: int, sni: str, public_key: str, short_id: str) -> str:
    return f"vless://{uuid}@{address}:{port}?encryption=none&flow=xtls-rprx-vision&security=reality&sni={sni}&fp=chrome&pbk={public_key}&sid={short_id}&type=tcp&headerType=none"


def render_config(
    *,
    port: int,
    uuid: str,
    sni: str,
    short_id: str,
    private_key: str,
    sniff: bool,
    loglevel: str,
    access_log: str,
    error_log: str,
    limit_fallback: bool,
) -> dict:
    template = _build_config_template()
    template["log"]["loglevel"] = loglevel
    if access_log:
        template["log"]["access"] = access_log
    if error_log:
        template["log"]["error"] = error_log

    inbound = template["inbounds"][0]
    inbound["port"] = port
    inbound["sniffing"]["enabled"] = sniff
    inbound["settings"]["clients"][0]["id"] = uuid

    reality = inbound["streamSettings"]["realitySettings"]
    reality["dest"] = f"{sni}:443"
    reality["serverNames"] = [sni]
    reality["shortIds"] = [short_id]
    reality["privateKey"] = private_key

    if limit_fallback:
        reality["limitFallbackUpload"] = _build_limit_fallback_section()
        reality["limitFallbackDownload"] = _build_limit_fallback_section()

    return template


@cmd.command()
def build(
    port: int | None = typer.Option(None, help="监听端口, 缺省为 443"),
    sni: str | None = typer.Option(None, help=f"伪装目标域名 (SNI), 缺省为 {DEFAULT_SNI}"),
    sniff: bool | None = typer.Option(None, "--sniff/--no-sniff", help="是否启用 sniffing, 缺省关闭"),
    short_ids: str | None = typer.Option(None, "--short-ids", help=f"REALITY shortIds, 缺省为 {DEFAULT_SHORT_IDS}"),
    uuid: str | None = typer.Option(None, help="VLESS 客户端 UUID, 缺省自动生成"),
    public_key: str | None = typer.Option(None, "--public-key", help="REALITY 公钥, 必须与 --private-key 一同提供"),
    private_key: str | None = typer.Option(None, "--private-key", help="REALITY 私钥, 必须与 --public-key 一同提供"),
    address: str | None = typer.Option(None, help="服务器公网 IP, 缺省时通过 cloudflare/cdn-cgi/trace 自动探测"),
    loglevel: str = typer.Option("warning", help="xray 日志级别"),
    access_log: str = typer.Option(DEFAULT_ACCESS_LOG, "--access-log", help="xray access 日志路径, 留空则不写入"),
    error_log: str = typer.Option(DEFAULT_ERROR_LOG, "--error-log", help="xray error 日志路径, 留空则不写入"),
    limit_fallback: bool = typer.Option(False, "--limit-fallback/--no-limit-fallback", help="是否启用回落限速, 启用后参数随机生成"),
    config_path: Path = typer.Option(DEFAULT_CONFIG_PATH, "--config-path", help="服务端配置写入路径"),
    client_info_path: Path = typer.Option(DEFAULT_CLIENT_INFO_PATH, "--client-info-path", help="客户端信息写入路径"),
    skip_install: bool = typer.Option(False, "--skip-install", help="跳过 xray 自动安装步骤"),
    yes: bool = typer.Option(False, "--yes", "-y", help="跳过 xray 安装的二次确认 (curl-bash)"),
    skip_enable: bool = typer.Option(False, "--skip-enable", help="跳过 systemctl enable / restart 步骤"),
    dry_run: bool = typer.Option(False, "--dry-run", help="仅渲染并打印配置, 不写盘 / 不安装 / 不操作 systemd"),
    interactive: bool = typer.Option(False, "--interactive", help="缺省值时通过交互式提示补齐"),
):
    """生成 Xray REALITY 服务端配置 / 客户端信息 / vless URL。

    Usage examples::

        # 在 Linux 服务器以 root 身份生成并部署
        sudo ai-assistant reality build

        # 在 macOS 预览即将下发的配置, 不动任何文件
        ai-assistant reality build --dry-run --address 1.2.3.4 \\
            --public-key <pbk> --private-key <prv>

        # 重用已有 xray 安装, 仅刷新配置并重启服务
        sudo ai-assistant reality build --skip-install
    """
    if not dry_run and not _is_root():
        typer.echo("非 root 用户不允许执行实际部署, 请使用 sudo 或追加 `--dry-run` 仅渲染配置。", err=True)
        raise typer.Exit(code=1)

    if (public_key is None) != (private_key is None):
        raise typer.BadParameter("--public-key 与 --private-key 必须同时提供, 或同时缺省由本命令自动生成。")

    if port is None:
        port = typer.prompt("监听端口", default=DEFAULT_PORT, type=int) if interactive else DEFAULT_PORT
    if not 1 <= port <= 65535:
        raise typer.BadParameter(f"端口必须在 1-65535 之间, 收到: {port}")

    if sni is None:
        sni = typer.prompt("伪装目标域名 (SNI)", default=DEFAULT_SNI) if interactive else DEFAULT_SNI
    if sniff is None:
        sniff = typer.confirm("是否启用 sniffing?", default=False) if interactive else False
    if short_ids is None:
        short_ids = typer.prompt("REALITY shortIds", default=DEFAULT_SHORT_IDS) if interactive else DEFAULT_SHORT_IDS
    if uuid is None:
        uuid = str(uuid4())

    if not address:
        if dry_run:
            typer.echo("`--dry-run` 未提供 `--address`, 仍尝试自动探测公网 IP (避免网络调用请显式传入)。", err=True)
        address = _detect_public_address()

    if not dry_run and not skip_install:
        if Path(XRAY_BINARY).exists():
            typer.echo(f"检测到 {XRAY_BINARY}, 跳过 Xray 安装。")
        else:
            _install_xray(yes=yes)

    if private_key is None or public_key is None:
        if dry_run:
            typer.echo("`--dry-run` 未提供密钥, 跳过 x25519 生成 (输出中以占位符代替)。", err=True)
            private_key = private_key or "<dry-run-private-key>"
            public_key = public_key or "<dry-run-public-key>"
        else:
            private_key, public_key = _generate_x25519_keys()

    config = render_config(
        port=port,
        uuid=uuid,
        sni=sni,
        short_id=short_ids,
        private_key=private_key,
        sniff=sniff,
        loglevel=loglevel,
        access_log=access_log,
        error_log=error_log,
        limit_fallback=limit_fallback,
    )

    client_info = {
        "port": port,
        "address": address,
        "uuid": uuid,
        "public key": public_key,
        "sni": sni,
        "shortIds": short_ids,
    }
    vless_url = _format_vless_url(
        uuid=uuid,
        address=address,
        port=port,
        sni=sni,
        public_key=public_key,
        short_id=short_ids,
    )

    config_text = json.dumps(config, indent=4)
    client_info_text = json.dumps(client_info, indent=4)

    if dry_run:
        typer.echo("=== xray config (--dry-run) ===")
        typer.echo(config_text)
        typer.echo("")
        typer.echo("=== client info (--dry-run) ===")
        typer.echo(client_info_text)
        typer.echo("")
        typer.echo(vless_url)
        return

    config_path = config_path.expanduser()
    client_info_path = client_info_path.expanduser()
    config_path.parent.mkdir(parents=True, exist_ok=True)
    client_info_path.parent.mkdir(parents=True, exist_ok=True)

    config_backup = _backup_existing_file(config_path)
    client_info_backup = _backup_existing_file(client_info_path)
    if config_backup:
        typer.echo(f"已备份原配置: {config_backup}")
    if client_info_backup:
        typer.echo(f"已备份原客户端信息: {client_info_backup}")

    config_path.write_text(config_text)
    client_info_path.write_text(client_info_text)

    if skip_enable:
        typer.echo("已跳过 systemctl enable / restart 步骤。")
    elif platform.system() != "Linux":
        typer.echo(f"非 Linux 平台 ({platform.system()}), 跳过 systemctl 步骤。", err=True)
    else:
        _enable_xray_service()

    typer.echo(f"服务端配置: {config_path}")
    typer.echo(f"客户端配置: {client_info_path}")
    typer.echo(vless_url)
    typer.echo(client_info_text)
    typer.echo("xray 关闭: systemctl stop xray.service")
    typer.echo("xray 重启: systemctl restart xray.service")
    typer.echo("xray 状态: systemctl status xray.service")


if __name__ == "__main__":
    cmd()
