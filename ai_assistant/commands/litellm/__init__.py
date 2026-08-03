"""LiteLLM gateway commands."""

from __future__ import annotations

from ai_assistant.commands import make_typer
from ai_assistant.commands.litellm.probe_chat_models import cmd as probe_chat_models_cmd

helptext = """
LiteLLM 网关诊断工具。
"""

cmd = make_typer(helptext)
cmd.add_typer(probe_chat_models_cmd, name="probe-chat-models")


if __name__ == "__main__":
    cmd()
