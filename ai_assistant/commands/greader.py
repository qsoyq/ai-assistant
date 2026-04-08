import functools
import json
import time
from dataclasses import dataclass
from typing import cast
from urllib.parse import quote, urlencode

import httpx
import typer
from rich.console import Console
from rich.table import Table

from ai_assistant.commands import default_invoke_without_command

_CONSOLE = Console()

_STATE_PREFIX = "user/-/state/com.google/"
READING_LIST = f"{_STATE_PREFIX}reading-list"
READ = f"{_STATE_PREFIX}read"
STARRED = f"{_STATE_PREFIX}starred"

helptext = """
Google Reader API 客户端工具

     ┌───────────────────┬──────────────────────────────────────────────────────────┬────────────────────────────────────────────┐
     │      Command      │                       API Endpoint                       │                Description                 │
     ├───────────────────┼──────────────────────────────────────────────────────────┼────────────────────────────────────────────┤
     │ login             │ POST /accounts/ClientLogin + GET /reader/api/0/user-info │ Verify auth, show user info                │
     ├───────────────────┼──────────────────────────────────────────────────────────┼────────────────────────────────────────────┤
     │ subscriptions     │ GET /reader/api/0/subscription/list                      │ List subscriptions (table output)          │
     ├───────────────────┼──────────────────────────────────────────────────────────┼────────────────────────────────────────────┤
     │ tags              │ GET /reader/api/0/tag/list                               │ List tags                                  │
     ├───────────────────┼──────────────────────────────────────────────────────────┼────────────────────────────────────────────┤
     │ unread-count      │ GET /reader/api/0/unread-count                           │ Show unread counts per feed (table output) │
     ├───────────────────┼──────────────────────────────────────────────────────────┼────────────────────────────────────────────┤
     │ stream-contents   │ GET /reader/api/0/stream/contents/:streamId              │ Get items from a stream                    │
     ├───────────────────┼──────────────────────────────────────────────────────────┼────────────────────────────────────────────┤
     │ stream-item-ids   │ GET /reader/api/0/stream/items/ids                       │ Get item IDs for a stream                  │
     ├───────────────────┼──────────────────────────────────────────────────────────┼────────────────────────────────────────────┤
     │ edit-tag          │ POST /reader/api/0/edit-tag                              │ Add/remove tags on items                   │
     ├───────────────────┼──────────────────────────────────────────────────────────┼────────────────────────────────────────────┤
     │ mark-all-read     │ POST /reader/api/0/mark-all-as-read                      │ Mark all items in stream as read           │
     ├───────────────────┼──────────────────────────────────────────────────────────┼────────────────────────────────────────────┤
     │ subscription-edit │ POST /reader/api/0/subscription/edit                     │ Subscribe/unsubscribe/edit                 │
     └───────────────────┴──────────────────────────────────────────────────────────┴────────────────────────────────────────────┘

     Subcommands — Workflow (combining multiple APIs)

     ┌──────────────┬──────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────┐
     │   Command    │                                                       Description                                                        │
     ├──────────────┼──────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────┤
     │ fetch-unread │ Paginated fetch of all unread items (stream/contents + exclude read + continuation). Options: --stream, --count, --limit │
     ├──────────────┼──────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────┤
     │ refresh-all  │ List all subscriptions then hit stream/contents for each to trigger server-side refresh                                  │
     └──────────────┴──────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────┘
"""

cmd = typer.Typer(help=helptext)


def add_default_invoke():
    for _cmd in (cmd,):
        _cmd.callback(invoke_without_command=True)(default_invoke_without_command)


add_default_invoke()


# ---------------------------------------------------------------------------
# Data types
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class AuthInfo:
    sid: str
    lsid: str
    auth: str


# ---------------------------------------------------------------------------
# Low-level helpers
# ---------------------------------------------------------------------------


def _api_url(endpoint: str, path: str) -> str:
    return f"{endpoint.rstrip('/')}{path}"


