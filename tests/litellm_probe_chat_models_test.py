import json
import threading
import time
from pathlib import Path

import httpx
from typer.testing import CliRunner

from ai_assistant.commands import main as root_commands
from ai_assistant.commands.litellm.probe_chat_models import ProbeResponse, cmd, result

runner = CliRunner()
_REAL_CLIENT = httpx.Client


def _client_with(handler):
    return _REAL_CLIENT(transport=httpx.MockTransport(handler))


def test_root_help_lists_litellm():
    result = runner.invoke(root_commands.cmd, ["--help"])
    assert result.exit_code == 0, result.output
    assert "litellm" in result.output


def test_probe_filters_retries_and_redacts(monkeypatch, tmp_path: Path):
    calls: list[tuple[str, str]] = []
    attempts = {"temporary": 0}
    active = 0
    max_active = 0
    lock = threading.Lock()

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal active, max_active
        with lock:
            active += 1
            max_active = max(max_active, active)
        time.sleep(0.005)
        calls.append((request.method, request.url.path))
        try:
            if request.url.path == "/v1/models":
                return httpx.Response(
                    200,
                    json={
                        "data": [
                            {"id": "chat-model"},
                            {"id": "embedding-model"},
                            {"id": "passthrough-model", "metadata": {"endpoint_type": "passthrough", "secret": "do-not-report"}},
                            {"id": "temporary-model"},
                        ]
                    },
                )
            payload = json.loads(request.content)
            if payload["model"] == "temporary-model":
                attempts["temporary"] += 1
                if attempts["temporary"] == 1:
                    return httpx.Response(500, json={"error": {"message": "upstream-key=secret-token"}})
            if payload["model"] == "chat-model" and request.url.path == "/v1/chat/completions":
                return httpx.Response(404, json={"error": {"message": "route missing"}})
            if payload.get("reasoning_effort") not in (None, "low"):
                return httpx.Response(400, json={"error": {"message": "unsupported effort"}})
            return httpx.Response(200, json={"id": "ok"})
        finally:
            with lock:
                active -= 1

    monkeypatch.setattr(httpx, "Client", lambda: _client_with(handler))
    result = runner.invoke(
        cmd,
        [
            "--base-url",
            "https://gateway.example.invalid/v1",
            "--api-key",
            "secret-token",
            "--retries",
            "1",
            "--concurrency",
            "2",
            "--reasoning-levels",
            "low,high",
            "--output-dir",
            str(tmp_path),
        ],
    )

    assert result.exit_code == 0, result.output
    report = json.loads((tmp_path / "model-capabilities.json").read_text())
    assert report["summary"] == {"listed": 4, "excluded": 2, "chatCandidates": 2, "chatSupported": 2}
    assert report["source"] == {"wireApi": "auto", "concurrency": 2, "timeout": 30.0, "reasoningLevels": ["low", "high"]}
    temporary = next(item for item in report["models"] if item["id"] == "temporary-model")
    assert attempts["temporary"] >= 2
    assert temporary["chat"]["status"] == "accepted"
    assert (tmp_path / "model-capabilities.md").exists()
    output = (tmp_path / "model-capabilities.json").read_text() + (tmp_path / "model-capabilities.md").read_text() + result.output
    assert "secret-token" not in output
    assert "gateway.example.invalid" not in output
    assert "do-not-report" not in output
    assert ("POST", "/v1/responses") in calls
    assert 1 < max_active <= 2


def test_probe_dry_run_does_not_probe_capabilities(monkeypatch, tmp_path: Path):
    methods: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        methods.append(request.method)
        if request.url.path == "/v1/models":
            return httpx.Response(200, json={"data": [{"id": "chat-model"}]})
        raise AssertionError("dry-run should not send capability probes")

    monkeypatch.setattr(httpx, "Client", lambda: _client_with(handler))
    result = runner.invoke(cmd, ["--base-url", "http://127.0.0.1:1", "--api-key", "<API_KEY>", "--dry-run", "--format", "json", "--output-dir", str(tmp_path)])

    assert result.exit_code == 0, result.output
    assert methods == ["GET"]
    report = json.loads((tmp_path / "model-capabilities.json").read_text())
    assert report["models"][0]["chat"] == {"status": "not_run"}


def test_probe_rejects_unknown_options():
    result = runner.invoke(cmd, ["--base-url", "<BASE_URL>", "--api-key", "<API_KEY>", "--wire-api", "invalid"])
    assert result.exit_code != 0
    assert "--wire-api" in result.output


def test_failure_reports_are_generic_and_redacted():
    temporary = result(ProbeResponse(429, 10, "http_error", "No deployments available; deployment-secret"))
    network = result(ProbeResponse(None, 10, "network_error", "secret-token timed out"))

    assert temporary["failure"] == {
        "category": "temporary_unavailable",
        "reason": "No healthy deployment was available at probe time; retry later.",
    }
    assert network["failure"] == {
        "category": "network_error",
        "reason": "Network or timeout error while contacting the gateway.",
    }
    assert "deployment-secret" not in json.dumps(temporary)
    assert "secret-token" not in json.dumps(network)
