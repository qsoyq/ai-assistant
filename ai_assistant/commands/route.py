"""Cross-platform runtime route management helpers."""

from __future__ import annotations

import hashlib
import ipaddress
import json
import os
import shlex
import subprocess
import sys
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from enum import Enum
from pathlib import Path

import rich
import typer

from ai_assistant.commands import make_typer

helptext = """
跨平台运行时路由管理工具。

这个命令只可靠管理它自己添加过的路由规则: add 成功后会把规则写入本地
JSON 状态文件, list 默认只展示这些 managed routes, 并尽量和当前系统路由表
对比后标记 active / missing / changed / unknown。

平台实现:
- macOS: route / netstat
- Linux: ip route
- Windows: PowerShell NetTCPIP cmdlets

重要限制:
- 系统路由表没有统一字段能说明一条路由是谁添加的, 因此本工具不会声称能
  自动识别所有自定义路由。
- add / delete 通常需要管理员权限: macOS/Linux 用 sudo 运行, Windows 用
  管理员 PowerShell/CMD 运行。
- 第一版只管理运行时路由。重启后是否保留取决于系统, 本工具不会改写发行版
  网络配置、launchd、NetworkManager、netplan 或 Windows 持久策略。

示例:
- 查看本工具管理的路由:
  ai-assistant route list
- 查看系统原始路由表:
  ai-assistant route list --all-system
- 添加一条运行时路由:
  sudo ai-assistant route add --dest 10.0.0.0/8 --gateway 192.168.1.1
- 删除一条 managed route:
  sudo ai-assistant route delete <route-id>
- 查询某个 IP 的实际系统路由:
  ai-assistant route query 10.1.2.3
"""

cmd = make_typer(helptext)


class Platform(str, Enum):
    macos = "macos"
    linux = "linux"
    windows = "windows"


class RouteState(str, Enum):
    active = "active"
    missing = "missing"
    changed = "changed"
    unknown = "unknown"


@dataclass(frozen=True)
class RouteSpec:
    dest: str
    gateway: str
    interface: str | None = None
    metric: int | None = None

    @property
    def family(self) -> str:
        return "ipv6" if ipaddress.ip_network(self.dest).version == 6 else "ipv4"

    @property
    def stable_id(self) -> str:
        raw = "|".join([self.dest, self.gateway, self.interface or "", str(self.metric or "")])
        return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:12]


@dataclass(frozen=True)
class ManagedRoute:
    id: str
    dest: str
    gateway: str
    interface: str | None
    metric: int | None
    family: str
    created_at: str

    @property
    def spec(self) -> RouteSpec:
        return RouteSpec(dest=self.dest, gateway=self.gateway, interface=self.interface, metric=self.metric)


@dataclass(frozen=True)
class CommandResult:
    args: list[str]
    returncode: int
    stdout: str
    stderr: str


def detect_platform(value: str | None = None) -> Platform:
    name = value or sys.platform
    if name == "darwin":
        return Platform.macos
    if name.startswith("linux"):
        return Platform.linux
    if name == "win32":
        return Platform.windows
    raise RuntimeError(f"unsupported platform: {name}")


def parse_route_spec(dest: str, gateway: str, interface: str | None = None, metric: int | None = None) -> RouteSpec:
    if "/" not in dest:
        raise typer.BadParameter("dest must be CIDR, e.g. 10.0.0.0/8 or 2001:db8::/32")
    try:
        network = ipaddress.ip_network(dest, strict=False)
    except ValueError as exc:
        raise typer.BadParameter(f"invalid dest CIDR: {dest}") from exc
    try:
        gateway_ip = ipaddress.ip_address(gateway)
    except ValueError as exc:
        raise typer.BadParameter(f"invalid gateway IP: {gateway}") from exc
    if network.version != gateway_ip.version:
        raise typer.BadParameter("dest and gateway must use the same IP family")
    if metric is not None and metric < 0:
        raise typer.BadParameter("metric must be >= 0")
    clean_interface = interface.strip() if interface else None
    return RouteSpec(dest=str(network), gateway=str(gateway_ip), interface=clean_interface, metric=metric)


