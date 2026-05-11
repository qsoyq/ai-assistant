from pathlib import Path

import typer

from ai_assistant.commands import httpx_disable_verify, make_typer, requests_disable_verify

helptext = """
聚合命令：同时管理 httpx 和 requests 的 SSL verify 禁用补丁。

等价于依次执行：
  ai-assistant httpx-disable-verify <subcommand> [options]
  ai-assistant requests-disable-verify <subcommand> [options]

参数与底层两个命令完全一致，会按顺序转发给二者。任一子命令的非 0 退出码
都会被聚合，返回值取最大值；但前一个失败不会中断后一个的执行。
"""

cmd = make_typer(helptext)


def _run(label: str, func, **kwargs) -> int:
    typer.echo(f"=== {label} ===")
    try:
        func(**kwargs)
    except typer.Exit as exc:
        return int(exc.exit_code or 0)
    return 0


@cmd.command()
def install(
    target: Path | None = typer.Option(
        None,
        "--target",
        "-t",
        help="自定义 .pth 写入目录，默认使用 site.getsitepackages()[0]",
        file_okay=False,
        dir_okay=True,
    ),
    yes: bool = typer.Option(False, "--yes", "-y", help="跳过确认提示直接写入"),
):
    """同时安装 httpx 和 requests 的 .pth 补丁。

    Usage examples::

        ai-assistant disable-ssl-verify install
        ai-assistant disable-ssl-verify install --yes
        ai-assistant disable-ssl-verify install --target ./custom-site-packages
    """
    code1 = _run("httpx-disable-verify install", httpx_disable_verify.install, target=target, yes=yes)
    code2 = _run("requests-disable-verify install", requests_disable_verify.install, target=target, yes=yes)
    raise typer.Exit(code=max(code1, code2))


@cmd.command()
def uninstall(
    target: Path | None = typer.Option(
        None,
        "--target",
        "-t",
        help="自定义 .pth 所在目录，默认使用 site.getsitepackages()[0]",
        file_okay=False,
        dir_okay=True,
    ),
    quiet: bool = typer.Option(False, "--quiet", "-q", help="文件不存在时静默退出 0"),
):
    """同时移除 httpx 和 requests 的 .pth 补丁。

    Usage examples::

        ai-assistant disable-ssl-verify uninstall
        ai-assistant disable-ssl-verify uninstall --quiet
    """
    code1 = _run("httpx-disable-verify uninstall", httpx_disable_verify.uninstall, target=target, quiet=quiet)
    code2 = _run("requests-disable-verify uninstall", requests_disable_verify.uninstall, target=target, quiet=quiet)
    raise typer.Exit(code=max(code1, code2))


@cmd.command()
def status(
    target: Path | None = typer.Option(
        None,
        "--target",
        "-t",
        help="自定义 .pth 所在目录，默认使用 site.getsitepackages()[0]",
        file_okay=False,
        dir_okay=True,
    ),
):
    """查看 httpx 和 requests 的 .pth 补丁安装状态。

    Usage examples::

        ai-assistant disable-ssl-verify status
    """
    code1 = _run("httpx-disable-verify status", httpx_disable_verify.status, target=target)
    code2 = _run("requests-disable-verify status", requests_disable_verify.status, target=target)
    raise typer.Exit(code=max(code1, code2))


if __name__ == "__main__":
    cmd()
