import sys
from pathlib import Path

import typer

from ai_assistant.commands import make_typer
from ai_assistant.commands._pth_patch import build_pth_content, resolve_target_dir

helptext = """
通过 site-packages 下的 .pth 文件，对当前 Python 解释器全局禁用 httpx 的 SSL verify。

工作原理：
  解释器启动时，site 模块会自动 exec .pth 中以 `import` 开头的行。
  本命令写入的 .pth 在 import httpx 后，对以下入口注入 verify=False：
    - httpx.Client.__init__ / httpx.AsyncClient.__init__
    - httpx._api.request / httpx.request
    - httpx._api.stream / httpx.stream
  覆盖 httpx 0.28.x 全部公共顶层 API（同步 / 异步 / 流式 / get·post·put·...）。

注意：
  - 作用范围是当前解释器看到的 site-packages，会影响该环境内所有 Python 进程。
  - 用户传入的 verify=True 或自定义 SSLContext 会被无声覆盖为 False，请仅在受控环境使用。
"""

cmd = make_typer(helptext)
PTH_FILENAME = "ai_assistant_httpx_disable_verify.pth"

_PATCH_BODY = (
    "def _ai_assistant_httpx_dv_patch():\n"
    "    from functools import wraps\n"
    "    import httpx\n"
    "    def force(o):\n"
    "        @wraps(o)\n"
    "        def w(*a, **k):\n"
    "            k['verify'] = False\n"
    "            try:\n"
    "                return o(*a, **k)\n"
    "            except TypeError as e:\n"
    "                if 'verify' not in str(e):\n"
    "                    raise\n"
    "                k.pop('verify', None)\n"
    "                return o(*a, **k)\n"
    "        return w\n"
    "    httpx.Client.__init__ = force(httpx.Client.__init__)\n"
    "    httpx.AsyncClient.__init__ = force(httpx.AsyncClient.__init__)\n"
    "    httpx._api.request = force(httpx._api.request)\n"
    "    httpx.request = httpx._api.request\n"
    "    httpx._api.stream = force(httpx._api.stream)\n"
    "    httpx.stream = httpx._api.stream\n"
    "try:\n"
    "    _ai_assistant_httpx_dv_patch()\n"
    "except ImportError:\n"
    "    pass\n"
    "finally:\n"
    "    del _ai_assistant_httpx_dv_patch\n"
)


def _build_pth_content() -> str:
    return build_pth_content(_PATCH_BODY)


def _resolve_target_dir(target: Path | None) -> Path:
    return resolve_target_dir(target)


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
    """将 .pth 补丁安装到当前解释器的 site-packages。

    Usage examples::

        ai-assistant httpx-disable-verify install
        ai-assistant httpx-disable-verify install --yes
        ai-assistant httpx-disable-verify install --target ./custom-site-packages
    """
    try:
        import httpx  # noqa: F401
    except ImportError as exc:
        typer.echo(f"未检测到 httpx，请先安装: pip install httpx ({exc})", err=True)
        raise typer.Exit(code=1) from exc

    target_dir = _resolve_target_dir(target)
    pth_path = target_dir / PTH_FILENAME

    typer.echo(f"目标 .pth 路径: {pth_path}")
    typer.echo(f"当前解释器: {sys.executable}")

    already_exists = pth_path.exists()

    if not yes and not typer.confirm("确认写入并禁用 httpx verify？", default=False):
        typer.echo("已取消。")
        raise typer.Exit(code=0)

    pth_path.write_text(_build_pth_content(), encoding="utf-8")
    typer.echo(f"已{'覆盖' if already_exists else '安装'}: {pth_path}")


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
    """移除 site-packages 下的 .pth 补丁。

    Usage examples::

        ai-assistant httpx-disable-verify uninstall
        ai-assistant httpx-disable-verify uninstall --quiet
    """
    target_dir = _resolve_target_dir(target)
    pth_path = target_dir / PTH_FILENAME

    if not pth_path.exists():
        if quiet:
            raise typer.Exit(code=0)
        typer.echo(f"pth 不存在: {pth_path}", err=True)
        raise typer.Exit(code=1)

    if not pth_path.is_file():
        typer.echo(f"pth 路径不是文件: {pth_path}", err=True)
        raise typer.Exit(code=2)

    pth_path.unlink()
    typer.echo(f"已卸载: {pth_path}")


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
    """查看 .pth 补丁是否已安装及其内容。

    Usage examples::

        ai-assistant httpx-disable-verify status
    """
    target_dir = _resolve_target_dir(target)
    pth_path = target_dir / PTH_FILENAME

    typer.echo(f"目标 .pth 路径: {pth_path}")
    typer.echo(f"当前解释器: {sys.executable}")

    if not pth_path.exists():
        typer.echo("状态: 未安装")
        raise typer.Exit(code=0)

    typer.echo("状态: 已安装")
    typer.echo("--- 内容 ---")
    typer.echo(pth_path.read_text(encoding="utf-8").rstrip())


if __name__ == "__main__":
    cmd()