def _auth_headers(auth: str) -> dict[str, str]:
    return {"Authorization": f"GoogleLogin auth={auth}"}


def _parse_login_response(text: str) -> AuthInfo:
    fields: dict[str, str] = {}
    for line in text.strip().splitlines():
        if "=" in line:
            key, value = line.split("=", 1)
            fields[key.strip()] = value.strip()
    return AuthInfo(
        sid=fields.get("SID", ""),
        lsid=fields.get("LSID", ""),
        auth=fields.get("Auth", ""),
    )


def _encode_form(items: list[tuple[str, str]]) -> bytes:
    return urlencode(items, doseq=True).encode()


def _resolve_stream_id(stream: str) -> str:
    shortcuts = {
        "reading-list": READING_LIST,
        "starred": STARRED,
        "read": READ,
    }
    if stream in shortcuts:
        return shortcuts[stream]
    if stream.startswith("label/"):
        return f"user/-/label/{stream[6:]}"
    return stream


# ---------------------------------------------------------------------------
# API functions
# ---------------------------------------------------------------------------


def authenticate(endpoint: str, user: str, password: str) -> AuthInfo:
    resp = httpx.post(
        _api_url(endpoint, "/accounts/ClientLogin"),
        data={"Email": user, "Passwd": password},
        timeout=30,
    )
    resp.raise_for_status()
    info = _parse_login_response(resp.text)
    if not info.auth:
        raise RuntimeError("认证失败: 未返回 Auth token")
    return info


def _get_write_token(endpoint: str, auth: str) -> str:
    resp = httpx.get(
        _api_url(endpoint, "/reader/api/0/token"),
        headers=_auth_headers(auth),
        timeout=30,
    )
    resp.raise_for_status()
    token = resp.text.strip()
    if not token:
        raise RuntimeError("未能获取写操作 token")
    return token


def _get_user_info(endpoint: str, auth: str) -> dict:
    resp = httpx.get(
        _api_url(endpoint, "/reader/api/0/user-info"),
        headers=_auth_headers(auth),
        params={"output": "json"},
        timeout=30,
    )
    resp.raise_for_status()
    return cast(dict, resp.json())


def _get_subscriptions(endpoint: str, auth: str) -> list[dict]:
    resp = httpx.get(
        _api_url(endpoint, "/reader/api/0/subscription/list"),
        headers=_auth_headers(auth),
        params={"output": "json"},
        timeout=30,
    )
    resp.raise_for_status()
    return cast(list[dict], resp.json().get("subscriptions", []))


def _get_tags(endpoint: str, auth: str) -> list[dict]:
    resp = httpx.get(
        _api_url(endpoint, "/reader/api/0/tag/list"),
        headers=_auth_headers(auth),
        params={"output": "json"},
        timeout=30,
    )
    resp.raise_for_status()
    return cast(list[dict], resp.json().get("tags", []))


def _get_unread_counts(endpoint: str, auth: str) -> dict:
    resp = httpx.get(
        _api_url(endpoint, "/reader/api/0/unread-count"),
        headers=_auth_headers(auth),
        params={"output": "json"},
        timeout=30,
    )
    resp.raise_for_status()
    return cast(dict, resp.json())


def _get_stream_contents(
    endpoint: str,
    auth: str,
    stream_id: str,
    count: int = 20,
    exclude_target: str = "",
    continuation: str = "",
    older_than: int = 0,
) -> dict:
    url = _api_url(endpoint, f"/reader/api/0/stream/contents/{quote(stream_id, safe='')}")
    params: dict[str, str | int] = {"output": "json", "n": count}
    if exclude_target:
        params["xt"] = exclude_target
    if continuation:
        params["c"] = continuation
    if older_than > 0:
        params["ot"] = older_than
    resp = httpx.get(url, headers=_auth_headers(auth), params=params, timeout=60)
    resp.raise_for_status()
    return cast(dict, resp.json())


