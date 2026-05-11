import importlib.metadata

import typer


def version_callback(ctx: typer.Context, value: bool) -> None:
    """根据调用入口显示命令名, 版本号统一来自 ai-assistant 包。"""
    if not value:
        return
    name = ctx.find_root().info_name or "ai-assistant"
    version = importlib.metadata.version("ai-assistant")
    typer.echo(f"{name} cli version: {version}")
    raise typer.Exit(0)


def default_invoke_without_command(
    _: bool = typer.Option(False, "--version", "-v", "-V", callback=version_callback),
): ...


def make_typer(help: str, **kwargs) -> typer.Typer:
    """Build a Typer with the standard `--version` callback wired up.

    Most subcommand modules need exactly this shape; using the helper avoids
    the 5-line `add_default_invoke` boilerplate they would otherwise repeat.
    Pass extra `typer.Typer` kwargs (e.g. `cls=...`) through `**kwargs`.
    """
    app = typer.Typer(help=help, **kwargs)
    app.callback(invoke_without_command=True)(default_invoke_without_command)
    return app
