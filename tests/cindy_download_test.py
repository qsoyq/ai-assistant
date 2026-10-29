"""Real loopback HTTP service for metadata, redirects and Range transfers."""

from __future__ import annotations

import hashlib
import json
import os
import re
import threading
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
        assert '"region": "global"' in result.output
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