def _get_stream_item_ids(
    endpoint: str,
    auth: str,
    stream_id: str,
    count: int = 1000,
    exclude_target: str = "",
    include_target: str = "",
    continuation: str = "",
) -> dict:
    params: dict[str, str | int] = {"s": stream_id, "output": "json", "n": count}
    if exclude_target:
        params["xt"] = exclude_target
    if include_target:
        params["it"] = include_target
    if continuation:
        params["c"] = continuation
    resp = httpx.get(
        _api_url(endpoint, "/reader/api/0/stream/items/ids"),
        headers=_auth_headers(auth),
        params=params,
        timeout=60,
    )
    resp.raise_for_status()
    return cast(dict, resp.json())


def _edit_tag(
    endpoint: str,
    auth: str,
    token: str,
    item_ids: list[str],
    add_tag: str = "",
    remove_tag: str = "",
) -> None:
    data: list[tuple[str, str]] = [("T", token)]
    if add_tag:
        data.append(("a", add_tag))
    if remove_tag:
        data.append(("r", remove_tag))
    for item_id in item_ids:
        data.append(("i", item_id))
    resp = httpx.post(
        _api_url(endpoint, "/reader/api/0/edit-tag"),
        headers={**_auth_headers(auth), "Content-Type": "application/x-www-form-urlencoded"},
        content=_encode_form(data),
        timeout=60,
    )
    resp.raise_for_status()
    if resp.text.strip() != "OK":
        raise RuntimeError(f"edit-tag 失败: {resp.text.strip()}")


def _batch_edit_tag(
    endpoint: str,
    auth: str,
    token: str,
    item_ids: list[str],
    add_tag: str = "",
    remove_tag: str = "",
    batch_size: int = 250,
) -> None:
    for start in range(0, len(item_ids), batch_size):
        batch = item_ids[start : start + batch_size]
        _edit_tag(endpoint, auth, token, batch, add_tag=add_tag, remove_tag=remove_tag)


def _mark_all_as_read_api(
    endpoint: str,
    auth: str,
    token: str,
    stream_id: str,
    timestamp: int = 0,
) -> None:
    ts = timestamp if timestamp > 0 else int(time.time())
    resp = httpx.post(
        _api_url(endpoint, "/reader/api/0/mark-all-as-read"),
        headers={**_auth_headers(auth), "Content-Type": "application/x-www-form-urlencoded"},
        content=_encode_form([("s", stream_id), ("ts", str(ts)), ("T", token)]),
        timeout=60,
    )
    resp.raise_for_status()
    if resp.text.strip() != "OK":
        raise RuntimeError(f"mark-all-as-read 失败: {resp.text.strip()}")


def _subscription_edit_api(
    endpoint: str,
    auth: str,
    token: str,
    action: str,
    stream_id: str,
    title: str = "",
    add_label: str = "",
    remove_label: str = "",
) -> None:
    data: list[tuple[str, str]] = [
        ("ac", action),
        ("s", stream_id),
        ("T", token),
    ]
    if title:
        data.append(("t", title))
    if add_label:
        data.append(("a", f"user/-/label/{add_label}"))
    if remove_label:
        data.append(("r", f"user/-/label/{remove_label}"))
    resp = httpx.post(
        _api_url(endpoint, "/reader/api/0/subscription/edit"),
        headers={**_auth_headers(auth), "Content-Type": "application/x-www-form-urlencoded"},
        content=_encode_form(data),
        timeout=60,
    )
    resp.raise_for_status()
    if resp.text.strip() != "OK":
        raise RuntimeError(f"subscription/edit 失败: {resp.text.strip()}")


def _fetch_all_stream_contents(
    endpoint: str,
    auth: str,
    stream_id: str,
    exclude_target: str = "",
    max_items: int = 0,
) -> list[dict]:
    all_items: list[dict] = []
    continuation = ""
    while True:
        batch_size = 1000
        if max_items > 0:
            remaining = max_items - len(all_items)
            if remaining <= 0:
                break
            batch_size = min(batch_size, remaining)

        result = _get_stream_contents(
            endpoint,
            auth,
            stream_id,
            count=batch_size,
            exclude_target=exclude_target,
            continuation=continuation,
        )
        items = result.get("items", [])
        all_items.extend(items)

        continuation = result.get("continuation", "")
        if not continuation or not items:
            break

    if max_items > 0:
        return all_items[:max_items]
    return all_items


