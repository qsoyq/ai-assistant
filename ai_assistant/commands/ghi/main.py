import shutil

import typer

from ai_assistant.commands import version_callback
from ai_assistant.commands.ghi import release

helptext = """
A Wrapper for github cli (https://cli.github.com/).
"""

cmd = typer.Typer(help=helptext)
cmd.add_typer(release.cmd, name="release")


@cmd.callback(invoke_without_command=True)
def _root(
    _: bool = typer.Option(False, "--version", "-v", "-V", callback=version_callback),
):
    if not shutil.which("gh"):
        typer.echo("gh not found, install from https://cli.github.com/", err=True)
        raise typer.Exit(1)


if __name__ == "__main__":
    cmd()
