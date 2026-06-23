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
     Add --scope project only when the hook should be local to one project.

  2. Agent-assisted install:
     ai-assistant plugins install-guide agent-bark-notify --target codex
     ai-assistant plugins install-guide agent-bark-notify --target claude
     Global scope is the default; project scope remains available with --scope project.

Hooks run local commands. Review the generated hook command and only trust it if you accept it.
"""

cmd = make_typer(helptext)

Target = Literal["codex", "claude"]
Scope = Literal["global", "project"]

PLUGIN_NAME = "agent-bark-notify"


def _validate_plugin(plugin: str) -> None:
    if plugin != PLUGIN_NAME:
        typer.echo(f"Unknown plugin: {plugin}", err=True)
        raise typer.Exit(1)


def codex_snippet(scope: Scope) -> str:
    location = "global Codex plugin hook file" if scope == "global" else "project Codex plugin hook file"
    return (
        f"# {location}: hooks/hooks.json\n"
        + """{
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
    )


def claude_snippet(scope: Scope) -> str:
    location = "global Claude Code settings" if scope == "global" else "project Claude Code settings"
    return (
        f"# {location} hook snippet\n"
        + """{
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
    )


def install_guide(target: Target, scope: Scope) -> str:
    if target == "codex":
        scope_note = (
            "Use the global plugin scope unless you only want this notification hook for one project."
            if scope == "global"
            else "Use project scope only when this notification hook should apply to the current project."
        )
        return f"""Agent-assisted Codex install guide for agent-bark-notify

Scope: {scope}
{scope_note}

Paste this into Codex:

Install the qsoyq/ai-assistant plugin marketplace in {scope} scope if it is not already installed. Then install or enable agent-bark-notify-codex from that marketplace. Review the hook command before trusting it:

  ai-assistant agent-bark-notify hook --runtime codex --event approval_needed
  ai-assistant agent-bark-notify hook --runtime codex --event completion

Required runtime env:
  BARK_DEVICE_KEY=<your Bark device key>

Manual fallback:
  ai-assistant plugins config-snippet agent-bark-notify --target codex --scope {scope}
"""
    scope_flag = "--scope user" if scope == "global" else "--scope project"
    scope_note = (
        "Use the global/user plugin scope unless you only want this notification hook for one project."
        if scope == "global"
        else "Use project scope only when this notification hook should apply to the current project."
    )
    return f"""Agent-assisted Claude Code install guide for agent-bark-notify

Scope: {scope}
{scope_note}

Paste this into Claude Code:

Add the qsoyq/ai-assistant plugin marketplace if it is not already installed, install agent-bark-notify, then reload plugins:

  /plugin marketplace add qsoyq/ai-assistant {scope_flag}
  /plugin install agent-bark-notify@ai-assistant
  /reload-plugins

Review and trust the hook command only if you accept it:

  ai-assistant agent-bark-notify hook --runtime claude --event approval_needed
  ai-assistant agent-bark-notify hook --runtime claude --event completion

Required runtime env:
  BARK_DEVICE_KEY=<your Bark device key>

Manual fallback:
  ai-assistant plugins config-snippet agent-bark-notify --target claude --scope {scope}
"""


@cmd.command("list")
def list_plugins() -> None:
    """List ai-assistant companion plugins."""
    typer.echo("agent-bark-notify\tBark notifications for Codex and Claude Code hooks")


@cmd.command("config-snippet")
def print_config_snippet(
    plugin: str = typer.Argument(..., help="Plugin name, e.g. agent-bark-notify"),
    target: Target = typer.Option(..., "--target", help="Target agent: codex or claude."),
    scope: Scope = typer.Option("global", "--scope", help="Config scope: global or project."),
) -> None:
    """Print manual hook configuration for a plugin."""
    _validate_plugin(plugin)
    typer.echo(codex_snippet(scope) if target == "codex" else claude_snippet(scope))


@cmd.command("install-guide")
def print_install_guide(
    plugin: str = typer.Argument(..., help="Plugin name, e.g. agent-bark-notify"),
    target: Target = typer.Option(..., "--target", help="Target agent: codex or claude."),
    scope: Scope = typer.Option("global", "--scope", help="Plugin install scope: global or project."),
) -> None:
    """Print instructions for agent-assisted plugin installation."""
    _validate_plugin(plugin)
    typer.echo(install_guide(target, scope))


if __name__ == "__main__":
    cmd()
