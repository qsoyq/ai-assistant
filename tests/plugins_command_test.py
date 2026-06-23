from typer.testing import CliRunner

from ai_assistant.commands import plugins

runner = CliRunner()


def test_plugins_list_includes_agent_bark_notify():
    result = runner.invoke(plugins.cmd, ["list"])

    assert result.exit_code == 0
    assert "agent-bark-notify" in result.output


def test_codex_config_snippet_contains_hooks_json_command():
    result = runner.invoke(plugins.cmd, ["config-snippet", "agent-bark-notify", "--target", "codex"])

    assert result.exit_code == 0
    assert "hooks/hooks.json" in result.output
    assert "ai-assistant agent-bark-notify hook --runtime codex --event completion" in result.output
    assert "PermissionRequest" in result.output


def test_claude_config_snippet_contains_settings_hook_command():
    result = runner.invoke(plugins.cmd, ["config-snippet", "agent-bark-notify", "--target", "claude"])

    assert result.exit_code == 0
    assert "Claude Code settings hook snippet" in result.output
    assert "ai-assistant agent-bark-notify hook --runtime claude --event approval_needed" in result.output
    assert "Notification" in result.output


def test_install_guides_explain_manual_and_agent_assisted_paths():
    codex = runner.invoke(plugins.cmd, ["install-guide", "agent-bark-notify", "--target", "codex"])
    claude = runner.invoke(plugins.cmd, ["install-guide", "agent-bark-notify", "--target", "claude"])

    assert codex.exit_code == 0
    assert claude.exit_code == 0
    assert "Review the hook command before trusting it" in codex.output
    assert "Manual fallback" in codex.output
    assert "/plugin install agent-bark-notify@ai-assistant" in claude.output
    assert "Manual fallback" in claude.output
