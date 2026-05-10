import json
import os
from pathlib import Path

import pytest
import typer
from typer.testing import CliRunner

from ai_assistant.commands import reality
from ai_assistant.commands.reality import (
    _build_limit_fallback_section,
    _detect_public_address,
    _format_vless_url,
    cmd,
    render_config,
)

runner = CliRunner()


def test_render_config_substitutes_required_fields():
    config = render_config(
        port=8443,
        uuid="11111111-2222-3333-4444-555555555555",
        sni="www.example.com",
        short_id="abcd",
        private_key="priv-key-value",
        sniff=True,
        loglevel="info",
        access_log="/var/log/xray/access.log",
        error_log="/var/log/xray/error.log",
        limit_fallback=False,
    )

    inbound = config["inbounds"][0]
    assert inbound["port"] == 8443
    assert inbound["sniffing"]["enabled"] is True
    assert inbound["settings"]["clients"][0]["id"] == "11111111-2222-3333-4444-555555555555"
    assert inbound["settings"]["clients"][0]["flow"] == "xtls-rprx-vision"

    reality = inbound["streamSettings"]["realitySettings"]
    assert reality["dest"] == "www.example.com:443"
    assert reality["serverNames"] == ["www.example.com"]
    assert reality["shortIds"] == ["abcd"]
    assert reality["privateKey"] == "priv-key-value"
    assert reality["limitFallbackUpload"] == {"afterBytes": 0, "bytesPerSec": 0, "burstBytesPerSec": 0}
    assert reality["limitFallbackDownload"] == {"afterBytes": 0, "bytesPerSec": 0, "burstBytesPerSec": 0}

    assert config["log"]["loglevel"] == "info"
    assert config["log"]["access"] == "/var/log/xray/access.log"
    assert config["log"]["error"] == "/var/log/xray/error.log"


def test_render_config_omits_log_paths_when_empty():
    config = render_config(
        port=443,
        uuid="u",
        sni="www.amazon.com",
        short_id="88",
        private_key="p",
        sniff=False,
        loglevel="warning",
        access_log="",
        error_log="",
        limit_fallback=False,
    )

    assert "access" not in config["log"]
    assert "error" not in config["log"]


def test_render_config_with_limit_fallback_inserts_random_values():
    config = render_config(
        port=443,
        uuid="u",
        sni="www.amazon.com",
        short_id="88",
        private_key="p",
        sniff=False,
        loglevel="warning",
        access_log="",
        error_log="",
        limit_fallback=True,
    )

    reality = config["inbounds"][0]["streamSettings"]["realitySettings"]
    for key in ("limitFallbackUpload", "limitFallbackDownload"):
        section = reality[key]
        assert 1024 * 1024 <= section["afterBytes"] <= 1024 * 1024 * 4
        assert int(1024 * 1024 / 8) <= section["bytesPerSec"] <= int(1024 * 1024 * 2 / 8)
        assert section["burstBytesPerSec"] >= section["bytesPerSec"]


def test_build_limit_fallback_section_values_in_range():
    for _ in range(50):
        section = _build_limit_fallback_section()
        assert 1024 * 1024 <= section["afterBytes"] <= 1024 * 1024 * 4
        assert int(1024 * 1024 / 8) <= section["bytesPerSec"] <= int(1024 * 1024 * 2 / 8)
        assert section["burstBytesPerSec"] >= section["bytesPerSec"]


def test_format_vless_url_contains_required_query_params():
    url = _format_vless_url(
        uuid="u-uuid",
        address="1.2.3.4",
        port=8443,
        sni="www.example.com",
        public_key="pub-key",
        short_id="ab",
    )

    assert url.startswith("vless://u-uuid@1.2.3.4:8443?")
    for fragment in (
        "encryption=none",
        "flow=xtls-rprx-vision",
        "security=reality",
        "sni=www.example.com",
        "fp=chrome",
        "pbk=pub-key",
        "sid=ab",
        "type=tcp",
        "headerType=none",
    ):
        assert fragment in url


def test_build_dry_run_renders_full_config_without_writing(tmp_path: Path):
    config_path = tmp_path / "config.json"
    client_info_path = tmp_path / "reclient.json"

    result = runner.invoke(
        cmd,
        [
            "build",
            "--dry-run",
            "--address",
            "1.2.3.4",
            "--port",
            "8443",
            "--sni",
            "www.example.com",
            "--short-ids",
            "ab",
            "--uuid",
            "11111111-2222-3333-4444-555555555555",
            "--public-key",
            "pub-key-value",
            "--private-key",
            "priv-key-value",
            "--config-path",
            str(config_path),
            "--client-info-path",
            str(client_info_path),
        ],
    )

    assert result.exit_code == 0, result.output
    assert not config_path.exists()
    assert not client_info_path.exists()

    output = result.output
    assert '"port": 8443' in output
    assert '"www.example.com:443"' in output
    assert '"privateKey": "priv-key-value"' in output
    assert '"shortIds": [' in output
    assert '"ab"' in output
    assert "vless://11111111-2222-3333-4444-555555555555@1.2.3.4:8443" in output
    assert "pbk=pub-key-value" in output
    assert "sid=ab" in output


