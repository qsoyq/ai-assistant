from typing import Literal

import typer

from ai_assistant.commands import make_typer

helptext = """
Manage ai-assistant companion plugins.

Available plugins:
  agent-bark-notify  Sends Bark notifications from Codex, Claude Code, and OpenClaw hooks.

Direct install commands:
  codex plugin marketplace add qsoyq/ai-assistant
  codex plugin add agent-bark-notify-codex@ai-assistant
  claude plugin marketplace add qsoyq/ai-assistant
  claude plugin install agent-bark-notify@ai-assistant --scope user
  openclaw plugins install --link ./plugins/agent-bark-notify-openclaw
  openclaw plugins enable agent-bark-notify-openclaw

Install paths:
  1. Manual config:
     ai-assistant plugins config-snippet agent-bark-notify --target codex
     ai-assistant plugins config-snippet agent-bark-notify --target claude
     ai-assistant plugins config-snippet agent-bark-notify --target openclaw
     Add --scope project only when the hook should be local to one project.

  2. Agent-assisted install:
     ai-assistant plugins install-guide agent-bark-notify --target codex
     ai-assistant plugins install-guide agent-bark-notify --target claude
     ai-assistant plugins install-guide agent-bark-notify --target openclaw
     Global scope is the default; project scope remains available with --scope project.

Hooks run local commands. Review the generated hook command and only trust it if you accept it.
"""

cmd = make_typer(helptext)

Target = Literal["codex", "claude", "openclaw"]
Scope = Literal["global", "project"]

PLUGIN_NAME = "agent-bark-notify"
OPENCLAW_CONVERSATION_ACCESS_PATCH = '{"plugins":{"entries":{"agent-bark-notify-openclaw":{"hooks":{"allowConversationAccess":true}}}}}'


def install_commands(scope: Scope = "global") -> str:
    claude_scope = "--scope user" if scope == "global" else "--scope project"
    return f"""Codex:
  codex plugin marketplace add qsoyq/ai-assistant
  codex plugin add agent-bark-notify-codex@ai-assistant

Claude Code:
  claude plugin marketplace add qsoyq/ai-assistant
  claude plugin install agent-bark-notify@ai-assistant {claude_scope}

OpenClaw:
  openclaw plugins install --link ./plugins/agent-bark-notify-openclaw
  openclaw plugins enable agent-bark-notify-openclaw
  openclaw plugins inspect agent-bark-notify-openclaw --runtime --json
"""


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
        "command": "ai-assistant agent-bark-notify hook --runtime codex --event approval_needed --summary-mode extract"
      }
    ],
    "Stop": [
      {
        "command": "ai-assistant agent-bark-notify hook --runtime codex --event completion --summary-mode extract"
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
            "command": "ai-assistant agent-bark-notify hook --runtime claude --event approval_needed --summary-mode extract"
          }
        ]
      }
    ],
    "Notification": [
      {
        "hooks": [
          {
            "type": "command",
            "command": "ai-assistant agent-bark-notify hook --runtime claude --event approval_needed --summary-mode extract"
          }
        ]
      }
    ],
    "Stop": [
      {
        "hooks": [
          {
            "type": "command",
            "command": "ai-assistant agent-bark-notify hook --runtime claude --event completion --summary-mode extract"
          }
        ]
      }
    ]
  }
}
"""
    )


def openclaw_snippet(scope: Scope) -> str:
    location = "global OpenClaw plugin install" if scope == "global" else "project OpenClaw plugin install"
    return (
        f"# {location}\n"
        + f"""openclaw plugins install --link ./plugins/agent-bark-notify-openclaw
openclaw plugins enable agent-bark-notify-openclaw
printf '%s' '{OPENCLAW_CONVERSATION_ACCESS_PATCH}' \\
  | openclaw config patch --stdin
openclaw gateway restart
openclaw plugins inspect agent-bark-notify-openclaw --runtime --json