# ---------------------------------------------------------------------------
# Common error handler
# ---------------------------------------------------------------------------


def _handle_errors(func):
    @functools.wraps(func)
    def wrapper(*args, **kwargs):
        try:
            return func(*args, **kwargs)
        except httpx.HTTPStatusError as exc:
            typer.echo(f"API 请求失败: HTTP {exc.response.status_code}", err=True)
            raise typer.Exit(code=1) from exc
        except httpx.RequestError as exc:
            typer.echo(f"网络请求失败: {exc}", err=True)
            raise typer.Exit(code=1) from exc
        except RuntimeError as exc:
            typer.echo(str(exc), err=True)
            raise typer.Exit(code=1) from exc

    return wrapper


def _json_output(data) -> None:
    typer.echo(json.dumps(data, indent=2, ensure_ascii=False))


# ---------------------------------------------------------------------------
# CLI commands — API endpoints
# ---------------------------------------------------------------------------


@cmd.command()
@_handle_errors
def login(
    endpoint: str = typer.Option(..., help="GReader API 端点", envvar="GREADER_ENDPOINT"),
    user: str = typer.Option(..., help="用户名", envvar="GREADER_USER"),
    password: str = typer.Option(..., help="密码或 API Token", envvar="GREADER_PASSWORD"),
):
    """验证登录并显示用户信息

    Usage examples::
        ai-assistant greader login --endpoint https://rss.example.com/api/greader.php --user admin --password secret
    """
    auth_info = authenticate(endpoint, user, password)
    typer.echo(f"登录成功, Auth: {auth_info.auth[:20]}...")

    user_info = _get_user_info(endpoint, auth_info.auth)
    _json_output(user_info)


@cmd.command()
@_handle_errors
def subscriptions(
    endpoint: str = typer.Option(..., help="GReader API 端点", envvar="GREADER_ENDPOINT"),
    user: str = typer.Option(..., help="用户名", envvar="GREADER_USER"),
    password: str = typer.Option(..., help="密码或 API Token", envvar="GREADER_PASSWORD"),
    output_json: bool = typer.Option(False, "--json", help="输出原始 JSON"),
):
    """列出所有订阅源

    Usage examples::
        ai-assistant greader subscriptions
        ai-assistant greader subscriptions --json
    """
    auth_info = authenticate(endpoint, user, password)
    subs = _get_subscriptions(endpoint, auth_info.auth)

    if output_json:
        _json_output(subs)
        return

    table = Table(title=f"订阅源 ({len(subs)})")
    table.add_column("ID", style="dim", max_width=60)
    table.add_column("标题", style="bold")
    table.add_column("分类")
    table.add_column("URL", style="dim", max_width=50)

    for sub in subs:
        categories = ", ".join(cat.get("label", "") for cat in sub.get("categories", []))
        table.add_row(sub.get("id", ""), sub.get("title", ""), categories, sub.get("url", ""))

    _CONSOLE.print(table)


@cmd.command()
@_handle_errors
def tags(
    endpoint: str = typer.Option(..., help="GReader API 端点", envvar="GREADER_ENDPOINT"),
    user: str = typer.Option(..., help="用户名", envvar="GREADER_USER"),
    password: str = typer.Option(..., help="密码或 API Token", envvar="GREADER_PASSWORD"),
):
    """列出所有标签

    Usage examples::
        ai-assistant greader tags
    """
    auth_info = authenticate(endpoint, user, password)
    tag_list = _get_tags(endpoint, auth_info.auth)
    _json_output(tag_list)


