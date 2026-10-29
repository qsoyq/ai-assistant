"""Bounded HTTP requests, trusted-origin redirects and resumable verified files."""

from __future__ import annotations

import os
import re
import time
from contextlib import closing
from pathlib import Path
from typing import Any
from urllib.parse import urljoin, urlsplit

from .common import CindyError
from .paths import is_link, private_dir, root_path
from .state import atomic_json, read_json, sha256

MAX_DOWNLOAD = 2 * 1024**3
OFFICIAL_HOSTS = {"hotfix.cindy.com.cn", "hotfix.cindy.app", "api.github.com", "github.com", "release-assets.githubusercontent.com", "objects.githubusercontent.com"}


def allowed_url(url: str, *, origins: tuple[str, ...] = ()) -> None:
    parsed = urlsplit(url)
    if parsed.username or parsed.password or parsed.fragment or not parsed.hostname:
        raise CindyError("下载 URL 含不允许的凭证、片段或无效主机。", 4)
    local = parsed.hostname in {"127.0.0.1", "localhost", "::1"} and parsed.scheme == "http"
    supplied = any((parsed.scheme, parsed.netloc) == (urlsplit(base).scheme, urlsplit(base).netloc) for base in origins)
    if not ((parsed.scheme == "https" and (parsed.hostname in OFFICIAL_HOSTS or supplied)) or (local and supplied)):
        raise CindyError("URL 不属于允许的 HTTPS 来源或明确的本机测试服务。", 4)


def request(client: Any, url: str, *, headers: dict[str, str] | None = None, origins: tuple[str, ...] = ()) -> Any:
    allowed_url(url, origins=origins)
    response = None
    for _ in range(6):
        # Authorization must never follow a redirect or a custom API base.
        safe_headers = dict(headers or {})
        if urlsplit(url).scheme != "https" or urlsplit(url).netloc != "api.github.com":
            safe_headers.pop("Authorization", None)
        response = client.send(client.build_request("GET", url, headers=safe_headers), stream=True)
        if response.status_code not in {301, 302, 303, 307, 308}:
            return response
        location = response.headers.get("location")
        response.close()
        if not location:
            raise CindyError("重定向缺少 Location。", 4)
        url = urljoin(url, location)
        allowed_url(url, origins=origins)
        headers = {key: value for key, value in (headers or {}).items() if key.lower() != "authorization"}
    raise CindyError("重定向次数超过限制。", 4)


def http_json(url: str, *, token: str | None = None, origins: tuple[str, ...] = ()) -> Any:
    import httpx

    headers = {"Accept": "application/json", "Accept-Encoding": "identity", "User-Agent": "ai-assistant-cindy"}
    if token and urlsplit(url).netloc == "api.github.com" and urlsplit(url).scheme == "https":
        headers["Authorization"] = f"Bearer {token}"
    try:
        with httpx.Client(timeout=httpx.Timeout(60, connect=10), follow_redirects=False) as client:
            for attempt in range(3):
                response = request(client, url, headers=headers, origins=origins)
                with closing(response):
                    if response.status_code == 404:
                        raise CindyError("远端没有对应元数据或产物。", 5)
                    if response.status_code in {408, 429, 500, 502, 503, 504} and attempt < 2:
                        time.sleep(min(5, int(response.headers.get("retry-after", "1"))) if response.headers.get("retry-after", "1").isdigit() else 1)
                        continue
                    if response.status_code != 200:
                        raise CindyError(f"远端元数据请求失败，HTTP {response.status_code}。")
                    content = bytearray()
                    for block in response.iter_bytes():
                        content.extend(block)
                        if len(content) > 16 * 1024**2:
                            raise CindyError("远端元数据超过上限。", 4)
                    import json

                    return json.loads(content)
    except httpx.HTTPError as exc:
        raise CindyError(f"网络请求失败（{type(exc).__name__}），不是版本不存在。") from exc
    except ValueError as exc:
        raise CindyError("远端 JSON 损坏。", 4) from exc


