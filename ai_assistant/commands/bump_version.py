"""Bump the project.version field in the current directory's pyproject.toml."""

import re
from pathlib import Path

import tomlkit
import typer

from ai_assistant.commands import version_callback

helptext = """
对当前目录的 pyproject.toml 的 project.version 加一。

默认对最后一段加一 (例: 0.1.0 -> 0.1.1)。
通过 -p / --position 指定加一的段位 (1-indexed: 1=major, 2=minor, 3=patch)，
被加段位之后的所有段位会重置为 0 (例: -p 2 时 0.1.5 -> 0.2.0)。

使用示例:
- `ai-assistant bump-version`               # 0.1.0 -> 0.1.1
- `ai-assistant bump-version -p 2`          # 0.1.5 -> 0.2.0
- `ai-assistant bump-version -p 1`          # 0.1.5 -> 1.0.0
- `ai-assistant bump-version --dry-run`     # 仅打印, 不写入
"""

cmd = typer.Typer(help=helptext)


_VERSION_RE = re.compile(r"^\d+(?:\.\d+)*$")


def bump_version(version: str, position: int | None) -> str:
    """Return the version string with the chosen segment incremented.

    `position` is 1-indexed. None means the last segment. Segments after the
    bumped one are reset to 0.
    """
    if not _VERSION_RE.match(version):
        raise typer.BadParameter(f"version '{version}' is not a plain dotted-numeric version (e.g. 1.2.3)")
    parts = [int(p) for p in version.split(".")]
    idx = (position - 1) if position is not None else len(parts) - 1
    if idx < 0 or idx >= len(parts):
        raise typer.BadParameter(f"--position {position} is out of range for {len(parts)}-segment version '{version}'")
    parts[idx] += 1
    for j in range(idx + 1, len(parts)):
        parts[j] = 0
    return ".".join(str(p) for p in parts)


def read_project_version(text: str) -> str:
    doc = tomlkit.parse(text)
    project = doc.get("project")
    if project is None or "version" not in project:
        raise typer.BadParameter("pyproject.toml has no [project].version field")
    return str(project["version"])


def replace_project_version(text: str, new_version: str) -> str:
    """Update [project].version, preserving comments, whitespace, and quote styles."""
    doc = tomlkit.parse(text)
    project = doc.get("project")
    if project is None or "version" not in project:
        raise typer.BadParameter("pyproject.toml has no [project].version field")
    project["version"] = new_version
    return str(tomlkit.dumps(doc))


@cmd.callback(invoke_without_command=True)
def main(
    ctx: typer.Context,
    _: bool = typer.Option(False, "--version", "-v", "-V", callback=version_callback),
    position: int | None = typer.Option(
        None,
        "--position",
        "-p",
        help="1-indexed 段位 (1=major, 2=minor, 3=patch)。默认最后一段。",
    ),
    path: Path = typer.Option(
        Path("pyproject.toml"),
        "--path",
        help="pyproject.toml 路径, 默认当前目录的 pyproject.toml。",
    ),
    dry_run: bool = typer.Option(False, "--dry-run", help="仅打印结果, 不写入文件。"),
) -> None:
    if ctx.invoked_subcommand is not None:
        return
    if not path.exists():
        typer.echo(f"file not found: {path}", err=True)
        raise typer.Exit(1)
    text = path.read_text(encoding="utf-8")
    current = read_project_version(text)
    new_version = bump_version(current, position)
    if dry_run:
        typer.echo(f"{current} -> {new_version} (dry-run, {path})")
        return
    new_text = replace_project_version(text, new_version)
    path.write_text(new_text, encoding="utf-8")
    typer.echo(f"{current} -> {new_version} ({path})")


if __name__ == "__main__":
    cmd()
