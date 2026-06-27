"""Telegram bot reply matching and button click automation."""

from __future__ import annotations

import asyncio
import os
import shutil
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import typer

from ai_assistant.commands import version_callback
from ai_assistant.commands._lazy import print_extras_hint

helptext = """
Telegram bot 自动点击工具。

向指定 bot 发送一条触发消息, 在等待时间内监听回复, 找到包含指定文本的
回复后点击按钮。默认点击命中消息中的第一个按钮; 如果消息有多个按钮,
建议使用 --button-text 精确指定要点击的按钮文本。

这个命令通过 Telegram MTProto 使用你的用户账号登录。首次使用时可能需要
输入 Telegram 验证码; 如果账号开启了 2FA, 还会提示输入 2FA 密码。登录态
保存为本地 session 文件, 后续定时任务可复用。

Session 文件等同于账号登录凭据, 请按敏感文件保护。默认 session 位于用户
state 目录, 也可以通过 --session 指定已有 session 文件, 或用
--export-session / --import-session 在机器之间迁移。

使用示例:
- 发送 /start, 等待包含“签到”的回复, 然后点击第一个按钮:
  ai-assistant tg-bot-click @example_bot --trigger /start --match 签到
- 使用环境变量提供 Telegram 凭据:
  TG_API_ID=123 TG_API_HASH=xxx TG_PHONE=+8613xxx ai-assistant tg-bot-click @example_bot --match 签到
- 多按钮回复中按按钮文本点击:
  ai-assistant tg-bot-click @example_bot --match 签到 --button-text 签到
- 导出默认 session 文件:
  ai-assistant tg-bot-click --export-session ./telegram.session
- 导入已有 session 到默认位置:
  ai-assistant tg-bot-click --import-session ./telegram.session
"""

_app = typer.Typer(help=helptext)


class TgBotClickError(RuntimeError):
    """User-facing runtime error for tg-bot-click."""


@dataclass(frozen=True)
class ButtonSelection:
    row: int
    column: int
    text: str


@dataclass(frozen=True)
class TelegramCredentials:
    api_id: int
    api_hash: str
    phone: str


def default_session_file(platform: str | None = None) -> Path:
    current_platform = platform or sys.platform
    if current_platform == "win32":
        base = Path(os.environ.get("LOCALAPPDATA") or Path.home() / "AppData" / "Local")
    else:
        base = Path(os.environ.get("XDG_STATE_HOME") or Path.home() / ".local" / "state")
    return base / "ai-assistant" / "telegram" / "tg-bot-click.session"


def resolve_session_file(session: Path | None) -> Path:
    return session.expanduser() if session is not None else default_session_file()


def _same_file(left: Path, right: Path) -> bool:
    return left.expanduser().resolve(strict=False) == right.expanduser().resolve(strict=False)


def copy_session_file(source: Path, destination: Path, *, force: bool = False) -> Path:
    source = source.expanduser()
    destination = destination.expanduser()
    if not source.exists():
        raise TgBotClickError(f"session file does not exist: {source}")
    if not source.is_file():
        raise TgBotClickError(f"session path is not a file: {source}")
    if _same_file(source, destination):
        return destination
    if destination.exists() and not force:
        raise TgBotClickError(f"target session already exists: {destination}; pass --force to overwrite")
    destination.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(source, destination)
    return destination


def validate_bot_username(bot: str | None) -> str:
    if bot is None or not bot.strip():
        raise TgBotClickError("target bot is required unless --import-session or --export-session is used")
    cleaned = bot.strip()
    return cleaned[1:] if cleaned.startswith("@") else cleaned


def require_credentials(api_id: int | None, api_hash: str | None, phone: str | None) -> TelegramCredentials:
    missing: list[str] = []
    if api_id is None:
        missing.append("--api-id or TG_API_ID")
    if not api_hash:
        missing.append("--api-hash or TG_API_HASH")
    if not phone:
        missing.append("--phone or TG_PHONE")
    if missing:
        raise TgBotClickError(f"missing Telegram credential option(s): {', '.join(missing)}")
    assert api_id is not None
    assert api_hash is not None
    assert phone is not None
    return TelegramCredentials(api_id=api_id, api_hash=api_hash, phone=phone)


def require_match_text(match_text: str | None) -> str:
    if match_text is None or match_text == "":
        raise TgBotClickError("--match is required unless --import-session or --export-session is used")
    return match_text


def button_label(button: object) -> str:
    return str(getattr(button, "text", button))


def select_button(buttons: Any, button_text: str | None = None) -> ButtonSelection:
    if not buttons:
        raise TgBotClickError("matched reply has no clickable buttons")
    first: ButtonSelection | None = None
    for row_index, row in enumerate(buttons):
        for column_index, button in enumerate(row):
            label = button_label(button)
            selection = ButtonSelection(row=row_index, column=column_index, text=label)
            if first is None:
                first = selection
            if button_text is not None and label == button_text:
                return selection
    if button_text is not None:
        raise TgBotClickError(f"matched reply has no button with text: {button_text}")
    if first is None:
        raise TgBotClickError("matched reply has no clickable buttons")
    return first


def message_text(message: object) -> str:
    return str(getattr(message, "raw_text", None) or getattr(message, "text", "") or "")


def _import_telethon() -> tuple[type[Any], type[Exception]]:
    try:
        from telethon import TelegramClient
        from telethon.errors import SessionPasswordNeededError
    except ModuleNotFoundError as exc:
        print_extras_hint(
            command_label="tg-bot-click",
            entry_invocation="ai-assistant tg-bot-click",
            extra="telegram",
            exc=exc,
        )
        raise typer.Exit(code=1) from exc
    return TelegramClient, SessionPasswordNeededError


