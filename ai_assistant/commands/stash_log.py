import json
import traceback
import urllib.parse
import uuid
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Generator

import httpx
import typer
from pydantic import BaseModel, Field

from ai_assistant.commands import default_invoke_without_command

helptext = """
Stash 抓包日志解析工具
"""

cmd = typer.Typer(help=helptext)


def add_default_invoke():
    for _cmd in (cmd,):
        _cmd.callback(invoke_without_command=True)(default_invoke_without_command)


add_default_invoke()

_USER_AGENT = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/135.0.0.0 Safari/537.36"


class Request(BaseModel):
    url: str
    method: str
    headers: dict
    body: str | None | dict | list = Field(None)


class Response(BaseModel):
    status: int
    headers: dict
    body: str | None | dict | list = Field(None)
    json_: object | None = Field(None, alias="json")


class Dev(BaseModel):
    timestamp: int = Field(..., description="秒时间戳")
    curl: str = Field(..., description="curl 命令")


class LogEntry(BaseModel):
    request: Request
    response: Response
    dev: Dev


def _parse_json(text: str) -> tuple[dict | None, str | None]:
    try:
        return (json.loads(text), None)
    except json.JSONDecodeError as e:
        return (None, str(e))


def _parse_log(file: Path) -> Generator[dict, None, None]:
    if not file.exists():
        typer.echo(f"路径不存在: {file}", err=True)
        raise typer.Exit(1)

    if not file.is_file():
        typer.echo(f"路径必须是文件: {file}", err=True)
        raise typer.Exit(2)

    for line in file.read_text().split("\n"):
        if len(line) > 16 and line[12:16] == "JSON":
            jsonstr = line[18:]
            body, err = _parse_json(jsonstr)
            if err is not None:
                typer.echo(f"JSON 解析失败: {err}\t原始内容: {jsonstr}", err=True)
            elif body is not None:
                yield body


def _fetch_media(url: str, *, prefix: str = "shcp/") -> None:
    try:
        typer.echo(f"下载: {url}")
        parse_result = urllib.parse.urlparse(url)
        download_path = prefix + parse_result.netloc + parse_result.path[0] + parse_result.path[1:].replace("/", "-")
        resp = httpx.get(url, verify=False, headers={"User-Agent": _USER_AGENT})
        if resp.is_error:
            typer.echo(f"下载失败 {url}: {resp.status_code}, body: {resp.text}", err=True)
            return

        ct = resp.headers.get("content-type", "")
        ext = ""
        path = Path(download_path)

        try:
            if path.exists():
                typer.echo(f"文件已存在, 跳过: {path}")
                return
        except OSError as e:
            if "File name too long" in str(e):
                uid = uuid.uuid4().hex
                new_path = Path(prefix + uid + ext)
                typer.echo(f"文件名过长, 重新映射: {path} -> {new_path}")
                path = new_path
                if path.exists():
                    typer.echo(f"文件已存在, 跳过: {path}")
                    return
            else:
                traceback.print_exc()

        path.parent.mkdir(parents=True, exist_ok=True)

        if ct.startswith("image/") or ct.startswith("video/"):
            ext = ct.split("/", 1)[-1]
            path = path.with_suffix(f".{ext}")

        if path.exists():
            typer.echo(f"文件已存在, 跳过: {path}")
            return

        path.write_bytes(resp.content)
    except Exception as e:
        traceback.print_exc()
        typer.echo(f"下载失败 {url}: {type(e).__name__} {e}", err=True)


@cmd.command()
def download(
    file: Path = typer.Argument(..., help="日志文件路径"),
    output_dir: str = typer.Option("Assets", "--output-dir", "-o", help="下载输出目录前缀"),
):
    """下载抓包日志中的图片和视频

    使用示例:
    - `ai-assistant stash-log download access.log`
    - `ai-assistant stash-log download access.log -o shcp`
    """
    image_urls: list[str] = []
    video_urls: list[str] = []

    for line in _parse_log(file):
        entry = LogEntry(**line)
        content_type = entry.response.headers.get("Content-Type", "")
        if "image" in content_type:
            image_urls.append(entry.request.url)
        if "video" in content_type:
            video_urls.append(entry.request.url)

    with ThreadPoolExecutor() as executor:
        for url in image_urls:
            executor.submit(_fetch_media, url, prefix=f"{output_dir}/image/")

        for url in video_urls:
            executor.submit(_fetch_media, url, prefix=f"{output_dir}/video/")

        executor.shutdown(wait=True)

    typer.echo(f"完成, 图片: {len(image_urls)}, 视频: {len(video_urls)}")


@cmd.command()
def urls(
    file: Path = typer.Argument(..., help="日志文件路径"),
    dest: Path = typer.Option("-", "--dest", help="结果输出路径, 默认标准输出"),
    uniq: bool = typer.Option(True, "--uniq", help="去重"),
    sort: bool = typer.Option(True, "--sort", help="排序"),
):
    """提取抓包日志中的所有请求 URL

    使用示例:
    - `ai-assistant stash-log urls access.log`
    - `ai-assistant stash-log urls access.log --dest output.txt`
    - `ai-assistant stash-log urls access.log --no-uniq --no-sort`
    """
    url_list = [line["request"]["url"] for line in _parse_log(file) if line]

    if uniq:
        url_list = list(set(url_list))

    if sort:
        url_list.sort()

    output = "\n".join(url_list)

    if str(dest) == "-":
        typer.echo(output)
    else:
        dest.write_text(output)
        typer.echo(f"已写入: {dest}")


if __name__ == "__main__":
    cmd()
