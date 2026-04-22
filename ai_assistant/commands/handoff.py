import sys

import typer

from ai_assistant.commands import default_invoke_without_command

helptext = """
macOS Handoff 操作工具
"""

cmd = typer.Typer(help=helptext)


def add_default_invoke():
    for _cmd in (cmd,):
        _cmd.callback(invoke_without_command=True)(default_invoke_without_command)


add_default_invoke()


def _get_dock_pid() -> int | None:
    from Cocoa import NSWorkspace

    for app in NSWorkspace.sharedWorkspace().runningApplications():
        if app.bundleIdentifier() == "com.apple.dock":
            return int(app.processIdentifier())
    return None


def _find_handoff_item():
    from ApplicationServices import (
        AXUIElementCopyAttributeValue,
        AXUIElementCreateApplication,
        kAXChildrenAttribute,
        kAXSubroleAttribute,
    )

    pid = _get_dock_pid()
    if pid is None:
        return None

    dock = AXUIElementCreateApplication(pid)

    def walk(element):
        err, sub = AXUIElementCopyAttributeValue(element, kAXSubroleAttribute, None)
        if err == 0 and sub == "AXHandoffDockItem":
            return element
        err, kids = AXUIElementCopyAttributeValue(element, kAXChildrenAttribute, None)
        if err == 0 and kids:
            for k in kids:
                found = walk(k)
                if found is not None:
                    return found
        return None

    err, children = AXUIElementCopyAttributeValue(dock, kAXChildrenAttribute, None)
    if err != 0 or not children:
        return None

    for child in children:
        found = walk(child)
        if found is not None:
            return found
    return None


@cmd.command()
def website():
    """点击 Dock 中的 Handoff 图标, 把 iPhone 当前网页接到 Mac

    使用示例:
    - `ai-assistant handoff website`

    前置条件:
    - 系统设置 → 隐私与安全性 → 辅助功能 中授权运行此命令的终端
    - iPhone 上对应 app 的网页处于活跃状态, 且 Mac Dock 中已出现 Handoff 图标
    """
    if sys.platform != "darwin":
        typer.echo("仅支持 macOS", err=True)
        raise typer.Exit(2)

    from ApplicationServices import AXIsProcessTrusted, AXUIElementPerformAction, kAXPressAction

    if not AXIsProcessTrusted():
        typer.echo("缺少辅助功能权限, 请到 系统设置 → 隐私与安全性 → 辅助功能 授权当前终端", err=True)
        raise typer.Exit(3)

    elem = _find_handoff_item()
    if elem is None:
        typer.echo("No Handoff item in Dock right now.", err=True)
        raise typer.Exit(1)

    err = AXUIElementPerformAction(elem, kAXPressAction)
    if err != 0:
        typer.echo(f"AXPress 失败, 错误码: {err}", err=True)
        raise typer.Exit(1)


if __name__ == "__main__":
    cmd()
