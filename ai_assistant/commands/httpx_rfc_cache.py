import sys
from pathlib import Path

import typer

from ai_assistant.commands import make_typer
from ai_assistant.commands._pth_patch import (
    build_pth_content,
    check_python_imports,
    inspect_python_site,
    resolve_python,
    resolve_target_dir,
)

helptext = """
通过 site-packages 下的 .pth 文件，为指定 Python 解释器全局启用 httpx 的 RFC 9111 HTTP cache。

工作原理：
  解释器启动时，site 模块会自动 exec .pth 中以 `import` 开头的行。
  本命令写入的 .pth 在 import httpx 和 hishel.httpx 后，对以下入口注入 Hishel cache transport：
    - httpx.Client._init_transport / _init_proxy_transport
    - httpx.AsyncClient._init_transport / _init_proxy_transport

注意：
  - 作用范围是目标解释器看到的 site-packages，会影响该环境内所有 Python 进程。
  - 默认遵循 HTTP cache 标准语义，不会强制缓存非标准或不可缓存响应。
  - 显式传入的自定义 transport 会被保留，不会被本补丁覆盖。
  - 运行时可设置 AI_ASSISTANT_HTTPX_RFC_CACHE_DISABLE=1 临时关闭补丁。
"""

cmd = make_typer(helptext)
PTH_FILENAME = "ai_assistant_httpx_rfc_cache.pth"
DISABLE_ENV = "AI_ASSISTANT_HTTPX_RFC_CACHE_DISABLE"
DEFAULT_CACHE_ROOT = "~/.cache/ai-assistant/httpx-rfc-cache"

_PATCH_BODY = (
    "def _ai_assistant_httpx_rfc_cache_patch():\n"
    "    import hashlib\n"
    "    import inspect\n"
    "    import os\n"
    "    import sys\n"
    "    from pathlib import Path\n"
    "    import httpx\n"
    "    from hishel import AsyncSqliteStorage, SyncSqliteStorage\n"
    "    from hishel.httpx import AsyncCacheTransport, SyncCacheTransport\n"
    "    if getattr(httpx, '_ai_assistant_httpx_rfc_cache_patched', False):\n"
    "        return\n"
    "    disable_env = 'AI_ASSISTANT_HTTPX_RFC_CACHE_DISABLE'\n"
    "    cache_root = os.environ.get('AI_ASSISTANT_HTTPX_RFC_CACHE_DIR', '~/.cache/ai-assistant/httpx-rfc-cache')\n"
    "    cache_key = hashlib.sha256(sys.executable.encode('utf-8')).hexdigest()[:16]\n"
    "    def disabled():\n"
    "        return os.environ.get(disable_env, '').lower() in {'1', 'true', 'yes', 'on'}\n"
    "    def cache_db_path():\n"
    "        cache_dir = Path(cache_root).expanduser() / cache_key\n"
    "        cache_dir.mkdir(parents=True, exist_ok=True)\n"
    "        return cache_dir / 'hishel_cache.db'\n"
    "    def has_explicit_transport(original, self, args, kwargs):\n"
    "        try:\n"
    "            bound = inspect.signature(original).bind_partial(self, *args, **kwargs)\n"
    "        except TypeError:\n"
    "            return kwargs.get('transport') is not None\n"
    "        return bound.arguments.get('transport') is not None\n"
    "    def wrap_sync_transport(transport):\n"
    "        if disabled() or isinstance(transport, SyncCacheTransport):\n"
    "            return transport\n"
    "        return SyncCacheTransport(next_transport=transport, storage=SyncSqliteStorage(database_path=cache_db_path()))\n"
    "    def wrap_async_transport(transport):\n"
    "        if disabled() or isinstance(transport, AsyncCacheTransport):\n"
    "            return transport\n"
    "        return AsyncCacheTransport(next_transport=transport, storage=AsyncSqliteStorage(database_path=cache_db_path()))\n"
    "    orig_sync_init_transport = httpx.Client._init_transport\n"
    "    def sync_init_transport(self, *args, **kwargs):\n"
    "        explicit_transport = has_explicit_transport(orig_sync_init_transport, self, args, kwargs)\n"
    "        transport = orig_sync_init_transport(self, *args, **kwargs)\n"
    "        return transport if explicit_transport else wrap_sync_transport(transport)\n"
    "    orig_sync_init_proxy_transport = httpx.Client._init_proxy_transport\n"
    "    def sync_init_proxy_transport(self, *args, **kwargs):\n"
    "        return wrap_sync_transport(orig_sync_init_proxy_transport(self, *args, **kwargs))\n"
    "    orig_async_init_transport = httpx.AsyncClient._init_transport\n"
    "    def async_init_transport(self, *args, **kwargs):\n"
    "        explicit_transport = has_explicit_transport(orig_async_init_transport, self, args, kwargs)\n"
    "        transport = orig_async_init_transport(self, *args, **kwargs)\n"
    "        return transport if explicit_transport else wrap_async_transport(transport)\n"
    "    orig_async_init_proxy_transport = httpx.AsyncClient._init_proxy_transport\n"
    "    def async_init_proxy_transport(self, *args, **kwargs):\n"
    "        return wrap_async_transport(orig_async_init_proxy_transport(self, *args, **kwargs))\n"
    "    httpx.Client._init_transport = sync_init_transport\n"
    "    httpx.Client._init_proxy_transport = sync_init_proxy_transport\n"
    "    httpx.AsyncClient._init_transport = async_init_transport\n"
    "    httpx.AsyncClient._init_proxy_transport = async_init_proxy_transport\n"
    "    httpx._ai_assistant_httpx_rfc_cache_patched = True\n"
    "try:\n"
    "    _ai_assistant_httpx_rfc_cache_patch()\n"
    "except ImportError:\n"
    "    pass\n"
    "finally:\n"
    "    del _ai_assistant_httpx_rfc_cache_patch\n"
)


