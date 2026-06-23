import json
from pathlib import Path


def test_codex_bark_plugin_uses_default_hook_config_path():
    plugin_root = Path("plugins/agent-bark-notify-codex")
    manifest = json.loads((plugin_root / ".codex-plugin/plugin.json").read_text())

    assert "hooks" not in manifest
    assert (plugin_root / "hooks/hooks.json").is_file()


def test_codex_bark_plugin_hook_config_uses_codex_schema():
    plugin_root = Path("plugins/agent-bark-notify-codex")
    hook_config = json.loads((plugin_root / "hooks/hooks.json").read_text())

    permission_hook = hook_config["hooks"]["PermissionRequest"][0]["hooks"][0]
    stop_hook = hook_config["hooks"]["Stop"][0]["hooks"][0]
    assert permission_hook == {
        "type": "command",
        "command": "ai-assistant agent-bark-notify hook --runtime codex --event approval_needed --summary-mode extract",
    }
    assert stop_hook == {
        "type": "command",
        "command": "ai-assistant agent-bark-notify hook --runtime codex --event completion --summary-mode extract",
    }


def test_bark_plugin_versions_are_bumped_for_extract_hooks():
    codex_manifest = json.loads(Path("plugins/agent-bark-notify-codex/.codex-plugin/plugin.json").read_text())
    claude_manifest = json.loads(Path("plugins/agent-bark-notify-claude/.claude-plugin/plugin.json").read_text())

    assert codex_manifest["version"] == "0.1.3"
    assert claude_manifest["version"] == "0.1.3"
