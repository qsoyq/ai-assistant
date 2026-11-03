"""Real loopback HTTP service for metadata, redirects and Range transfers."""

from __future__ import annotations

import hashlib
import json
import os
import re
import select
import subprocess
import sys
import threading
import time
import zipfile
from contextlib import contextmanager
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Iterator

import pytest
from typer.testing import CliRunner

from ai_assistant.commands.cindy import cmd
from ai_assistant.commands.cindy.common import CindyError
from ai_assistant.commands.cindy.download import allowed_url, download_file
from ai_assistant.commands.cindy.install import extract_portable
from ai_assistant.commands.cindy.releases import Releases
from ai_assistant.commands.cindy.state import State, atomic_json

pytestmark = pytest.mark.skipif(os.name != "posix", reason="POSIX private-storage gate; Windows mutations remain disabled")


@contextmanager
def local_http(routes: dict[str, bytes]) -> Iterator[tuple[str, list[dict[str, str]]]]:
    requests: list[dict[str, str]] = []

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *args):
            pass

        def do_GET(self):
            requests.append({"path": self.path, **dict(self.headers.items())})
            if self.path == "/redirect":
                self.send_response(302)
                self.send_header("Location", "http://untrusted.invalid/payload")
                self.end_headers()
                return
            if self.path == "/retry" and sum(item["path"] == "/retry" for item in requests) == 1:
                self.send_response(503)
                self.send_header("Retry-After", "0")
                self.end_headers()
                return
            data = routes.get(self.path)
            if data is None:
                self.send_error(404)
                return
            etag = '"fixture-v1"'
            match = re.fullmatch(r"bytes=([0-9]+)-", self.headers.get("Range", ""))
            offset = int(match[1]) if match and self.headers.get("If-Range") == etag else 0
            if offset >= len(data) and offset:
                self.send_response(416)
                self.send_header("Content-Range", f"bytes */{len(data)}")
                self.end_headers()
                return
            self.send_response(206 if offset else 200)
            if offset:
                self.send_header("Content-Range", f"bytes {offset}-{len(data) - 1}/{len(data)}")
            if self.path != "/unknown":
                self.send_header("Content-Length", str(len(data) - offset))
            self.send_header("ETag", etag)
            self.end_headers()
            self.wfile.write(data[offset:])

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield f"http://127.0.0.1:{server.server_port}", requests
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)


def test_download_resume_206_and_cache_rehash(tmp_path: Path):
    payload = b"fixture-download-data" * 1000
    digest = hashlib.sha256(payload).hexdigest()
    with local_http({"/payload": payload}) as (origin, requests):
        target = tmp_path / "payload"
        target.with_name("payload.part").write_bytes(payload[:100])
        atomic_json(target.with_name("payload.part.json"), {"binding": {"url": f"{origin}/payload", "sha256": digest, "size": len(payload)}, "etag": '"fixture-v1"'})
        download_file(f"{origin}/payload", target, digest, size=len(payload), origins=(origin,))
        assert target.read_bytes() == payload
        assert {key.lower(): value for key, value in requests[0].items()}["range"] == "bytes=100-"
        assert {key.lower(): value for key, value in requests[0].items()}["if-range"] == '"fixture-v1"'
        assert download_file(f"{origin}/payload", target, digest, origins=(origin,)) == target
        target.write_bytes(b"corrupted")
        with pytest.raises(CindyError, match="拒绝覆盖"):
            download_file(f"{origin}/payload", target, digest, origins=(origin,))


def test_download_digest_mismatch_size_and_redirect_are_not_retried(tmp_path: Path):
    with local_http({"/payload": b"fixture"}) as (origin, requests):
        with pytest.raises(CindyError, match="SHA-256"):
            download_file(f"{origin}/payload", tmp_path / "wrong", "0" * 64, origins=(origin,))
        assert len(requests) == 1
        with pytest.raises(CindyError):
            download_file(f"{origin}/payload", tmp_path / "large", "0" * 64, origins=(origin,), max_size=1)
        with pytest.raises(CindyError, match="来源"):
            download_file(f"{origin}/redirect", tmp_path / "redirect", "0" * 64, origins=(origin,))
        assert not (tmp_path / "redirect").exists()
    with pytest.raises(CindyError):
        allowed_url("http://api.github.com/anything")
    with pytest.raises(CindyError):
        allowed_url("https://user:pass@github.com/anything")


