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
        "BARK_DEVICE_KEY",
        "BARK_GROUP",
        "BARK_SERVER",
        "AI_ASSISTANT_AGENT_BARK_NOTIFY_STATE_DIR",
        "AI_ASSISTANT_AGENT_BARK_NOTIFY_AUDIT_LOG",
        "AI_ASSISTANT_AGENT_BARK_NOTIFY_AUDIT_LOG_FILE",
    ):
        monkeypatch.delenv(key, raising=False)


def _read_jsonl(path):
    return [json.loads(line) for line in path.read_text().splitlines()]


def test_dry_run_reports_missing_device_key(monkeypatch, tmp_path):
    _clear_agent_env(monkeypatch)
    monkeypatch.delenv("BARK_DEVICE_KEY", raising=False)
    monkeypatch.setenv("AI_ASSISTANT_AGENT_BARK_NOTIFY_STATE_DIR", str(tmp_path))

    result = runner.invoke(agent_bark_notify.cmd, ["hook", "--event", "completion", "--dry-run"], input="{}")

    assert result.exit_code == 0
    assert "BARK_DEVICE_KEY is missing" in result.output


def test_audit_log_is_disabled_by_default(monkeypatch, tmp_path):
    _clear_agent_env(monkeypatch)
    audit_log = tmp_path / "audit.jsonl"
    monkeypatch.setenv("AI_ASSISTANT_AGENT_BARK_NOTIFY_AUDIT_LOG_FILE", str(audit_log))
    monkeypatch.delenv("BARK_DEVICE_KEY", raising=False)
    monkeypatch.setenv("AI_ASSISTANT_AGENT_BARK_NOTIFY_STATE_DIR", str(tmp_path / "state"))

    result = runner.invoke(agent_bark_notify.cmd, ["hook", "--event", "completion", "--dry-run"], input="{}")

    assert result.exit_code == 0
    assert not audit_log.exists()


def test_audit_log_uses_default_path_when_enabled(monkeypatch, tmp_path):
    _clear_agent_env(monkeypatch)
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setenv("AI_ASSISTANT_AGENT_BARK_NOTIFY_AUDIT_LOG", "1")
    monkeypatch.delenv("BARK_DEVICE_KEY", raising=False)
    monkeypatch.setenv("AI_ASSISTANT_AGENT_BARK_NOTIFY_STATE_DIR", str(tmp_path / "state"))

    result = runner.invoke(agent_bark_notify.cmd, ["hook", "--runtime", "codex", "--event", "completion", "--dry-run"], input=json.dumps({"session_id": "s-audit-default"}))

    assert result.exit_code == 0
    records = _read_jsonl(tmp_path / ".ai-assistant" / "agent-bark-notify.log")
    assert len(records) == 1
    assert records[0]["status"] == "skipped_missing_device_key"
    assert records[0]["runtime"] == "codex"
    assert records[0]["event"] == "completion"
    assert records[0]["session_id_hash"]


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
    assert body["title"] == "[Codex] [Done] [demo-project]"
    assert body["body"] == "done"
    assert body["group"] == "agents"
    assert body["url"] == "https://api.day.app/device-key"


def test_audit_log_records_sent_metadata_without_secrets(monkeypatch, tmp_path):
    _clear_agent_env(monkeypatch)
    audit_log = tmp_path / "audit.jsonl"
    monkeypatch.setenv("AI_ASSISTANT_AGENT_BARK_NOTIFY_AUDIT_LOG", "1")
    monkeypatch.setenv("AI_ASSISTANT_AGENT_BARK_NOTIFY_AUDIT_LOG_FILE", str(audit_log))
    monkeypatch.setenv("BARK_DEVICE_KEY", "secret-device-key")
    monkeypatch.setenv("AI_ASSISTANT_AGENT_BARK_NOTIFY_STATE_DIR", str(tmp_path / "state"))

    result = runner.invoke(
        agent_bark_notify.cmd,
        ["hook", "--runtime", "codex", "--event", "completion", "--message", "done with token=secret", "--dry-run"],
        input=json.dumps({"cwd": "/tmp/demo-project", "session_id": "s-audit-sent", "raw": "secret-device-key"}),
    )

    assert result.exit_code == 0
    records = _read_jsonl(audit_log)
    assert len(records) == 1
    record = records[0]
    assert record["status"] == "sent"
    assert record["project"] == "demo-project"
    assert record["title"] == "[Codex] [Done] [demo-project]"
    assert record["body_len"] == len("done with token=secret")
    assert record["dedupe_key_hash"]
    raw_record = json.dumps(record)
    assert "secret-device-key" not in raw_record
    assert "done with token=secret" not in raw_record


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
    assert "title=%5BCodex%5D+%5BApproval%5D+%5Bdemo-project%5D" in form
    assert "body=%E9%9C%80%E8%A6%81%E4%BD%A0%E5%AE%A1%E6%89%B9%E5%BD%93%E5%89%8D%E6%93%8D%E4%BD%9C" in form
    assert "group=agents" in form


