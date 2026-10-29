"""Shared CLI contracts; no optional dependencies at import time."""

from __future__ import annotations

import functools
import json
import sys
from enum import Enum
from typing import Any, Callable, TypeVar, cast

import typer


class CindyError(RuntimeError):
    def __init__(self, message: str, code: int = 1):
        super().__init__(message)
        self.code = code


class Region(str, Enum):
    cn = "cn"
    global_ = "global"
    dev = "dev"


class ReleaseRegion(str, Enum):
    cn = "cn"
    global_ = "global"


class Compression(str, Enum):
    auto = "auto"
    none = "none"
    zstd = "zstd"
    gzip = "gzip"


class Channel(str, Enum):
    release = "release"
    beta = "beta"
    canary = "canary"


class Mode(str, Enum):
    auto = "auto"
    dmg = "dmg"
    portable = "portable"
    installer = "installer"
    user_install = "user-install"


class Source(str, Enum):
    cdn = "cdn"
    github = "github"


REGION_HELP = "区域。可选值：cn（中国大陆版）、global（国际版）、dev（开发区域版，不等同于隔离 profile）。"
RELEASE_REGION_HELP = "发行区域。可选值：cn（中国大陆版）、global（国际版）。"
COMPRESSION_HELP = "压缩。可选值：auto（有 zstd 时使用，否则不压缩）、none（不压缩）、zstd（Zstandard）、gzip（Gzip）。默认 auto。"
PLATFORM_HELP = "平台。可选值：darwin（macOS）、win32（Windows）、linux（Linux）。默认本机；别名 mac/macos、win/windows。"
ARCH_HELP = "架构。可选值：x64（64 位 x86）、arm64（64 位 ARM）。默认本机原生架构；别名 intel/amd64/x86_64、aarch64。不支持 Windows/Linux ARM 产物。"
CHANNEL_HELP = "渠道。可选值：release（正式）、beta（测试）、canary（灰度）。latest 时默认 release；不能与显式版本合用。"
MODE_HELP = (
    "模式。可选值：auto（自动）、dmg（macOS）、portable（Windows 便携）、installer（Windows 官方安装器）、user-install（Linux 用户级）。默认 auto：macOS=dmg、Windows=portable、Linux=user-install。"
)
SOURCE_HELP = "来源。可选值：cdn（区域官方 CDN）、github（GitHub Releases 同产物）。默认 cdn；无同类型资产则拒绝。"
MAX_BYTES = 100 * 1024**3
MAX_ENTRIES = 200_000
F = TypeVar("F", bound=Callable[..., Any])


def guarded(function: F) -> F:
    @functools.wraps(function)
    def invoke(*args: Any, **kwargs: Any) -> Any:
        try:
            return function(*args, **kwargs)
        except CindyError as exc:
            typer.echo(str(exc), err=True)
            raise typer.Exit(exc.code) from exc
        except (OSError, ValueError) as exc:
            typer.echo(f"操作失败：{exc}", err=True)
            raise typer.Exit(1) from exc
        except KeyboardInterrupt as exc:
            typer.echo("操作已中断；已开始的事务请运行 cindy recover 检查。", err=True)
            raise typer.Exit(130) from exc

    return cast(F, invoke)


def tty_required() -> None:
    if not sys.stdin.isatty() or not sys.stdout.isatty():
        raise CindyError("需要交互终端（TTY）；restore 请显式提供归档，其他命令可使用 --yes（clear 除外）。", 2)


def confirm(message: str, yes: bool = False) -> bool:
    typer.echo(message)
    if yes:
        return True
    tty_required()
    try:
        result = typer.confirm("确认执行？", default=False)
    except (KeyboardInterrupt, typer.Abort):
        result = False
    if not result:
        typer.echo("已取消，未做任何更改。")
    return result


def emit(value: Any, as_json: bool = False) -> None:
    typer.echo(json.dumps({"format_version": 1, "result": value}, ensure_ascii=False, indent=2, default=str) if as_json else json.dumps(value, ensure_ascii=False, indent=2, default=str))
