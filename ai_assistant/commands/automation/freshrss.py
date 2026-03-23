from pathlib import Path
from typing import TypedDict, cast
from urllib.parse import quote

import httpx
import typer
from sqlalchemy import create_engine, text
from sqlalchemy.engine import make_url

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


def _database_url(target: str) -> str:
    value = target.strip()
    if "://" not in value:
        path = Path(value).expanduser().resolve()
        return f"sqlite:///{path.as_posix()}"

    if value.startswith("mysql://"):
        return value.replace("mysql://", "mysql+pymysql://", 1)
    if value.startswith("postgres://"):
        return value.replace("postgres://", "postgresql+psycopg://", 1)
    if value.startswith("postgresql://"):
        return value.replace("postgresql://", "postgresql+psycopg://", 1)
    return value


def _masked_database_url(database_url: str) -> str:
    url = make_url(database_url)
    masked_url = url

    if url.username is not None:
        masked_url = masked_url.set(username="***")
    if url.password is not None:
        masked_url = masked_url.set(password="***")

    return cast(str, masked_url.render_as_string(hide_password=False))


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


@cmd.command("disable-priority")
def disable_priority(
    target: str = typer.Argument(..., help="SQLite 文件路径或数据库 DSN", envvar="FRESHRSS_DATABASE"),
):
    """将所有 feed 的 priority 置为 0

    支持 SQLite 文件路径或数据库 DSN，适用于 sqlite/mysql/postgresql。

    Usage examples::
        ai-assistant-freshrss disable-priority /path/to/db.sqlite
        ai-assistant-freshrss disable-priority sqlite:////path/to/db.sqlite
        ai-assistant-freshrss disable-priority mysql://user:pass@127.0.0.1:3306/freshrss
        ai-assistant-freshrss disable-priority postgresql://user:pass@127.0.0.1:5432/freshrss
    """
    database_url = _database_url(target)
    typer.echo(f"连接数据库: {_masked_database_url(database_url)}")

    # 统一通过 SQLAlchemy 执行同一条 SQL，兼容 sqlite/mysql/postgresql。
    engine = create_engine(database_url)
    with engine.begin() as connection:
        result = connection.execute(text("UPDATE feed SET priority = 0 WHERE priority != 0"))
        remaining = connection.execute(text("SELECT COUNT(*) FROM feed WHERE priority != 0")).scalar_one()

    affected = 0 if result.rowcount is None or result.rowcount < 0 else result.rowcount
    typer.echo(f"已更新 {affected} 条 feed 记录")
    typer.echo(f"剩余 priority != 0 的 feed 数量: {remaining}")
    if remaining != 0:
        raise typer.Exit(1)


if __name__ == "__main__":
    cmd()