def test_audit_log_records_http_error_without_url_secret(monkeypatch, tmp_path):
    _clear_agent_env(monkeypatch)
    audit_log = tmp_path / "audit.jsonl"
    monkeypatch.setenv("AI_ASSISTANT_AGENT_BARK_NOTIFY_AUDIT_LOG", "1")
    monkeypatch.setenv("AI_ASSISTANT_AGENT_BARK_NOTIFY_AUDIT_LOG_FILE", str(audit_log))
    monkeypatch.setenv("BARK_DEVICE_KEY", "secret-device-key")
    monkeypatch.setenv("AI_ASSISTANT_AGENT_BARK_NOTIFY_STATE_DIR", str(tmp_path / "state"))
    real_client = httpx.Client

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(500, request=request, text="failed")

    monkeypatch.setattr(httpx, "Client", lambda **kw: real_client(transport=httpx.MockTransport(handler)))

    result = runner.invoke(
        agent_bark_notify.cmd,
        ["hook", "--runtime", "codex", "--event", "completion"],
        input=json.dumps({"cwd": "/tmp/demo-project", "session_id": "s-audit-http-error"}),
    )

    assert result.exit_code == 0
    records = _read_jsonl(audit_log)
    assert len(records) == 1
    record = records[0]
    assert record["status"] == "bark_http_error"
    assert record["error_class"] == "HTTPStatusError"
    assert "secret-device-key" not in record["error_message"]
    assert "https://api.day.app/[REDACTED]" in record["error_message"]


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


def test_audit_log_distinguishes_skip_statuses(monkeypatch, tmp_path):
    _clear_agent_env(monkeypatch)
    audit_log = tmp_path / "audit.jsonl"
    monkeypatch.setenv("AI_ASSISTANT_AGENT_BARK_NOTIFY_AUDIT_LOG", "1")
    monkeypatch.setenv("AI_ASSISTANT_AGENT_BARK_NOTIFY_AUDIT_LOG_FILE", str(audit_log))
    monkeypatch.setenv("AI_ASSISTANT_AGENT_BARK_NOTIFY_STATE_DIR", str(tmp_path / "state"))

    unsupported = runner.invoke(agent_bark_notify.cmd, ["hook", "--runtime", "codex", "--dry-run"], input=json.dumps({"hook_event_name": "Notification", "session_id": "s-unsupported"}))
    missing_key = runner.invoke(agent_bark_notify.cmd, ["hook", "--runtime", "codex", "--event", "completion", "--dry-run"], input=json.dumps({"session_id": "s-missing"}))
    monkeypatch.setenv("BARK_DEVICE_KEY", "device-key")
    first = runner.invoke(agent_bark_notify.cmd, ["hook", "--runtime", "codex", "--event", "completion", "--dry-run"], input=json.dumps({"session_id": "s-duplicate"}))
    duplicate = runner.invoke(agent_bark_notify.cmd, ["hook", "--runtime", "codex", "--event", "completion", "--dry-run"], input=json.dumps({"session_id": "s-duplicate"}))

    assert unsupported.exit_code == 0
    assert missing_key.exit_code == 0
    assert first.exit_code == 0
    assert duplicate.exit_code == 0
    assert [record["status"] for record in _read_jsonl(audit_log)] == [
        "skipped_unsupported_event",
        "skipped_missing_device_key",
        "sent",
        "skipped_duplicate",
    ]


def test_audit_log_write_failure_does_not_fail_hook(monkeypatch, tmp_path):
    _clear_agent_env(monkeypatch)
    monkeypatch.setenv("AI_ASSISTANT_AGENT_BARK_NOTIFY_AUDIT_LOG", "1")
    monkeypatch.setenv("AI_ASSISTANT_AGENT_BARK_NOTIFY_AUDIT_LOG_FILE", str(tmp_path))
    monkeypatch.delenv("BARK_DEVICE_KEY", raising=False)
    monkeypatch.setenv("AI_ASSISTANT_AGENT_BARK_NOTIFY_STATE_DIR", str(tmp_path / "state"))

    result = runner.invoke(agent_bark_notify.cmd, ["hook", "--event", "completion", "--dry-run"], input="{}")

    assert result.exit_code == 0
    assert "BARK_DEVICE_KEY is missing" in result.output