@cmd.command("unread-count")
@_handle_errors
def unread_count(
    endpoint: str = typer.Option(..., help="GReader API 端点", envvar="GREADER_ENDPOINT"),
    user: str = typer.Option(..., help="用户名", envvar="GREADER_USER"),
    password: str = typer.Option(..., help="密码或 API Token", envvar="GREADER_PASSWORD"),
    output_json: bool = typer.Option(False, "--json", help="输出原始 JSON"),
):
    """显示各订阅源的未读数量

    Usage examples::
        ai-assistant greader unread-count
        ai-assistant greader unread-count --json
    """
    auth_info = authenticate(endpoint, user, password)
    data = _get_unread_counts(endpoint, auth_info.auth)

    if output_json:
        _json_output(data)
        return

    counts = data.get("unreadcounts", [])
    table = Table(title="未读数量")
    table.add_column("订阅源 / 标签", style="bold", max_width=80)
    table.add_column("未读数", justify="right")
    table.add_column("最新时间戳", style="dim")

    for entry in counts:
        table.add_row(
            entry.get("id", ""),
            str(entry.get("count", 0)),
            str(entry.get("newestItemTimestampUsec", "")),
        )

    _CONSOLE.print(table)
    typer.echo(f"总未读: {data.get('max', 'N/A')}")


@cmd.command("stream-contents")
@_handle_errors
def stream_contents(
    stream: str = typer.Argument(..., help="Stream ID 或快捷名 (reading-list, starred, read, label/<name>, feed/<url>)"),
    endpoint: str = typer.Option(..., help="GReader API 端点", envvar="GREADER_ENDPOINT"),
    user: str = typer.Option(..., help="用户名", envvar="GREADER_USER"),
    password: str = typer.Option(..., help="密码或 API Token", envvar="GREADER_PASSWORD"),
    count: int = typer.Option(20, "-n", "--count", help="返回条目数"),
    exclude: str = typer.Option("", "--exclude", help="排除的 stream/tag ID"),
    continuation: str = typer.Option("", "--continuation", help="分页 continuation token"),
):
    """获取指定 stream 的内容

    stream 参数支持快捷名:
    - ``reading-list`` -> user/-/state/com.google/reading-list
    - ``starred`` -> user/-/state/com.google/starred
    - ``read`` -> user/-/state/com.google/read
    - ``label/<name>`` -> user/-/label/<name>
    - 其他值直接作为 stream ID 使用

    Usage examples::
        ai-assistant greader stream-contents reading-list -n 10
        ai-assistant greader stream-contents starred
        ai-assistant greader stream-contents label/tech -n 50
        ai-assistant greader stream-contents 'feed/https://example.com/feed' -n 5
    """
    auth_info = authenticate(endpoint, user, password)
    resolved = _resolve_stream_id(stream)
    data = _get_stream_contents(
        endpoint,
        auth_info.auth,
        resolved,
        count=count,
        exclude_target=exclude,
        continuation=continuation,
    )
    _json_output(data)


@cmd.command("stream-item-ids")
@_handle_errors
def stream_item_ids(
    stream: str = typer.Argument(..., help="Stream ID 或快捷名"),
    endpoint: str = typer.Option(..., help="GReader API 端点", envvar="GREADER_ENDPOINT"),
    user: str = typer.Option(..., help="用户名", envvar="GREADER_USER"),
    password: str = typer.Option(..., help="密码或 API Token", envvar="GREADER_PASSWORD"),
    count: int = typer.Option(1000, "-n", "--count", help="返回条目数"),
    exclude: str = typer.Option("", "--exclude", help="排除的 stream/tag ID"),
    include: str = typer.Option("", "--include", help="包含的 stream/tag ID"),
):
    """获取指定 stream 的条目 ID 列表

    Usage examples::
        ai-assistant greader stream-item-ids reading-list -n 100
        ai-assistant greader stream-item-ids starred
    """
    auth_info = authenticate(endpoint, user, password)
    resolved = _resolve_stream_id(stream)
    data = _get_stream_item_ids(
        endpoint,
        auth_info.auth,
        resolved,
        count=count,
        exclude_target=exclude,
        include_target=include,
    )
    _json_output(data)


