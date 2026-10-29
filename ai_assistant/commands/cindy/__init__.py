"""Cindy CLI: share conversion, cold snapshots, and verified artifacts."""

from ai_assistant.commands import make_typer

from . import data
from .cshare import (
    CshareError,
    PasswordInvalidOrCorruptError,
    PasswordRequiredError,
    cshare_bytes_to_markdown,
    cshare_to_markdown,
    read_cshare_input,
)
from .install import install, installs, releases, uninstall

helptext = """
Cindy 会话转换、数据备份恢复与客户端安装工具。
"""

cmd = make_typer(helptext, rich_markup_mode=None)
cmd.command("cshare-to-markdown")(cshare_to_markdown)
cmd.add_typer(data.cmd, name="data")
cmd.command("install")(install)
cmd.command("installs")(installs)
cmd.command("releases")(releases)
cmd.command("uninstall")(uninstall)
cmd.command("recover")(data.recover_all)

__all__ = ["CshareError", "PasswordInvalidOrCorruptError", "PasswordRequiredError", "cmd", "cshare_bytes_to_markdown", "read_cshare_input"]
