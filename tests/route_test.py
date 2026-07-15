import hashlib
import json
import struct
import sys

import pytest
import typer
from typer.testing import CliRunner

from ai_assistant.commands import _macos_rtsock, route

runner = CliRunner()


def test_parse_route_spec_normalizes_cidr_and_gateway():
    spec = route.parse_route_spec("10.1.2.3/8", "192.168.1.1", " en0 ", 20)
    assert spec.dest == "10.0.0.0/8"
    assert spec.gateway == "192.168.1.1"
    assert spec.interface == "en0"
    assert spec.metric == 20
    assert spec.family == "ipv4"
    assert spec.stable_id == route.parse_route_spec("10.0.0.0/8", "192.168.1.1", "en0", 20).stable_id


def test_parse_route_spec_rejects_missing_prefix():
    with pytest.raises(typer.BadParameter):
        route.parse_route_spec("10.0.0.0", "192.168.1.1")


def test_parse_route_spec_rejects_mismatched_family():
    with pytest.raises(typer.BadParameter):
        route.parse_route_spec("10.0.0.0/8", "2001:db8::1")


def test_linux_command_construction_ipv4():
    spec = route.parse_route_spec("10.0.0.0/8", "192.168.1.1", "eth0", 20)
    backend = route.RouteBackend(route.Platform.linux)
    assert backend.add_args(spec) == ["ip", "-4", "route", "add", "10.0.0.0/8", "via", "192.168.1.1", "dev", "eth0", "metric", "20"]
    assert backend.delete_args(spec) == ["ip", "-4", "route", "delete", "10.0.0.0/8", "via", "192.168.1.1", "dev", "eth0", "metric", "20"]
    assert backend.query_args("8.8.8.8") == ["ip", "-4", "route", "get", "8.8.8.8"]


def test_macos_command_construction_ipv6():
    spec = route.parse_route_spec("2001:db8::/32", "2001:db8::1")
    backend = route.RouteBackend(route.Platform.macos)
    assert backend.add_args(spec) == ["route", "-n", "add", "-inet6", "-net", "2001:db8::/32", "2001:db8::1"]
    assert backend.query_args("2001:4860:4860::8888") == ["route", "-n", "get", "-inet6", "2001:4860:4860::8888"]


def test_windows_command_construction_quotes_values():
    spec = route.parse_route_spec("10.0.0.0/8", "192.168.1.1", "Ethernet 2", 5)
    backend = route.RouteBackend(route.Platform.windows)
    add_args = backend.add_args(spec)
    assert add_args[:3] == ["powershell", "-NoProfile", "-Command"]
    assert "New-NetRoute" in add_args[3]
    assert "-DestinationPrefix '10.0.0.0/8'" in add_args[3]
    assert "-InterfaceAlias 'Ethernet 2'" in add_args[3]
    assert "-RouteMetric 5" in add_args[3]


def test_store_upsert_load_remove_roundtrip(tmp_path):
    store = route.RouteStore(tmp_path / "routes.json")
    spec = route.parse_route_spec("10.0.0.0/8", "192.168.1.1")

    managed = store.upsert(spec)

    assert managed.id == spec.stable_id
    loaded = store.load()
    assert loaded == [managed]
    assert json.loads(store.path.read_text(encoding="utf-8"))["version"] == 1
    assert store.remove(managed.id) == managed
    assert store.load() == []


