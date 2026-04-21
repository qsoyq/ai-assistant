import site
import sys
from pathlib import Path

import typer

from ai_assistant.commands import default_invoke_without_command

helptext = """
通过 site-packages 下的 .pth 文件，对当前 Python 解释器全局禁用 requests 的 SSL verify。

工作原理：
  解释器启动时，site 模块会自动 exec .pth 中以 `import` 开头的行。
  本命令写入的 .pth 在 import requests 后，对以下入口注入 verify=False：
    - requests.Session.__init__   （后置改写 self.verify = False）
    - requests.Session.request    （强制 kwargs['verify'] = False）
  覆盖 requests.get/post/put/... 与 Session.* 全部公共调用路径。
  同时调用 urllib3.disable_warnings(InsecureRequestWarning) 抑制告警轰炸。

注意：
  - 作用范围是当前解释器看到的 site-packages，会影响该环境内所有 Python 进程。
  - 用户传入的 verify=True 或自定义 CA bundle 会被无声覆盖为 False，请仅在受控环境使用。
"""

cmd = typer.Typer(help=helptext)


def add_default_invoke():
    for _cmd in (cmd,):
        _cmd.callback(invoke_without_command=True)(default_invoke_without_command)


add_default_invoke()


PTH_FILENAME = "ai_assistant_requests_disable_verify.pth"

_PATCH_BODY = (
    "def _ai_assistant_requests_dv_patch():\n"
    "    from functools import wraps\n"
    "    import requests\n"
    "    try:\n"
    "        import urllib3\n"
    "        urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)\n"
    "    except Exception:\n"
    "        pass\n"
    "    orig_init = requests.Session.__init__\n"
    "    @wraps(orig_init)\n"
    "    def new_init(self, *a, **k):\n"
    "        orig_init(self, *a, **k)\n"
    "        self.verify = False\n"
    "    requests.Session.__init__ = new_init\n"
    "    orig_request = requests.Session.request\n"
    "    @wraps(orig_request)\n"
    "    def new_request(self, *a, **k):\n"
    "        k['verify'] = False\n"
    "        return orig_request(self, *a, **k)\n"
    "    requests.Session.request = new_request\n"
    "try:\n"
    "    _ai_assistant_requests_dv_patch()\n"
    "except ImportError:\n"
    "    pass\n"
    "finally:\n"
    "    del _ai_assistant_requests_dv_patch\n"
)


def _build_pth_content() -> str:
    payload = repr(_PATCH_BODY)
    return f"import os; exec({payload})\n"


def _resolve_target_dir(target: Path | None) -> Path:
    if target is not None:
        resolved = target.expanduser().resolve()
        if not resolved.exists():
            raise typer.BadParameter(f"目标目录不存在: {resolved}")
        if not resolved.is_dir():
            raise typer.BadParameter(f"目标路径不是目录: {resolved}")
        return resolved

    candidates: list[str] = []
    try:
        candidates.extend(site.getsitepackages())
    except AttributeError:
        pass
    user_site = site.getusersitepackages()
    if user_site:
        candidates.append(user_site)

    if not candidates:
        raise typer.BadParameter("无法确定 site-packages 路径，请通过 --target 显式指定")

    return Path(candidates[0])


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

        ai-assistant requests-disable-verify install
        ai-assistant requests-disable-verify install --yes
        ai-assistant requests-disable-verify install --target ./custom-site-packages
    """
    try:
        import requests  # noqa: F401
    except ImportError as exc:
        typer.echo(f"未检测到 requests，请先安装: pip install requests ({exc})", err=True)
        raise typer.Exit(code=1) from exc

    target_dir = _resolve_target_dir(target)
    pth_path = target_dir / PTH_FILENAME

    typer.echo(f"目标 .pth 路径: {pth_path}")
    typer.echo(f"当前解释器: {sys.executable}")

    if pth_path.exists():
        typer.echo("pth 已存在，请先 uninstall 再重试。", err=True)
        raise typer.Exit(code=1)

    if not yes and not typer.confirm("确认写入并禁用 requests verify？", default=False):
        typer.echo("已取消。")
        raise typer.Exit(code=0)

    pth_path.write_text(_build_pth_content(), encoding="utf-8")
    typer.echo(f"已安装: {pth_path}")


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

        ai-assistant requests-disable-verify uninstall
        ai-assistant requests-disable-verify uninstall --quiet
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

        ai-assistant requests-disable-verify status
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