def test_range_ignored_200_restarts_instead_of_appending(tmp_path: Path):
    payload = b"fresh"
    digest = hashlib.sha256(payload).hexdigest()
    with local_http({"/payload": payload}) as (origin, _):
        target = tmp_path / "output"
        target.with_name("output.part").write_bytes(b"stale")
        atomic_json(target.with_name("output.part.json"), {"binding": {"url": f"{origin}/payload", "sha256": digest, "size": None}, "etag": '"changed"'})
        download_file(f"{origin}/payload", target, digest, origins=(origin,))
        assert target.read_bytes() == payload


def test_completed_range_416_verified_before_publication(tmp_path: Path):
    payload = b"complete"
    digest = hashlib.sha256(payload).hexdigest()
    with local_http({"/payload": payload}) as (origin, _):
        target = tmp_path / "output"
        target.with_name("output.part").write_bytes(payload)
        atomic_json(target.with_name("output.part.json"), {"binding": {"url": f"{origin}/payload", "sha256": digest, "size": len(payload)}, "etag": '"fixture-v1"'})
        download_file(f"{origin}/payload", target, digest, size=len(payload), origins=(origin,))
        assert target.read_bytes() == payload


def test_latest_region_download_only_cli_no_tokens_to_overrides(tmp_path: Path):
    payload = b"synthetic-installer-not-executable"
    digest = hashlib.sha256(payload).hexdigest()
    manifest = json.dumps({"app": {"version": "0.1.119", "installer": {"file": "app/win32-x64/cindy-0.1.119-Setup.exe", "sha256": digest, "size": len(payload)}}}).encode()
    routes = {"/global/manifest-win32-x64-beta.json": manifest, "/global/app/win32-x64/cindy-0.1.119-Setup.exe": payload}
    with local_http(routes) as (origin, requests):
        env = {"HOME": str(tmp_path), "AI_ASSISTANT_CINDY_HOME": str(tmp_path / "state"), "AI_ASSISTANT_CINDY_CDN_GLOBAL": f"{origin}/global", "GITHUB_TOKEN": "obviously-invalid-fixture-token"}
        result = CliRunner().invoke(cmd, ["install", "--region", "global", "--channel", "beta", "--platform", "win32", "--arch", "x64", "--mode", "installer", "--download-only"], env=env)
        assert result.exit_code == 0, result.output
        assert json.loads(result.stdout)["artifact"]["region"] == "global"
        assert "[阶段]" not in result.stdout
        for message in ("解析客户端版本与可信摘要", "读取 global/win32/x64 的 beta 渠道清单", "请求版本元数据", "版本解析完成", "连接下载服务", "开始下载", "校验下载 SHA-256", "下载与摘要验证完成"):
            assert message in result.stderr
        assert "obviously-invalid-fixture-token" not in result.stderr
        assert "\x1b[" not in result.stderr
        assert payload in [path.read_bytes() for path in (tmp_path / "state/downloads").rglob("*.exe")]
        assert not any("Authorization" in request for request in requests)
        assert not (tmp_path / "state/installs.json").exists()


def test_historical_portable_never_uses_setup_digest(tmp_path: Path):
    with local_http({}) as (origin, _):
        resolver = Releases(State(tmp_path / "state", tmp_path / "runtime"))
        resolver.cdns = {"cn": origin, "global": origin}
        resolver.api = origin
        resolver.origins = (origin,)
        with pytest.raises(CindyError, match="可信 SHA-256"):
            resolver.resolve("cn", "win32", "x64", version="0.1.118")
        with pytest.raises(CindyError) as unavailable:
            resolver.resolve("cn", "win32", "arm64")
        assert unavailable.value.code == 5
        with pytest.raises(CindyError):
            resolver.resolve("cn", "win32", "x64", version="0.1.118", source="github", manual_sha256="0" * 64)


