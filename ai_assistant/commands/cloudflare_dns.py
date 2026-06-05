from enum import Enum

import httpx
import rich
import typer

from ai_assistant.commands import make_typer
from ai_assistant.settings import CloudflareSettings

helptext = """
管理 Cloudflare DNS 记录, 支持添加/修改 A 和 CNAME 记录
"""

cmd = make_typer(helptext)

CLOUDFLARE_API = "https://api.cloudflare.com/client/v4"


class CloudflareError(RuntimeError):
    pass


class DnsRecordType(str, Enum):
    A = "A"
    CNAME = "CNAME"


def _echo(msg: str) -> None:
    rich.print(msg)


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


def upsert_dns_record(
    token: str,
    record_type: DnsRecordType,
    name: str,
    content: str,
    zone: str | None,
    ttl: int,
    proxied: bool,
    dry_run: bool,
) -> None:
    headers = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}
    with httpx.Client(headers=headers, timeout=30) as client:
        zone_name, zone_id = resolve_zone_id(client, name, zone)
        existing = _cf_request(client, "GET", f"/zones/{zone_id}/dns_records", params={"type": record_type.value, "name": name})["result"]
        body = {"type": record_type.value, "name": name, "content": content, "ttl": ttl, "proxied": proxied}

        if existing:
            record = existing[0]
            old_content = record.get("content")
            old_proxied = record.get("proxied")
            old_ttl = record.get("ttl")
            if old_content == content and old_proxied == proxied and old_ttl == ttl:
                _echo(f"[green]{record_type.value} 记录已是最新[/green]: {name} -> {content} (zone={zone_name})")
                return
            if dry_run:
                _echo(f"[cyan][dry-run] 将更新[/cyan] {record_type.value} {name}: {old_content} -> {content}")
                return
            _cf_request(client, "PUT", f"/zones/{zone_id}/dns_records/{record['id']}", json=body)
            _echo(f"[green]已更新[/green] {record_type.value} {name}: {old_content} -> {content} (zone={zone_name})")
            return

        if dry_run:
            _echo(f"[cyan][dry-run] 将创建[/cyan] {record_type.value} {name} -> {content}")
            return
        _cf_request(client, "POST", f"/zones/{zone_id}/dns_records", json=body)
        _echo(f"[green]已创建[/green] {record_type.value} {name} -> {content} (zone={zone_name})")


def _resolve_token(token: str | None) -> str:
    resolved = token or CloudflareSettings().api_token
    if not resolved:
        _echo("[red]缺少 Cloudflare API Token, 请用 --token 或设置环境变量 CLOUDFLARE_API_TOKEN[/red]")
        raise typer.Exit(1)
    return resolved


def _upsert_or_exit(token: str | None, record_type: DnsRecordType, name: str, content: str, zone: str | None, ttl: int, proxied: bool, dry_run: bool) -> None:
    try:
        upsert_dns_record(_resolve_token(token), record_type, name, content, zone, ttl, proxied, dry_run)
    except (CloudflareError, httpx.HTTPError) as e:
        _echo(f"[red]操作失败: {e}[/red]")
        raise typer.Exit(1) from e


@cmd.command()
def upsert(
    record_type: DnsRecordType = typer.Option(..., "--type", "-T", case_sensitive=False, help="记录类型: A 或 CNAME"),
    name: str = typer.Option(..., "--name", "-n", help="记录名/FQDN, 如 nas.example.com"),
    content: str = typer.Option(..., "--content", "-c", help="记录内容: A 为 IPv4 地址, CNAME 为目标域名"),
    token: str | None = typer.Option(None, "--token", "-t", help="Cloudflare API Token, 缺省读环境变量 CLOUDFLARE_API_TOKEN"),
    zone: str | None = typer.Option(None, "--zone", "-z", help="Cloudflare zone 名, 缺省按记录名自动匹配"),
    ttl: int = typer.Option(1, "--ttl", help="DNS TTL, 1 表示 auto"),
    proxied: bool = typer.Option(False, "--proxied/--no-proxied", help="是否经 Cloudflare 代理 (橙云)"),
    dry_run: bool = typer.Option(False, "--dry-run", help="只打印将要执行的变更, 不真正调用 API"),
):
    """添加或修改 Cloudflare DNS 记录

    使用示例:
    - A 记录:     `ai-assistant cloudflare-dns upsert --type A -n nas.example.com -c 1.2.3.4`
    - CNAME 记录: `ai-assistant cloudflare-dns upsert --type CNAME -n www.example.com -c target.example.com`
    - 指定 zone:  `ai-assistant cloudflare-dns upsert --type A -n nas.example.com -c 1.2.3.4 -z example.com`
    """
    _upsert_or_exit(token, record_type, name, content, zone, ttl, proxied, dry_run)


@cmd.command("a")
def a_record(
    name: str = typer.Option(..., "--name", "-n", help="A 记录名/FQDN, 如 nas.example.com"),
    ip: str = typer.Option(..., "--ip", "-i", help="IPv4 地址"),
    token: str | None = typer.Option(None, "--token", "-t", help="Cloudflare API Token, 缺省读环境变量 CLOUDFLARE_API_TOKEN"),
    zone: str | None = typer.Option(None, "--zone", "-z", help="Cloudflare zone 名, 缺省按记录名自动匹配"),
    ttl: int = typer.Option(1, "--ttl", help="DNS TTL, 1 表示 auto"),
    proxied: bool = typer.Option(False, "--proxied/--no-proxied", help="是否经 Cloudflare 代理 (橙云)"),
    dry_run: bool = typer.Option(False, "--dry-run", help="只打印将要执行的变更, 不真正调用 API"),
):
    """添加或修改 Cloudflare A 记录

    使用示例:
    - `ai-assistant cloudflare-dns a -n nas.example.com -i 1.2.3.4`
    - `ai-assistant cloudflare-dns a -n nas.example.com -i 1.2.3.4 --proxied`
    """
    _upsert_or_exit(token, DnsRecordType.A, name, ip, zone, ttl, proxied, dry_run)


@cmd.command("cname")
def cname_record(
    name: str = typer.Option(..., "--name", "-n", help="CNAME 记录名/FQDN, 如 www.example.com"),
    target: str = typer.Option(..., "--target", "-c", help="CNAME 目标域名, 如 target.example.com"),
    token: str | None = typer.Option(None, "--token", "-t", help="Cloudflare API Token, 缺省读环境变量 CLOUDFLARE_API_TOKEN"),
    zone: str | None = typer.Option(None, "--zone", "-z", help="Cloudflare zone 名, 缺省按记录名自动匹配"),
    ttl: int = typer.Option(1, "--ttl", help="DNS TTL, 1 表示 auto"),
    proxied: bool = typer.Option(False, "--proxied/--no-proxied", help="是否经 Cloudflare 代理 (橙云)"),
    dry_run: bool = typer.Option(False, "--dry-run", help="只打印将要执行的变更, 不真正调用 API"),
):
    """添加或修改 Cloudflare CNAME 记录

    使用示例:
    - `ai-assistant cloudflare-dns cname -n www.example.com -c target.example.com`
    - `ai-assistant cloudflare-dns cname -n www.example.com -c target.example.com --proxied`
    """
    _upsert_or_exit(token, DnsRecordType.CNAME, name, target, zone, ttl, proxied, dry_run)


if __name__ == "__main__":
    cmd()