# The OpenClaw Gateway service must see ai-assistant and Bark env vars.
# If ai-assistant was installed with uv tool, make sure ~/.local/bin is on PATH.
# For launchd/systemd/schtasks services, install the gateway with a wrapper that exports:
#   PATH="$HOME/.local/bin:$PATH"
#   BARK_DEVICE_KEY=<your Bark device key>
# Optional:
#   AI_ASSISTANT_AGENT_BARK_NOTIFY_GROUP_MODE=agent
#   BARK_GROUP=OpenClaw  # fixed group override
#   BARK_SERVER=https://api.day.app
#   AI_ASSISTANT_AGENT_BARK_NOTIFY_AUDIT_LOG=1
#   AI_ASSISTANT_AGENT_BARK_NOTIFY_AUDIT_LOG_FILE=$HOME/.ai-assistant/agent-bark-notify.log

# The plugin registers an agent_end typed hook and forwards it to:
ai-assistant agent-bark-notify hook --runtime openclaw --event completion --summary-mode extract

# Message delivery can be checked directly with:
printf '%s' '{{"source":"openclaw","hook_event_name":"message_sent","success":true,"content":"test","channelId":"telegram","messageId":"test"}}' \\
  | ai-assistant agent-bark-notify hook --runtime openclaw --event completion --summary-mode extract --dry-run
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

Run these commands to add the marketplace and install the Codex plugin:

{install_commands("global").split("Claude Code:", 1)[0].rstrip()}

Then review the hook command before trusting it:

  ai-assistant agent-bark-notify hook --runtime codex --event approval_needed --summary-mode extract
  ai-assistant agent-bark-notify hook --runtime codex --event completion --summary-mode extract

Required runtime env:
  BARK_DEVICE_KEY=<your Bark device key>

Manual fallback:
  ai-assistant plugins config-snippet agent-bark-notify --target codex --scope {scope}
"""
    if target == "openclaw":
        scope_note = (
            "Use a linked local install while validating this repository checkout."
            if scope == "global"
            else "Run the install command from the project that should use this OpenClaw notification plugin."
        )
        return f"""Agent-assisted OpenClaw install guide for agent-bark-notify

Scope: {scope}
{scope_note}

Run these commands from this repository checkout:

OpenClaw:
  openclaw plugins install --link ./plugins/agent-bark-notify-openclaw
  openclaw plugins enable agent-bark-notify-openclaw
  printf '%s' '{OPENCLAW_CONVERSATION_ACCESS_PATCH}' \\
    | openclaw config patch --stdin
  openclaw gateway restart
  openclaw plugins inspect agent-bark-notify-openclaw --runtime --json

Install ai-assistant where the Gateway service can execute it:

  uv tool install --force .
  command -v ai-assistant

Set OpenClaw Gateway service env. If your Gateway runs as launchd/systemd/schtasks,
put env exports in a wrapper and reinstall the service with --wrapper:

  cat > ~/.openclaw/ai-assistant-bark-wrapper.sh <<'SH'
  #!/bin/sh
  export PATH="$HOME/.local/bin:$PATH"
  export BARK_DEVICE_KEY=<your Bark device key>
  # Default group mode is agent. Use project or project-branch to split notifications.
  # export AI_ASSISTANT_AGENT_BARK_NOTIFY_GROUP_MODE=project-branch
  # export BARK_GROUP=OpenClaw  # fixed group override
  # export BARK_SERVER=https://api.day.app
  # export AI_ASSISTANT_AGENT_BARK_NOTIFY_AUDIT_LOG=1
  # export AI_ASSISTANT_AGENT_BARK_NOTIFY_AUDIT_LOG_FILE="$HOME/.ai-assistant/agent-bark-notify.log"
  exec "$@"
  SH
  chmod +x ~/.openclaw/ai-assistant-bark-wrapper.sh
  openclaw gateway install --force --wrapper ~/.openclaw/ai-assistant-bark-wrapper.sh
  openclaw gateway restart

Review and trust the hook command only if you accept it:

  ai-assistant agent-bark-notify hook --runtime openclaw --event completion --summary-mode extract
  ai-assistant agent-bark-notify hook --runtime openclaw --event approval_needed --summary-mode extract

Required runtime env:
  BARK_DEVICE_KEY=<your Bark device key>

