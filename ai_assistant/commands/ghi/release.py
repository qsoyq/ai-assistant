import shlex
import subprocess
from pathlib import Path

import tomlkit
import typer

from ai_assistant.commands import make_typer

helptext = """
A Wrapper for github cli release command.
"""

cmd = make_typer(helptext)


def _resolve_tag_from_pyproject() -> str:
    config_path = Path("pyproject.toml")
    if not config_path.exists():
        typer.echo("pyproject.toml is not exists.", err=True)
        raise typer.Exit(1)
    doc = tomlkit.parse(config_path.read_text(encoding="utf-8"))

    version: object = None
    project = doc.get("project")
    if isinstance(project, dict):
        version = project.get("version")
    if not isinstance(version, str) or not version:
        tool = doc.get("tool")
        if isinstance(tool, dict):
            poetry = tool.get("poetry")
            if isinstance(poetry, dict):
                version = poetry.get("version")

    if not isinstance(version, str) or not version:
        typer.echo("version is not found in pyproject.toml (looked at project.version and tool.poetry.version)", err=True)
        raise typer.Exit(1)
    return version


def _run(args: list[str], *, verbose: bool) -> subprocess.CompletedProcess[str]:
    if verbose:
        typer.echo(f"cmd: {shlex.join(args)}")
    return subprocess.run(args, capture_output=True, text=True)


@cmd.command()
def create(
    tag: str | None = typer.Option(None, "--tag", help="Tag name, default to pyproject.toml version"),
    title: str = typer.Option("", "-t", "--title", help="Release title"),
    target: str = typer.Option("", "--target", help="Target branch or full commit SHA (default: main branch)"),
    notes: str = typer.Option("", "--notes", "-n", help="Release notes"),
    prerelease: bool = typer.Option(False, "-p", "--prerelease", help="Mark the release as a prerelease"),
    verbose: bool = typer.Option(False, "--verbose"),
):
    """Create a new GitHub Release for a repository."""
    args: list[str] = ["gh", "release", "create"]
    if notes:
        args += ["--notes", notes]
    else:
        args += ["--generate-notes"]
    if prerelease:
        args += ["--prerelease"]
    if target:
        args += ["--target", target]
    if title:
        args += ["-t", title]
    if tag is None:
        tag = _resolve_tag_from_pyproject()
    args += [tag]

    p = _run(args, verbose=verbose)
    if p.returncode != 0:
        typer.echo(p.stderr, err=True)
        raise typer.Exit(p.returncode)
    typer.echo(p.stdout)


@cmd.command()
def delete(
    tag: str | None = typer.Option(None, "--tag", help="Tag name, default to pyproject.toml version"),
    verbose: bool = typer.Option(False, "--verbose"),
    skip_prompt: bool = typer.Option(True, "-y", "--yes", help="Skip the confirmation prompt"),
    delete_tag: bool = typer.Option(True, "--delete-tag/--no-delete-tag", help="Also delete the local and remote git tag"),
):
    """Delete a release."""
    if tag is None:
        tag = _resolve_tag_from_pyproject()
    args: list[str] = ["gh", "release", "delete"]
    if skip_prompt:
        args += ["-y"]
    args += [tag]

    p = _run(args, verbose=verbose)
    if p.returncode != 0:
        typer.echo(p.stderr, err=True)
        raise typer.Exit(p.returncode)
    typer.echo(p.stdout)
    if not delete_tag:
        return

    _run(["git", "tag", "-d", tag], verbose=verbose)
    p = _run(["git", "push", "origin", f":refs/tags/{tag}"], verbose=verbose)
    if p.returncode != 0:
        typer.echo(p.stderr, err=True)
        raise typer.Exit(p.returncode)


if __name__ == "__main__":
    cmd()