def parse_query_ip(value: str) -> ipaddress.IPv4Address | ipaddress.IPv6Address:
    try:
        return ipaddress.ip_address(value)
    except ValueError as exc:
        raise typer.BadParameter(f"invalid IP address: {value}") from exc


def default_state_file() -> Path:
    override = os.environ.get("AI_ASSISTANT_ROUTE_STATE")
    if override:
        return Path(override)
    if sys.platform == "win32":
        base = Path(os.environ.get("LOCALAPPDATA") or Path.home() / "AppData" / "Local")
        return base / "ai-assistant" / "routes.json"
    base = Path(os.environ.get("XDG_STATE_HOME") or Path.home() / ".local" / "state")
    return base / "ai-assistant" / "routes.json"


class RouteStore:
    def __init__(self, path: Path) -> None:
        self.path = path

    def load(self) -> list[ManagedRoute]:
        if not self.path.exists():
            return []
        data = json.loads(self.path.read_text(encoding="utf-8"))
        return [ManagedRoute(**item) for item in data.get("routes", [])]

    def save(self, routes: list[ManagedRoute]) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        payload = {"version": 1, "routes": [asdict(route) for route in routes]}
        self.path.write_text(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")

    def upsert(self, spec: RouteSpec) -> ManagedRoute:
        route = ManagedRoute(
            id=spec.stable_id,
            dest=spec.dest,
            gateway=spec.gateway,
            interface=spec.interface,
            metric=spec.metric,
            family=spec.family,
            created_at=datetime.now(UTC).isoformat(timespec="seconds"),
        )
        routes = [item for item in self.load() if item.id != route.id]
        routes.append(route)
        self.save(routes)
        return route

    def remove(self, route_id: str) -> ManagedRoute | None:
        routes = self.load()
        target = next((route for route in routes if route.id == route_id), None)
        if target is None:
            return None
        self.save([route for route in routes if route.id != route_id])
        return target

    def remove_many(self, route_ids: set[str]) -> list[ManagedRoute]:
        routes = self.load()
        removed = [route for route in routes if route.id in route_ids]
        if removed:
            self.save([route for route in routes if route.id not in route_ids])
        return removed


class RouteBackend:
    def __init__(self, platform: Platform | None = None) -> None:
        self.platform = platform or detect_platform()

    def add_args(self, spec: RouteSpec) -> list[str]:
        if self.platform is Platform.linux:
            args = ["ip", "-6" if spec.family == "ipv6" else "-4", "route", "add", spec.dest, "via", spec.gateway]
            if spec.interface:
                args.extend(["dev", spec.interface])
            if spec.metric is not None:
                args.extend(["metric", str(spec.metric)])
            return args
        if self.platform is Platform.macos:
            family = ["-inet6"] if spec.family == "ipv6" else ["-inet"]
            args = ["route", "-n", "add", *family, "-net", spec.dest, spec.gateway]
            if spec.interface:
                args.extend(["-ifscope", spec.interface])
            return args
        script = _windows_new_route_script(spec)
        return ["powershell", "-NoProfile", "-Command", script]

    def delete_args(self, spec: RouteSpec) -> list[str]:
        if self.platform is Platform.linux:
            args = ["ip", "-6" if spec.family == "ipv6" else "-4", "route", "delete", spec.dest, "via", spec.gateway]
            if spec.interface:
                args.extend(["dev", spec.interface])
            if spec.metric is not None:
                args.extend(["metric", str(spec.metric)])
            return args
        if self.platform is Platform.macos:
            family = ["-inet6"] if spec.family == "ipv6" else ["-inet"]
            return ["route", "-n", "delete", *family, "-net", spec.dest, spec.gateway]
        script = _windows_remove_route_script(spec)
        return ["powershell", "-NoProfile", "-Command", script]

    def query_args(self, target: str) -> list[str]:
        ip = parse_query_ip(target)
        if self.platform is Platform.linux:
            return ["ip", "-6" if ip.version == 6 else "-4", "route", "get", str(ip)]
        if self.platform is Platform.macos:
            family = ["-inet6"] if ip.version == 6 else ["-inet"]
            return ["route", "-n", "get", *family, str(ip)]
        script = f"Find-NetRoute -RemoteIPAddress {_ps_quote(str(ip))} | Format-List *"
        return ["powershell", "-NoProfile", "-Command", script]

    def show_args(self) -> list[list[str]]:
        if self.platform is Platform.linux:
            return [["ip", "-4", "route", "show"], ["ip", "-6", "route", "show"]]
        if self.platform is Platform.macos:
            return [["netstat", "-rn"]]
        script = "Get-NetRoute | Select-Object DestinationPrefix,NextHop,InterfaceAlias,RouteMetric,AddressFamily | ConvertTo-Json -Depth 2"
        return [["powershell", "-NoProfile", "-Command", script]]

    def run(self, args: list[str]) -> CommandResult:
        proc = subprocess.run(args, capture_output=True, text=True, check=False)
        return CommandResult(args=args, returncode=proc.returncode, stdout=proc.stdout, stderr=proc.stderr)

    def run_show(self) -> tuple[str | None, list[CommandResult]]:
        results = [self.run(args) for args in self.show_args()]
        if any(result.returncode != 0 for result in results):
            return None, results
        return "\n".join(result.stdout for result in results), results


def _ps_quote(value: str) -> str:
    return "'" + value.replace("'", "''") + "'"


def _windows_new_route_script(spec: RouteSpec) -> str:
    parts = ["New-NetRoute", "-DestinationPrefix", _ps_quote(spec.dest), "-NextHop", _ps_quote(spec.gateway)]
    if spec.interface:
        parts.extend(["-InterfaceAlias", _ps_quote(spec.interface)])
    if spec.metric is not None:
        parts.extend(["-RouteMetric", str(spec.metric)])
    return " ".join(parts)


def _windows_remove_route_script(spec: RouteSpec) -> str:
    parts = ["Get-NetRoute", "-DestinationPrefix", _ps_quote(spec.dest), "-NextHop", _ps_quote(spec.gateway)]
    if spec.interface:
        parts.extend(["-InterfaceAlias", _ps_quote(spec.interface)])
    return " ".join(parts) + " | Remove-NetRoute -Confirm:$false"


def route_state(route: ManagedRoute, system_routes: str | None) -> RouteState:
    if system_routes is None:
        return RouteState.unknown
    dest_seen = route.dest in system_routes
    gateway_seen = route.gateway in system_routes
    if dest_seen and gateway_seen:
        return RouteState.active
    if dest_seen:
        return RouteState.changed
    return RouteState.missing


def shell_join(args: list[str]) -> str:
    return shlex.join(args)


def _state_file_option(state_file: Path | None) -> Path:
    return state_file or default_state_file()


def _route_matches_ip(route: ManagedRoute, target: ipaddress.IPv4Address | ipaddress.IPv6Address) -> bool:
    return target in ipaddress.ip_network(route.dest)


@cmd.command("list")
def list_routes(
    all_system: bool = typer.Option(False, "--all-system", help="显示系统原始路由表。注意: 这不是 managed route 列表, 不能据此判断哪些是自定义路由。"),
    state_file: Path | None = typer.Option(None, "--state-file", help="managed route JSON 状态文件路径; 默认使用 AI_ASSISTANT_ROUTE_STATE 或用户 state 目录。"),
):
    """列出本工具管理的路由, 并尽量校验当前系统状态。

    默认只读取本工具状态文件里的 managed routes。系统路由表通常无法说明一条
    路由是谁添加的, 因此本命令不会把 VPN、Docker、DHCP、MDM 或其他工具添加的
    路由误报为 managed route。

    使用示例:
    - ai-assistant route list
    - ai-assistant route list --state-file ./routes.json
    - ai-assistant route list --all-system
    """
    backend = RouteBackend()
    if all_system:
        output, results = backend.run_show()
        if output is None:
            for result in results:
                if result.returncode != 0:
                    rich.print(f"[red]failed:[/red] {shell_join(result.args)}\n{result.stderr.strip()}")
            raise typer.Exit(1)
        typer.echo(output.rstrip())
        return

    store = RouteStore(_state_file_option(state_file))
    routes = store.load()
    if not routes:
        rich.print("[yellow]No managed routes found.[/yellow]")
        rich.print(f"State file: {store.path}")
        return

    system_routes, _results = backend.run_show()
    rich.print("ID           DEST                GATEWAY             IFACE        METRIC  STATE")
    for route in routes:
        state = route_state(route, system_routes).value
        rich.print(f"{route.id:<12} {route.dest:<19} {route.gateway:<19} {(route.interface or '-'): <12} {str(route.metric or '-'): <7} {state}")


@cmd.command()
def add(
    dest: str = typer.Option(..., "--dest", help="目标网段 CIDR, 如 10.0.0.0/8 或 2001:db8::/32。必须包含前缀长度。"),
    gateway: str = typer.Option(..., "--gateway", help="下一跳网关 IP, 必须和 --dest 使用同一地址族。"),
    interface: str | None = typer.Option(None, "--interface", "-i", help="可选出口网卡名/接口别名, 如 macOS en0、Linux eth0、Windows Ethernet。"),
    metric: int | None = typer.Option(None, "--metric", help="可选路由 metric/优先级。不同平台语义略有差异。"),
    dry_run: bool = typer.Option(False, "--dry-run", help="只打印将执行的平台命令, 不修改系统路由表, 也不写状态文件。"),
    state_file: Path | None = typer.Option(None, "--state-file", help="managed route JSON 状态文件路径。"),
):
    """添加一条运行时 managed route。

    add 成功后会写入本工具状态文件, 后续 list/delete 默认只管理这些记录。
    本命令通常需要管理员权限: macOS/Linux 建议用 sudo 运行, Windows 需要管理员
    PowerShell/CMD。

    使用示例:
    - sudo ai-assistant route add --dest 10.0.0.0/8 --gateway 192.168.1.1
    - sudo ai-assistant route add --dest 10.20.0.0/16 --gateway 192.168.1.1 --interface en0 --metric 20
    - ai-assistant route add --dest 10.0.0.0/8 --gateway 192.168.1.1 --dry-run
    """
    spec = parse_route_spec(dest=dest, gateway=gateway, interface=interface, metric=metric)
    backend = RouteBackend()
    args = backend.add_args(spec)
    if dry_run:
        rich.print(f"[cyan](dry-run)[/cyan] {shell_join(args)}")
        return
    result = backend.run(args)
    if result.returncode != 0:
        rich.print(f"[red]route add failed:[/red] {result.stderr.strip() or result.stdout.strip()}")
        raise typer.Exit(result.returncode)
    route = RouteStore(_state_file_option(state_file)).upsert(spec)
    rich.print(f"[green]added managed route[/green] {route.id}: {route.dest} via {route.gateway}")


@cmd.command()
def delete(
    route_id: str | None = typer.Argument(None, help="managed route ID, 可从 `ai-assistant route list` 获取。"),
    dest: str | None = typer.Option(None, "--dest", help="按目标网段删除 managed route; 多条匹配时请改用 route ID 或显式加 --all-matching。"),
    gateway: str | None = typer.Option(None, "--gateway", help="和 --dest 一起精确匹配下一跳网关。"),
    all_matching: bool = typer.Option(False, "--all-matching", help="当 --dest/--gateway 匹配多条 managed routes 时, 显式删除全部匹配项。"),
    unmanaged: bool = typer.Option(False, "--unmanaged", help="允许删除未记录在状态文件中的系统路由。危险选项, 必须同时提供 --dest 和 --gateway。"),
    force_state: bool = typer.Option(False, "--force-state", help="只清理状态文件中的 managed route, 不执行系统 delete。用于系统路由已手动删除的 stale 记录。"),
    dry_run: bool = typer.Option(False, "--dry-run", help="只打印将执行的平台命令, 不修改系统路由表或状态文件。"),
    state_file: Path | None = typer.Option(None, "--state-file", help="managed route JSON 状态文件路径。"),
):
    """删除一条 managed route。

    默认只删除本工具状态文件里存在的 managed route, 避免误删 VPN、Docker、公司
    MDM 或其他工具添加的系统路由。确实要删除 unmanaged route 时必须显式使用
    --unmanaged --dest ... --gateway ...。

    使用示例:
    - sudo ai-assistant route delete 7bb0e5a99a2c
    - sudo ai-assistant route delete --dest 10.0.0.0/8 --gateway 192.168.1.1
    - sudo ai-assistant route delete --dest 10.0.0.0/8 --all-matching
    - ai-assistant route delete 7bb0e5a99a2c --force-state
    - sudo ai-assistant route delete --unmanaged --dest 10.0.0.0/8 --gateway 192.168.1.1
    """
    if unmanaged and all_matching:
        raise typer.BadParameter("--all-matching only applies to managed routes")
    store = RouteStore(_state_file_option(state_file))
    managed_routes = store.load()
    routes = _select_routes_for_delete(managed_routes, route_id, dest, gateway, all_matching)

    if not routes and not unmanaged:
        rich.print("[red]No matching managed route found. Use --unmanaged with --dest and --gateway to delete an unmanaged system route.[/red]")
        raise typer.Exit(1)

    if not routes:
        if dest is None or gateway is None:
            raise typer.BadParameter("--unmanaged requires --dest and --gateway")
        routes_and_specs: list[tuple[ManagedRoute | None, RouteSpec]] = [(None, parse_route_spec(dest=dest, gateway=gateway))]
    else:
        routes_and_specs = [(route, route.spec) for route in routes]

    backend = RouteBackend()
    planned = [(route, spec, backend.delete_args(spec)) for route, spec in routes_and_specs]
    if dry_run:
        for _route, _spec, args in planned:
            rich.print(f"[cyan](dry-run)[/cyan] {shell_join(args)}")
        return

    removed_ids: set[str] = set()
    for route, spec, args in planned:
        if force_state and route is None:
            raise typer.BadParameter("--force-state only applies to managed routes")
        if not force_state:
            result = backend.run(args)
            if result.returncode != 0:
                rich.print(f"[red]route delete failed:[/red] {result.stderr.strip() or result.stdout.strip()}")
                raise typer.Exit(result.returncode)
        if route is None:
            rich.print(f"[green]deleted unmanaged system route[/green] {spec.dest} via {spec.gateway}")
        else:
            removed_ids.add(route.id)
            rich.print(f"[green]removed managed route[/green] {route.id}: {route.dest} via {route.gateway}")
    if removed_ids:
        store.remove_many(removed_ids)


def _select_routes_for_delete(routes: list[ManagedRoute], route_id: str | None, dest: str | None, gateway: str | None, all_matching: bool) -> list[ManagedRoute]:
    if route_id:
        if all_matching:
            raise typer.BadParameter("--all-matching cannot be used with route ID")
        return [route] if (route := next((route for route in routes if route.id == route_id), None)) else []
    if dest is None:
        return []
    target_dest = str(ipaddress.ip_network(dest, strict=False))
    target_gateway = str(ipaddress.ip_address(gateway)) if gateway is not None else None
    matches = [route for route in routes if route.dest == target_dest and (target_gateway is None or route.gateway == target_gateway)]
    if len(matches) > 1 and not all_matching:
        raise typer.BadParameter("multiple managed routes matched; delete by route ID or pass --all-matching")
    return matches


@cmd.command()
def query(
    ip: str = typer.Argument(..., help="要查询的目标 IP, 如 8.8.8.8 或 2001:4860:4860::8888。"),
    state_file: Path | None = typer.Option(None, "--state-file", help="managed route JSON 状态文件路径; 用于提示该 IP 是否落入某条 managed route 的目标网段。"),
):
    """查询某个 IP 当前实际匹配的系统路由。

    本命令委托系统自己的路由决策查询能力, 不在 Python 里重新实现 longest-prefix
    match。Linux 使用 `ip route get`, macOS 使用 `route -n get`, Windows 使用
    `Find-NetRoute`。

    使用示例:
    - ai-assistant route query 8.8.8.8
    - ai-assistant route query 10.1.2.3
    - ai-assistant route query 2001:4860:4860::8888
    """
    target = parse_query_ip(ip)
    backend = RouteBackend()
    result = backend.run(backend.query_args(str(target)))
    if result.returncode != 0:
        rich.print(f"[red]route query failed:[/red] {result.stderr.strip() or result.stdout.strip()}")
        raise typer.Exit(result.returncode)

    matches = [route for route in RouteStore(_state_file_option(state_file)).load() if _route_matches_ip(route, target)]
    if matches:
        rich.print("Managed route candidate(s):")
        for route in matches:
            rich.print(f"- {route.id}: {route.dest} via {route.gateway}")
        rich.print("")
    typer.echo(result.stdout.rstrip())