@cmd.command("edit-tag")
@_handle_errors
def edit_tag(
    item_ids: list[str] = typer.Argument(..., help="条目 ID，可传入多个"),
    endpoint: str = typer.Option(..., help="GReader API 端点", envvar="GREADER_ENDPOINT"),
    user: str = typer.Option(..., help="用户名", envvar="GREADER_USER"),
    password: str = typer.Option(..., help="密码或 API Token", envvar="GREADER_PASSWORD"),
    add: str = typer.Option("", "--add", "-a", help="添加的 tag (如 user/-/state/com.google/starred)"),
    remove: str = typer.Option("", "--remove", "-r", help="移除的 tag"),
):
    """修改条目的标签 (已读/加星等)

    常用 tag:
    - ``user/-/state/com.google/read`` -- 已读
    - ``user/-/state/com.google/starred`` -- 加星
    - ``user/-/state/com.google/kept-unread`` -- 保持未读

    Usage examples::
        ai-assistant greader edit-tag ITEM_ID --add user/-/state/com.google/starred
        ai-assistant greader edit-tag ITEM_ID --remove user/-/state/com.google/read
        ai-assistant greader edit-tag ID1 ID2 ID3 --add user/-/state/com.google/read
    """
    if not add and not remove:
        typer.echo("请至少指定 --add 或 --remove 之一", err=True)
        raise typer.Exit(code=1)

    auth_info = authenticate(endpoint, user, password)
    token = _get_write_token(endpoint, auth_info.auth)
    _batch_edit_tag(endpoint, auth_info.auth, token, item_ids, add_tag=add, remove_tag=remove)
    typer.echo(f"完成，已处理 {len(item_ids)} 个条目")


@cmd.command("mark-all-read")
@_handle_errors
def mark_all_read(
    stream: str = typer.Argument(..., help="Stream ID 或快捷名"),
    endpoint: str = typer.Option(..., help="GReader API 端点", envvar="GREADER_ENDPOINT"),
    user: str = typer.Option(..., help="用户名", envvar="GREADER_USER"),
    password: str = typer.Option(..., help="密码或 API Token", envvar="GREADER_PASSWORD"),
    timestamp: int = typer.Option(0, "--timestamp", help="UNIX 时间戳起点，默认当前时间"),
):
    """将指定 stream 的所有条目标记为已读

    Usage examples::
        ai-assistant greader mark-all-read reading-list
        ai-assistant greader mark-all-read label/tech
        ai-assistant greader mark-all-read 'feed/https://example.com/feed'
    """
    auth_info = authenticate(endpoint, user, password)
    token = _get_write_token(endpoint, auth_info.auth)
    resolved = _resolve_stream_id(stream)
    _mark_all_as_read_api(endpoint, auth_info.auth, token, resolved, timestamp=timestamp)
    typer.echo(f"已将 {resolved} 标记为全部已读")


@cmd.command("subscription-edit")
@_handle_errors
def subscription_edit(
    stream_id: str = typer.Argument(..., help="订阅 stream ID (如 feed/https://example.com/feed)"),
    endpoint: str = typer.Option(..., help="GReader API 端点", envvar="GREADER_ENDPOINT"),
    user: str = typer.Option(..., help="用户名", envvar="GREADER_USER"),
    password: str = typer.Option(..., help="密码或 API Token", envvar="GREADER_PASSWORD"),
    action: str = typer.Option(..., "--action", "-a", help="操作: subscribe, unsubscribe, edit"),
    title: str = typer.Option("", "--title", help="订阅标题 (subscribe/edit 时可用)"),
    add_label: str = typer.Option("", "--add-label", help="添加分类标签名"),
    remove_label: str = typer.Option("", "--remove-label", help="移除分类标签名"),
):
    """管理订阅 (订阅/退订/编辑)

    Usage examples::
        ai-assistant greader subscription-edit 'feed/https://example.com/feed' --action subscribe --title "Example"
        ai-assistant greader subscription-edit 'feed/https://example.com/feed' --action unsubscribe
        ai-assistant greader subscription-edit 'feed/https://example.com/feed' --action edit --add-label tech
    """
    if action not in {"subscribe", "unsubscribe", "edit"}:
        typer.echo(f"不支持的操作: {action}，可选: subscribe, unsubscribe, edit", err=True)
        raise typer.Exit(code=1)

    auth_info = authenticate(endpoint, user, password)
    token = _get_write_token(endpoint, auth_info.auth)
    _subscription_edit_api(
        endpoint,
        auth_info.auth,
        token,
        action=action,
        stream_id=stream_id,
        title=title,
        add_label=add_label,
        remove_label=remove_label,
    )
    typer.echo(f"完成: {action} {stream_id}")