def _build_pth_content() -> str:
    return build_pth_content(_PATCH_BODY)


def _resolve_target(target: Path | None, python: Path | None) -> tuple[Path, Path]:
    if target is not None:
        return resolve_python(python), resolve_target_dir(target)

    site_info = inspect_python_site(python)
    return site_info.executable, site_info.site_packages


def _check_dependencies(python: Path | None) -> None:
    missing = check_python_imports(python, ["httpx", "hishel.httpx"])
    if not missing:
        return

    resolved_python = resolve_python(python)
    typer.echo(f"目标解释器缺少依赖: {', '.join(missing)}", err=True)
    typer.echo(f"请先安装: {resolved_python} -m pip install 'hishel[httpx]>=1.3.0'", err=True)
    raise typer.Exit(code=1)


@cmd.command()
def install(
    target: Path | None = typer.Option(
        None,
        "--target",
        "-t",
        help="自定义 .pth 写入目录；未指定时查询 --python 对应的 site-packages",
        file_okay=False,
        dir_okay=True,
    ),
    python: Path | None = typer.Option(
        None,
        "--python",
        "-p",
        help="目标 Python 解释器路径，默认使用当前解释器",
        file_okay=True,
        dir_okay=False,
    ),
    yes: bool = typer.Option(False, "--yes", "-y", help="跳过确认提示直接写入"),
):
    """将 RFC HTTP cache .pth 补丁安装到目标解释器的 site-packages。

    Usage examples::

        ai-assistant httpx-rfc-cache install
        ai-assistant httpx-rfc-cache install --python .venv/bin/python --yes
        ai-assistant httpx-rfc-cache install --target ./custom-site-packages --yes
    """
    _check_dependencies(python)
    target_python, target_dir = _resolve_target(target, python)
    pth_path = target_dir / PTH_FILENAME

    typer.echo(f"目标 .pth 路径: {pth_path}")
    typer.echo(f"目标解释器: {target_python}")
    typer.echo(f"默认缓存目录: {DEFAULT_CACHE_ROOT}/<interpreter-hash>/hishel_cache.db")

    already_exists = pth_path.exists()

    if not yes and not typer.confirm("确认写入并启用 httpx RFC HTTP cache？", default=False):
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
        help="自定义 .pth 所在目录；未指定时查询 --python 对应的 site-packages",
        file_okay=False,
        dir_okay=True,
    ),
    python: Path | None = typer.Option(
        None,
        "--python",
        "-p",
        help="目标 Python 解释器路径，默认使用当前解释器",
        file_okay=True,
        dir_okay=False,
    ),
    quiet: bool = typer.Option(False, "--quiet", "-q", help="文件不存在时静默退出 0"),
):
    """移除 site-packages 下的 RFC HTTP cache .pth 补丁。

    Usage examples::

        ai-assistant httpx-rfc-cache uninstall
        ai-assistant httpx-rfc-cache uninstall --python .venv/bin/python --quiet
    """
    _, target_dir = _resolve_target(target, python)
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
        help="自定义 .pth 所在目录；未指定时查询 --python 对应的 site-packages",
        file_okay=False,
        dir_okay=True,
    ),
    python: Path | None = typer.Option(
        None,
        "--python",
        "-p",
        help="目标 Python 解释器路径，默认使用当前解释器",
        file_okay=True,
        dir_okay=False,
    ),
):
    """查看 RFC HTTP cache .pth 补丁是否已安装及其内容。

    Usage examples::

        ai-assistant httpx-rfc-cache status
        ai-assistant httpx-rfc-cache status --python .venv/bin/python
    """
    target_python, target_dir = _resolve_target(target, python)
    pth_path = target_dir / PTH_FILENAME

    typer.echo(f"目标 .pth 路径: {pth_path}")
    typer.echo(f"目标解释器: {target_python}")
    typer.echo(f"当前解释器: {sys.executable}")

    if not pth_path.exists():
        typer.echo("状态: 未安装")
        raise typer.Exit(code=0)

    typer.echo("状态: 已安装")
    typer.echo("--- 内容 ---")
    typer.echo(pth_path.read_text(encoding="utf-8").rstrip())


if __name__ == "__main__":
    cmd()
