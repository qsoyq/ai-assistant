import httpx
import pytest
from typer.testing import CliRunner

from ai_assistant.commands import lan_ddns
from ai_assistant.commands.lan_ddns import (
    CloudflareError,
    cmd,
    find_ip_by_mac,
    normalize_mac,
    read_arp_table,
    resolve_zone_id,
    upsert_a_record,
)

runner = CliRunner()

_REAL_CLIENT = httpx.Client  # 真实构造器, 避免被 monkeypatch 后递归


# --------------------------------------------------------------------------- #
# normalize_mac
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize(
    "raw,expected",
    [
        ("aa:bb:cc:dd:ee:ff", "aa:bb:cc:dd:ee:ff"),
        ("AA-BB-CC-DD-EE-FF", "aa:bb:cc:dd:ee:ff"),
        ("a:b:c:1:2:3", "0a:0b:0c:01:02:03"),  # macOS arp 丢前导 0
        ("  AA:0B:cc:DD:e:ff  ", "aa:0b:cc:dd:0e:ff"),
    ],
)
def test_normalize_mac(raw, expected):
    assert normalize_mac(raw) == expected


# --------------------------------------------------------------------------- #
# read_arp_table
# --------------------------------------------------------------------------- #
def test_read_arp_table_parses_and_normalizes(monkeypatch):
    sample = "\n".join(
        [
            "gateway (192.168.1.1) at aa:bb:cc:dd:ee:ff on en0 ifscope [ethernet]",
            "? (192.168.1.5) at a:b:c:1:2:3 on en0 ifscope [ethernet]",
            "? (192.168.1.9) at (incomplete) on en0 ifscope [ethernet]",
        ]
    )

    class _Completed:
        stdout = sample

    monkeypatch.setattr(lan_ddns.subprocess, "run", lambda *a, **k: _Completed())
    table = read_arp_table()

    assert table["aa:bb:cc:dd:ee:ff"] == "192.168.1.1"
    assert table["0a:0b:0c:01:02:03"] == "192.168.1.5"  # 归一化后可命中
    assert "192.168.1.9" not in table.values()  # incomplete 被跳过


# --------------------------------------------------------------------------- #
# find_ip_by_mac
# --------------------------------------------------------------------------- #
def test_find_ip_by_mac_hit_from_arp_without_sweep(monkeypatch):
    swept: list = []
    monkeypatch.setattr(lan_ddns, "sweep", lambda net, *a, **k: swept.append(net))
    monkeypatch.setattr(lan_ddns, "read_arp_table", lambda: {"aa:bb:cc:dd:ee:ff": "192.168.1.50"})

    ip = find_ip_by_mac("AA-BB-CC-DD-EE-FF", None, "192.168.1.0/24", 1.0, 8)
    assert ip == "192.168.1.50"
    assert swept == []  # 命中即返回, 不触发扫描


def test_find_ip_by_mac_miss_default_no_sweep(monkeypatch):
    """默认 do_sweep=False: 缓存里没有就直接返回 None, 绝不扫描。"""
    swept: list = []
    monkeypatch.setattr(lan_ddns, "sweep", lambda net, *a, **k: swept.append(net))
    monkeypatch.setattr(lan_ddns, "read_arp_table", lambda: {})

    ip = find_ip_by_mac("aa:bb:cc:dd:ee:ff", None, "192.168.1.0/24", 1.0, 8)
    assert ip is None
    assert swept == []  # 关键: 默认不发任何扫描流量


def test_find_ip_by_mac_sweep_when_enabled_and_missing(monkeypatch):
    """do_sweep=True 且缓存未命中时, 才会扫描, 扫描后再读一次 ARP。"""
    swept: list = []
    tables = iter([{}, {"aa:bb:cc:dd:ee:ff": "192.168.1.60"}])
    monkeypatch.setattr(lan_ddns, "sweep", lambda net, *a, **k: swept.append(net))
    monkeypatch.setattr(lan_ddns, "read_arp_table", lambda: next(tables))

    ip = find_ip_by_mac("aa:bb:cc:dd:ee:ff", None, "192.168.1.0/24", 1.0, 8, do_sweep=True)
    assert ip == "192.168.1.60"
    assert len(swept) == 1


def test_find_ip_by_mac_skips_oversized_subnet(monkeypatch):
    swept: list = []
    monkeypatch.setattr(lan_ddns, "sweep", lambda net, *a, **k: swept.append(net))
    monkeypatch.setattr(lan_ddns, "read_arp_table", lambda: {})

    find_ip_by_mac("aa:bb:cc:dd:ee:ff", None, "10.0.0.0/16", 1.0, 8, do_sweep=True)
    assert swept == []  # 即便开启 sweep, /16 超过 1024 地址也跳过


# --------------------------------------------------------------------------- #
# Cloudflare: 用 httpx MockTransport 拦截请求
# --------------------------------------------------------------------------- #
def _client_with(handler) -> httpx.Client:
    return _REAL_CLIENT(transport=httpx.MockTransport(handler))


def test_resolve_zone_id_auto_longest_suffix():
    def handler(request):
        return httpx.Response(200, json={"success": True, "result": [{"name": "example.com", "id": "zid1"}, {"name": "sub.example.com", "id": "zid2"}]})

    with _client_with(handler) as client:
        name, zid = resolve_zone_id(client, "nas.sub.example.com", None)
    assert (name, zid) == ("sub.example.com", "zid2")


