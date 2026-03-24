import re
from html import unescape
from http.cookies import SimpleCookie
from pathlib import Path
from typing import TypedDict, cast
from urllib.parse import quote, urlparse

import httpx
import typer
from sqlalchemy import create_engine, text
from sqlalchemy.engine import make_url

from ai_assistant.commands import default_invoke_without_command
from ai_assistant.commands.cookies import _extract_cookies_for_domain

helptext = """
FreshRSS 工具集.
"""

cmd = typer.Typer(help=helptext)


class Account(TypedDict):
    sid: str
    lsid: str
    auth: str


class SelectOption(TypedDict):
    value: str
    label: str


def add_default_invoke():
    for _cmd in (cmd,):
        _cmd.callback(invoke_without_command=True)(default_invoke_without_command)


add_default_invoke()


def _greader_url(endpoint: str, path: str) -> str:
    return f"{endpoint.rstrip('/')}/api/greader.php{path}"


def _web_base_url(endpoint: str) -> str:
    value = endpoint.strip().rstrip("/")
    if value.endswith("/api/greader.php"):
        value = value[: -len("/api/greader.php")]
    return value


def _web_ui_base_url(endpoint: str) -> str:
    value = _web_base_url(endpoint)
    if value.endswith("/i"):
        return value
    return f"{value}/i"


def _parse_cookie_header(cookie_header: str) -> dict[str, str]:
    cookie = SimpleCookie()
    cookie.load(cookie_header)
    return {key: morsel.value for key, morsel in cookie.items()}


def _cookies_for_endpoint(endpoint: str, cookie_header: str) -> dict[str, str]:
    if cookie_header.strip():
        cookies = _parse_cookie_header(cookie_header)
        if cookies:
            return cookies
        typer.echo("传入的 Cookie 字符串为空或格式无效", err=True)
        raise typer.Exit(1)

    host = urlparse(_web_base_url(endpoint)).hostname
    if not host:
        typer.echo(f"无法从 endpoint 解析域名: {endpoint}", err=True)
        raise typer.Exit(1)

    cookies = _extract_cookies_for_domain(host)
    if cookies:
        return cookies

    typer.echo(f"未从系统浏览器中找到 {host} 的 FreshRSS Cookie", err=True)
    typer.echo("请先在浏览器中登录 FreshRSS，或通过 --cookies 显式传入", err=True)
    raise typer.Exit(1)


def _extract_input_value(html: str, input_name: str) -> str:
    patterns = [
        rf'<input[^>]*name=["\']{re.escape(input_name)}["\'][^>]*value=["\']([^"\']*)["\']',
        rf'<input[^>]*value=["\']([^"\']*)["\'][^>]*name=["\']{re.escape(input_name)}["\']',
    ]
    for pattern in patterns:
        match = re.search(pattern, html, flags=re.IGNORECASE)
        if match:
            return unescape(match.group(1))
    return ""


def _strip_tags(html_fragment: str) -> str:
    text = re.sub(r"<[^>]+>", " ", html_fragment)
    return " ".join(unescape(text).split())


def _extract_select_options(html: str, select_name: str) -> list[SelectOption]:
    select_match = re.search(
        rf'<select[^>]*name=["\']{re.escape(select_name)}["\'][^>]*>(.*?)</select>',
        html,
        flags=re.IGNORECASE | re.DOTALL,
    )
    if not select_match:
        return []

    options: list[SelectOption] = []
    for value, body in re.findall(
        r'<option[^>]*value=["\']([^"\']*)["\'][^>]*>(.*?)</option>',
        select_match.group(1),
        flags=re.IGNORECASE | re.DOTALL,
    ):
        options.append(SelectOption(value=unescape(value), label=_strip_tags(body)))
    return options


def _normalise_option_label(value: str) -> str:
    return re.sub(r"[^a-z0-9\u4e00-\u9fff]+", "", value.lower())


def _resolve_category_id(category: str, options: list[SelectOption]) -> str:
    value = category.strip()
    if value == "":
        return ""
    if value.isdigit():
        return value

    normalized_target = _normalise_option_label(value)
    for option in options:
        if _normalise_option_label(option["label"]) == normalized_target:
            return option["value"]
    return ""


