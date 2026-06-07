import httpx
import pytest
from typer.testing import CliRunner

from ai_assistant.commands import cloudflare_dns
from ai_assistant.commands.cloudflare_dns import (
    CloudflareError,
    DnsRecordType,
    cmd,
    list_dns_records,
    resolve_explicit_zone_id,
    resolve_zone_id,
    upsert_dns_record,
)

runner = CliRunner()

_REAL_CLIENT = httpx.Client


def _client_with(handler) -> httpx.Client:
    return _REAL_CLIENT(transport=httpx.MockTransport(handler))


def _zone_response() -> httpx.Response:
    return httpx.Response(200, json={"success": True, "result": [{"name": "example.com", "id": "zid"}]})


def _records_response(records: list[dict], page: int = 1, total_pages: int = 1) -> httpx.Response:
    return httpx.Response(200, json={"success": True, "result": records, "result_info": {"page": page, "total_pages": total_pages}})


def _record(record_id: str, record_type: str, name: str, content: str) -> dict:
    return {"id": record_id, "type": record_type, "name": name, "content": content, "ttl": 1, "proxied": False}


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


def test_resolve_explicit_zone_id_requires_zone_match():
    def handler(request):
        return _zone_response()

    with _client_with(handler) as client:
        assert resolve_explicit_zone_id(client, "example.com") == ("example.com", "zid")
        with pytest.raises(CloudflareError):
            resolve_explicit_zone_id(client, "missing.com")


def test_list_dns_records_fetches_with_filters_and_prints(monkeypatch, capsys):
    calls: list[httpx.Request] = []

    def handler(request):
        calls.append(request)
        if request.url.path == "/client/v4/zones":
            return _zone_response()
        assert request.url.path == "/client/v4/zones/zid/dns_records"
        assert request.url.params["type"] == "A"
        assert request.url.params["name"] == "nas.example.com"
        assert request.url.params["content"] == "1.2.3.4"
        assert request.url.params["page"] == "1"
        assert request.url.params["per_page"] == "100"
        return _records_response([_record("rec", "A", "nas.example.com", "1.2.3.4")])

    monkeypatch.setattr(httpx, "Client", lambda **kw: _client_with(handler))
    list_dns_records("tok", "example.com", DnsRecordType.A, "nas.example.com", "1.2.3.4", None, delete=False, dry_run=False)
    out = capsys.readouterr().out
    assert "找到 1 条 DNS 记录" in out
    assert "A nas.example.com -> 1.2.3.4" in out
    assert [request.method for request in calls] == ["GET", "GET"]


def test_list_dns_records_handles_pagination(monkeypatch, capsys):
    pages: list[str] = []

    def handler(request):
        if request.url.path == "/client/v4/zones":
            return _zone_response()
        pages.append(request.url.params["page"])
        if request.url.params["page"] == "1":
            return _records_response([_record("rec1", "A", "one.example.com", "1.1.1.1")], page=1, total_pages=2)
        return _records_response([_record("rec2", "A", "two.example.com", "2.2.2.2")], page=2, total_pages=2)

    monkeypatch.setattr(httpx, "Client", lambda **kw: _client_with(handler))
    list_dns_records("tok", "example.com", DnsRecordType.A, None, None, None, delete=False, dry_run=False)
    out = capsys.readouterr().out
    assert pages == ["1", "2"]
    assert "one.example.com" in out
    assert "two.example.com" in out


def test_list_dns_records_search_filters_name_or_content(monkeypatch, capsys):
    def handler(request):
        if request.url.path == "/client/v4/zones":
            return _zone_response()
        return _records_response(
            [
                _record("rec1", "A", "nas.example.com", "1.2.3.4"),
                _record("rec2", "CNAME", "www.example.com", "old-target.example.net"),
                _record("rec3", "A", "api.example.com", "5.6.7.8"),
            ]
        )

    monkeypatch.setattr(httpx, "Client", lambda **kw: _client_with(handler))
    list_dns_records("tok", "example.com", None, None, None, "old-target", delete=False, dry_run=False)
    out = capsys.readouterr().out
    assert "www.example.com" in out
    assert "nas.example.com" not in out
    assert "api.example.com" not in out


def test_list_dns_records_delete_dry_run_does_not_delete(monkeypatch, capsys):
    methods: list[str] = []

    def handler(request):
        methods.append(request.method)
        if request.url.path == "/client/v4/zones":
            return _zone_response()
        if request.method == "GET":
            return _records_response([_record("rec", "CNAME", "old.example.com", "target.example.com")])
        raise AssertionError("dry-run should not delete")

    monkeypatch.setattr(httpx, "Client", lambda **kw: _client_with(handler))
    list_dns_records("tok", "example.com", DnsRecordType.CNAME, None, None, "old", delete=True, dry_run=True)
    out = capsys.readouterr().out
    assert "[dry-run] 将删除" in out
    assert methods == ["GET", "GET"]


def test_list_dns_records_delete_filtered_records(monkeypatch, capsys):
    calls: list[tuple[str, str]] = []

    def handler(request):
        calls.append((request.method, request.url.path))
        if request.url.path == "/client/v4/zones":
            return _zone_response()
        if request.method == "GET":
            return _records_response([_record("rec", "A", "nas.example.com", "1.2.3.4")])
        if request.method == "DELETE":
            return httpx.Response(200, json={"success": True, "result": {"id": "rec"}})
        raise AssertionError(f"unexpected request: {request.method} {request.url}")

    monkeypatch.setattr(httpx, "Client", lambda **kw: _client_with(handler))
    list_dns_records("tok", "example.com", DnsRecordType.A, "nas.example.com", None, None, delete=True, dry_run=False)
    out = capsys.readouterr().out
    assert "已删除" in out
    assert ("DELETE", "/client/v4/zones/zid/dns_records/rec") in calls


def test_list_dns_records_delete_without_filters_raises(monkeypatch):
    def fail_client(**kw):
        raise AssertionError("should not create client when delete has no filters")

    monkeypatch.setattr(httpx, "Client", fail_client)
    with pytest.raises(CloudflareError):
        list_dns_records("tok", "example.com", None, None, None, None, delete=True, dry_run=False)


def test_cli_list_calls_list_records(monkeypatch):
    seen: dict = {}

    def fake_list(token, zone, record_type, name, content, search, delete, dry_run):
        seen.update(token=token, zone=zone, record_type=record_type, name=name, content=content, search=search, delete=delete, dry_run=dry_run)

    monkeypatch.setattr(cloudflare_dns, "list_dns_records", fake_list)
    result = runner.invoke(cmd, ["list", "-z", "example.com", "--type", "cname", "-n", "www.example.com", "-c", "target.example.com", "--search", "target", "--delete", "--dry-run", "-t", "tok"])
    assert result.exit_code == 0
    assert seen == {
        "token": "tok",
        "zone": "example.com",
        "record_type": DnsRecordType.CNAME,
        "name": "www.example.com",
        "content": "target.example.com",
        "search": "target",
        "delete": True,
        "dry_run": True,
    }


def test_cli_list_delete_without_filters_exits_1(monkeypatch):
    monkeypatch.setattr(cloudflare_dns.CloudflareSettings, "api_token", None, raising=False)
    result = runner.invoke(cmd, ["list", "-z", "example.com", "--delete", "-t", "tok"])
    assert result.exit_code == 1
    assert "拒绝删除" in result.output


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
