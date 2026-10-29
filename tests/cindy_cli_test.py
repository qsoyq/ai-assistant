"""CLI contract and real PTY coverage, without touching real installs or data."""

from __future__ import annotations

import json
import os
import re
import select
import subprocess
import sys
import time
from pathlib import Path

import pytest
import typer
from typer.testing import CliRunner

from ai_assistant.commands.cindy import cmd
from ai_assistant.commands.cindy.archive import create_backup
from ai_assistant.commands.cindy.paths import profile_for

COMMANDS = [
    [],
    ["cshare-to-markdown"],
    ["data"],
    *[["data", name] for name in ("backup", "verify", "restore", "reset", "list", "prune", "clear", "recover")],
    *[[name] for name in ("install", "installs", "releases", "uninstall", "recover")],
]


@pytest.mark.parametrize("width", [80, 120])
@pytest.mark.parametrize("command", COMMANDS)
def test_all_help_is_chinese_and_available_without_io(command: list[str], width: int):
    result = CliRunner().invoke(cmd, [*command, "--help"], terminal_width=width)
    assert result.exit_code == 0, result.output
    assert re.search(r"[\u4e00-\u9fff]", result.output)
    assert "…" not in result.output


@pytest.mark.parametrize(
    "command,parameter,values",
    [
        (["install"], "--region", ["cn", "global"]),
        (["install"], "--channel", ["release", "beta", "canary"]),
        (["install"], "--mode", ["auto", "dmg", "portable", "installer", "user-install"]),
        (["install"], "--source", ["cdn", "github"]),
        (["install"], "--platform", ["darwin", "win32", "linux"]),
        (["install"], "--arch", ["x64", "arm64"]),
        (["data", "backup"], "--compress", ["auto", "none", "zstd", "gzip"]),
        (["data", "backup"], "--region", ["cn", "global", "dev"]),
    ],
)
def test_enum_values_in_explicit_parameter_help(command: list[str], parameter: str, values: list[str]):
    from typer.core import TyperGroup, TyperOption

    click_command = typer.main.get_command(cmd)
    for name in command:
        assert isinstance(click_command, TyperGroup)
        with click_command.make_context("test", [], resilient_parsing=True) as context:
            selected = click_command.get_command(context, name)
            assert selected is not None
            click_command = selected
    parameter_object = next(item for item in click_command.params if parameter in item.opts)
    assert isinstance(parameter_object, TyperOption)
    text = parameter_object.help
    assert text is not None
    assert "可选值" in text
    for value in values:
        assert value in text
    result = CliRunner().invoke(cmd, [*command, "--help"], terminal_width=80)
    compact = re.sub(r"\s+", "", result.output)
    for value in values:
        assert value in compact


@pytest.mark.parametrize("command", [["data", "restore"], ["data", "clear"], ["data", "clear", "--select"]])
def test_non_tty_interaction_rejected_before_any_write(tmp_path: Path, command: list[str]):
    result = CliRunner().invoke(cmd, command, env={"HOME": str(tmp_path), "AI_ASSISTANT_CINDY_HOME": str(tmp_path / "state")})
    assert result.exit_code == 2, result.output
    assert "TTY" in result.output
    assert not (tmp_path / "state").exists()


def test_parameter_errors_before_network_or_writes(tmp_path: Path):
    cases = [
        ["install", "--region", "dev"],
        ["install", "--region", "cn", "--download-only", "--dest", str(tmp_path / "app")],
        ["install", "--region", "cn", "--download-only", "--allow-signature-only"],
        ["install", "--region", "global", "--platform", "windows", "--arch", "amd64"],
    ]
    for args in cases:
        result = CliRunner().invoke(cmd, args, env={"HOME": str(tmp_path), "AI_ASSISTANT_CINDY_HOME": str(tmp_path / "state")})
        assert result.exit_code in {2, 5}, result.output
    assert not (tmp_path / "state").exists()


def test_installs_read_only_with_empty_state(tmp_path: Path):
    result = CliRunner().invoke(cmd, ["installs", "--json"], env={"HOME": str(tmp_path), "AI_ASSISTANT_CINDY_HOME": str(tmp_path / "state")})
    assert result.exit_code == 0
    assert json.loads(result.output)["result"]["installs"] == []
    assert not (tmp_path / "state").exists()


def run_pty(args: list[str], home: Path, answer: bytes) -> tuple[int, str]:
    import pty

    master, slave = pty.openpty()
    env = {**os.environ, "HOME": str(home), "AI_ASSISTANT_CINDY_HOME": str(home / "state"), "AI_ASSISTANT_CINDY_TUI": "plain", "TERM": "dumb"}
    process = subprocess.Popen([sys.executable, "-c", "from ai_assistant.commands.cindy import cmd;cmd()", *args], stdin=slave, stdout=slave, stderr=slave, env=env)
    os.close(slave)
    chunks = []
    deadline = time.monotonic() + 15
    os.write(master, answer)
    try:
        while time.monotonic() < deadline:
            ready, _, _ = select.select([master], [], [], 0.1)
            if ready:
                try:
                    block = os.read(master, 65536)
                except OSError:
                    break
                if not block:
                    break
                chunks.append(block)
            elif process.poll() is not None:
                break
        if process.poll() is None:
            process.wait(timeout=2)
        return process.returncode, b"".join(chunks).decode("utf-8", errors="replace")
    finally:
        if process.poll() is None:
            process.kill()
            process.wait(timeout=5)
        os.close(master)


@pytest.mark.skipif(os.name != "posix", reason="Real POSIX PTY; Windows needs ConPTY acceptance")
@pytest.mark.parametrize("answer,deleted", [(b"wrong\n", False), (b"delete 1\n", True)])
def test_clear_real_terminal_confirmation(tmp_path: Path, answer: bytes, deleted: bool):
    root = tmp_path / "fixture"
    root.mkdir()
    (root / "synthetic").write_text("fixture")
    archive, _ = create_backup(profile_for(root, "cn"), tmp_path / "state/backups", compression="none")
    result, output = run_pty(["data", "clear"], tmp_path, answer)
    assert result == 0, output
    assert archive.exists() is not deleted
    index = json.loads((tmp_path / "state/backups/index.json").read_text())["records"]
    assert (archive.name in index) is not deleted


@pytest.mark.skipif(os.name != "posix", reason="Real POSIX PTY")
def test_restore_picker_cancel_is_no_write(tmp_path: Path):
    root = tmp_path / "fixture"
    root.mkdir()
    (root / "synthetic").write_text("fixture")
    archive, _ = create_backup(profile_for(root, "cn"), tmp_path / "state/backups", compression="none")
    result, output = run_pty(["data", "restore"], tmp_path, b"\n")
    assert result == 0, output
    assert "已取消" in output
    assert archive.exists() and (root / "synthetic").read_text() == "fixture"
    assert not (tmp_path / "state/journal").exists()