def test_macos_add_and_delete_args_include_ifscope():
    spec = route.parse_route_spec("192.0.2.10/32", "198.51.100.254", "en0")
    backend = route.RouteBackend(route.Platform.macos)
    assert backend.add_args(spec) == ["route", "-n", "add", "-inet", "-net", "192.0.2.10/32", "198.51.100.254", "-ifscope", "en0"]
    assert backend.delete_args(spec) == ["route", "-n", "delete", "-inet", "-net", "192.0.2.10/32", "198.51.100.254", "-ifscope", "en0"]


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("default", "0.0.0.0/0"),
        ("127", "127.0.0.0/8"),
        ("10", "10.0.0.0/8"),
        ("169.254", "169.254.0.0/16"),
        ("10.20/16", "10.20.0.0/16"),
        ("198.51.100/24", "198.51.100.0/24"),
        ("192.0.2.10", "192.0.2.10/32"),
        ("192.0.2.10/32", "192.0.2.10/32"),
        ("fe80::%utun0/64", "fe80::/64"),
        ("2001:db8::1", "2001:db8::1/128"),
        ("link#4", None),
        ("", None),
    ],
)
def test_normalize_macos_dest(raw, expected):
    assert route.normalize_macos_dest(raw) == expected


MACOS_NETSTAT_FIXTURE = """\
Routing tables

Internet:
Destination        Gateway            Flags               Netif Expire
default            198.51.100.254     UGScg                 en0
10.20/16           link#19            UCS                 utun9
127                127.0.0.1          UCS                   lo0
192.0.2.10/32      198.51.100.254     UGScI                 en0
192.0.2.10         link#19            UHWIig              utun9   1590
198.51.100/24      link#4             UCS                   en0
224.0.0/4          link#19            UmCSI               utun9

Internet6:
Destination                             Gateway                         Flags               Netif Expire
default                                 fe80::1%en0                     UGcg                  en0
fe80::%utun9/64                         link#19                         UcI                 utun9
"""


def test_parse_macos_netstat_fixture():
    entries = route.parse_macos_netstat(MACOS_NETSTAT_FIXTURE)
    assert route.SystemRouteEntry("0.0.0.0/0", "198.51.100.254", "UGScg", "en0") in entries
    assert route.SystemRouteEntry("10.20.0.0/16", "link#19", "UCS", "utun9") in entries
    assert route.SystemRouteEntry("127.0.0.0/8", "127.0.0.1", "UCS", "lo0") in entries
    assert route.SystemRouteEntry("192.0.2.10/32", "198.51.100.254", "UGScI", "en0") in entries
    assert route.SystemRouteEntry("192.0.2.10/32", "link#19", "UHWIig", "utun9") in entries
    assert route.SystemRouteEntry("::/0", "fe80::1%en0", "UGcg", "en0") in entries
    assert route.SystemRouteEntry("fe80::/64", "link#19", "UcI", "utun9") in entries
    assert all("Destination" != entry.dest for entry in entries)


def test_parse_linux_ip_route():
    output = "default via 192.168.1.1 dev eth0 proto dhcp metric 100\n10.0.0.0/8 via 10.0.0.1 dev eth0\n192.168.1.0/24 dev eth0 proto kernel scope link src 192.168.1.7\n"
    entries = route.parse_linux_ip_route(output)
    assert route.SystemRouteEntry("0.0.0.0/0", "192.168.1.1", "", "eth0") in entries
    assert route.SystemRouteEntry("10.0.0.0/8", "10.0.0.1", "", "eth0") in entries
    assert route.SystemRouteEntry("192.168.1.0/24", "", "", "eth0") in entries


def test_parse_windows_routes_json():
    output = (
        '[{"DestinationPrefix": "10.0.0.0/8", "NextHop": "192.168.1.1", "InterfaceAlias": "Ethernet 2"}, {"DestinationPrefix": "0.0.0.0/0", "NextHop": "192.168.1.1", "InterfaceAlias": "Ethernet 2"}]'
    )
    entries = route.parse_windows_routes(output)
    assert route.SystemRouteEntry("10.0.0.0/8", "192.168.1.1", "", "Ethernet 2") in entries
    assert len(entries) == 2
    assert route.parse_windows_routes("not json") == []