def test_build_dry_run_emits_valid_json_blocks(tmp_path: Path):
    result = runner.invoke(
        cmd,
        [
            "build",
            "--dry-run",
            "--address",
            "1.2.3.4",
            "--uuid",
            "abc",
            "--public-key",
            "pub",
            "--private-key",
            "prv",
        ],
    )

    assert result.exit_code == 0, result.output
    config_block = result.output.split("=== xray config (--dry-run) ===", 1)[1]
    config_block = config_block.split("=== client info (--dry-run) ===", 1)[0].strip()
    config = json.loads(config_block)

    assert config["inbounds"][0]["settings"]["clients"][0]["id"] == "abc"
    assert config["inbounds"][0]["streamSettings"]["realitySettings"]["privateKey"] == "prv"


def test_build_rejects_only_one_key_provided():
    result = runner.invoke(
        cmd,
        [
            "build",
            "--dry-run",
            "--address",
            "1.2.3.4",
            "--public-key",
            "pub-only",
        ],
    )

    assert result.exit_code != 0
    assert "public-key" in result.output.lower() or "private-key" in result.output.lower()


def test_build_rejects_invalid_port():
    result = runner.invoke(
        cmd,
        [
            "build",
            "--dry-run",
            "--address",
            "1.2.3.4",
            "--port",
            "70000",
            "--public-key",
            "pub",
            "--private-key",
            "prv",
        ],
    )

    assert result.exit_code != 0


def test_build_uses_placeholder_keys_in_dry_run_when_keys_omitted():
    result = runner.invoke(
        cmd,
        [
            "build",
            "--dry-run",
            "--address",
            "1.2.3.4",
            "--uuid",
            "fixed-uuid",
        ],
    )

    assert result.exit_code == 0, result.output
    assert "<dry-run-private-key>" in result.output
    assert "<dry-run-public-key>" in result.output


def test_build_limit_fallback_flag_populates_random_values():
    result = runner.invoke(
        cmd,
        [
            "build",
            "--dry-run",
            "--address",
            "1.2.3.4",
            "--uuid",
            "abc",
            "--public-key",
            "pub",
            "--private-key",
            "prv",
            "--limit-fallback",
        ],
    )

    assert result.exit_code == 0, result.output
    config_block = result.output.split("=== xray config (--dry-run) ===", 1)[1]
    config_block = config_block.split("=== client info (--dry-run) ===", 1)[0].strip()
    reality = json.loads(config_block)["inbounds"][0]["streamSettings"]["realitySettings"]

    for key in ("limitFallbackUpload", "limitFallbackDownload"):
        section = reality[key]
        assert section["afterBytes"] > 0
        assert section["bytesPerSec"] > 0
        assert section["burstBytesPerSec"] >= section["bytesPerSec"]


def test_detect_public_address_reports_failures_from_both_families(monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]):
    calls: list[str] = []

    def fake_trace(local_address: str) -> tuple[str | None, str | None]:
        calls.append(local_address)
        return None, f"boom-on-{local_address}"

    monkeypatch.setattr(reality, "_trace_via_httpx", fake_trace)

    with pytest.raises(typer.Exit) as exc_info:
        _detect_public_address()

    assert exc_info.value.exit_code == 2
    assert calls == ["0.0.0.0", "::"]
    captured = capsys.readouterr()
    assert "公网 IP 探测失败" in captured.err
    assert "boom-on-0.0.0.0" in captured.err
    assert "boom-on-::" in captured.err


def test_detect_public_address_returns_ipv6_when_ipv4_fails(monkeypatch: pytest.MonkeyPatch):
    def fake_trace(local_address: str) -> tuple[str | None, str | None]:
        if local_address == "0.0.0.0":
            return None, "ipv4-down"
        return "2606:4700:4700::1111", None

    monkeypatch.setattr(reality, "_trace_via_httpx", fake_trace)
    assert _detect_public_address() == "2606:4700:4700::1111"


def test_build_non_root_non_dry_run_errors(tmp_path: Path):
    if os.geteuid() == 0:
        pytest.skip("test asserts non-root rejection; running as root")

    config_path = tmp_path / "config.json"
    client_info_path = tmp_path / "reclient.json"

    result = runner.invoke(
        cmd,
        [
            "build",
            "--address",
            "1.2.3.4",
            "--public-key",
            "pub",
            "--private-key",
            "prv",
            "--skip-install",
            "--skip-enable",
            "--config-path",
            str(config_path),
            "--client-info-path",
            str(client_info_path),
        ],
    )

    assert result.exit_code == 1
    assert "root" in result.output.lower()
    assert not config_path.exists()
    assert not client_info_path.exists()
