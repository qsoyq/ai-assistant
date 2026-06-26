import json

from typer.testing import CliRunner

from ai_assistant.commands import agent_bark_notify

runner = CliRunner()

OLD_AGENT_BARK_NOTIFY_PREFIX = "AI_ASSISTANT" + "_AGENT_BARK_NOTIFY_"


class _Completed:
    def __init__(self, args, returncode=0, stdout="", stderr=""):
        self.args = args
        self.returncode = returncode
        self.stdout = stdout
        self.stderr = stderr


def _plain(text: str) -> str:
    return text.replace("│", " ").replace("┃", " ").replace("┏", " ").replace("┓", " ").replace("└", " ").replace("┘", " ")


def test_install_skips_missing_agent_clis(monkeypatch):
    monkeypatch.setattr(agent_bark_notify.shutil, "which", lambda command: None)

    result = runner.invoke(agent_bark_notify.cmd, ["install"])

    assert result.exit_code == 0
    assert "Codex" in result.output
    assert "Claude Code" in result.output
    assert "OpenClaw" in result.output
    assert "skipped" in result.output
    assert "CLI not found" in result.output
    assert "Summary: 0 succeeded, 3 skipped, 0 failed." in result.output
    assert "BARK_DEVICE_KEY=<your Bark device key>" in result.output
    assert OLD_AGENT_BARK_NOTIFY_PREFIX not in result.output


def test_install_codex_first_install(monkeypatch):
    calls = []
    codex_versions = iter([None, "0.1.5"])

    def fake_which(command):
        return "/opt/homebrew/bin/codex" if command == "codex" else None

    def fake_run(args, **kwargs):
        calls.append(args)
        if args == ["codex", "plugin", "list", "--json"]:
            version = next(codex_versions)
            installed = [] if version is None else [{"pluginId": "agent-bark-notify-codex@ai-assistant", "version": version}]
            return _Completed(args, stdout=json.dumps({"installed": installed}))
        return _Completed(args)

    monkeypatch.setattr(agent_bark_notify.shutil, "which", fake_which)
    monkeypatch.setattr(agent_bark_notify.subprocess, "run", fake_run)

    result = runner.invoke(agent_bark_notify.cmd, ["install"])

    assert result.exit_code == 0
    assert "Codex" in result.output
    assert "installed" in result.output
    assert "none -> 0.1.5" in result.output
    assert ["codex", "plugin", "marketplace", "add", "qsoyq/ai-assistant"] in calls
    assert ["codex", "plugin", "marketplace", "upgrade", "ai-assistant"] in calls
    assert ["codex", "plugin", "add", "agent-bark-notify-codex@ai-assistant"] in calls


def test_install_codex_continues_when_marketplace_is_already_configured(monkeypatch):
    codex_versions = iter([None, "0.1.5"])

    def fake_which(command):
        return "/opt/homebrew/bin/codex" if command == "codex" else None

    def fake_run(args, **kwargs):
        if args == ["codex", "plugin", "list", "--json"]:
            version = next(codex_versions)
            installed = [] if version is None else [{"pluginId": "agent-bark-notify-codex@ai-assistant", "version": version}]
            return _Completed(args, stdout=json.dumps({"installed": installed}))
        if args == ["codex", "plugin", "marketplace", "add", "qsoyq/ai-assistant"]:
            return _Completed(args, returncode=1, stderr="marketplace already configured")
        return _Completed(args)

    monkeypatch.setattr(agent_bark_notify.shutil, "which", fake_which)
    monkeypatch.setattr(agent_bark_notify.subprocess, "run", fake_run)

    result = runner.invoke(agent_bark_notify.cmd, ["install"])

    assert result.exit_code == 0
    assert "installed" in result.output
    assert "none -> 0.1.5" in result.output