def _resolve_feed_kind_value(feed_kind: str, options: list[SelectOption]) -> str:
    value = feed_kind.strip()
    if value == "":
        typer.echo("请通过 --feed-kind 指定订阅源类型", err=True)
        raise typer.Exit(1)
    if value.isdigit():
        return value

    normalized_target = _normalise_option_label(value)
    exact_aliases = {
        "rss": {"rss", "atom", "rssatom"},
        "jsonfeed": {"jsonfeed", "json+feed", "json-feed"},
        "json": {"json", "jsondotnotation", "jsondot", "jsondottedpaths"},
        "htmlxpath": {"htmlxpath", "html+xpath"},
        "xmlxpath": {"xmlxpath", "xml+xpath"},
        "htmlxpathjson": {"htmlxpathjson", "html+xpath+json", "htmljson"},
    }

    def label_matches(option: SelectOption, alias_key: str) -> bool:
        normalized_label = _normalise_option_label(option["label"])
        if alias_key == "jsonfeed":
            return (
                "jsonfeed" in normalized_label
                or ("json" in normalized_label and "订阅源" in option["label"] and "点" not in option["label"])
                or ("json" in normalized_label and "feed" in normalized_label and "dot" not in normalized_label)
            )
        if alias_key == "json":
            return "json" in normalized_label and "feed" not in normalized_label
        if alias_key == "rss":
            return "rss" in normalized_label or "atom" in normalized_label
        if alias_key == "htmlxpath":
            return "html" in normalized_label and "xpath" in normalized_label and "json" not in normalized_label
        if alias_key == "xmlxpath":
            return "xml" in normalized_label and "xpath" in normalized_label
        if alias_key == "htmlxpathjson":
            return "html" in normalized_label and "xpath" in normalized_label and "json" in normalized_label
        return False

    for option in options:
        if _normalise_option_label(option["label"]) == normalized_target:
            return option["value"]

    for alias_key, aliases in exact_aliases.items():
        if normalized_target not in aliases:
            continue
        for option in options:
            if label_matches(option, alias_key):
                return option["value"]

    labels = ", ".join(f"{item['label']}={item['value']}" for item in options)
    typer.echo(f"无法识别订阅源类型: {feed_kind}", err=True)
    typer.echo(f"当前 FreshRSS 可用类型: {labels}", err=True)
    raise typer.Exit(1)


def _ensure_logged_in(response: httpx.Response) -> None:
    body = response.text.lower()
    url = str(response.url).lower()
    if "c=auth" in url or ('name="password"' in body and 'name="username"' in body):
        typer.echo("FreshRSS 登录态无效，请重新登录浏览器或通过 --cookies 传入有效 Cookie", err=True)
        raise typer.Exit(1)


def _fetch_add_page(
    client: httpx.Client,
    endpoint: str,
    feed_url: str,
) -> tuple[str, list[SelectOption], list[SelectOption]]:
    response = client.get(
        f"{_web_ui_base_url(endpoint)}/",
        params={"c": "subscription", "a": "add", "url_rss": feed_url},
        follow_redirects=True,
        timeout=30,
    )
    response.raise_for_status()
    _ensure_logged_in(response)

    csrf = _extract_input_value(response.text, "_csrf")
    if csrf == "":
        typer.echo("未能从 FreshRSS 添加页面提取到 CSRF token", err=True)
        raise typer.Exit(1)

    categories = _extract_select_options(response.text, "category")
    feed_kinds = _extract_select_options(response.text, "feed_kind")
    return csrf, categories, feed_kinds


