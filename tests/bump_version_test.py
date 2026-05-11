"""Tests for bump-version: bump logic, surgical TOML rewrite, and CLI flow."""

from pathlib import Path

import pytest
import typer
from typer.testing import CliRunner

from ai_assistant.commands import bump_version

runner = CliRunner()


@pytest.mark.parametrize(
    "version, position, expected",
    [
        ("0.1.0", None, "0.1.1"),
        ("0.1.0", 3, "0.1.1"),
        ("0.1.0", 2, "0.2.0"),
        ("0.1.0", 1, "1.0.0"),
        ("0.1.5", 2, "0.2.0"),
        ("1.2.3.4", None, "1.2.3.5"),
        ("1.2.3.4", 2, "1.3.0.0"),
        ("1.0", 1, "2.0"),
        ("1.0", None, "1.1"),
        ("7", None, "8"),
        ("7", 1, "8"),
    ],
)
def test_bump_version_logic(version, position, expected):
    assert bump_version.bump_version(version, position) == expected


@pytest.mark.parametrize("bad", ["1.0.0a1", "1.0.0.dev0", "1.0.0+local", "v1.0.0", "abc"])
def test_bump_rejects_non_numeric(bad):
    with pytest.raises(typer.BadParameter):
        bump_version.bump_version(bad, None)


@pytest.mark.parametrize("position", [0, 4, -1, 99])
def test_bump_rejects_out_of_range(position):
    with pytest.raises(typer.BadParameter):
        bump_version.bump_version("1.2.3", position)


def test_replace_preserves_formatting_and_comments():
    text = '[build-system]\nrequires = ["hatchling"]\n\n[project]\nname = "demo"  # 项目名\nversion = "0.1.0"  # inline comment\ndescription = "x"\nkeywords = [\n    "a",\n    "b",\n]\n'
    out = bump_version.replace_project_version(text, "0.1.1")
    assert 'version = "0.1.1"  # inline comment\n' in out
    assert 'name = "demo"  # 项目名\n' in out
    assert '[build-system]\nrequires = ["hatchling"]\n' in out
    assert 'keywords = [\n    "a",\n    "b",\n]\n' in out


def test_replace_only_touches_project_version():
    text = '[project]\nname = "demo"\nversion = "0.1.0"\n\n[tool.poetry]\nversion = "9.9.9"\n'
    out = bump_version.replace_project_version(text, "0.1.1")
    assert 'version = "0.1.1"' in out
    assert 'version = "9.9.9"' in out


def test_replace_handles_array_of_tables_project():
    """`[[project]]` is a TOML array-of-tables, not the standard PEP 621 table.

    tomlkit parses it correctly and we should refuse to touch it.
    """
    text = '[[project]]\nversion = "0.1.0"\n'
    with pytest.raises(typer.BadParameter):
        bump_version.replace_project_version(text, "0.1.1")


def test_replace_raises_when_missing():
    text = '[tool.poetry]\nversion = "1.0.0"\n'
    with pytest.raises(typer.BadParameter):
        bump_version.replace_project_version(text, "1.0.1")


def test_read_version_uses_project_table_only():
    text = '[tool.poetry]\nversion = "9.9.9"\n[project]\nname = "demo"\nversion = "0.1.0"\n'
    assert bump_version.read_project_version(text) == "0.1.0"


def _write_pyproject(tmp_path: Path, version: str = "0.1.0") -> Path:
    p = tmp_path / "pyproject.toml"
    p.write_text(f'[project]\nname = "demo"\nversion = "{version}"\n', encoding="utf-8")
    return p


def test_cli_default_bumps_last_segment(tmp_path):
    p = _write_pyproject(tmp_path, "0.1.0")
    result = runner.invoke(bump_version.cmd, ["--path", str(p)])
    assert result.exit_code == 0, result.output
    assert "0.1.0 -> 0.1.1" in result.output
    assert 'version = "0.1.1"' in p.read_text(encoding="utf-8")


def test_cli_position_resets_trailing(tmp_path):
    p = _write_pyproject(tmp_path, "0.1.5")
    result = runner.invoke(bump_version.cmd, ["--path", str(p), "-p", "2"])
    assert result.exit_code == 0, result.output
    assert "0.1.5 -> 0.2.0" in result.output
    assert 'version = "0.2.0"' in p.read_text(encoding="utf-8")


def test_cli_dry_run_does_not_write(tmp_path):
    p = _write_pyproject(tmp_path, "0.1.0")
    before = p.read_text(encoding="utf-8")
    result = runner.invoke(bump_version.cmd, ["--path", str(p), "--dry-run"])
    assert result.exit_code == 0, result.output
    assert "(dry-run" in result.output
    assert p.read_text(encoding="utf-8") == before


def test_cli_missing_file(tmp_path):
    result = runner.invoke(bump_version.cmd, ["--path", str(tmp_path / "nope.toml")])
    assert result.exit_code == 1
    assert "file not found" in result.output


def test_cli_bad_position(tmp_path):
    p = _write_pyproject(tmp_path, "0.1.0")
    result = runner.invoke(bump_version.cmd, ["--path", str(p), "-p", "9"])
    assert result.exit_code != 0