async def _ensure_authorized(client: Any, phone: str, session_password_needed_error: type[Exception]) -> None:
    await client.connect()
    if await client.is_user_authorized():
        return

    await client.send_code_request(phone)
    code = typer.prompt("Telegram verification code")
    try:
        await client.sign_in(phone=phone, code=code)
    except session_password_needed_error:
        password = typer.prompt("Telegram 2FA password", hide_input=True)
        await client.sign_in(password=password)


async def _send_wait_click(
    client: Any,
    *,
    bot: str,
    trigger: str,
    match_text: str,
    timeout: float,
    button_text: str | None,
) -> ButtonSelection:
    try:
        async with client.conversation(bot, timeout=timeout, total_timeout=timeout, exclusive=False) as conv:
            await conv.send_message(trigger)
            while True:
                message = await conv.get_response()
                if match_text not in message_text(message):
                    continue
                selection = select_button(getattr(message, "buttons", None), button_text)
                result = await message.click(selection.row, selection.column)
                if isinstance(result, str) and result.startswith(("http://", "https://", "tg://")):
                    raise TgBotClickError("matched button is a URL/WebApp-style button; browser automation is out of scope")
                return selection
    except asyncio.TimeoutError as exc:
        raise TgBotClickError(f"timed out after {timeout:g}s waiting for a reply containing: {match_text}") from exc


async def _run_click(
    *,
    bot: str,
    trigger: str,
    match_text: str,
    timeout: float,
    button_text: str | None,
    session_file: Path,
    credentials: TelegramCredentials,
) -> ButtonSelection:
    TelegramClient, SessionPasswordNeededError = _import_telethon()
    session_file.parent.mkdir(parents=True, exist_ok=True)
    client = TelegramClient(str(session_file), credentials.api_id, credentials.api_hash)
    try:
        await _ensure_authorized(client, credentials.phone, SessionPasswordNeededError)
        return await _send_wait_click(
            client,
            bot=bot,
            trigger=trigger,
            match_text=match_text,
            timeout=timeout,
            button_text=button_text,
        )
    finally:
        await client.disconnect()


def _fail(message: str) -> None:
    typer.echo(f"Error: {message}", err=True)
    raise typer.Exit(code=1)


@_app.command(name="tg-bot-click", help=helptext, short_help="Telegram bot 自动点击工具。", no_args_is_help=True)
def main(
    ctx: typer.Context,
    _: bool = typer.Option(False, "--version", "-v", "-V", callback=version_callback),
    bot: str | None = typer.Argument(None, help="目标 Telegram bot 用户名, 可带或不带 @。导入/导出 session 时可省略。"),
    trigger: str = typer.Option("/start", "--trigger", help="发送给 bot 的触发语, 默认 /start。"),
    match_text: str | None = typer.Option(None, "--match", help="待匹配的回复文本; 命中条件为回复正文包含该文本。"),
    timeout: float = typer.Option(30.0, "--timeout", min=0.1, help="等待匹配回复的总超时时间, 秒。"),
    button_text: str | None = typer.Option(None, "--button-text", help="可选按钮文本。未指定时点击命中消息中的第一个按钮。"),
    api_id: int | None = typer.Option(None, "--api-id", envvar="TG_API_ID", help="Telegram API ID, 也可通过 TG_API_ID 提供。"),
    api_hash: str | None = typer.Option(None, "--api-hash", envvar="TG_API_HASH", help="Telegram API hash, 也可通过 TG_API_HASH 提供。"),
    phone: str | None = typer.Option(None, "--phone", envvar="TG_PHONE", help="Telegram 账号手机号, 也可通过 TG_PHONE 提供。"),
    session: Path | None = typer.Option(None, "--session", envvar="TG_SESSION", help="Telegram session 文件路径; 默认使用用户 state 目录。"),
    export_session: Path | None = typer.Option(None, "--export-session", help="把当前 --session 或默认 session 文件复制到指定路径, 用于备份/迁移。"),
    import_session: Path | None = typer.Option(None, "--import-session", help="把已有 session 文件复制到当前 --session 或默认 session 位置。"),
    force: bool = typer.Option(False, "--force", "-f", help="导入/导出 session 时允许覆盖目标文件。"),
) -> None:
    session_file = resolve_session_file(session)
    try:
        if import_session is not None and export_session is not None:
            raise TgBotClickError("--import-session and --export-session cannot be used together")
        if import_session is not None:
            copied = copy_session_file(import_session, session_file, force=force)
            typer.echo(f"Imported Telegram session to: {copied}")
            typer.echo("Treat this session file as a sensitive account credential.")
            return
        if export_session is not None:
            copied = copy_session_file(session_file, export_session, force=force)
            typer.echo(f"Exported Telegram session to: {copied}")
            typer.echo("Treat this exported session file as a sensitive account credential.")
            return
        if bot is None:
            typer.echo(ctx.get_help())
            return

        target_bot = validate_bot_username(bot)
        credentials = require_credentials(api_id, api_hash, phone)
        required_match = require_match_text(match_text)
        selection = asyncio.run(
            _run_click(
                bot=target_bot,
                trigger=trigger,
                match_text=required_match,
                timeout=timeout,
                button_text=button_text,
                session_file=session_file,
                credentials=credentials,
            )
        )
    except TgBotClickError as exc:
        _fail(str(exc))

    typer.echo(f"Clicked button: {selection.text}")


app = _app
cmd = typer.main.get_command(app)