def download_file(url: str, destination: Path, expected: str | None, *, size: int | None = None, origins: tuple[str, ...] = (), max_size: int = MAX_DOWNLOAD) -> Path:
    import httpx

    allowed_url(url, origins=origins)
    destination = root_path(destination)
    if expected is not None and not re.fullmatch(r"[0-9a-f]{64}", expected):
        raise CindyError("SHA-256 必须为 64 位十六进制。", 2)
    if size is not None and (type(size) is not int or size < 1 or size > max_size):
        raise CindyError("产物大小超过限制或无效。", 4)
    private_dir(destination.parent)
    if destination.exists():
        if not destination.is_file() or destination.stat().st_size > max_size:
            raise CindyError("已有缓存/输出不是受限大小的普通文件。", 4)
        if not is_link(destination) and expected and sha256(destination) == expected and (size is None or destination.stat().st_size == size):
            return destination
        raise CindyError("已有缓存/输出文件无法通过摘要验证，拒绝覆盖。", 4)
    partial = destination.with_name(f"{destination.name}.part")
    metadata = destination.with_name(f"{destination.name}.part.json")
    if partial.exists() and partial.stat().st_size > max_size:
        raise CindyError("已有续传文件超过大小限制。", 4)
    binding = {"url": url, "sha256": expected, "size": size}
    if is_link(partial) or is_link(metadata) or (partial.exists() and (not partial.is_file() or partial.stat().st_nlink != 1)):
        raise CindyError("下载临时文件不能为链接。", 4)
    with httpx.Client(timeout=httpx.Timeout(60, connect=10), follow_redirects=False) as client:
        for attempt in range(3):
            saved = read_json(metadata)
            etag = saved.get("etag")
            strong_etag = isinstance(etag, str) and re.fullmatch(r'"[^"\x00-\x20\x7f]*"', etag) is not None
            resume = partial.stat().st_size if partial.exists() and saved.get("binding") == binding and strong_etag else 0
            headers = {"Accept-Encoding": "identity"}
            if resume:
                headers.update({"Range": f"bytes={resume}-", "If-Range": str(etag)})
            try:
                response = request(client, url, headers=headers, origins=origins)
                with closing(response):
                    if response.status_code == 404:
                        raise CindyError("对应下载产物不存在。", 5)
                    if response.status_code == 416:
                        if resume and expected and sha256(partial) == expected and (size is None or resume == size):
                            os.rename(partial, destination)
                            metadata.unlink(missing_ok=True)
                            return destination
                        atomic_json(metadata, {"binding": binding, "etag": None})
                        continue
                    if response.status_code in {408, 429, 500, 502, 503, 504} and attempt < 2:
                        retry = response.headers.get("retry-after", "1")
                        time.sleep(min(int(retry), 5) if retry.isdigit() else 1)
                        continue
                    if response.status_code not in {200, 206}:
                        raise CindyError(f"下载失败，HTTP {response.status_code}。")
                    if response.headers.get("content-encoding", "identity") != "identity":
                        raise CindyError("下载必须使用 identity 内容编码。", 4)
                    range_total = None
                    if response.status_code == 206:
                        match = re.fullmatch(r"bytes ([0-9]+)-([0-9]+)/([0-9]+)", response.headers.get("content-range", ""))
                        if not resume or not match or int(match[1]) != resume or int(match[3]) > max_size or int(match[2]) != int(match[3]) - 1 or (size is not None and int(match[3]) != size):
                            raise CindyError("续传 Content-Range 不匹配。", 4)
                        range_total = int(match[3])
                        if response.headers.get("etag") != etag:
                            raise CindyError("续传 ETag 发生变化。", 4)
                    else:
                        resume = 0
                    length = response.headers.get("content-length")
                    if length and (not length.isdigit() or int(length) + resume > max_size):
                        raise CindyError("下载 Content-Length 超过限制。", 4)
                    new_etag = response.headers.get("etag")
                    atomic_json(metadata, {"binding": binding, "etag": new_etag if new_etag and not new_etag.startswith("W/") else None})
                    flags = os.O_WRONLY | os.O_CREAT | getattr(os, "O_NOFOLLOW", 0) | (os.O_APPEND if resume else os.O_TRUNC)
                    with os.fdopen(os.open(partial, flags, 0o600), "wb") as stream:
                        count = resume
                        for block in response.iter_raw():
                            count += len(block)
                            if count > max_size or (size is not None and count > size):
                                raise CindyError("下载实际大小超过限制。", 4)
                            stream.write(block)
                        stream.flush()
                        os.fsync(stream.fileno())
                    if (size is not None and count != size) or (range_total is not None and count != range_total):
                        raise CindyError("下载字节数与预期或 Content-Range 不同。", 4)
                    if expected and sha256(partial) != expected:
                        raise CindyError("下载 SHA-256 校验失败；不自动切换来源。", 4)
                    os.rename(partial, destination)
                    metadata.unlink(missing_ok=True)
                    return destination
            except httpx.HTTPError as exc:
                if attempt == 2:
                    raise CindyError(f"下载传输失败（{type(exc).__name__}），保留续传文件。") from exc
                time.sleep(attempt + 1)
    raise CindyError("下载重试耗尽，保留临时文件。")