def test_route_state_detects_active_changed_missing_unknown():
    item = route.ManagedRoute("abc", "10.0.0.0/8", "192.168.1.1", None, None, "ipv4", "now")
    active = [route.SystemRouteEntry("10.0.0.0/8", "192.168.1.1", "UGSc", "en0")]
    changed_gateway = [route.SystemRouteEntry("10.0.0.0/8", "192.168.1.2", "UGSc", "en0")]
    other_dest = [route.SystemRouteEntry("0.0.0.0/0", "192.168.1.1", "UGSc", "en0")]
    assert route.route_state(item, None) is route.RouteState.unknown
    assert route.route_state(item, active) is route.RouteState.active
    assert route.route_state(item, changed_gateway) is route.RouteState.changed
    assert route.route_state(item, other_dest) is route.RouteState.missing


def test_route_state_requires_same_line_match():
    # dest 和 gateway 各自出现在不同条目时不能误报 active (旧实现的子串匹配缺陷)。
    item = route.ManagedRoute("abc", "10.0.0.0/8", "192.168.1.1", None, None, "ipv4", "now")
    entries = [
        route.SystemRouteEntry("10.0.0.0/8", "10.9.9.9", "UGSc", "utun9"),
        route.SystemRouteEntry("0.0.0.0/0", "192.168.1.1", "UGSc", "en0"),
    ]
    assert route.route_state(item, entries) is route.RouteState.changed


def test_route_state_scoped_only_entry_is_changed_for_interfaceless_route():
    # VPN 场景: 系统里只剩 interface-scoped 条目 (flags 含 I), 普通流量不会命中,
    # managed route 未指定 interface 时不能报 active。
    item = route.ManagedRoute("abc", "192.0.2.10/32", "198.51.100.254", None, None, "ipv4", "now")
    scoped = [route.SystemRouteEntry("192.0.2.10/32", "198.51.100.254", "UGScI", "en0")]
    assert route.route_state(item, scoped) is route.RouteState.changed

    bound = route.ManagedRoute("abc", "192.0.2.10/32", "198.51.100.254", "en0", None, "ipv4", "now")
    assert route.route_state(bound, scoped) is route.RouteState.active


def test_cli_help_mentions_boundary():
    result = runner.invoke(route.cmd, ["--help"])
    assert result.exit_code == 0
    assert "managed routes" in result.output
    assert "自动识别所有自定义路由" in result.output


@pytest.mark.parametrize("subcommand", ["list", "add", "delete", "query"])
def test_subcommand_help_has_examples(subcommand):
    result = runner.invoke(route.cmd, [subcommand, "--help"])
    assert result.exit_code == 0
    assert "使用示例" in result.output


def test_cli_add_dry_run_does_not_write_state(tmp_path):
    state_file = tmp_path / "routes.json"
    result = runner.invoke(route.cmd, ["add", "--dest", "10.0.0.0/8", "--gateway", "192.168.1.1", "--state-file", str(state_file), "--dry-run"])
    assert result.exit_code == 0
    assert "dry-run" in result.output
    assert not state_file.exists()


def test_cli_list_empty_state(tmp_path):
    result = runner.invoke(route.cmd, ["list", "--state-file", str(tmp_path / "missing.json")])
    assert result.exit_code == 0
    assert "No managed routes found" in result.output


def test_cli_delete_rejects_multiple_dest_matches_without_all_matching(tmp_path):
    state_file = tmp_path / "routes.json"
    store = route.RouteStore(state_file)
    store.upsert(route.parse_route_spec("10.0.0.0/8", "192.168.1.1"))
    store.upsert(route.parse_route_spec("10.0.0.0/8", "192.168.2.1"))

    result = runner.invoke(route.cmd, ["delete", "--dest", "10.0.0.0/8", "--state-file", str(state_file)])

    assert result.exit_code != 0
    assert "multiple managed routes matched" in result.output
    assert len(store.load()) == 2


