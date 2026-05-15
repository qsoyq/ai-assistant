"""Tests for win-env: pure helpers (cross-platform) + Windows-only registry round-trip."""

from __future__ import annotations

import os
import sys
import uuid
from pathlib import Path

import pytest
from typer.testing import CliRunner

from ai_assistant.commands import win_env

runner = CliRunner()


# ---------------------------------------------------------------------------
# Pure helpers (cross-platform)
# ---------------------------------------------------------------------------
def test_split_path_drops_empty():
    assert win_env.split_path("") == []
    assert win_env.split_path(";;C:\\a;;C:\\b;") == ["C:\\a", "C:\\b"]


def test_join_path_roundtrip():
    entries = ["C:\\a", "C:\\b", "C:\\c"]
    assert win_env.split_path(win_env.join_path(entries)) == entries


def test_dedup_path_stable_first_wins():
    entries = ["C:\\A", "C:\\b", "c:\\a", "C:\\B\\"]
    out = win_env.dedup_path(entries)
    # First occurrence kept; case/normpath duplicates dropped.
    assert out[0] == "C:\\A"
    # Only first 'a' kept regardless of case.
    keys = [os.path.normcase(os.path.normpath(e)) for e in out]
    assert len(keys) == len(set(keys))


def test_path_contains_case_insensitive():
    entries = ["C:\\Windows\\System32"]
    assert win_env.path_contains(entries, "c:\\windows\\system32")
    assert win_env.path_contains(entries, "C:/Windows/System32/")
    assert not win_env.path_contains(entries, "C:\\Other")


def test_path_remove_drops_matching_entries():
    entries = ["C:\\a", "C:\\b", "c:\\A"]  # last is a dup of first by key
    out = win_env.path_remove(entries, "C:\\A")
    assert out == ["C:\\b"]


def test_render_path_diff_no_change():
    assert win_env.render_path_diff(["C:\\a"], ["C:\\a"]) == "(no change)"


def test_render_path_diff_add_remove():
    out = win_env.render_path_diff(["C:\\a", "C:\\b"], ["C:\\a", "C:\\c"])
    assert "+ C:\\c" in out
    assert "- C:\\b" in out


def test_reg_type_label_known():
    assert win_env.reg_type_label(win_env.REG_SZ) == "REG_SZ"
    assert win_env.reg_type_label(win_env.REG_EXPAND_SZ) == "REG_EXPAND_SZ"
    assert "REG_TYPE(99)" in win_env.reg_type_label(99)


def test_resolve_reg_type_explicit_overrides_existing():
    assert win_env.resolve_reg_type("FOO", win_env.RegTypeOpt.sz, win_env.REG_EXPAND_SZ) == win_env.REG_SZ
    assert win_env.resolve_reg_type("FOO", win_env.RegTypeOpt.expand, win_env.REG_SZ) == win_env.REG_EXPAND_SZ


def test_resolve_reg_type_preserves_existing_when_unspecified():
    assert win_env.resolve_reg_type("FOO", None, win_env.REG_EXPAND_SZ) == win_env.REG_EXPAND_SZ
    assert win_env.resolve_reg_type("FOO", None, win_env.REG_SZ) == win_env.REG_SZ


def test_resolve_reg_type_path_default_expand_when_new():
    assert win_env.resolve_reg_type("PATH", None, None) == win_env.REG_EXPAND_SZ
    assert win_env.resolve_reg_type("path", None, None) == win_env.REG_EXPAND_SZ
    assert win_env.resolve_reg_type("MY_VAR", None, None) == win_env.REG_SZ


def test_default_backup_dir_shape():
    p = win_env.default_backup_dir()
    assert isinstance(p, Path)
    assert "win-env-backup" in str(p)


def test_write_path_backup_creates_file(tmp_path):
    out = win_env.write_path_backup(win_env.WriteScope.user, "C:\\a;C:\\b", tmp_path)
    assert out.exists()
    assert out.read_text(encoding="utf-8") == "C:\\a;C:\\b"
    assert out.name.startswith("PATH-user-")
    assert out.name.endswith(".txt")


# ---------------------------------------------------------------------------
# Non-Windows guard
# ---------------------------------------------------------------------------
@pytest.mark.skipif(sys.platform == "win32", reason="non-Windows guard test")
def test_cli_refuses_on_non_windows():
    result = runner.invoke(win_env.cmd, ["list"])
    assert result.exit_code == 1
    assert "win-env 仅支持 Windows" in result.output


# ---------------------------------------------------------------------------
# Windows-only end-to-end registry round-trip
# ---------------------------------------------------------------------------
pytestmark_win = pytest.mark.skipif(sys.platform != "win32", reason="winreg only on Windows")


@pytest.fixture
def temp_var_name():
    """Unique HKCU\\Environment value name; teardown deletes it unconditionally."""
    name = f"AI_ASSISTANT_TEST_{uuid.uuid4().hex[:12]}"
    yield name
    try:
        win_env.delete_var(win_env.WriteScope.user, name)
    except Exception:
        pass


@pytestmark_win
def test_set_get_unset_roundtrip(temp_var_name):
    name = temp_var_name
    # set
    result = runner.invoke(win_env.cmd, ["set", name, "hello-world"])
    assert result.exit_code == 0, result.output
    # read back via API
    got = win_env.read_var(win_env.WriteScope.user, name)
    assert got is not None
    assert got[0] == "hello-world"
    assert got[1] == win_env.REG_SZ
    # process env updated too
    assert os.environ.get(name) == "hello-world"
    # unset
    result = runner.invoke(win_env.cmd, ["unset", name])
    assert result.exit_code == 0, result.output
    assert win_env.read_var(win_env.WriteScope.user, name) is None
    assert name not in os.environ


@pytestmark_win
def test_set_dry_run_does_not_write(temp_var_name):
    name = temp_var_name
    result = runner.invoke(win_env.cmd, ["set", name, "x", "--dry-run"])
    assert result.exit_code == 0, result.output
    assert "(dry-run" in result.output
    assert win_env.read_var(win_env.WriteScope.user, name) is None


@pytestmark_win
def test_set_preserves_existing_reg_type(temp_var_name):
    name = temp_var_name
    win_env.write_var(win_env.WriteScope.user, name, "%USERPROFILE%\\foo", win_env.REG_EXPAND_SZ)
    result = runner.invoke(win_env.cmd, ["set", name, "%USERPROFILE%\\bar"])
    assert result.exit_code == 0, result.output
    got = win_env.read_var(win_env.WriteScope.user, name)
    assert got is not None
    assert got[1] == win_env.REG_EXPAND_SZ  # type preserved
