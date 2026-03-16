from typing import TypedDict
from urllib.parse import quote

import httpx
import typer

from ai_assistant.commands import default_invoke_without_command

helptext = """
FreshRSS 工具集.
"""

cmd = typer.Typer(help=helptext)


class Account(TypedDict):
    sid: str
    lsid: str
    auth: str


def add_default_invoke():
    for _cmd in (cmd,):
        _cmd.callback(invoke_without_command=True)(default_invoke_without_command)


add_default_invoke()


def _greader_url(endpoint: str, path: str) -> str:
    return f"{endpoint.rstrip('/')}/api/greader.php{path}"


def _get_subscription_ids(endpoint: str, auth: str) -> list[str]:
    url = _greader_url(endpoint, "/reader/api/0/subscription/list")
    resp = httpx.get(url, headers={"Authorization": f"GoogleLogin auth={auth}"}, params={"output": "json"}, timeout=30)
    resp.raise_for_status()
    return [sub["id"] for sub in resp.json().get("subscriptions", [])]


def _refresh_feed(endpoint: str, auth: str, feed_id: str) -> int:
    """请求单个 feed 的 stream/contents 以触发服务端拉取，返回 HTTP 状态码。"""
    url = _greader_url(endpoint, f"/reader/api/0/stream/contents/{quote(feed_id, safe='')}")
    resp = httpx.get(url, headers={"Authorization": f"GoogleLogin auth={auth}"}, params={"output": "json", "n": 1}, timeout=60)
    return resp.status_code


def _get_account_info(endpoint: str, user: str, password: str) -> Account:
    url = f"{endpoint}/accounts/ClientLogin"
    resp = httpx.get(url, params={"Email": user, "Passwd": password}, timeout=10)
    resp.raise_for_status()
    items = resp.text.split("\n")
    body = {item.split("=", 1)[0].strip().lower(): item.split("=", 1)[1] for item in items if item and "=" in item}
    return Account(sid=body.get("sid", ""), lsid=body.get("lsid", ""), auth=body.get("auth", ""))


@cmd.command()
def refresh(
    endpoint: str = typer.Argument(..., help="FreshRSS 端点地址", envvar="FRESHRSS_ENDPOINT"),
    user: str = typer.Option(..., help="FreshRSS 用户名", envvar="FRESHRSS_USER"),
    token: str = typer.Option(..., help="FreshRSS API Token", envvar="FRESHRSS_API_TOKEN"),
):
    """刷新当前所有订阅源

    通过 Google Reader API 获取订阅列表，然后逐个请求 stream/contents 触发服务端刷新。

    Usage examples::
        ai-assistant-freshrss refresh
        ai-assistant-freshrss refresh http://freshrss.example.org/api/greader.php  --user <user> --token <token>
    """
    typer.echo(f"正在获取订阅列表: {endpoint}")
    account_info = _get_account_info(endpoint, user, token)
    auth = account_info["auth"]
    typer.echo(account_info)
    feed_ids = _get_subscription_ids(endpoint, auth)
    typer.echo(f"共 {len(feed_ids)} 个订阅源，开始刷新")
    ok, failed = 0, 0
    for i, feed_id in enumerate(feed_ids, 1):
        status = _refresh_feed(endpoint, auth, feed_id)
        if status == 200:
            ok += 1
            typer.echo(f"[{i}/{len(feed_ids)}] {feed_id} ✓")
        else:
            failed += 1
            typer.echo(f"[{i}/{len(feed_ids)}] {feed_id} ✗ (HTTP {status})")

    typer.echo(f"刷新完成: 成功 {ok}, 失败 {failed}")
    if failed > 0:
        raise typer.Exit(1)


if __name__ == "__main__":
    cmd()
