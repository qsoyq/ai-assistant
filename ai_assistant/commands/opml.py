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
):
    """异步获取 RSS，使用信号量控制并发"""
    async with semaphore:
        try:
            resp = await client.get(url, timeout=60, follow_redirects=True)
            if resp.status_code in (502, 530):
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


async def fetch_all_rss(urllist: list[str], max_concurrent: int = 5):
    """并发获取所有 RSS，最大并发数为 max_concurrent"""
    semaphore = asyncio.Semaphore(max_concurrent)

    async with httpx.AsyncClient(verify=False) as client:
        tasks = [fetch_rss(client, url, semaphore) for url in urllist]
        await asyncio.gather(*tasks)


async def async_fetch(
    opml_path: Path,
    max_concurrent: int = 5,
    loop: bool = False,
):
    """异步抓取 RSS 源"""
    urllist = fetch_opml(opml_path.expanduser())

    while True:
        current_time = time.time()
        random.shuffle(urllist)
        logger.info(f"开始新一轮抓取，共 {len(urllist)} 个 RSS 源，最大并发数: {max_concurrent}")
        await fetch_all_rss(urllist, max_concurrent=max_concurrent)
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
    max_concurrent: int = typer.Option(5, help="最大并发数"),
    loop: bool = typer.Option(False, help="是否循环抓取"),
    log_level: str = typer.Option("INFO", help="日志级别 (DEBUG, INFO, WARNING, ERROR)"),
):
    """从 OPML 文件中读取 RSS 源并抓取"""
    logging.basicConfig(level=getattr(logging, log_level.upper()), format="%(asctime)s - %(name)s - %(levelname)s - %(message)s")
    asyncio.run(async_fetch(opml_path, max_concurrent, loop))


if __name__ == "__main__":
    cmd()