Optional runtime env:
  AI_ASSISTANT_AGENT_BARK_NOTIFY_GROUP_MODE=agent
  AI_ASSISTANT_AGENT_BARK_NOTIFY_GROUP_MODE=project
  AI_ASSISTANT_AGENT_BARK_NOTIFY_GROUP_MODE=project-branch
  BARK_GROUP=OpenClaw  # fixed group override
  BARK_SERVER=https://api.day.app
  AI_ASSISTANT_AGENT_BARK_NOTIFY_AUDIT_LOG=1
  AI_ASSISTANT_AGENT_BARK_NOTIFY_AUDIT_LOG_FILE=~/.ai-assistant/agent-bark-notify.log

Verification:
  openclaw --version
  which openclaw
  openclaw gateway status --deep
  openclaw plugins inspect agent-bark-notify-openclaw --runtime --json
  printf '%s' '{{"source":"openclaw","hook_event_name":"message_sent","success":true,"content":"test","channelId":"telegram","messageId":"test"}}' \\
    | ai-assistant agent-bark-notify hook --runtime openclaw --event completion --summary-mode extract --dry-run

In plugin inspect output, confirm the plugin is enabled, runtime hook count is non-zero,
message_sent/agent_end hooks are present, and allowConversationAccess is true.
If openclaw reports a config/CLI version mismatch, fix PATH or reinstall the Gateway
service from the same openclaw binary before testing channel delivery.

Manual fallback:
  ai-assistant plugins config-snippet agent-bark-notify --target openclaw --scope {scope}
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

Run these commands to add the marketplace and install the Claude Code plugin:

Claude Code:
  claude plugin marketplace add qsoyq/ai-assistant
  claude plugin install agent-bark-notify@ai-assistant {scope_flag}

Or paste these slash commands inside Claude Code:

  /plugin marketplace add qsoyq/ai-assistant {scope_flag}
  /plugin install agent-bark-notify@ai-assistant
  /reload-plugins

Review and trust the hook command only if you accept it:

  ai-assistant agent-bark-notify hook --runtime claude --event approval_needed --summary-mode extract
  ai-assistant agent-bark-notify hook --runtime claude --event completion --summary-mode extract

Required runtime env:
  BARK_DEVICE_KEY=<your Bark device key>

Manual fallback:
  ai-assistant plugins config-snippet agent-bark-notify --target claude --scope {scope}
"""


@cmd.command("list")
def list_plugins() -> None:
    """List ai-assistant companion plugins.

    Direct install commands:
      codex plugin marketplace add qsoyq/ai-assistant
      codex plugin add agent-bark-notify-codex@ai-assistant
      claude plugin marketplace add qsoyq/ai-assistant
      claude plugin install agent-bark-notify@ai-assistant --scope user
      openclaw plugins install --link ./plugins/agent-bark-notify-openclaw
      openclaw plugins enable agent-bark-notify-openclaw
    """
    typer.echo(
        f"""agent-bark-notify
  Bark notifications for Codex, Claude Code, and OpenClaw hooks.

Direct install commands:
{install_commands().rstrip()}
"""
    )


@cmd.command("config-snippet")
def print_config_snippet(
    plugin: str = typer.Argument(..., help="Plugin name, e.g. agent-bark-notify"),
    target: Target = typer.Option(..., "--target", help="Target agent: codex, claude, or openclaw."),
    scope: Scope = typer.Option("global", "--scope", help="Config scope: global or project."),
) -> None:
    """Print manual hook configuration for a plugin."""
    _validate_plugin(plugin)
    if target == "codex":
        typer.echo(codex_snippet(scope))
        return
    if target == "claude":
        typer.echo(claude_snippet(scope))
        return
    typer.echo(openclaw_snippet(scope))


@cmd.command("install-guide")
def print_install_guide(
    plugin: str = typer.Argument(..., help="Plugin name, e.g. agent-bark-notify"),
    target: Target = typer.Option(..., "--target", help="Target agent: codex, claude, or openclaw."),
    scope: Scope = typer.Option("global", "--scope", help="Plugin install scope: global or project."),
) -> None:
    """Print instructions for agent-assisted plugin installation."""
    _validate_plugin(plugin)
    typer.echo(install_guide(target, scope))


if __name__ == "__main__":
    cmd()