# ---------------------------------------------------------------------------
# CLI commands — Workflow
# ---------------------------------------------------------------------------


@cmd.command("fetch-unread")
@_handle_errors
def fetch_unread(
    endpoint: str = typer.Option(..., help="GReader API 端点", envvar="GREADER_ENDPOINT"),
    user: str = typer.Option(..., help="用户名", envvar="GREADER_USER"),
    password: str = typer.Option(..., help="密码或 API Token", envvar="GREADER_PASSWORD"),
    stream: str = typer.Option("reading-list", "--stream", help="Stream ID 或快捷名，默认 reading-list"),
    limit: int = typer.Option(0, "--limit", help="最多返回条目数，0 表示不限制"),
    output_json: bool = typer.Option(False, "--json", help="输出原始 JSON"),
):
    """获取所有未读条目 (自动分页)

    自动处理 continuation 分页，获取指定 stream 下排除已读的全部条目。

    Usage examples::
        ai-assistant greader fetch-unread
        ai-assistant greader fetch-unread --stream label/tech --limit 50
        ai-assistant greader fetch-unread --json
    """
    auth_info = authenticate(endpoint, user, password)
    resolved = _resolve_stream_id(stream)
    typer.echo(f"正在获取未读条目: {resolved}")

    items = _fetch_all_stream_contents(
        endpoint,
        auth_info.auth,
        resolved,
        exclude_target=READ,
        max_items=limit,
    )

    if output_json:
        _json_output(items)
        return

    for item in items:
        title = item.get("title", "(无标题)")
        item_id = item.get("id", "")
        origin = item.get("origin", {}).get("title", "")
        prefix = f"[{origin}] " if origin else ""
        typer.echo(f"- {prefix}{title}  ({item_id})")

    typer.echo(f"\n共 {len(items)} 条未读")


@cmd.command("refresh-all")
@_handle_errors
def refresh_all(
    endpoint: str = typer.Option(..., help="GReader API 端点", envvar="GREADER_ENDPOINT"),
    user: str = typer.Option(..., help="用户名", envvar="GREADER_USER"),
    password: str = typer.Option(..., help="密码或 API Token", envvar="GREADER_PASSWORD"),
):
    """刷新所有订阅源

    逐个请求每个订阅源的 stream/contents 以触发服务端拉取。

    Usage examples::
        ai-assistant greader refresh-all
    """
    auth_info = authenticate(endpoint, user, password)
    subs = _get_subscriptions(endpoint, auth_info.auth)
    typer.echo(f"共 {len(subs)} 个订阅源，开始刷新")

    ok, failed = 0, 0
    for i, sub in enumerate(subs, 1):
        feed_id = sub.get("id", "")
        feed_title = sub.get("title", feed_id)
        try:
            _get_stream_contents(endpoint, auth_info.auth, feed_id, count=1)
            ok += 1
            typer.echo(f"[{i}/{len(subs)}] {feed_title}")
        except (httpx.HTTPStatusError, httpx.RequestError):
            failed += 1
            typer.echo(f"[{i}/{len(subs)}] {feed_title} (failed)")

    typer.echo(f"刷新完成: 成功 {ok}, 失败 {failed}")
    if failed > 0:
        raise typer.Exit(code=1)


if __name__ == "__main__":
    cmd()
