from __future__ import annotations

import enum
import json
import logging
import pprint
from typing import Optional

import typer

from ai_assistant.commands import default_invoke_without_command

logger = logging.getLogger(__name__)

helptext = """
从本地浏览器中提取指定域名的 Cookie。

对于指定的单个域名, 会同时读取 . 域名。

例如:
    $ ai-assistant-cookies get github.com
    会同时读取 github.com 和 .github.com 的 Cookie
"""

cmd = typer.Typer(help=helptext)

_TWITTER_DOMAINS = ("x.com", "twitter.com")
_CURSOR_DOMAINS = ("cursor.com", "cursor.sh")


class OutputFormat(str, enum.Enum):
    string = "string"
    dict = "dict"
    json = "json"


def _match_domain(cookie_domain: str, target_domain: str) -> bool:
    """判断 cookie 的域名是否属于 target_domain。

    支持带点前缀的域名匹配，例如 `.example.com` 匹配 `example.com`。
    """
    cookie_domain = cookie_domain.lstrip(".")
    target_domain = target_domain.lstrip(".")
    return cookie_domain == target_domain or cookie_domain.endswith(f".{target_domain}")


def _extract_cookies_for_domain(domain: str) -> dict[str, str]:
    """从本地浏览器提取指定域名的所有 Cookie。"""
    try:
        import browser_cookie3
    except ImportError:
        typer.echo("错误: 未安装 browser_cookie3，请执行: uv pip install browser-cookie3", err=True)
        raise typer.Exit(1)

    browsers = [
        ("arc", browser_cookie3.arc),
        ("chrome", browser_cookie3.chrome),
        ("edge", browser_cookie3.edge),
        ("firefox", browser_cookie3.firefox),
        ("brave", browser_cookie3.brave),
    ]

    bare_domain = domain.lstrip(".")
    domain_variants = [bare_domain, f".{bare_domain}"]

    all_cookies: dict[str, str] = {}
    for name, fn in browsers:
        try:
            for dv in domain_variants:
                jar = fn(domain_name=dv)
                for cookie in jar:
                    cookie_domain = cookie.domain or ""
                    if _match_domain(cookie_domain, bare_domain) and cookie.name and cookie.value:
                        all_cookies[cookie.name] = cookie.value
            if all_cookies:
                logger.debug(f"从 {name} 提取到 {len(all_cookies)} 个 Cookie")
                break
        except Exception as e:
            logger.debug(f"{name} 提取失败: {e}")
            continue

    return all_cookies


def _format_output(cookies: dict[str, str], fmt: OutputFormat, fields: Optional[list[str]] = None) -> str:
    if fields:
        cookies = {k: v for k, v in cookies.items() if k in fields}

    if not cookies:
        return ""

    if fmt == OutputFormat.string:
        return "; ".join(f"{k}={v}" for k, v in cookies.items())
    elif fmt == OutputFormat.dict:
        return pprint.pformat(cookies)
    elif fmt == OutputFormat.json:
        return json.dumps(cookies, ensure_ascii=False, indent=4)
    return ""


FormatOption = typer.Option(
    OutputFormat.string,
    "--format",
    "-f",
    help="输出格式: string (a=b; c=d), dict (Python dict), json (JSON 字符串)",
)

FieldsOption = typer.Option(
    None,
    "--field",
    "-F",
    help="只提取指定名称的 Cookie，可多次使用",
)


@cmd.command()
def get(
    domains: list[str] = typer.Argument(..., help="目标域名，可指定多个，例如 example.com api.example.com"),
    fmt: OutputFormat = FormatOption,
    fields: Optional[list[str]] = FieldsOption,
):
    """从本地浏览器提取指定域名的 Cookie

    Usage::

        # 提取 github.com 的所有 Cookie（默认 string 格式: a=b; c=d）
        $ ai-assistant-cookies get github.com

        # 同时提取多个域名的 Cookie
        $ ai-assistant-cookies get github.com api.github.com

        # 以 JSON 格式输出
        $ ai-assistant-cookies get github.com -f json

        # 以 Python dict 格式输出
        $ ai-assistant-cookies get github.com -f dict

        # 只提取指定字段
        $ ai-assistant-cookies get github.com -F session_id -F user_id
    """
    all_cookies: dict[str, str] = {}
    for domain in domains:
        all_cookies.update(_extract_cookies_for_domain(domain))

    if not all_cookies:
        label = ", ".join(domains)
        typer.echo(f"未从浏览器中找到域名 {label} 的 Cookie", err=True)
        raise typer.Exit(1)
    output = _format_output(all_cookies, fmt, fields)
    if output:
        typer.echo(output)
    else:
        typer.echo("未找到匹配的 Cookie 字段", err=True)
        raise typer.Exit(1)


@cmd.command()
def twitter(
    fmt: OutputFormat = FormatOption,
    fields: Optional[list[str]] = FieldsOption,
):
    """从本地浏览器提取 Twitter/X 的 Cookie

    Usage::

        # 提取所有 Twitter Cookie（默认 string 格式: a=b; c=d）
        $ ai-assistant-cookies twitter

        # 以 JSON 格式输出
        $ ai-assistant-cookies twitter -f json

        # 以 Python dict 格式输出
        $ ai-assistant-cookies twitter -f dict

        # 只提取 auth_token 和 ct0
        $ ai-assistant-cookies twitter -F auth_token -F ct0
    """
    all_cookies: dict[str, str] = {}
    for domain in _TWITTER_DOMAINS:
        all_cookies.update(_extract_cookies_for_domain(domain))

    if not all_cookies:
        typer.echo("未从浏览器中找到 Twitter/X 的 Cookie", err=True)
        typer.echo("请确保已在浏览器中登录 Twitter/X", err=True)
        raise typer.Exit(1)

    output = _format_output(all_cookies, fmt, fields)
    if output:
        typer.echo(output)
    else:
        typer.echo("未找到匹配的 Cookie 字段", err=True)
        raise typer.Exit(1)


@cmd.command()
def cursor(
    fmt: OutputFormat = FormatOption,
    fields: Optional[list[str]] = FieldsOption,
):
    """从本地浏览器提取 Cursor 的 Cookie

    Usage::

        # 提取所有 Cursor Cookie（默认 string 格式: a=b; c=d）
        $ ai-assistant-cookies cursor

        # 以 JSON 格式输出
        $ ai-assistant-cookies cursor -f json

        # 以 Python dict 格式输出
        $ ai-assistant-cookies cursor -f dict

        # 只提取 WorkosCursorSessionToken
        $ ai-assistant-cookies cursor -F WorkosCursorSessionToken
    """
    all_cookies: dict[str, str] = {}
    for domain in _CURSOR_DOMAINS:
        all_cookies.update(_extract_cookies_for_domain(domain))

    if not all_cookies:
        typer.echo("未从浏览器中找到 Cursor 的 Cookie", err=True)
        typer.echo("请确保已在浏览器中登录 cursor.com", err=True)
        raise typer.Exit(1)

    output = _format_output(all_cookies, fmt, fields)
    if output:
        typer.echo(output)
    else:
        typer.echo("未找到匹配的 Cookie 字段", err=True)
        raise typer.Exit(1)


def add_default_invoke():
    for _cmd in (cmd,):
        _cmd.callback(invoke_without_command=True)(default_invoke_without_command)


add_default_invoke()

if __name__ == "__main__":
    cmd()