def test_historical_installer_github_digest_downloads_same_artifact(tmp_path: Path):
    payload = b"old-official-artifact-fixture"
    digest = hashlib.sha256(payload).hexdigest()
    routes: dict[str, bytes] = {}
    with local_http(routes) as (origin, requests):
        asset = {"name": "cindy-0.1.118-darwin-arm64-cn.dmg", "digest": f"sha256:{digest}", "size": len(payload), "browser_download_url": f"{origin}/asset.dmg"}
        routes["/repos/makecindy/cindy/releases/tags/v0.1.118"] = json.dumps({"assets": [asset]}).encode()
        routes["/asset.dmg"] = payload
        resolver = Releases(State(tmp_path / "state", tmp_path / "runtime"))
        resolver.cdns = {"cn": origin, "global": origin}
        resolver.api = origin
        resolver.origins = (origin,)
        artifact = resolver.resolve("cn", "darwin", "arm64", version="0.1.118", mode="dmg", source="github")
        assert artifact.sha256 == digest and artifact.url.endswith("asset.dmg")
        download_file(artifact.url, tmp_path / "download", artifact.sha256, origins=(origin,))
        assert (tmp_path / "download").read_bytes() == payload
        assert not any("Authorization" in request for request in requests)


@pytest.mark.parametrize("name", ["../escape", "C:\\escape", "folder\\..\\escape", "file:stream", "CON", "a/../../escape"])
def test_zip_traversal_and_windows_paths_rejected(tmp_path: Path, name: str):
    archive = tmp_path / "portable.zip"
    with zipfile.ZipFile(archive, "w") as output:
        output.writestr(name, "synthetic")
    with pytest.raises(CindyError):
        extract_portable(archive, tmp_path / "extract")
    assert not (tmp_path / "escape").exists()


def test_zip_backslash_paths_and_conflicts(tmp_path: Path):
    archive = tmp_path / "portable.zip"
    with zipfile.ZipFile(archive, "w") as output:
        output.writestr("resources\\fixture.txt", "synthetic")
    extract_portable(archive, tmp_path / "extract")
    assert (tmp_path / "extract/resources/fixture.txt").read_text() == "synthetic"
    with zipfile.ZipFile(archive, "w") as output:
        output.writestr("resources/file", "one")
        output.writestr("RESOURCES/FILE", "two")
    with pytest.raises(CindyError):
        extract_portable(archive, tmp_path / "other")


@pytest.mark.parametrize("response_path", ["/payload", "/unknown", "/retry"])
def test_non_terminal_byte_summary_and_retry(tmp_path: Path, capsys: pytest.CaptureFixture[str], response_path: str):
    payload = b"real-progress-fixture" * 8192
    digest = hashlib.sha256(payload).hexdigest()
    with local_http({response_path: payload}) as (origin, requests):
        download_file(f"{origin}{response_path}", tmp_path / "download", digest, origins=(origin,))
    output = capsys.readouterr()
    assert output.out == ""
    assert "开始下载：0/" in output.err
    assert f"下载传输完成：{len(payload)}/" in output.err
    assert "校验下载 SHA-256：完成" in output.err
    assert "\x1b[" not in output.err
    if response_path == "/unknown":
        assert f"{len(payload)}/未知 字节" in output.err
    if response_path == "/retry":
        assert "HTTP 503" in output.err and len(requests) == 2