def test_cli_delete_all_matching_removes_multiple_managed_routes_from_state(tmp_path):
    state_file = tmp_path / "routes.json"
    store = route.RouteStore(state_file)
    first = store.upsert(route.parse_route_spec("10.0.0.0/8", "192.168.1.1"))
    second = store.upsert(route.parse_route_spec("10.0.0.0/8", "192.168.2.1"))

    result = runner.invoke(route.cmd, ["delete", "--dest", "10.0.0.0/8", "--all-matching", "--force-state", "--state-file", str(state_file)])

    assert result.exit_code == 0, result.output
    assert first.id in result.output
    assert second.id in result.output
    assert store.load() == []


@pytest.mark.skipif(sys.platform != "linux", reason="registration smoke uses installed command on CI host")
def test_root_command_registers_route():
    from ai_assistant.commands.main import cmd as root_cmd

    result = runner.invoke(root_cmd, ["route", "add", "--dest", "10.0.0.0/8", "--gateway", "192.168.1.1", "--dry-run"])
    assert result.exit_code == 0
    assert "ip -4 route add 10.0.0.0/8 via 192.168.1.1" in result.output


def test_pack_sockaddr_in_golden():
    assert _macos_rtsock.pack_sockaddr_in("192.168.1.1") == bytes([16, 2, 0, 0, 192, 168, 1, 1]) + b"\x00" * 8


def test_build_route_message_golden():
    msg = _macos_rtsock.build_route_message(_macos_rtsock.RTM_ADD, "10.20.0.0/16", "192.168.1.1", seq=7, pid=1234)
    assert len(msg) == 140
    assert struct.unpack_from("=HBBH", msg) == (140, 5, _macos_rtsock.RTM_ADD, 0)
    flags, addrs, pid, seq = struct.unpack_from("=iiii", msg, 8)
    assert flags == 0x40000803  # RTF_UP | RTF_GATEWAY | RTF_STATIC | RTF_GLOBAL
    assert addrs == 0x7  # RTA_DST | RTA_GATEWAY | RTA_NETMASK
    assert (pid, seq) == (1234, 7)
    assert msg[36:92] == b"\x00" * 56
    assert msg[92:108] == _macos_rtsock.pack_sockaddr_in("10.20.0.0")
    assert msg[108:124] == _macos_rtsock.pack_sockaddr_in("192.168.1.1")
    assert msg[124:140] == _macos_rtsock.pack_sockaddr_in("255.255.0.0")

    delete_msg = _macos_rtsock.build_route_message(_macos_rtsock.RTM_DELETE, "10.20.0.0/16", "192.168.1.1", seq=7, pid=1234)
    assert delete_msg[3] == _macos_rtsock.RTM_DELETE
    assert delete_msg[4:] == msg[4:]


def test_build_route_message_rejects_ipv6():
    with pytest.raises(ValueError):
        _macos_rtsock.build_route_message(_macos_rtsock.RTM_ADD, "2001:db8::/32", "2001:db8::1", seq=1, pid=1)


def test_parse_route_ack_roundtrip():
    msg = _macos_rtsock.build_route_message(_macos_rtsock.RTM_ADD, "10.0.0.0/8", "192.168.1.1", seq=3, pid=1)
    assert _macos_rtsock.parse_route_ack(msg) == (_macos_rtsock.RTM_ADD, 3, 0)


def test_parse_route_spec_rejects_macos_global_with_ipv6_or_interface():
    with pytest.raises(typer.BadParameter):
        route.parse_route_spec("2001:db8::/32", "2001:db8::1", macos_global=True)
    with pytest.raises(typer.BadParameter):
        route.parse_route_spec("10.0.0.0/8", "192.168.1.1", "en0", macos_global=True)


def test_stable_id_backward_compat_and_global_variant():
    plain = route.parse_route_spec("10.0.0.0/8", "192.168.1.1")
    legacy_raw = "|".join(["10.0.0.0/8", "192.168.1.1", "", ""])
    assert plain.stable_id == hashlib.sha256(legacy_raw.encode("utf-8")).hexdigest()[:12]
    assert plain.stable_id != route.parse_route_spec("10.0.0.0/8", "192.168.1.1", macos_global=True).stable_id


