"""(import_path, extra_name). extra_name=None means dependency is in default install."""

import ast
import importlib
import importlib.util
from functools import lru_cache
from pathlib import Path

import click
import typer
from typer.core import TyperGroup

LazyEntry = tuple[str, str | None]


def print_extras_hint(*, command_label: str, entry_invocation: str, extra: str, exc: BaseException) -> None:
    """Print a friendly install hint when an optional dependency is missing."""
    underlying = getattr(exc, "msg", None) or str(exc)
    typer.echo(
        f"command '{command_label}' requires the optional dependency group '{extra}'.\n"
        f"  install with:  pip install 'ai-assistant[{extra}]'\n"
        f"  or via uvx:    uvx 'ai-assistant[{extra}]' {entry_invocation} ...\n"
        f"  underlying ImportError: {underlying}",
        err=True,
    )


@lru_cache(maxsize=None)
def _extract_short_help(import_path: str) -> str:
    mod_name = import_path.split(":", 1)[0]
    try:
        spec = importlib.util.find_spec(mod_name)
    except (ImportError, ValueError):
        return ""
    if spec is None or spec.origin is None:
        return ""
    try:
        tree = ast.parse(Path(spec.origin).read_text(encoding="utf-8"))
    except (OSError, SyntaxError):
        return ""
    for node in tree.body:
        if not isinstance(node, ast.Assign):
            continue
        if not any(isinstance(t, ast.Name) and t.id == "helptext" for t in node.targets):
            continue
        if not (isinstance(node.value, ast.Constant) and isinstance(node.value.value, str)):
            return ""
        for line in node.value.value.splitlines():
            stripped = line.strip()
            if stripped:
                return stripped
        return ""
    return ""


class LazySubGroup(TyperGroup):
    """Stub group that defers importing the real subcommand module until needed.

    Root `--help` renders this stub by reading `name` and `short_help` only,
    avoiding any module import. Any other interaction (sub-help, parsing,
    invocation) triggers `_resolve()` which imports the real module exactly
    once and delegates the rest of the call lifecycle to it.

    If `extra` is given and the import fails with `ModuleNotFoundError`, the
    stub prints a friendly install hint instead of raising a raw traceback.
    """

    def __init__(
        self,
        *,
        name: str,
        short_help: str,
        import_path: str,
        extra: str | None = None,
    ) -> None:
        super().__init__(name=name, short_help=short_help)
        self._import_path = import_path
        self._extra = extra
        self._real: click.Group | None = None

    def _resolve(self) -> click.Group:
        if self._real is None:
            mod_path, attr = self._import_path.split(":", 1)
            try:
                mod = importlib.import_module(mod_path)
            except ModuleNotFoundError as exc:
                if self._extra is None:
                    raise
                print_extras_hint(
                    command_label=self.name or "",
                    entry_invocation=f"ai-assistant {self.name}",
                    extra=self._extra,
                    exc=exc,
                )
                raise typer.Exit(code=1) from exc
            target = getattr(mod, attr)
            real = target if isinstance(target, click.Group) else typer.main.get_command(target)
            assert isinstance(real, click.Group), f"{self._import_path} did not resolve to a click.Group"
            self._real = real
        return self._real

    def list_commands(self, ctx: click.Context) -> list[str]:
        return self._resolve().list_commands(ctx)

    def get_command(self, ctx: click.Context, cmd_name: str) -> click.Command | None:
        return self._resolve().get_command(ctx, cmd_name)

    def make_context(
        self,
        info_name: str | None,
        args: list[str],
        parent: click.Context | None = None,
        **extra,
    ) -> click.Context:
        return self._resolve().make_context(info_name, args, parent=parent, **extra)

    def invoke(self, ctx: click.Context):
        return self._resolve().invoke(ctx)

    def get_help(self, ctx: click.Context) -> str:
        return self._resolve().get_help(ctx)


class LazyRootGroup(TyperGroup):
    """Root group whose subcommands are described by a registry of `(import_path, extra)`.

    Subclasses populate `lazy_subcommands = {name: ("module.path:attr", extra_or_none)}`.
    On root `--help`, only the AST-extracted short_help is read for each entry —
    no subcommand modules are imported.
    """

    lazy_subcommands: dict[str, LazyEntry] = {}

    def list_commands(self, ctx: click.Context) -> list[str]:
        return sorted({*super().list_commands(ctx), *self.lazy_subcommands})

    def get_command(self, ctx: click.Context, cmd_name: str) -> click.Command | None:
        entry = self.lazy_subcommands.get(cmd_name)
        if entry is None:
            return super().get_command(ctx, cmd_name)
        import_path, extra = entry
        return LazySubGroup(
            name=cmd_name,
            short_help=_extract_short_help(import_path),
            import_path=import_path,
            extra=extra,
        )