def test_resolve_zone_id_no_match_raises():
    def handler(request):
        return httpx.Response(200, json={"success": True, "result": [{"name": "other.com", "id": "z"}]})

    with _client_with(handler) as client:
        with pytest.raises(CloudflareError):
            resolve_zone_id(client, "nas.example.com", None)


def test_upsert_creates_when_absent(monkeypatch):
    calls: list[tuple[str, str]] = []

    def handler(request):
        calls.append((request.method, request.url.path))
        if request.url.path == "/client/v4/zones":
            return httpx.Response(200, json={"success": True, "result": [{"name": "example.com", "id": "zid"}]})
        if request.method == "GET":  # 查现有记录, 无
            return httpx.Response(200, json={"success": True, "result": []})
        return httpx.Response(200, json={"success": True, "result": {"id": "rec"}})  # POST 创建

    monkeypatch.setattr(httpx, "Client", lambda **kw: _client_with(handler))
    upsert_a_record("tok", "nas.example.com", "1.2.3.4", None, 1, False, dry_run=False)
    assert ("POST", "/client/v4/zones/zid/dns_records") in calls


def test_upsert_skips_when_ip_unchanged(monkeypatch):
    methods: list[str] = []

    def handler(request):
        methods.append(request.method)
        if request.url.path == "/client/v4/zones":
            return httpx.Response(200, json={"success": True, "result": [{"name": "example.com", "id": "zid"}]})
        return httpx.Response(200, json={"success": True, "result": [{"id": "rec", "content": "1.2.3.4", "proxied": False}]})

    monkeypatch.setattr(httpx, "Client", lambda **kw: _client_with(handler))
    upsert_a_record("tok", "nas.example.com", "1.2.3.4", None, 1, False, dry_run=False)
    assert "PUT" not in methods  # 内容一致, 不更新


def test_upsert_updates_when_ip_changed(monkeypatch):
    calls: list[tuple[str, str]] = []

    def handler(request):
        calls.append((request.method, request.url.path))
        if request.url.path == "/client/v4/zones":
            return httpx.Response(200, json={"success": True, "result": [{"name": "example.com", "id": "zid"}]})
        if request.method == "GET":
            return httpx.Response(200, json={"success": True, "result": [{"id": "rec", "content": "9.9.9.9", "proxied": False}]})
        return httpx.Response(200, json={"success": True, "result": {"id": "rec"}})

    monkeypatch.setattr(httpx, "Client", lambda **kw: _client_with(handler))
    upsert_a_record("tok", "nas.example.com", "1.2.3.4", None, 1, False, dry_run=False)
    assert ("PUT", "/client/v4/zones/zid/dns_records/rec") in calls


# --------------------------------------------------------------------------- #
# CLI 行为
# --------------------------------------------------------------------------- #
def test_cli_missing_token_exits_1(monkeypatch):
    monkeypatch.setattr(lan_ddns.CloudflareSettings, "api_token", None, raising=False)
    monkeypatch.setenv("CLOUDFLARE_API_TOKEN", "")
    result = runner.invoke(cmd, ["update", "-m", "aa:bb:cc:dd:ee:ff", "-d", "nas.example.com"])
    assert result.exit_code == 1


def test_cli_mac_not_found_exits_0(monkeypatch):
    monkeypatch.setattr(lan_ddns, "find_ip_by_mac", lambda *a, **k: None)
    result = runner.invoke(cmd, ["update", "-m", "aa:bb:cc:dd:ee:ff", "-d", "nas.example.com", "-t", "tok"])
    assert result.exit_code == 0  # 未匹配静默退出


def test_cli_sweep_flag_threaded(monkeypatch):
    captured: dict = {}
    monkeypatch.setattr(lan_ddns, "upsert_a_record", lambda *a, **k: None)

    def fake_find(mac, interface, subnet, timeout, workers, do_sweep=False):
        captured["do_sweep"] = do_sweep
        return "192.168.1.10"

    monkeypatch.setattr(lan_ddns, "find_ip_by_mac", fake_find)

    runner.invoke(cmd, ["update", "-m", "aa:bb:cc:dd:ee:ff", "-d", "x.example.com", "-t", "tok"])
    assert captured["do_sweep"] is False  # 默认不扫描

    runner.invoke(cmd, ["update", "-m", "aa:bb:cc:dd:ee:ff", "-d", "x.example.com", "-t", "tok", "--sweep"])
    assert captured["do_sweep"] is True


def test_cli_match_then_update(monkeypatch):
    monkeypatch.setattr(lan_ddns, "find_ip_by_mac", lambda *a, **k: "192.168.1.77")
    seen: dict = {}

    def fake_upsert(token, fqdn, ip, *a, **k):
        seen.update(token=token, fqdn=fqdn, ip=ip)

    monkeypatch.setattr(lan_ddns, "upsert_a_record", fake_upsert)
    result = runner.invoke(cmd, ["update", "-m", "aa:bb:cc:dd:ee:ff", "-d", "nas.example.com", "-t", "tok"])
    assert result.exit_code == 0
    assert seen == {"token": "tok", "fqdn": "nas.example.com", "ip": "192.168.1.77"}
