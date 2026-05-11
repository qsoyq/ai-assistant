"""Standalone-script entry wrappers for commands that depend on optional extras.

These wrap each `[project.scripts]` entry that imports an optional dependency at
module top-level, so a missing dep prints the same friendly install hint the
unified `ai-assistant` CLI shows, instead of a raw `ModuleNotFoundError`.
"""

import importlib
import sys

import typer

from ai_assistant.commands._lazy import print_extras_hint


def _run(*, script: str, extra: str, import_path: str) -> None:
    mod_path, attr = import_path.split(":", 1)
    try:
        mod = importlib.import_module(mod_path)
    except ModuleNotFoundError as exc:
        print_extras_hint(
            command_label=script,
            entry_invocation=script,
            extra=extra,
            exc=exc,
        )
        sys.exit(1)
    cmd = getattr(mod, attr)
    if not callable(cmd):
        typer.echo(f"entry '{import_path}' is not callable", err=True)
        sys.exit(1)
    cmd()


def cursor_usage() -> None:
    _run(
        script="ai-assistant-cursor-usage",
        extra="cursor",
        import_path="ai_assistant.commands.cursor.usage:cmd",
    )


def similar_questions() -> None:
    _run(
        script="ai-assistant-similar-questions",
        extra="mcd",
        import_path="ai_assistant.commands.similar_questions:cmd",
    )


def freshrss() -> None:
    _run(
        script="ai-assistant-freshrss",
        extra="freshrss",
        import_path="ai_assistant.commands.automation.freshrss:cmd",
    )
