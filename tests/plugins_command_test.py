import re

from typer.testing import CliRunner

from ai_assistant.commands import plugins

runner = CliRunner()

_ANSI_RE = re.compile(r"\x1b\[[0-9;]*[a-zA-Z]")


def _plain(text: str) -> str:
    return _ANSI_RE.sub("", text)


def test_plugins_list_includes_agent_bark_notify():
    result = runner.invoke(plugins.cmd, ["list"])

    assert result.exit_code == 0
    assert "agent-bark-notify" in result.output
    assert "codex plugin add agent-bark-notify-codex@ai-assistant" in result.output
    assert "claude plugin install agent-bark-notify@ai-assistant --scope user" in result.output
    assert "openclaw plugins install --link ./plugins/agent-bark-notify-openclaw" in result.output
    assert "openclaw plugins enable agent-bark-notify-openclaw" in result.output


def test_plugins_help_surfaces_direct_install_commands():
    root_help = runner.invoke(plugins.cmd, ["--help"])
    list_help = runner.invoke(plugins.cmd, ["list", "--help"])

    assert root_help.exit_code == 0
    assert list_help.exit_code == 0
    for output in (_plain(root_help.output), _plain(list_help.output)):
        assert "codex plugin marketplace add qsoyq/ai-assistant" in output
        assert "codex plugin add agent-bark-notify-codex@ai-assistant" in output
        assert "claude plugin marketplace add qsoyq/ai-assistant" in output
        assert "claude plugin install agent-bark-notify@ai-assistant --scope user" in output
        assert "openclaw plugins install --link ./plugins/agent-bark-notify-openclaw" in output
        assert "openclaw plugins enable agent-bark-notify-openclaw" in output


def test_codex_config_snippet_contains_hooks_json_command():
    result = runner.invoke(plugins.cmd, ["config-snippet", "agent-bark-notify", "--target", "codex"])

    assert result.exit_code == 0
    assert "global Codex plugin hook file" in result.output
    assert "hooks/hooks.json" in result.output
    assert "ai-assistant agent-bark-notify hook --runtime codex --event completion --summary-mode extract" in result.output
    assert "PermissionRequest" in result.output


def test_claude_config_snippet_contains_settings_hook_command():
    result = runner.invoke(plugins.cmd, ["config-snippet", "agent-bark-notify", "--target", "claude"])

    assert result.exit_code == 0
    assert "global Claude Code settings hook snippet" in result.output
    assert "ai-assistant agent-bark-notify hook --runtime claude --event approval_needed --summary-mode extract" in result.output
    assert "Notification" in result.output


def test_openclaw_config_snippet_contains_local_install_commands():
    result = runner.invoke(plugins.cmd, ["config-snippet", "agent-bark-notify", "--target", "openclaw"])

    assert result.exit_code == 0
    assert "global OpenClaw plugin install" in result.output
    assert "openclaw plugins install --link ./plugins/agent-bark-notify-openclaw" in result.output
    assert "openclaw plugins enable agent-bark-notify-openclaw" in result.output
    assert '"allowConversationAccess":true' in result.output
    assert "openclaw plugins inspect agent-bark-notify-openclaw --runtime --json" in result.output
    assert 'PATH="$HOME/.local/bin:$PATH"' in result.output
    assert "BARK_DEVICE_KEY=<your Bark device key>" in result.output
    assert "ai-assistant agent-bark-notify hook --runtime openclaw --event completion --summary-mode extract" in result.output
    assert '"hook_event_name":"message_sent"' in result.output


def test_install_guides_explain_manual_and_agent_assisted_paths():
    codex = runner.invoke(plugins.cmd, ["install-guide", "agent-bark-notify", "--target", "codex"])
    claude = runner.invoke(plugins.cmd, ["install-guide", "agent-bark-notify", "--target", "claude"])
    openclaw = runner.invoke(plugins.cmd, ["install-guide", "agent-bark-notify", "--target", "openclaw"])

    assert codex.exit_code == 0
    assert claude.exit_code == 0
    assert openclaw.exit_code == 0
    assert "codex plugin marketplace add qsoyq/ai-assistant" in codex.output
    assert "codex plugin add agent-bark-notify-codex@ai-assistant" in codex.output
    assert "review the hook command before trusting it" in codex.output
    assert "Scope: global" in codex.output
    assert "Manual fallback" in codex.output
    assert "claude plugin marketplace add qsoyq/ai-assistant" in claude.output
    assert "claude plugin install agent-bark-notify@ai-assistant --scope user" in claude.output
    assert "--scope user" in claude.output
    assert "/plugin install agent-bark-notify@ai-assistant" in claude.output
    assert "Manual fallback" in claude.output
    assert "openclaw plugins install --link ./plugins/agent-bark-notify-openclaw" in openclaw.output
    assert "openclaw plugins enable agent-bark-notify-openclaw" in openclaw.output
    assert '"allowConversationAccess":true' in openclaw.output
    assert "openclaw plugins inspect agent-bark-notify-openclaw --runtime --json" in openclaw.output
    assert "openclaw gateway install --force --wrapper" in openclaw.output
    assert "BARK_GROUP=OpenClaw" in openclaw.output
    assert "AI_ASSISTANT_AGENT_BARK_NOTIFY_AUDIT_LOG=1" in openclaw.output
    assert "openclaw gateway status --deep" in openclaw.output
    assert "config/CLI version mismatch" in openclaw.output
    assert "Manual fallback" in openclaw.output


def test_project_scope_is_available_for_install_and_config():
    guide = runner.invoke(plugins.cmd, ["install-guide", "agent-bark-notify", "--target", "claude", "--scope", "project"])
    snippet = runner.invoke(plugins.cmd, ["config-snippet", "agent-bark-notify", "--target", "codex", "--scope", "project"])

    assert guide.exit_code == 0
    assert snippet.exit_code == 0
    assert "Scope: project" in guide.output
    assert "--scope project" in guide.output
    assert "project Codex plugin hook file" in snippet.output