def test_auto_event_maps_permission_request(monkeypatch, tmp_path):
    _clear_agent_env(monkeypatch)
    monkeypatch.setenv("BARK_DEVICE_KEY", "device-key")
    monkeypatch.setenv("AI_ASSISTANT_AGENT_BARK_NOTIFY_STATE_DIR", str(tmp_path))

    result = runner.invoke(
        agent_bark_notify.cmd,
        ["hook", "--runtime", "claude", "--dry-run"],
        input=json.dumps({"cwd": "/tmp/demo-project", "hook_event_name": "PermissionRequest", "session_id": "s4"}),
    )

    assert result.exit_code == 0
    body = json.loads(result.output)
    assert body["title"] == "[Claude Code] [Approval] [demo-project]"
    assert body["body"] == "需要你审批当前操作"


def test_titles_include_normalized_event_for_codex_and_claude(monkeypatch, tmp_path):
    _clear_agent_env(monkeypatch)
    monkeypatch.setenv("BARK_DEVICE_KEY", "device-key")
    monkeypatch.setenv("AI_ASSISTANT_AGENT_BARK_NOTIFY_STATE_DIR", str(tmp_path))

    cases = [
        (
            ["hook", "--runtime", "codex", "--event", "completion", "--dry-run"],
            {"cwd": "/tmp/demo-project", "session_id": "codex-done"},
            "[Codex] [Done] [demo-project]",
        ),
        (
            ["hook", "--runtime", "codex", "--event", "approval_needed", "--dry-run"],
            {"cwd": "/tmp/demo-project", "session_id": "codex-approval"},
            "[Codex] [Approval] [demo-project]",
        ),
        (
            ["hook", "--runtime", "claude", "--event", "completion", "--dry-run"],
            {"cwd": "/tmp/demo-project", "session_id": "claude-done"},
            "[Claude Code] [Done] [demo-project]",
        ),
        (
            ["hook", "--runtime", "claude", "--event", "approval_needed", "--dry-run"],
            {"cwd": "/tmp/demo-project", "session_id": "claude-approval"},
            "[Claude Code] [Approval] [demo-project]",
        ),
        (
            ["hook", "--runtime", "codex", "--event", "failed", "--dry-run"],
            {"cwd": "/tmp/demo-project", "session_id": "codex-failed"},
            "[Codex] [Failed] [demo-project]",
        ),
    ]

    for args, payload, expected_title in cases:
        result = runner.invoke(agent_bark_notify.cmd, args, input=json.dumps(payload))

        assert result.exit_code == 0
        assert json.loads(result.output)["title"] == expected_title


def test_explicit_runtime_controls_title_even_in_lody_env(monkeypatch, tmp_path):
    _clear_agent_env(monkeypatch)
    monkeypatch.setenv("LODY_SESSION_ID", "lody-session")
    monkeypatch.setenv("BARK_DEVICE_KEY", "device-key")
    monkeypatch.setenv("AI_ASSISTANT_AGENT_BARK_NOTIFY_STATE_DIR", str(tmp_path))

    result = runner.invoke(
        agent_bark_notify.cmd,
        ["hook", "--runtime", "claude", "--event", "completion", "--dry-run"],
        input=json.dumps({"cwd": "/tmp/demo-project", "session_id": "explicit-claude"}),
    )

    assert result.exit_code == 0
    assert json.loads(result.output)["title"] == "[Claude Code] [Done] [demo-project]"


def test_extract_completion_uses_last_assistant_message(monkeypatch, tmp_path):
    _clear_agent_env(monkeypatch)
    monkeypatch.setenv("BARK_DEVICE_KEY", "device-key")
    monkeypatch.setenv("AI_ASSISTANT_AGENT_BARK_NOTIFY_STATE_DIR", str(tmp_path / "state"))

    result = runner.invoke(
        agent_bark_notify.cmd,
        ["hook", "--runtime", "codex", "--event", "completion", "--summary-mode", "extract", "--dry-run"],
        input=json.dumps(
            {
                "cwd": "/tmp/demo-project",
                "session_id": "s5",
                "last_assistant_message": "Implemented safe summaries.\n\n```text\nlarge output\n```",
            }
        ),
    )

    assert result.exit_code == 0
    body = json.loads(result.output)
    assert body["body"] == "Implemented safe summaries."


