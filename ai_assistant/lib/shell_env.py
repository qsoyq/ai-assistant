"""Evaluate shell exports with Bashkit without inheriting the host environment."""

from __future__ import annotations

import re
from collections.abc import Mapping, Sequence
from pathlib import Path

_NAME = re.compile(r"[A-Za-z_][A-Za-z0-9_]*\Z")


class ShellEnvError(ValueError):
    """An import cannot proceed; messages never contain shell variable values."""


def validate_exports(exports: Mapping[str, str]) -> None:
    """Preflight names and values before touching Windows environment variables."""
    seen: set[str] = set()
    for name, value in exports.items():
        if not _NAME.fullmatch(name):
            raise ShellEnvError("Invalid exported variable name.")
        key = name.upper()
        if key in seen:
            raise ShellEnvError(f"Variable names conflict on Windows: {name}.")
        seen.add(key)
        if "\0" in value:
            raise ShellEnvError(f"Variable {name} contains a NUL character.")
        try:
            units = len(value.encode("utf-16-le")) // 2
        except UnicodeEncodeError:
            raise ShellEnvError(f"Variable {name} contains invalid Unicode.") from None
        if units >= 32767:
            raise ShellEnvError(f"Variable {name} exceeds the Windows environment value limit.")


def parse_initial_env(entries: Sequence[str]) -> dict[str, str]:
    """Parse explicit --env assignments without including values in diagnostics."""
    env: dict[str, str] = {}
    for entry in entries:
        name, separator, value = entry.partition("=")
        if not separator or not _NAME.fullmatch(name):
            raise ShellEnvError("--env requires NAME=VALUE with a valid shell variable name.")
        env[name] = value
    validate_exports(env)
    return env


def evaluate_exports(file: Path, initial_env: Mapping[str, str] | None = None, *, timeout_seconds: float = 10) -> dict[str, str]:
    """Execute Bash-compatible text and return new or changed exported variables.

    The source directory is exposed read-only at /input. Relative source/cat
    reads work there; temporary writes elsewhere stay in Bashkit's virtual FS.
    Only explicitly supplied environment variables are passed into the engine.
    Bashkit is optional and imported only when evaluation is requested.
    """
    from bashkit import Bash, FileSystem

    env = dict(initial_env or {})
    validate_exports(env)
    try:
        source_file = file.resolve()
        # Windows copies of rc files commonly use CRLF. Universal-newline
        # reading restores shell source line endings; evaluated values below
        # are never normalized (including explicit \r escapes in the script).
        with source_file.open(encoding="utf-8-sig") as stream:
            source = stream.read()
    except (OSError, UnicodeError):
        raise ShellEnvError("Cannot read the source file as UTF-8.") from None

    try:
        shell = Bash(env=env, cwd="/input", timeout_seconds=timeout_seconds)
        shell.mount("/input", FileSystem.real(str(source_file.parent), writable=False), read_only=True)
        before = dict(shell.shell_state().env)
        # Fail early on command errors instead of importing a partial evaluation.
        result = shell.execute_sync("set -e\n" + source)
        if result.exit_code != 0 or result.stderr:
            raise ShellEnvError(f"Shell evaluation failed (exit code {result.exit_code}); no variables imported. Shell output is hidden.")
        state = shell.shell_state()
        # Bashkit 0.18.2 leaves env values stale after assigning an already
        # exported variable. env supplies exported names; variables has the
        # latest scalar values, including subsequent export NAME=value writes.
        final_exports = {name: state.variables.get(name, value) for name, value in state.env.items()}
        exports = {name: value for name, value in final_exports.items() if name not in before or before[name] != value}
    except ShellEnvError:
        raise
    except Exception:
        # Native parser/runtime errors may embed source lines and secrets.
        raise ShellEnvError("Shell evaluation failed or exceeded its limits; no variables imported. Shell output is hidden.") from None
    validate_exports(exports)
    return exports
