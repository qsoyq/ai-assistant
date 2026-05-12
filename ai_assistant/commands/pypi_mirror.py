"""Mirror a PEP 503 simple index: list packages, then download every file (async)."""

from __future__ import annotations

import asyncio
import importlib.metadata
from dataclasses import dataclass
from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import unquote, urljoin, urlsplit

import httpx
import typer
from tqdm.asyncio import tqdm

from ai_assistant.commands import version_callback


def _default_user_agent() -> str:
    """httpx's native UA — `python-httpx/<ver>`. Picked as default because
    private indexes commonly redirect both browser UAs and package-manager UAs
    (pip, twine, uv, poetry) to a login page, but pass generic HTTP clients."""
    try:
        version = importlib.metadata.version("httpx")
    except importlib.metadata.PackageNotFoundError:
        version = "0"
    return f"python-httpx/{version}"


helptext = """
按 PEP 503 simple 索引镜像下载 (asyncio 驱动): 拉取索引页 -> 并发抓取所有文件清单 ->
本地去重 -> 并发下载, 全程 tqdm 显示进度。

URL 应指向 simple 索引根, 例如 https://pypi.org/simple/ 或私有源的 /simple/。
鉴权与 pip 一致, 支持 --username/--password 走 HTTP Basic, 也可注入 --cookie 或自定义 --user-agent。

示例:
- ai-assistant pypi-mirror https://example.com/simple/
- ai-assistant pypi-mirror https://example.com/simple/ -o ./wheels -c 32
- ai-assistant pypi-mirror https://example.com/simple/ -u alice -p s3cret
- ai-assistant pypi-mirror https://example.com/simple/ --package mypkg --max 50
- ai-assistant pypi-mirror https://example.com/simple/ -f   # 强制重下, 不去重
"""

cmd = typer.Typer(help=helptext, context_settings={"allow_interspersed_args": True})


@dataclass(frozen=True)
class FileTask:
    package: str
    filename: str
    url: str

    @property
    def dest(self) -> Path:
        return Path(self.package) / self.filename


class _AnchorCollector(HTMLParser):
    """Pull (href, text) for every <a> tag — enough for a PEP 503 simple page."""

    def __init__(self) -> None:
        super().__init__()
        self.links: list[tuple[str, str]] = []
        self._href: str | None = None
        self._text: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag != "a":
            return
        for k, v in attrs:
            if k == "href" and v:
                self._href = v
                self._text = []
                return

    def handle_data(self, data: str) -> None:
        if self._href is not None:
            self._text.append(data)

    def handle_endtag(self, tag: str) -> None:
        if tag != "a" or self._href is None:
            return
        self.links.append((self._href, "".join(self._text).strip()))
        self._href = None
        self._text = []


def parse_anchors(html: str) -> list[tuple[str, str]]:
    p = _AnchorCollector()
    p.feed(html)
    return p.links


def filename_from_url(url: str, fallback: str) -> str:
    """Pick a sane filename from a package-file URL — last path segment, fragment stripped."""
    path = urlsplit(url).path
    name = unquote(path.rsplit("/", 1)[-1])
    return name or fallback


def _normalize_index_url(url: str) -> str:
    return url if url.endswith("/") else url + "/"


async def _list_packages(client: httpx.AsyncClient, base: str) -> tuple[list[str], str]:
    """Return (package names, raw response body) — body is kept so callers can
    surface a snippet when parsing yields nothing (UA gating, login redirect, …)."""
    resp = await client.get(base)
    resp.raise_for_status()
    seen: set[str] = set()
    out: list[str] = []
    for href, text in parse_anchors(resp.text):
        name = text or href.strip("/").rsplit("/", 1)[-1]
        if name and name not in seen:
            seen.add(name)
            out.append(name)
    return out, resp.text


async def _list_package_files(client: httpx.AsyncClient, base: str, name: str, sem: asyncio.Semaphore) -> list[FileTask]:
    pkg_url = urljoin(base, f"{name}/")
    async with sem:
        try:
            resp = await client.get(pkg_url)
            resp.raise_for_status()
        except httpx.HTTPError as exc:
            tqdm.write(f"  ! list {name}: {exc}")
            return []
    out: list[FileTask] = []
    for href, text in parse_anchors(resp.text):
        file_url = urljoin(pkg_url, href)
        fname = filename_from_url(file_url, fallback=text or "unknown")
        out.append(FileTask(package=name, filename=fname, url=file_url))
    return out


async def _download_one(
    client: httpx.AsyncClient,
    task: FileTask,
    output: Path,
    sem: asyncio.Semaphore,
) -> FileTask | None:
    """Return the task on success, None on failure — caller groups successes for the report."""
    dest = output / task.dest
    dest.parent.mkdir(parents=True, exist_ok=True)
    tmp = dest.with_suffix(dest.suffix + ".part")
    async with sem:
        try:
            async with client.stream("GET", task.url) as fr:
                fr.raise_for_status()
                with tmp.open("wb") as fh:
                    async for chunk in fr.aiter_bytes():
                        fh.write(chunk)
            tmp.replace(dest)
            return task
        except httpx.HTTPError as exc:
            tqdm.write(f"  ! fail {task.package}/{task.filename}: {exc}")
            tmp.unlink(missing_ok=True)
            return None


def _format_downloaded_markdown(tasks: list[FileTask]) -> str:
    """List the distinct packages with at least one successful download."""
    packages = sorted({t.package for t in tasks})
    return "\n".join(["## downloaded", *(f"- {p}" for p in packages)])


