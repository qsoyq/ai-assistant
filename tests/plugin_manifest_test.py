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
    openclaw_package = json.loads(Path("plugins/agent-bark-notify-openclaw/package.json").read_text())
    openclaw_manifest = json.loads(Path("plugins/agent-bark-notify-openclaw/openclaw.plugin.json").read_text())

    assert codex_manifest["version"] == "0.1.5"
    assert claude_manifest["version"] == "0.1.5"
    assert openclaw_package["version"] == "0.1.5"
    assert openclaw_manifest["version"] == "0.1.5"


def test_bark_plugin_versions_stay_in_sync_across_targets():
    versions = {
        "codex": json.loads(Path("plugins/agent-bark-notify-codex/.codex-plugin/plugin.json").read_text())["version"],
        "claude": json.loads(Path("plugins/agent-bark-notify-claude/.claude-plugin/plugin.json").read_text())["version"],
        "openclaw-package": json.loads(Path("plugins/agent-bark-notify-openclaw/package.json").read_text())["version"],
        "openclaw-manifest": json.loads(Path("plugins/agent-bark-notify-openclaw/openclaw.plugin.json").read_text())["version"],
    }

    assert set(versions.values()) == {"0.1.5"}


def test_claude_marketplace_exposes_bark_plugin():
    marketplace = json.loads(Path(".claude-plugin/marketplace.json").read_text())
    [plugin] = marketplace["plugins"]

    assert marketplace["name"] == "ai-assistant"
    assert plugin["name"] == "agent-bark-notify"
    assert plugin["source"] == "./plugins/agent-bark-notify-claude"
    assert Path("plugins/agent-bark-notify-claude/.claude-plugin/plugin.json").is_file()


def test_openclaw_bark_plugin_has_native_manifest_and_runtime_entry():
    plugin_root = Path("plugins/agent-bark-notify-openclaw")
    package_json = json.loads((plugin_root / "package.json").read_text())
    manifest = json.loads((plugin_root / "openclaw.plugin.json").read_text())
    source_entry = (plugin_root / "index.ts").read_text()
    runtime_entry = (plugin_root / "index.js").read_text()

    assert package_json["openclaw"]["extensions"] == ["./index.ts"]
    assert package_json["openclaw"]["runtimeExtensions"] == ["./index.js"]
    assert manifest["id"] == "agent-bark-notify-openclaw"
    assert manifest["activation"]["onStartup"] is True
    assert manifest["configSchema"] == {"type": "object", "additionalProperties": False}
    assert 'api.on(\n      "agent_end"' in source_entry
    assert "ai-assistant" in runtime_entry
    assert "--runtime" in runtime_entry
    assert "openclaw" in runtime_entry