def test_resume_progress_reset_and_cache_stages(tmp_path: Path, capsys: pytest.CaptureFixture[str]):
    payload = b"range-progress" * 4096
    digest = hashlib.sha256(payload).hexdigest()
    with local_http({"/payload": payload}) as (origin, _):
        for label, etag in (("resume", '"fixture-v1"'), ("restart", '"old"')):
            target = tmp_path / label
            target.with_name(f"{label}.part").write_bytes(payload[:100])
            atomic_json(target.with_name(f"{label}.part.json"), {"binding": {"url": f"{origin}/payload", "sha256": digest, "size": len(payload)}, "etag": etag})
            download_file(f"{origin}/payload", target, digest, size=len(payload), origins=(origin,))
            captured = capsys.readouterr()
            if label == "resume":
                assert f"断点续传：100/{len(payload)} 字节" in captured.err
            else:
                assert "从零下载" in captured.err
                assert f"开始下载：0/{len(payload)} 字节" in captured.err
            assert target.read_bytes() == payload
        download_file(f"{origin}/payload", tmp_path / "resume", digest, size=len(payload), origins=(origin,))
        captured = capsys.readouterr()
        assert "复核已有缓存 SHA-256：完成" in captured.err
        assert "复用已校验缓存，无需下载" in captured.err
        assert "开始下载" not in captured.err


def test_failed_checksum_is_not_reported_as_success(tmp_path: Path, capsys: pytest.CaptureFixture[str]):
    with local_http({"/payload": b"not-matching"}) as (origin, _):
        target = tmp_path / "download"
        with pytest.raises(CindyError):
            download_file(f"{origin}/payload", target, "0" * 64, origins=(origin,))
    captured = capsys.readouterr()
    assert "校验下载 SHA-256：未完成" in captured.err
    assert "校验下载 SHA-256：完成" not in captured.err
    assert "发布已完成下载" not in captured.err
    assert not target.exists()
    assert target.with_name("download.part").exists()


@pytest.mark.parametrize("response_path,resume", [("/payload", False), ("/payload", True), ("/unknown", False)])
def test_real_terminal_progress_and_clean_stdout(tmp_path: Path, response_path: str, resume: bool):
    import pty

    payload = b"terminal-byte-progress" * 8192
    digest = hashlib.sha256(payload).hexdigest()
    target = tmp_path / "download"
    with local_http({response_path: payload}) as (origin, _):
        if resume:
            target.with_name("download.part").write_bytes(payload[:100])
            atomic_json(target.with_name("download.part.json"), {"binding": {"url": f"{origin}{response_path}", "sha256": digest, "size": None}, "etag": '"fixture-v1"'})
        master, slave = pty.openpty()
        script = """
import json, sys
from pathlib import Path
from ai_assistant.commands.cindy.download import download_file
result = download_file(sys.argv[1], Path(sys.argv[2]), sys.argv[3], origins=(sys.argv[4],))
print(json.dumps({'path': str(result)}))
"""
        process = subprocess.Popen(
            [sys.executable, "-c", script, f"{origin}{response_path}", str(target), digest, origin],
            stdout=subprocess.PIPE,
            stderr=slave,
            env={**os.environ, "TERM": "xterm-256color", "COLUMNS": "120", "PYTHONIOENCODING": "utf-8"},
        )
        os.close(slave)
        chunks = []
        deadline = time.monotonic() + 15
        try:
            while time.monotonic() < deadline:
                ready, _, _ = select.select([master], [], [], 0.1)
                if ready:
                    try:
                        block = os.read(master, 65536)
                    except OSError:
                        break
                    if not block:
                        break
                    chunks.append(block)
                elif process.poll() is not None:
                    break
            stdout, _ = process.communicate(timeout=3)
            assert process.returncode == 0, b"".join(chunks).decode(errors="replace")
        finally:
            if process.poll() is None:
                process.kill()
                process.wait(timeout=5)
            os.close(master)
    rendered = re.sub(r"\x1b\[[0-?]*[ -/]*[@-~]", "", b"".join(chunks).decode("utf-8"))
    assert json.loads(stdout)["path"] == str(target)
    assert "下载" in rendered
    assert "字节" in rendered
    assert "100%" in rendered if response_path == "/payload" else "未知" in rendered
    if resume:
        assert "断点续传：100/" in rendered
    assert target.read_bytes() == payload