def test_extract_completion_falls_back_to_transcript(monkeypatch, tmp_path):
    _clear_agent_env(monkeypatch)
    monkeypatch.setenv("BARK_DEVICE_KEY", "device-key")
    monkeypatch.setenv("AI_ASSISTANT_AGENT_BARK_NOTIFY_STATE_DIR", str(tmp_path / "state"))
    transcript = tmp_path / "transcript.jsonl"
    transcript.write_text(
        "\n".join(
            [
                json.dumps({"role": "user", "content": "do the thing"}),
                json.dumps({"type": "assistant_message", "message": {"role": "assistant", "content": [{"type": "text", "text": "Finished transcript work."}]}}),
            ]
        )
    )

    result = runner.invoke(
        agent_bark_notify.cmd,
        ["hook", "--runtime", "claude", "--event", "completion", "--summary-mode", "extract", "--dry-run"],
        input=json.dumps({"cwd": "/tmp/demo-project", "session_id": "s6", "transcript_path": str(transcript)}),
    )

    assert result.exit_code == 0
    body = json.loads(result.output)
    assert body["body"] == "Finished transcript work."


def test_extract_completion_falls_back_to_fixed_message(monkeypatch, tmp_path):
    _clear_agent_env(monkeypatch)
    monkeypatch.setenv("BARK_DEVICE_KEY", "device-key")
    monkeypatch.setenv("AI_ASSISTANT_AGENT_BARK_NOTIFY_STATE_DIR", str(tmp_path))

    result = runner.invoke(
        agent_bark_notify.cmd,
        ["hook", "--event", "completion", "--summary-mode", "extract", "--dry-run"],
        input=json.dumps({"cwd": "/tmp/demo-project", "session_id": "s7", "last_assistant_message": '{"raw": "json", "payload": true}'}),
    )

    assert result.exit_code == 0
    body = json.loads(result.output)
    assert body["body"] == "任务已完成"


def test_extract_approval_uses_tool_description(monkeypatch, tmp_path):
    _clear_agent_env(monkeypatch)
    monkeypatch.setenv("BARK_DEVICE_KEY", "device-key")
    monkeypatch.setenv("AI_ASSISTANT_AGENT_BARK_NOTIFY_STATE_DIR", str(tmp_path))

    result = runner.invoke(
        agent_bark_notify.cmd,
        ["hook", "--runtime", "codex", "--event", "approval_needed", "--summary-mode", "extract", "--dry-run"],
        input=json.dumps({"session_id": "s8", "tool_input": {"description": "Run pytest for the Bark summary tests"}}),
    )

    assert result.exit_code == 0
    body = json.loads(result.output)
    assert body["body"] == "Run pytest for the Bark summary tests"


def test_extract_approval_uses_safe_tool_detail(monkeypatch, tmp_path):
    _clear_agent_env(monkeypatch)
    monkeypatch.setenv("BARK_DEVICE_KEY", "device-key")
    monkeypatch.setenv("AI_ASSISTANT_AGENT_BARK_NOTIFY_STATE_DIR", str(tmp_path))

    result = runner.invoke(
        agent_bark_notify.cmd,
        ["hook", "--runtime", "claude", "--event", "approval_needed", "--summary-mode", "extract", "--dry-run"],
        input=json.dumps({"session_id": "s9", "tool_name": "Edit", "tool_input": {"file_path": "/tmp/demo-project/app.py"}}),
    )

    assert result.exit_code == 0
    body = json.loads(result.output)
    assert body["body"] == "Edit: /tmp/demo-project/app.py"


def test_extract_redacts_secrets_url_queries_and_long_commands(monkeypatch, tmp_path):
    _clear_agent_env(monkeypatch)
    monkeypatch.setenv("BARK_DEVICE_KEY", "device-key")
    monkeypatch.setenv("AI_ASSISTANT_AGENT_BARK_NOTIFY_STATE_DIR", str(tmp_path))

    completion = runner.invoke(
        agent_bark_notify.cmd,
        ["hook", "--event", "completion", "--summary-mode", "extract", "--summary-max-chars", "80", "--dry-run"],
        input=json.dumps(
            {
                "session_id": "s10",
                "last_assistant_message": "Fetched https://example.test/path?token=secret&x=1 with api_key=abc123 and Authorization: Bearer secret",
            }
        ),
    )
    approval = runner.invoke(
        agent_bark_notify.cmd,
        ["hook", "--event", "approval_needed", "--summary-mode", "extract", "--dry-run"],
        input=json.dumps({"session_id": "s11", "tool_name": "Shell", "tool_input": {"command": "curl https://example.test?token=secret " + ("x" * 100)}}),
    )

    assert completion.exit_code == 0
    completion_body = json.loads(completion.output)["body"]
    assert "secret" not in completion_body.lower()
    assert "?token=" not in completion_body
    assert "[REDACTED]" in completion_body
    assert approval.exit_code == 0
    assert json.loads(approval.output)["body"] == "需要你审批当前操作"
