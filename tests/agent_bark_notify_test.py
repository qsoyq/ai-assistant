import json

import httpx
from typer.testing import CliRunner

from ai_assistant.commands import agent_bark_notify

runner = CliRunner()


def _clear_agent_env(monkeypatch):
    for key in (
        "LODY_SESSION_ID",
        "LODY_WORKSPACE_SESSION_ID",
        "LODY_ELECTRON_BOOTSTRAP",
        "__CFBundleIdentifier",
        "CLAUDECODE",
        "CLAUDE_CODE",
        "CLAUDE_PROJECT_DIR",
        "CLAUDE_CONFIG_DIR",
        "CODEX_CI",
        "CODEX_THREAD_ID",
    ):
        monkeypatch.delenv(key, raising=False)


def test_dry_run_reports_missing_device_key(monkeypatch, tmp_path):
    _clear_agent_env(monkeypatch)
    monkeypatch.delenv("BARK_DEVICE_KEY", raising=False)
    monkeypatch.setenv("AI_ASSISTANT_AGENT_BARK_NOTIFY_STATE_DIR", str(tmp_path))

    result = runner.invoke(agent_bark_notify.cmd, ["hook", "--event", "completion", "--dry-run"], input="{}")

    assert result.exit_code == 0
    assert "BARK_DEVICE_KEY is missing" in result.output


def test_dry_run_prints_notification(monkeypatch, tmp_path):
    _clear_agent_env(monkeypatch)
    monkeypatch.setenv("BARK_DEVICE_KEY", "device-key")
    monkeypatch.setenv("BARK_GROUP", "agents")
    monkeypatch.setenv("AI_ASSISTANT_AGENT_BARK_NOTIFY_STATE_DIR", str(tmp_path))

    result = runner.invoke(
        agent_bark_notify.cmd,
        ["hook", "--runtime", "codex", "--event", "completion", "--message", "done", "--dry-run"],
        input=json.dumps({"cwd": "/tmp/demo-project", "session_id": "s1"}),
    )

    assert result.exit_code == 0
    body = json.loads(result.output)
    assert body["title"] == "[Codex] [demo-project]"
    assert body["body"] == "done"
    assert body["group"] == "agents"
    assert body["url"] == "https://api.day.app/device-key"


def test_send_bark_posts_form_with_group(monkeypatch, tmp_path):
    _clear_agent_env(monkeypatch)
    monkeypatch.setenv("BARK_DEVICE_KEY", "device-key")
    monkeypatch.setenv("BARK_GROUP", "agents")
    monkeypatch.setenv("AI_ASSISTANT_AGENT_BARK_NOTIFY_STATE_DIR", str(tmp_path))
    calls: list[httpx.Request] = []
    real_client = httpx.Client

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(request)
        return httpx.Response(200, json={"code": 200})

    monkeypatch.setattr(httpx, "Client", lambda **kw: real_client(transport=httpx.MockTransport(handler)))

    result = runner.invoke(
        agent_bark_notify.cmd,
        ["hook", "--runtime", "codex", "--event", "approval_needed"],
        input=json.dumps({"cwd": "/tmp/demo-project", "session_id": "s2"}),
    )

    assert result.exit_code == 0
    assert len(calls) == 1
    assert str(calls[0].url) == "https://api.day.app/device-key"
    form = calls[0].content.decode()
    assert "title=%5BCodex%5D+%5Bdemo-project%5D" in form
    assert "body=%E9%9C%80%E8%A6%81%E4%BD%A0%E5%AE%A1%E6%89%B9%E5%BD%93%E5%89%8D%E6%93%8D%E4%BD%9C" in form
    assert "group=agents" in form


def test_duplicate_event_is_skipped(monkeypatch, tmp_path):
    _clear_agent_env(monkeypatch)
    monkeypatch.setenv("BARK_DEVICE_KEY", "device-key")
    monkeypatch.setenv("AI_ASSISTANT_AGENT_BARK_NOTIFY_STATE_DIR", str(tmp_path))
    payload = json.dumps({"cwd": "/tmp/demo-project", "session_id": "s3"})

    first = runner.invoke(agent_bark_notify.cmd, ["hook", "--event", "completion", "--dry-run"], input=payload)
    second = runner.invoke(agent_bark_notify.cmd, ["hook", "--event", "completion", "--dry-run"], input=payload)

    assert first.exit_code == 0
    assert second.exit_code == 0
    assert "duplicate notification" in second.output


def test_auto_event_maps_permission_request(monkeypatch, tmp_path):
    _clear_agent_env(monkeypatch)
    monkeypatch.setenv("BARK_DEVICE_KEY", "device-key")
    monkeypatch.setenv("AI_ASSISTANT_AGENT_BARK_NOTIFY_STATE_DIR", str(tmp_path))

    result = runner.invoke(
        agent_bark_notify.cmd,
        ["hook", "--runtime", "claude", "--dry-run"],
        input=json.dumps({"hook_event_name": "PermissionRequest", "session_id": "s4"}),
    )

    assert result.exit_code == 0
    body = json.loads(result.output)
    assert body["body"] == "需要你审批当前操作"
