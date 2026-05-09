import os
from typing import List, Optional, Tuple

import typer

from ai_assistant.commands import version_callback

helptext = """
从 github.com/USER/TOOL 拉取并 uvx 运行的薄壳。

用法:
  uvx-gh \\[uvx-options...] \\[--user X] TOOL\\[@REF] \\[tool-args...]

后缀语义:
  TOOL@latest  → 自动追加 --refresh
  TOOL@REF     → 作为 git ref 拼到 URL (tag / branch / sha)
"""

# uvx 中"独立 token 取值"的选项白名单（不带 = 时会吃下一个 argv）。
# 用户可用 `--flag=value` 形式绕过白名单；当 uv 加新选项时维护这里即可。
UVX_VALUE_FLAGS = frozenset(
    {
        "--from",
        "--with",
        "--with-editable",
        "--with-requirements",
        "--python",
        "-p",
        "--refresh-package",
        "--reinstall-package",
        "--upgrade-package",
        "-P",
        "--no-build-package",
        "--no-binary-package",
        "--index",
        "--default-index",
        "--index-url",
        "--extra-index-url",
        "--find-links",
        "--cache-dir",
        "--config-file",
        "--directory",
        "--project",
        "--exclude-newer",
        "--index-strategy",
        "--keyring-provider",
        "--resolution",
        "--prerelease",
        "--link-mode",
        "--color",
    }
)


cmd = typer.Typer(
    help=helptext,
    context_settings={
        "ignore_unknown_options": True,
        "allow_extra_args": True,
        "help_option_names": ["-h", "--help"],
    },
)


def split_argv(argv: List[str]) -> Tuple[List[str], Optional[str], List[str]]:
    """把透传过来的 argv 拆成 (uvx_flags, tool_spec, tool_args)。

    第一个非 flag (或 -- 之后的第一个) token 视为 tool_spec, 其后全部归 tool_args。
    含 `=` 的 flag 当成单 token, 不查白名单。
    """
    flags: List[str] = []
    i = 0
    while i < len(argv):
        a = argv[i]
        if a == "--":
            tool_spec = argv[i + 1] if i + 1 < len(argv) else None
            tail = argv[i + 2 :] if tool_spec is not None else []
            return flags, tool_spec, tail
        if not a.startswith("-"):
            return flags, a, argv[i + 1 :]
        if "=" in a or a not in UVX_VALUE_FLAGS:
            flags.append(a)
            i += 1
            continue
        if i + 1 >= len(argv):
            typer.echo(f"uvx-gh: {a} requires a value", err=True)
            raise typer.Exit(1)
        flags.extend([a, argv[i + 1]])
        i += 2
    return flags, None, []


def build_uvx_cmd(user: str, argv: List[str]) -> List[str]:
    """根据 user 和透传 argv 构造最终要执行的 uvx 命令向量。"""
    flags, tool_spec, tool_args = split_argv(argv)

    if not tool_spec:
        typer.echo(
            "Usage: uvx-gh [uvx-options...] [--user X] <tool>[@<ref>] [tool-args...]",
            err=True,
        )
        raise typer.Exit(1)

    tool, _, ref = tool_spec.partition("@")
    from_url = f"git+https://github.com/{user}/{tool}"
    if ref == "latest":
        flags.append("--refresh")
    elif ref:
        from_url = f"{from_url}@{ref}"

    return ["uvx", *flags, "--from", from_url, tool, *tool_args]


@cmd.callback(invoke_without_command=True)
def main(
    ctx: typer.Context,
    user: str = typer.Option("qsoyq", "--user", help="GitHub user/org"),
    _version: bool = typer.Option(
        False,
        "--version",
        "-v",
        "-V",
        callback=version_callback,
        help="打印命令版本并退出（不会透传给 uvx）",
        is_eager=True,
    ),
) -> None:
    """从 github.com/<user>/<tool> 拉取并 uvx 运行。"""
    if ctx.invoked_subcommand is not None:
        return

    cmd_vec = build_uvx_cmd(user, list(ctx.args))
    try:
        os.execvp(cmd_vec[0], cmd_vec)
    except FileNotFoundError as exc:
        typer.echo(f"uvx-gh: 未找到可执行文件 {cmd_vec[0]!r}, 请先安装 uv ({exc})", err=True)
        raise typer.Exit(127) from exc


if __name__ == "__main__":
    cmd()
