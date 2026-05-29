import ipaddress
import re
import socket
import subprocess
import time
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from datetime import datetime

import httpx
import psutil
import rich
import typer

from ai_assistant.commands import make_typer
from ai_assistant.settings import CloudflareSettings

helptext = """
根据局域网设备的 MAC 地址定位其 IP, 并更新 Cloudflare 上的 A 记录 (DDNS)
"""

cmd = make_typer(helptext)

CLOUDFLARE_API = "https://api.cloudflare.com/client/v4"
_ARP_RE = re.compile(r"\(([\d.]+)\)\s+at\s+([0-9a-fA-F:]+)")


def _now() -> str:
    return datetime.now().strftime(r"%Y-%m-%d %H:%M:%S")


def _echo(msg: str) -> None:
    rich.print(f"[{_now()}] {msg}")


def normalize_mac(mac: str) -> str:
    """归一化 MAC: 小写, `-` 转 `:`, 每段补足两位 (macOS arp 会丢前导 0)。"""
    parts = mac.strip().lower().replace("-", ":").split(":")
    return ":".join(p.zfill(2) for p in parts)


# --------------------------------------------------------------------------- #
# 局域网设备发现
# --------------------------------------------------------------------------- #
def detect_networks(interface: str | None) -> list[tuple[str, str, ipaddress.IPv4Network]]:
    """返回 [(网卡名, 本机IP, 所在网段)] 列表, 跳过回环与链路本地地址。"""
    result: list[tuple[str, str, ipaddress.IPv4Network]] = []
    for name, infos in psutil.net_if_addrs().items():
        if interface and name != interface:
            continue
        for info in infos:
            if info.family != socket.AF_INET or not info.netmask:
                continue
            if info.address.startswith(("127.", "169.254.")):
                continue
            try:
                net = ipaddress.ip_network(f"{info.address}/{info.netmask}", strict=False)
            except ValueError:
                continue
            if isinstance(net, ipaddress.IPv4Network):
                result.append((name, info.address, net))
    return result