def test_install_claude_updates_existing_user_plugin(monkeypatch):
    calls = []
    claude_versions = iter(["0.1.4", "0.1.5"])

    def fake_which(command):
        return "/Users/me/.local/bin/claude" if command == "claude" else None

    def fake_run(args, **kwargs):
        calls.append(args)
        if args == ["claude", "plugin", "list", "--json"]:
            version = next(claude_versions)
            return _Completed(args, stdout=json.dumps([{"id": "agent-bark-notify@ai-assistant", "scope": "user", "version": version}]))
        return _Completed(args)

    monkeypatch.setattr(agent_bark_notify.shutil, "which", fake_which)
    monkeypatch.setattr(agent_bark_notify.subprocess, "run", fake_run)

    result = runner.invoke(agent_bark_notify.cmd, ["install"])

    assert result.exit_code == 0
    assert "Claude Code" in result.output
    assert "updated" in result.output
    assert "0.1.4 -> 0.1.5" in result.output
    assert ["claude", "plugin", "marketplace", "add", "qsoyq/ai-assistant", "--scope", "user"] in calls
    assert ["claude", "plugin", "marketplace", "update", "ai-assistant"] in calls
    assert ["claude", "plugin", "update", "agent-bark-notify@ai-assistant", "--scope", "user"] in calls
    assert ["claude", "plugin", "install", "agent-bark-notify@ai-assistant", "--scope", "user"] not in calls


def test_install_reports_downgrade(monkeypatch):
    codex_versions = iter(["0.1.5", "0.1.4"])

    def fake_which(command):
        return "/opt/homebrew/bin/codex" if command == "codex" else None

    def fake_run(args, **kwargs):
        if args == ["codex", "plugin", "list", "--json"]:
            version = next(codex_versions)
            return _Completed(args, stdout=json.dumps({"installed": [{"pluginId": "agent-bark-notify-codex@ai-assistant", "version": version}]}))
        return _Completed(args)

    monkeypatch.setattr(agent_bark_notify.shutil, "which", fake_which)
    monkeypatch.setattr(agent_bark_notify.subprocess, "run", fake_run)

    result = runner.invoke(agent_bark_notify.cmd, ["install"])

    assert result.exit_code == 0
    assert "downgraded" in result.output
    assert "0.1.5 -> 0.1.4" in result.output


def test_install_reports_unchanged(monkeypatch):
    codex_versions = iter(["0.1.5", "0.1.5"])

    def fake_which(command):
        return "/opt/homebrew/bin/codex" if command == "codex" else None

    def fake_run(args, **kwargs):
        if args == ["codex", "plugin", "list", "--json"]:
            version = next(codex_versions)
            return _Completed(args, stdout=json.dumps({"installed": [{"pluginId": "agent-bark-notify-codex@ai-assistant", "version": version}]}))
        return _Completed(args)

    monkeypatch.setattr(agent_bark_notify.shutil, "which", fake_which)
    monkeypatch.setattr(agent_bark_notify.subprocess, "run", fake_run)

    result = runner.invoke(agent_bark_notify.cmd, ["install"])

    assert result.exit_code == 0
    assert "unchanged" in result.output
    assert "0.1.5" in result.output


def test_install_continues_after_agent_failure(monkeypatch):
    codex_versions = iter([None, "0.1.5"])
    claude_versions = iter(["0.1.4"])

    def fake_which(command):
        return {
            "codex": "/opt/homebrew/bin/codex",
            "claude": "/Users/me/.local/bin/claude",
        }.get(command)

    def fake_run(args, **kwargs):
        if args == ["codex", "plugin", "list", "--json"]:
            version = next(codex_versions)
            installed = [] if version is None else [{"pluginId": "agent-bark-notify-codex@ai-assistant", "version": version}]
            return _Completed(args, stdout=json.dumps({"installed": installed}))
        if args == ["claude", "plugin", "list", "--json"]:
            version = next(claude_versions)
            return _Completed(args, stdout=json.dumps([{"id": "agent-bark-notify@ai-assistant", "scope": "user", "version": version}]))
        if args == ["claude", "plugin", "update", "agent-bark-notify@ai-assistant", "--scope", "user"]:
            return _Completed(args, returncode=1, stderr="update failed")
        return _Completed(args)

    monkeypatch.setattr(agent_bark_notify.shutil, "which", fake_which)
    monkeypatch.setattr(agent_bark_notify.subprocess, "run", fake_run)

    result = runner.invoke(agent_bark_notify.cmd, ["install"])

    assert result.exit_code == 0
    assert "Codex" in result.output
    assert "installed" in result.output
    assert "Claude Code" in result.output
    assert "failed" in result.output
    assert "Summary: 1 succeeded, 1 skipped, 1 failed." in result.output
    assert "claude plugin update agent-bark-notify@ai-assistant --scope user" in result.output


