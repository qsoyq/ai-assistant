import json
import sys

import pytest
import typer
from typer.testing import CliRunner

from ai_assistant.commands import route

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


def test_route_state_detects_active_changed_missing_unknown():
    item = route.ManagedRoute("abc", "10.0.0.0/8", "192.168.1.1", None, None, "ipv4", "now")
    assert route.route_state(item, None) is route.RouteState.unknown
    assert route.route_state(item, "10.0.0.0/8 via 192.168.1.1") is route.RouteState.active
    assert route.route_state(item, "10.0.0.0/8 via 192.168.1.2") is route.RouteState.changed
    assert route.route_state(item, "default via 192.168.1.1") is route.RouteState.missing


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


@pytest.mark.skipif(sys.platform != "linux", reason="registration smoke uses installed command on CI host")
def test_root_command_registers_route():
    from ai_assistant.commands.main import cmd as root_cmd

    result = runner.invoke(root_cmd, ["route", "add", "--dest", "10.0.0.0/8", "--gateway", "192.168.1.1", "--dry-run"])
    assert result.exit_code == 0
    assert "ip -4 route add 10.0.0.0/8 via 192.168.1.1" in result.output