async def _run(
    *,
    base: str,
    output: Path,
    headers: dict[str, str],
    auth: tuple[str, str] | None,
    timeout: float,
    concurrency: int,
    package_filter: list[str],
    force: bool,
    max_files: int | None,
    dry_run: bool,
) -> None:
    output.mkdir(parents=True, exist_ok=True)
    output_abs = output.resolve()
    sem = asyncio.Semaphore(concurrency)

    async with httpx.AsyncClient(headers=headers, auth=auth, timeout=timeout, follow_redirects=True) as client:
        tqdm.write(f"output dir: {output_abs}")
        tqdm.write(f"GET {base}")
        packages, body = await _list_packages(client, base)
        if not packages:
            tqdm.write(
                "found 0 package(s) — the index page parsed to no anchors. "
                "If the server gates on User-Agent (some private indexes redirect "
                "browser UAs to a login page), retry with e.g. "
                '`--user-agent "python-httpx/0.28"`.'
            )
            snippet = body.strip().replace("\n", " ")[:300]
            tqdm.write(f"response snippet: {snippet}")
            return
        if package_filter:
            wanted = {p.lower() for p in package_filter}
            packages = [p for p in packages if p.lower() in wanted]
        tqdm.write(f"found {len(packages)} package(s); fetching file lists...")

        list_tasks = [_list_package_files(client, base, n, sem) for n in packages]
        results = await tqdm.gather(*list_tasks, desc="index", unit="pkg")
        all_files: list[FileTask] = [f for sub in results for f in sub]
        tqdm.write(f"collected {len(all_files)} file(s) across {len(packages)} package(s)")

        if force:
            todo = list(all_files)
        else:
            todo = [t for t in all_files if not (output / t.dest).exists() or (output / t.dest).stat().st_size == 0]
            tqdm.write(f"after dedupe: {len(todo)} new file(s) ({len(all_files) - len(todo)} skipped as existing)")

        if max_files is not None and len(todo) > max_files:
            tqdm.write(f"limiting to first {max_files} of {len(todo)} file(s) (--max)")
            todo = todo[:max_files]

        if dry_run:
            for t in todo:
                tqdm.write(f"  - would download {t.package}/{t.filename}  <-  {t.url}")
            tqdm.write(f"output dir: {output_abs}")
            return

        if not todo:
            tqdm.write("nothing to download.")
            tqdm.write(f"output dir: {output_abs}")
            return

        dl_tasks = [_download_one(client, t, output, sem) for t in todo]
        ok: list[FileTask] = []
        for coro in tqdm.as_completed(dl_tasks, desc="download", unit="file", total=len(dl_tasks)):
            result = await coro
            if result is not None:
                ok.append(result)
        tqdm.write(f"done: {len(ok)}/{len(todo)} succeeded")
        tqdm.write(f"output dir: {output_abs}")
        if ok:
            tqdm.write("")
            tqdm.write(_format_downloaded_markdown(ok))


@cmd.callback(invoke_without_command=True)
def main(
    ctx: typer.Context,
    index_url: str = typer.Argument(..., help="simple 索引根 URL, 例如 https://pypi.org/simple/"),
    _: bool = typer.Option(False, "--version", "-v", "-V", callback=version_callback),
    output: Path = typer.Option(Path("./dist/pypi"), "--output", "-o", help="下载根目录, 默认 ./dist/pypi"),
    user_agent: str = typer.Option(
        _default_user_agent(),
        "--user-agent",
        help="自定义 User-Agent。默认为 httpx 原生 UA (python-httpx/<ver>); 私有源若同时拒绝浏览器和 pip/twine/uv/poetry 等包管理 UA, 通用 HTTP 客户端 UA 通常能放行。",
    ),
    cookie: str | None = typer.Option(None, "--cookie", help="原样透传的 Cookie 头"),
    username: str | None = typer.Option(None, "--username", "-u", help="HTTP Basic 用户名 (与 pip 相同)"),
    password: str | None = typer.Option(None, "--password", "-p", help="HTTP Basic 密码"),
    package: list[str] = typer.Option([], "--package", help="只下载指定包, 可多次传; 默认全部"),
    timeout: float = typer.Option(60.0, "--timeout", help="单次请求超时秒数"),
    concurrency: int = typer.Option(16, "--concurrency", "-c", min=1, help="并发上限, 默认 16"),
    max_files: int | None = typer.Option(None, "--max", help="去重后最多下载的文件数; 默认不限"),
    force: bool = typer.Option(False, "--force", "-f", help="强制下载, 跳过本地去重"),
    dry_run: bool = typer.Option(False, "--dry-run", help="只列出将要下载的文件, 不真正下载"),
) -> None:
    if ctx.invoked_subcommand is not None:
        return
    if (username is None) != (password is None):
        raise typer.BadParameter("--username 与 --password 必须同时提供")

    headers = {"User-Agent": user_agent}
    if cookie:
        headers["Cookie"] = cookie
    auth = (username, password) if username and password else None
    base = _normalize_index_url(index_url)

    asyncio.run(
        _run(
            base=base,
            output=output,
            headers=headers,
            auth=auth,
            timeout=timeout,
            concurrency=concurrency,
            package_filter=package,
            force=force,
            max_files=max_files,
            dry_run=dry_run,
        )
    )


if __name__ == "__main__":
    cmd()