def test_install_exits_one_when_all_found_agents_fail(monkeypatch):
    def fake_which(command):
        return "/opt/homebrew/bin/codex" if command == "codex" else None

    def fake_run(args, **kwargs):
        if args == ["codex", "plugin", "list", "--json"]:
            return _Completed(args, stdout=json.dumps({"installed": []}))
        if args == ["codex", "plugin", "marketplace", "add", "qsoyq/ai-assistant"]:
            return _Completed(args, returncode=1, stderr="network failed")
        return _Completed(args)

    monkeypatch.setattr(agent_bark_notify.shutil, "which", fake_which)
    monkeypatch.setattr(agent_bark_notify.subprocess, "run", fake_run)

    result = runner.invoke(agent_bark_notify.cmd, ["install"])

    assert result.exit_code == 1
    assert "Codex" in result.output
    assert "failed" in result.output
    assert "Summary: 0 succeeded, 2 skipped, 1 failed." in result.output


def test_install_openclaw_fails_when_local_plugin_directory_is_missing(monkeypatch, tmp_path):
    def fake_which(command):
        return "/usr/local/bin/openclaw" if command == "openclaw" else None

    def fake_run(args, **kwargs):
        if args == ["openclaw", "plugins", "inspect", "agent-bark-notify-openclaw", "--runtime", "--json"]:
            return _Completed(args, stdout=json.dumps({"version": "0.1.5"}))
        return _Completed(args)

    monkeypatch.setattr(agent_bark_notify.shutil, "which", fake_which)
    monkeypatch.setattr(agent_bark_notify.subprocess, "run", fake_run)
    monkeypatch.setattr(agent_bark_notify, "_openclaw_plugin_dir", lambda: tmp_path / "missing")

    result = runner.invoke(agent_bark_notify.cmd, ["install"])

    assert result.exit_code == 1
    assert "OpenClaw" in result.output
    assert "failed" in result.output
    assert "Missing local plugin directory" in result.output
    assert "source checkout" in result.output


def test_install_handles_invalid_json_versions(monkeypatch):
    def fake_which(command):
        return "/opt/homebrew/bin/codex" if command == "codex" else None

    def fake_run(args, **kwargs):
        if args == ["codex", "plugin", "list", "--json"]:
            return _Completed(args, stdout="{not json")
        return _Completed(args)

    monkeypatch.setattr(agent_bark_notify.shutil, "which", fake_which)
    monkeypatch.setattr(agent_bark_notify.subprocess, "run", fake_run)

    result = runner.invoke(agent_bark_notify.cmd, ["install"])

    assert result.exit_code == 0
    assert "installed" in result.output
    assert "none -> unknown" in result.output


def test_install_help_describes_scope_plugins_and_environment():
    result = runner.invoke(agent_bark_notify.cmd, ["install", "--help"])
    output = _plain(result.output)

    assert result.exit_code == 0
    for expected in (
        "codex",
        "claude",
        "openclaw",
        "user/global scope",
        "Missing CLIs are skipped",
        "BARK_DEVICE_KEY",
        "AGENT_BARK_NOTIFY_GROUP_MODE",
        "AGENT_BARK_NOTIFY_HOOK_URL",
        "restricted or service environment",
    ):
        assert expected in output
    assert OLD_AGENT_BARK_NOTIFY_PREFIX not in output