def test_managed_route_legacy_json_without_macos_global(tmp_path):
    state_file = tmp_path / "routes.json"
    legacy = {
        "version": 1,
        "routes": [{"id": "abc", "dest": "10.0.0.0/8", "gateway": "192.168.1.1", "interface": None, "metric": None, "family": "ipv4", "created_at": "2026-01-01T00:00:00+00:00"}],
    }
    state_file.write_text(json.dumps(legacy), encoding="utf-8")
    loaded = route.RouteStore(state_file).load()
    assert loaded[0].macos_global is False
    assert loaded[0].spec.macos_global is False


def test_macos_global_describe_pseudo_commands():
    spec = route.parse_route_spec("10.20.0.0/16", "198.51.100.254", macos_global=True)
    backend = route.RouteBackend(route.Platform.macos)
    assert backend.describe_add(spec) == "pf-route RTM_ADD -net 10.20.0.0/16 198.51.100.254 flags=UP,GATEWAY,STATIC,GLOBAL"
    assert backend.describe_delete(spec) == "pf-route RTM_DELETE -net 10.20.0.0/16 198.51.100.254 flags=UP,GATEWAY,STATIC,GLOBAL"
    plain = route.parse_route_spec("10.20.0.0/16", "198.51.100.254")
    assert backend.describe_add(plain) == "route -n add -inet -net 10.20.0.0/16 198.51.100.254"


def test_route_state_macos_global_active_without_global_flag():
    # 实测内核会忽略非 scoped 路由上的 RTF_GLOBAL 标志 (netstat 无 g),
    # 只要存在非 scoped 的同 dest+gateway 条目就应视为 active。
    item = route.ManagedRoute("abc", "10.20.0.0/16", "198.51.100.254", None, None, "ipv4", "now", macos_global=True)
    unscoped = [route.SystemRouteEntry("10.20.0.0/16", "198.51.100.254", "UGSc", "en0")]
    scoped_only = [route.SystemRouteEntry("10.20.0.0/16", "198.51.100.254", "UGScI", "en0")]
    assert route.route_state(item, unscoped) is route.RouteState.active
    assert route.route_state(item, scoped_only) is route.RouteState.changed


@pytest.mark.skipif(sys.platform != "darwin", reason="--macos-global uses the live-platform backend")
def test_cli_add_macos_global_dry_run_does_not_write_state(tmp_path):
    state_file = tmp_path / "routes.json"
    result = runner.invoke(route.cmd, ["add", "--dest", "10.20.0.0/16", "--gateway", "198.51.100.254", "--macos-global", "--state-file", str(state_file), "--dry-run"])
    assert result.exit_code == 0, result.output
    assert "pf-route RTM_ADD" in result.output
    assert not state_file.exists()


@pytest.mark.skipif(sys.platform != "darwin", reason="--macos-global uses the live-platform backend")
def test_cli_delete_macos_global_dry_run_prints_pseudo_command(tmp_path):
    state_file = tmp_path / "routes.json"
    managed = route.RouteStore(state_file).upsert(route.parse_route_spec("10.20.0.0/16", "198.51.100.254", macos_global=True))
    result = runner.invoke(route.cmd, ["delete", managed.id, "--state-file", str(state_file), "--dry-run"])
    assert result.exit_code == 0, result.output
    assert "pf-route RTM_DELETE" in result.output


@pytest.mark.skipif(sys.platform == "darwin", reason="platform guard only fires off macOS")
def test_cli_add_macos_global_rejected_off_macos():
    result = runner.invoke(route.cmd, ["add", "--dest", "10.20.0.0/16", "--gateway", "198.51.100.254", "--macos-global", "--dry-run"])
    assert result.exit_code != 0