def _ping(ip: str, timeout: float) -> None:
    """发一个 ICMP 探测把邻居塞进 ARP 缓存; 结果不重要, 故忽略返回值。"""
    try:
        subprocess.run(
            ["ping", "-c", "1", ip],
            timeout=timeout,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
    except (subprocess.TimeoutExpired, OSError):
        pass


def sweep(net: ipaddress.IPv4Network, timeout: float, workers: int) -> None:
    """并发 ping 整个网段, 触发 ARP 解析。"""
    hosts = [str(ip) for ip in net.hosts()]
    with ThreadPoolExecutor(max_workers=workers) as pool:
        list(pool.map(lambda ip: _ping(ip, timeout), hosts))


def read_arp_table() -> dict[str, str]:
    """解析系统 ARP 表, 返回 {归一化MAC: IP}。"""
    table: dict[str, str] = {}
    try:
        out = subprocess.run(["arp", "-a"], capture_output=True, text=True, timeout=10).stdout
    except (OSError, subprocess.TimeoutExpired):
        out = ""
    for line in out.splitlines():
        if "incomplete" in line:
            continue
        m = _ARP_RE.search(line)
        if m:
            ip, mac = m.group(1), normalize_mac(m.group(2))
            table.setdefault(mac, ip)
    return table


def find_ip_by_mac(target_mac: str, interface: str | None, subnet: str | None, timeout: float, workers: int, do_sweep: bool = False) -> str | None:
    """在 ARP 表中查找目标 MAC 对应的 IP。

    默认只读本机已有的 ARP 缓存 (零网络流量); 仅当 ``do_sweep=True`` 时才
    主动 ping 扫描全网段以补全缓存 —— 在公司内网等敏感环境下需显式开启。
    """
    target = normalize_mac(target_mac)

    ip = read_arp_table().get(target)
    if ip or not do_sweep:
        return ip

    # ARP 缓存里没有, 且显式允许扫描时, 才做全网段 ping sweep 补全缓存。
    if subnet:
        nets: list[tuple[str, str, ipaddress.IPv4Network]] = [("(指定)", "", ipaddress.ip_network(subnet, strict=False))]  # type: ignore[list-item]
    else:
        nets = detect_networks(interface)
    if not nets:
        _echo("[red]未找到可用的 IPv4 网卡/网段[/red]")
        return None

    for name, _addr, net in nets:
        if net.num_addresses > 1024:
            _echo(f"[yellow]网段 {net} 过大 ({net.num_addresses} 个地址), 跳过; 请用 --subnet 指定更小范围[/yellow]")
            continue
        _echo(f"扫描 {name} {net} ...")
        sweep(net, timeout, workers)

    return read_arp_table().get(target)


# --------------------------------------------------------------------------- #
# Cloudflare DNS
# --------------------------------------------------------------------------- #
class CloudflareError(RuntimeError):
    pass


def _cf_request(client: httpx.Client, method: str, path: str, **kwargs) -> dict:
    resp = client.request(method, f"{CLOUDFLARE_API}{path}", **kwargs)
    data: dict = resp.json()
    if not data.get("success"):
        raise CloudflareError(f"Cloudflare API 错误: {data.get('errors')}")
    return data


def resolve_zone_id(client: httpx.Client, fqdn: str, zone: str | None) -> tuple[str, str]:
    """返回 (zone_name, zone_id); 未指定 zone 时按 fqdn 最长后缀自动匹配。"""
    data = _cf_request(client, "GET", "/zones", params={"per_page": 50})
    zones = {z["name"]: z["id"] for z in data["result"]}
    if zone:
        if zone not in zones:
            raise CloudflareError(f"账号下未找到 zone: {zone}")
        return zone, zones[zone]
    candidates = [name for name in zones if fqdn == name or fqdn.endswith("." + name)]
    if not candidates:
        raise CloudflareError(f"无法为 {fqdn} 自动匹配 zone, 请用 --zone 指定")
    best = max(candidates, key=len)
    return best, zones[best]


def upsert_a_record(token: str, fqdn: str, ip: str, zone: str | None, ttl: int, proxied: bool, dry_run: bool) -> None:
    headers = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}
    with httpx.Client(headers=headers, timeout=30) as client:
        zone_name, zone_id = resolve_zone_id(client, fqdn, zone)
        existing = _cf_request(client, "GET", f"/zones/{zone_id}/dns_records", params={"type": "A", "name": fqdn})["result"]
        body = {"type": "A", "name": fqdn, "content": ip, "ttl": ttl, "proxied": proxied}

        if existing:
            record = existing[0]
            if record["content"] == ip and record.get("proxied") == proxied:
                _echo(f"[green]A 记录已是最新[/green]: {fqdn} -> {ip} (zone={zone_name})")
                return
            if dry_run:
                _echo(f"[cyan][dry-run] 将更新[/cyan] {fqdn}: {record['content']} -> {ip}")
                return
            _cf_request(client, "PUT", f"/zones/{zone_id}/dns_records/{record['id']}", json=body)
            _echo(f"[green]已更新[/green] {fqdn}: {record['content']} -> {ip} (zone={zone_name})")
        else:
            if dry_run:
                _echo(f"[cyan][dry-run] 将创建[/cyan] {fqdn} -> {ip}")
                return
            _cf_request(client, "POST", f"/zones/{zone_id}/dns_records", json=body)
            _echo(f"[green]已创建[/green] {fqdn} -> {ip} (zone={zone_name})")


# --------------------------------------------------------------------------- #
# 一轮处理
# --------------------------------------------------------------------------- #
@dataclass
class RunResult:
    found: bool
    ip: str | None


