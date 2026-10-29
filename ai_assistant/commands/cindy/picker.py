"""Terminal-only selection, with an optional questionary frontend."""

from __future__ import annotations

import os
from typing import Any

import typer
from rich.console import Console
from rich.table import Table

from .common import CindyError, tty_required


def choose(items: list[dict[str, Any]], *, multiple: bool = False) -> list[dict[str, Any]]:
    tty_required()
    if not items:
        raise CindyError("没有可选择的备份。", 5)
    if os.environ.get("AI_ASSISTANT_CINDY_TUI") != "plain":
        try:
            import questionary

            choices = [questionary.Choice(item["display"], value=index, disabled=item.get("disabled") or None) for index, item in enumerate(items)]
            result = questionary.checkbox("选择备份", choices=choices).ask() if multiple else questionary.select("选择备份", choices=choices).ask()
            if result is None:
                return []
            return [items[index] for index in (result if multiple else [result])]
        except ImportError:
            pass
    table = Table("编号", "备份（待完整校验）", "不可选原因")
    for index, item in enumerate(items, 1):
        table.add_row(str(index), item["display"], item.get("disabled", ""))
    Console().print(table)
    try:
        answer = typer.prompt("输入编号（多选用逗号分隔，空回车取消）", default="", show_default=False).strip()
    except (KeyboardInterrupt, typer.Abort):
        return []
    if not answer:
        return []
    try:
        indices = list(dict.fromkeys(int(value.strip()) - 1 for value in answer.split(",")))
        if (not multiple and len(indices) != 1) or any(index < 0 or index >= len(items) or items[index].get("disabled") for index in indices):
            raise ValueError("selection")
    except ValueError as exc:
        raise CindyError("编号无效或对应备份不可选择。", 2) from exc
    return [items[index] for index in indices]


def choose_one(items: list[dict[str, Any]]) -> dict[str, Any] | None:
    result = choose(items)
    return result[0] if result else None


def choose_many(items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return choose(items, multiple=True)