def _create_category(client: httpx.Client, endpoint: str, csrf: str, category: str) -> None:
    response = client.post(
        f"{_web_ui_base_url(endpoint)}/",
        params={"c": "category", "a": "create"},
        data={"_csrf": csrf, "new-category": category},
        timeout=30,
    )
    if response.status_code not in {301, 302, 303, 307, 308}:
        response.raise_for_status()

    location = response.headers.get("location", "")
    if "c=subscription" not in location:
        typer.echo(f"创建分类失败: {category}", err=True)
        raise typer.Exit(1)


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
def subscribe(
    feed_url: str = typer.Argument(..., help="订阅源地址"),
    endpoint: str = typer.Option(..., help="FreshRSS 站点地址，例如 http://freshrss.docker.localhost/api/greader.php", envvar="FRESHRSS_ENDPOINT"),
    category: str = typer.Option("", "--category", help="分类名或分类 ID，留空则使用默认分类"),
    feed_kind: str = typer.Option("jsonfeed", "--feed-kind", help="订阅源类型，如 jsonfeed、json、rss，或直接传 FreshRSS 的数值；仅当当前页面提供该字段时需要"),
    cookies: str = typer.Option("", "--cookies", help="Cookie 字符串，格式如 'a=b; c=d'；为空时尝试从系统浏览器读取"),
):
    """通过 FreshRSS 网页添加接口新增订阅源

    会先读取添加页面，获取 CSRF token、分类，以及页面提供的订阅源类型选项，再提交表单。

    常见 ``--feed-kind`` 参数映射::

        rss            -> RSS / Atom (默认)
        atom           -> RSS / Atom (默认)
        jsonfeed       -> JSON 订阅源
        json           -> JSON (点表达式)
        htmlxpath      -> HTML + XPath (Web 抓取)
        xmlxpath       -> XML + XPath
        htmlxpathjson  -> HTML + XPath + JSON 点表示法（HTML 中的 JSON）
        25             -> 直接使用 FreshRSS 表单值 25

    Usage examples::
        FRESHRSS_ENDPOINT=https://rss.example.com/api/greader.php ai-assistant-freshrss subscribe https://example.com/feed.json --category twitter --feed-kind jsonfeed
        ai-assistant-freshrss subscribe https://example.com/feed.json --endpoint https://rss.example.com/api/greader.php --feed-kind 4 --cookies "FreshRSS=..."
    """
    resolved_cookies = _cookies_for_endpoint(endpoint, cookies)
    typer.echo(f"使用 {len(resolved_cookies)} 个 Cookie 访问 FreshRSS")

    with httpx.Client(cookies=resolved_cookies, follow_redirects=False) as client:
        csrf, categories, feed_kinds = _fetch_add_page(client, endpoint, feed_url)
        category_id = _resolve_category_id(category, categories)

        if category.strip() and category_id == "":
            typer.echo(f"分类不存在，尝试创建: {category}")
            _create_category(client, endpoint, csrf, category)
            csrf, categories, feed_kinds = _fetch_add_page(client, endpoint, feed_url)
            category_id = _resolve_category_id(category, categories)
            if category_id == "":
                typer.echo(f"创建分类后仍未找到分类: {category}", err=True)
                raise typer.Exit(1)

        feed_kind_value = ""
        if feed_kinds:
            feed_kind_value = _resolve_feed_kind_value(feed_kind, feed_kinds)
        else:
            typer.echo("FreshRSS 添加页未提供订阅源类型选项，将按页面默认行为提交")

        data = {
            "_csrf": csrf,
            "url_rss": feed_url,
        }
        if feed_kind_value != "":
            data["feed_kind"] = feed_kind_value
        if category_id != "":
            data["category"] = category_id

        typer.echo(f"开始添加订阅: {feed_url}")
        if category_id != "":
            typer.echo(f"目标分类: {category} ({category_id})")
        if feed_kind_value != "":
            typer.echo(f"订阅源类型: {feed_kind} ({feed_kind_value})")

        response = client.post(
            f"{_web_ui_base_url(endpoint)}/",
            params={"c": "feed", "a": "add"},
            data=data,
            timeout=60,
        )
        if response.status_code not in {301, 302, 303, 307, 308}:
            response.raise_for_status()
            _ensure_logged_in(response)

        location = response.headers.get("location", "")
        if "c=subscription" not in location:
            typer.echo("FreshRSS 未返回成功跳转，添加订阅可能失败", err=True)
            if location:
                typer.echo(f"返回跳转: {location}", err=True)
            raise typer.Exit(1)

    typer.echo("订阅已提交到 FreshRSS 网页接口")


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