def run_once(
    mac: str, domain: str, token: str, zone: str | None, subnet: str | None, interface: str | None, ttl: int, proxied: bool, ping_timeout: float, workers: int, dry_run: bool, do_sweep: bool = False
) -> RunResult:
    ip = find_ip_by_mac(mac, interface, subnet, ping_timeout, workers, do_sweep)
    if not ip:
        hint = "" if do_sweep else " (未开启 --sweep, 仅查了本机 ARP 缓存)"
        _echo(f"[yellow]未发现 MAC {normalize_mac(mac)}, 跳过本轮{hint}[/yellow]")
        return RunResult(found=False, ip=None)
    _echo(f"匹配到设备: {normalize_mac(mac)} -> {ip}")
    upsert_a_record(token, domain, ip, zone, ttl, proxied, dry_run)
    return RunResult(found=True, ip=ip)


@cmd.command()
def update(
    mac: str = typer.Option(..., "-m", "--mac", help="目标设备的 MAC 地址"),
    domain: str = typer.Option(..., "-d", "--domain", help="要更新的 A 记录 FQDN, 如 nas.example.com"),
    token: str | None = typer.Option(None, "-t", "--token", help="Cloudflare API Token, 缺省读环境变量 CLOUDFLARE_API_TOKEN"),
    zone: str | None = typer.Option(None, "-z", "--zone", help="Cloudflare zone 名, 缺省按域名自动匹配"),
    sweep_lan: bool = typer.Option(False, "--sweep/--no-sweep", help="ARP 缓存里没有时, 是否主动 ping 扫描全网段补全 (公司内网慎用, 默认关闭)"),
    subnet: str | None = typer.Option(None, "--subnet", help="--sweep 时指定扫描网段 CIDR, 如 192.168.1.0/24; 缺省自动推导"),
    interface: str | None = typer.Option(None, "--interface", help="--sweep 时限定使用的网卡名"),
    ttl: int = typer.Option(1, "--ttl", help="DNS TTL, 1 表示 auto"),
    proxied: bool = typer.Option(False, "--proxied/--no-proxied", help="是否经 Cloudflare 代理 (橙云)"),
    ping_timeout: float = typer.Option(1.0, "--ping-timeout", help="--sweep 时单个地址 ping 超时, 秒"),
    workers: int = typer.Option(64, "--workers", help="--sweep 时并发扫描线程数"),
    interval: float = typer.Option(0, "-i", "--interval", help="循环间隔秒数, 0 表示只执行一次"),
    dry_run: bool = typer.Option(False, "--dry-run", help="只打印将要执行的变更, 不真正调用 API"),
):
    """用 MAC 定位局域网设备 IP 并更新 Cloudflare A 记录

    默认只读本机 ARP 缓存 (零网络流量); 缓存里没有该 MAC 时直接跳过。
    需要主动 ping 扫描全网段来补全缓存时, 显式加 --sweep。

    使用示例:
    - 单次 (仅查 ARP): `ai-assistant lan-ddns update -m aa:bb:cc:dd:ee:ff -d nas.example.com`
    - 允许扫描:        `ai-assistant lan-ddns update -m aa:bb:cc:dd:ee:ff -d nas.example.com --sweep`
    - 守护:            `ai-assistant lan-ddns update -m aa:bb:cc:dd:ee:ff -d nas.example.com -i 300`
    """
    token = token or CloudflareSettings().api_token
    if not token:
        _echo("[red]缺少 Cloudflare API Token, 请用 --token 或设置环境变量 CLOUDFLARE_API_TOKEN[/red]")
        raise typer.Exit(1)

    def _tick() -> None:
        try:
            run_once(mac, domain, token, zone, subnet, interface, ttl, proxied, ping_timeout, workers, dry_run, sweep_lan)
        except (CloudflareError, httpx.HTTPError) as e:
            _echo(f"[red]更新失败: {e}[/red]")
            if interval <= 0:
                raise typer.Exit(1)

    if interval <= 0:
        _tick()
        return

    _echo(f"进入循环模式, 每 {interval}s 检查一次 (Ctrl+C 退出)")
    try:
        while True:
            _tick()
            time.sleep(interval)
    except KeyboardInterrupt:
        _echo("已停止")


if __name__ == "__main__":
    cmd()
