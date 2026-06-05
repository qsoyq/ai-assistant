import httpx
import pytest
from typer.testing import CliRunner

from ai_assistant.commands import cloudflare_dns
from ai_assistant.commands.cloudflare_dns import (
    CloudflareError,
    DnsRecordType,
    cmd,
    resolve_zone_id,
    upsert_dns_record,
)

runner = CliRunner()

_REAL_CLIENT = httpx.Client


def _client_with(handler) -> httpx.Client:
    return _REAL_CLIENT(transport=httpx.MockTransport(handler))


def test_resolve_zone_id_auto_longest_suffix():
    def handler(request):
        return httpx.Response(200, json={"success": True, "result": [{"name": "example.com", "id": "zid1"}, {"name": "sub.example.com", "id": "zid2"}]})

    with _client_with(handler) as client:
        name, zid = resolve_zone_id(client, "nas.sub.example.com", None)
    assert (name, zid) == ("sub.example.com", "zid2")


def test_resolve_zone_id_explicit_zone_not_found_raises():
    def handler(request):
        return httpx.Response(200, json={"success": True, "result": [{"name": "example.com", "id": "zid"}]})

    with _client_with(handler) as client:
        with pytest.raises(CloudflareError):
            resolve_zone_id(client, "nas.example.com", "missing.com")


def test_upsert_a_creates_when_absent(monkeypatch):
    calls: list[tuple[str, str]] = []

    def handler(request):
        calls.append((request.method, request.url.path))
        if request.url.path == "/client/v4/zones":
            return httpx.Response(200, json={"success": True, "result": [{"name": "example.com", "id": "zid"}]})
        if request.method == "GET":
            assert request.url.params["type"] == "A"
            assert request.url.params["name"] == "nas.example.com"
            return httpx.Response(200, json={"success": True, "result": []})
        return httpx.Response(200, json={"success": True, "result": {"id": "rec"}})

    monkeypatch.setattr(httpx, "Client", lambda **kw: _client_with(handler))
    upsert_dns_record("tok", DnsRecordType.A, "nas.example.com", "1.2.3.4", None, 1, False, dry_run=False)
    assert ("POST", "/client/v4/zones/zid/dns_records") in calls


def test_upsert_cname_updates_when_content_changed(monkeypatch):
    calls: list[tuple[str, str]] = []

    def handler(request):
        calls.append((request.method, request.url.path))
        if request.url.path == "/client/v4/zones":
            return httpx.Response(200, json={"success": True, "result": [{"name": "example.com", "id": "zid"}]})
        if request.method == "GET":
            assert request.url.params["type"] == "CNAME"
            return httpx.Response(200, json={"success": True, "result": [{"id": "rec", "content": "old.example.com", "proxied": False, "ttl": 1}]})
        return httpx.Response(200, json={"success": True, "result": {"id": "rec"}})

    monkeypatch.setattr(httpx, "Client", lambda **kw: _client_with(handler))
    upsert_dns_record("tok", DnsRecordType.CNAME, "www.example.com", "target.example.com", None, 1, False, dry_run=False)
    assert ("PUT", "/client/v4/zones/zid/dns_records/rec") in calls


def test_upsert_skips_when_record_unchanged(monkeypatch):
    methods: list[str] = []

    def handler(request):
        methods.append(request.method)
        if request.url.path == "/client/v4/zones":
            return httpx.Response(200, json={"success": True, "result": [{"name": "example.com", "id": "zid"}]})
        return httpx.Response(200, json={"success": True, "result": [{"id": "rec", "content": "1.2.3.4", "proxied": False, "ttl": 1}]})

    monkeypatch.setattr(httpx, "Client", lambda **kw: _client_with(handler))
    upsert_dns_record("tok", DnsRecordType.A, "nas.example.com", "1.2.3.4", None, 1, False, dry_run=False)
    assert "PUT" not in methods
    assert "POST" not in methods


def test_upsert_dry_run_does_not_write(monkeypatch):
    methods: list[str] = []

    def handler(request):
        methods.append(request.method)
        if request.url.path == "/client/v4/zones":
            return httpx.Response(200, json={"success": True, "result": [{"name": "example.com", "id": "zid"}]})
        if request.method == "GET":
            return httpx.Response(200, json={"success": True, "result": []})
        raise AssertionError("dry-run should not write")

    monkeypatch.setattr(httpx, "Client", lambda **kw: _client_with(handler))
    upsert_dns_record("tok", DnsRecordType.A, "nas.example.com", "1.2.3.4", None, 1, False, dry_run=True)
    assert methods == ["GET", "GET"]


def test_cli_missing_token_exits_1(monkeypatch):
    monkeypatch.setattr(cloudflare_dns.CloudflareSettings, "api_token", None, raising=False)
    monkeypatch.setenv("CLOUDFLARE_API_TOKEN", "")
    result = runner.invoke(cmd, ["a", "-n", "nas.example.com", "-i", "1.2.3.4"])
    assert result.exit_code == 1


def test_cli_a_record_calls_upsert(monkeypatch):
    seen: dict = {}

    def fake_upsert(token, record_type, name, content, zone, ttl, proxied, dry_run):
        seen.update(token=token, record_type=record_type, name=name, content=content, zone=zone, ttl=ttl, proxied=proxied, dry_run=dry_run)

    monkeypatch.setattr(cloudflare_dns, "upsert_dns_record", fake_upsert)
    result = runner.invoke(cmd, ["a", "-n", "nas.example.com", "-i", "1.2.3.4", "-t", "tok", "-z", "example.com", "--proxied", "--dry-run"])
    assert result.exit_code == 0
    assert seen == {
        "token": "tok",
        "record_type": DnsRecordType.A,
        "name": "nas.example.com",
        "content": "1.2.3.4",
        "zone": "example.com",
        "ttl": 1,
        "proxied": True,
        "dry_run": True,
    }


def test_cli_cname_record_calls_upsert(monkeypatch):
    seen: dict = {}

    def fake_upsert(token, record_type, name, content, *a, **k):
        seen.update(token=token, record_type=record_type, name=name, content=content)

    monkeypatch.setattr(cloudflare_dns, "upsert_dns_record", fake_upsert)
    result = runner.invoke(cmd, ["cname", "-n", "www.example.com", "-c", "target.example.com", "-t", "tok"])
    assert result.exit_code == 0
    assert seen == {"token": "tok", "record_type": DnsRecordType.CNAME, "name": "www.example.com", "content": "target.example.com"}


def test_cli_generic_upsert_calls_upsert(monkeypatch):
    seen: dict = {}

    def fake_upsert(token, record_type, name, content, *a, **k):
        seen.update(token=token, record_type=record_type, name=name, content=content)

    monkeypatch.setattr(cloudflare_dns, "upsert_dns_record", fake_upsert)
    result = runner.invoke(cmd, ["upsert", "--type", "cname", "-n", "www.example.com", "-c", "target.example.com", "-t", "tok"])
    assert result.exit_code == 0
    assert seen == {"token": "tok", "record_type": DnsRecordType.CNAME, "name": "www.example.com", "content": "target.example.com"}
