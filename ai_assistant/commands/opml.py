import asyncio
import json
import logging
import random
import time
from pathlib import Path

import httpx
import typer
from xmltodict import parse

from ai_assistant.commands import default_invoke_without_command

logger = logging.getLogger(__name__)
RATE_LIMIT_CACHE: dict[str, float] = {}

helptext = """
Fetch RSS feeds from OPML file periodically.
"""

cmd = typer.Typer(help=helptext)


def add_default_invoke():
    for _cmd in (cmd,):
        _cmd.callback(invoke_without_command=True)(default_invoke_without_command)


add_default_invoke()


def fetch_opml(path: Path) -> list[str]:
    data = path.read_text(encoding="utf-8")
    body = parse(data)
    try:
        outline = body["opml"]["body"]["outline"]
        urllist = []
        for line in outline:
            if isinstance(line["outline"], list):
                for item in line["outline"]:
                    url = item["@xmlUrl"]
                    urllist.append(url)
            elif isinstance(line["outline"], dict):
                # 部分组下只有一个订阅, 这里就是 dict 类型
                urllist.append(line["outline"]["@xmlUrl"])
            else:
                logger.error(f"opml file format error, line: {line}")
    except KeyError:
        raise ValueError("OPML 文件格式错误")
    return urllist


async def fetch_rss(
    client: httpx.AsyncClient,
    url: str,
    semaphore: asyncio.Semaphore,
    wait_time: int = 3,
    rate_limit_minutes: int = 10,
):
    """异步获取 RSS，使用信号量控制并发"""
    now = time.time()
    expires_at = RATE_LIMIT_CACHE.get(url)
    if expires_at is not None:
        if expires_at > now:
            remain_seconds = int(expires_at - now)
            logger.info(f"skip {url}, cached 429 cooldown remains {remain_seconds}s")
            return
        RATE_LIMIT_CACHE.pop(url, None)

    async with semaphore:
        try:
            resp = await client.get(url, timeout=60, follow_redirects=True)
            if resp.status_code == 429:
                expires_at = time.time() + rate_limit_minutes * 60
                RATE_LIMIT_CACHE[url] = expires_at
                logger.warning(f"fetch {url} failed, status code: 429, skip for next {rate_limit_minutes} minutes")
                await asyncio.sleep(wait_time * 2)
                return
            elif resp.status_code in (502, 530):
                logger.debug(f"fetch {url} failed, status code: {resp.status_code}, maybe cloudflare tunnel is offline")
                await asyncio.sleep(wait_time * 2)
            elif resp.status_code in (403, 401):
                logger.debug(f"fetch {url} failed, status code: {resp.status_code}, maybe the feed is protected")
                await asyncio.sleep(wait_time * 2)
            else:
                resp.raise_for_status()
                try:
                    data = resp.json()
                except json.JSONDecodeError:
                    logger.warning(f"fetch {url} failed, json decode error, text content: {resp.text}")
                    await asyncio.sleep(wait_time * 3)
                    return
                title = data["title"]
                homepage = data["home_page_url"]
                logger.info(f"title: {title} - homepage: {homepage} - feedurl: {url}\n\n\n")
                await asyncio.sleep(wait_time)
        except Exception as e:
            logging.error(f"fetch {url} failed, {e}", exc_info=True)
            await asyncio.sleep(wait_time * 3)


async def fetch_all_rss(
    urllist: list[str],
    max_concurrent: int = 5,
    rate_limit_minutes: int = 10,
):
    """并发获取所有 RSS，最大并发数为 max_concurrent"""
    semaphore = asyncio.Semaphore(max_concurrent)

    async with httpx.AsyncClient(verify=False) as client:
        tasks = [
            fetch_rss(
                client,
                url,
                semaphore,
                rate_limit_minutes=rate_limit_minutes,
            )
            for url in urllist
        ]
        await asyncio.gather(*tasks)


async def async_fetch(
    opml_path: Path,
    max_concurrent: int = 5,
    loop: bool = False,
    rate_limit_minutes: int = 10,
):
    while True:
        urllist = fetch_opml(opml_path.expanduser())
        current_time = time.time()
        random.shuffle(urllist)
        logger.info(f"开始新一轮抓取，共 {len(urllist)} 个 RSS 源，最大并发数: {max_concurrent}，429 跳过时长: {rate_limit_minutes} 分钟")
        await fetch_all_rss(
            urllist,
            max_concurrent=max_concurrent,
            rate_limit_minutes=rate_limit_minutes,
        )
        cost_time = time.time() - current_time
        logger.info(f"本轮抓取完成，耗时 {cost_time:.2f} 秒\n")

        if not loop:
            break


@cmd.command()
def fetch(
    opml_path: Path = typer.Argument(
        ...,
        help="OPML 文件路径",
        exists=True,
        file_okay=True,
        dir_okay=False,
        resolve_path=True,
    ),
    max_concurrent: int = typer.Option(5, "-m", "--max-concurrent", help="最大并发数"),
    loop: bool = typer.Option(False, help="是否循环抓取"),
    log_level: str = typer.Option("INFO", help="日志级别 (DEBUG, INFO, WARNING, ERROR)"),
    rate_limit_minutes: int = typer.Option(
        5,
        "--rate-limit-minutes",
        envvar="OPML_429_SKIP_MINUTES",
        min=1,
        help="遇到 429 后跳过该 URL 的分钟数，也可通过环境变量 OPML_429_SKIP_MINUTES 设置",
    ),
):
    """从 OPML 文件中读取 RSS 源并抓取

    使用示例::

        # 基本用法：抓取一次
        ai-assistant-opml fetch ~/feeds.opml

        # 设置最大并发数为 10
        ai-assistant-opml fetch ~/feeds.opml -m 10

        # 循环抓取
        ai-assistant-opml fetch ~/feeds.opml --loop

        # 遇到 429 后跳过该 URL 60 分钟
        ai-assistant-opml fetch ~/feeds.opml --rate-limit-minutes 60

        # 组合使用：并发 10、循环抓取、DEBUG 日志
        ai-assistant-opml fetch ~/feeds.opml -m 10 --loop --log-level DEBUG
    """
    logging.basicConfig(level=getattr(logging, log_level.upper()), format="%(asctime)s - %(name)s - %(levelname)s - %(message)s")
    asyncio.run(async_fetch(opml_path, max_concurrent, loop, rate_limit_minutes))


if __name__ == "__main__":
    cmd()
