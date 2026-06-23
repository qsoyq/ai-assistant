from typing import Literal

import typer

from ai_assistant.commands import make_typer

helptext = """
Manage ai-assistant companion plugins.

Available plugins:
  agent-bark-notify  Sends Bark notifications from Codex and Claude Code hooks.

Install paths:
  1. Manual config:
     ai-assistant plugins config-snippet agent-bark-notify --target codex
     ai-assistant plugins config-snippet agent-bark-notify --target claude

  2. Agent-assisted install:
     ai-assistant plugins install-guide agent-bark-notify --target codex
     ai-assistant plugins install-guide agent-bark-notify --target claude

Hooks run local commands. Review the generated hook command and only trust it if you accept it.
"""

cmd = make_typer(helptext)

Target = Literal["codex", "claude"]

PLUGIN_NAME = "agent-bark-notify"


def _validate_plugin(plugin: str) -> None:
    if plugin != PLUGIN_NAME:
        typer.echo(f"Unknown plugin: {plugin}", err=True)
        raise typer.Exit(1)


def codex_snippet() -> str:
    return """# Codex plugin hook file: hooks/hooks.json
{
  "hooks": {
    "PermissionRequest": [
      {
        "command": "ai-assistant agent-bark-notify hook --runtime codex --event approval_needed"
      }
    ],
    "Stop": [
      {
        "command": "ai-assistant agent-bark-notify hook --runtime codex --event completion"
      }
    ]
  }
}
"""


def claude_snippet() -> str:
    return """# Claude Code settings hook snippet
{
  "hooks": {
    "PermissionRequest": [
      {
        "hooks": [
          {
            "type": "command",
            "command": "ai-assistant agent-bark-notify hook --runtime claude --event approval_needed"
          }
        ]
      }
    ],
    "Notification": [
      {
        "hooks": [
          {
            "type": "command",
            "command": "ai-assistant agent-bark-notify hook --runtime claude --event approval_needed"
          }
        ]
      }
    ],
    "Stop": [
      {
        "hooks": [
          {
            "type": "command",
            "command": "ai-assistant agent-bark-notify hook --runtime claude --event completion"
          }
        ]
      }
    ]
  }
}
"""


def install_guide(target: Target) -> str:
    if target == "codex":
        return """Agent-assisted Codex install guide for agent-bark-notify

Paste this into Codex:

Install the qsoyq/ai-assistant plugin marketplace if it is not already installed. Then install or enable agent-bark-notify-codex from that marketplace. Review the hook command before trusting it:

  ai-assistant agent-bark-notify hook --runtime codex --event approval_needed
  ai-assistant agent-bark-notify hook --runtime codex --event completion

Required runtime env:
  BARK_DEVICE_KEY=<your Bark device key>

Manual fallback:
  ai-assistant plugins config-snippet agent-bark-notify --target codex
"""
    return """Agent-assisted Claude Code install guide for agent-bark-notify

Paste this into Claude Code:

Add the qsoyq/ai-assistant plugin marketplace if it is not already installed, install agent-bark-notify, then reload plugins:

  /plugin marketplace add qsoyq/ai-assistant
  /plugin install agent-bark-notify@ai-assistant
  /reload-plugins

Review and trust the hook command only if you accept it:

  ai-assistant agent-bark-notify hook --runtime claude --event approval_needed
  ai-assistant agent-bark-notify hook --runtime claude --event completion

Required runtime env:
  BARK_DEVICE_KEY=<your Bark device key>

Manual fallback:
  ai-assistant plugins config-snippet agent-bark-notify --target claude
"""


@cmd.command("list")
def list_plugins() -> None:
    """List ai-assistant companion plugins."""
    typer.echo("agent-bark-notify\tBark notifications for Codex and Claude Code hooks")


@cmd.command("config-snippet")
def print_config_snippet(
    plugin: str = typer.Argument(..., help="Plugin name, e.g. agent-bark-notify"),
    target: Target = typer.Option(..., "--target", help="Target agent: codex or claude."),
) -> None:
    """Print manual hook configuration for a plugin."""
    _validate_plugin(plugin)
    typer.echo(codex_snippet() if target == "codex" else claude_snippet())


@cmd.command("install-guide")
def print_install_guide(
    plugin: str = typer.Argument(..., help="Plugin name, e.g. agent-bark-notify"),
    target: Target = typer.Option(..., "--target", help="Target agent: codex or claude."),
) -> None:
    """Print instructions for agent-assisted plugin installation."""
    _validate_plugin(plugin)
    typer.echo(install_guide(target))


if __name__ == "__main__":
    cmd()
