"""Region-aware artifact resolution. Installer digests never authenticate ZIPs."""

from __future__ import annotations

import hashlib
import os
import re
import time
from dataclasses import asdict, dataclass
from pathlib import PurePosixPath
from typing import Any
from urllib.parse import urljoin, urlsplit

from .common import CindyError
from .download import allowed_url, http_json
from .state import State, atomic_json, read_json

CDN = {"cn": "https://hotfix.cindy.com.cn/cindy", "global": "https://hotfix.cindy.app/cindy"}
CHANNELS = ("release", "beta", "canary")
MATRIX = {("darwin", "x64"), ("darwin", "arm64"), ("win32", "x64"), ("linux", "x64")}
MODES = {"darwin": "dmg", "win32": "portable", "linux": "user-install"}
KINDS = {"dmg": "dmg", "portable": "hotfix-zip", "installer": "setup-exe", "user-install": "deb"}


@dataclass(frozen=True)
class Artifact:
    region: str
    platform: str
    arch: str
    mode: str
    kind: str
    version: str
    selector: str
    channel: str | None
    url: str
    sha256: str | None
    size: int | None
    digest_source: str

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


class Releases:
    def __init__(self, state: State | None = None):
        self.state = state or State()
        self.cdns = {region: os.environ.get(f"AI_ASSISTANT_CINDY_CDN_{region.upper()}", url).rstrip("/") for region, url in CDN.items()}
        self.api = os.environ.get("AI_ASSISTANT_CINDY_GITHUB_API", "https://api.github.com").rstrip("/")
        self.origins = (*self.cdns.values(), self.api)
        self.custom_sources = [f"{urlsplit(base).scheme}://{urlsplit(base).netloc}" for base in self.origins if base not in {*CDN.values(), "https://api.github.com"}]
        for base in self.origins:
            allowed_url(base, origins=self.origins)

    def get(self, url: str, *, cached: bool = False) -> Any:
        key = hashlib.sha256(url.encode()).hexdigest()
        path = self.state.home / "cache" / f"{key}.json"
        if cached:
            saved = read_json(path)
            if saved.get("url") == url and time.time() - saved.get("time", 0) < 600:
                return saved["data"]
        token = os.environ.get("GH_TOKEN") or os.environ.get("GITHUB_TOKEN")
        value = http_json(url, token=token, origins=self.origins)
        if cached:
            atomic_json(path, {"url": url, "time": time.time(), "data": value})
        return value

    def manifest(self, region: str, platform: str, arch: str, channel: str) -> dict[str, Any]:
        suffix = "" if channel == "release" else f"-{channel}"
        value = self.get(f"{self.cdns[region]}/manifest-{platform}-{arch}{suffix}.json")
        if not isinstance(value, dict) or not isinstance(value.get("app"), dict) or not isinstance(value["app"].get("version"), str):
            raise CindyError("渠道清单结构无效。", 4)
        return dict(value["app"])

    def release(self, version: str, beta: bool = False) -> dict[str, Any]:
        tags = [f"v{version}-beta"] if beta else [f"v{version}", f"v{version}-beta"]
        for index, tag in enumerate(tags):
            try:
                value = self.get(f"{self.api}/repos/makecindy/cindy/releases/tags/{tag}", cached=True)
                if not isinstance(value, dict) or not isinstance(value.get("assets"), list):
                    raise CindyError("GitHub release 结构无效。", 4)
                return value
            except CindyError as exc:
                if exc.code != 5 or index == len(tags) - 1:
                    raise
        raise CindyError("没有对应 Release。", 5)

    def asset(self, release: dict[str, Any], region: str, platform: str, arch: str, version: str, mode: str) -> dict[str, Any] | None:
        extension = {"dmg": "dmg", "installer": "exe", "user-install": "deb"}.get(mode)
        if extension is None:
            return None
        name = f"cindy-{version}-{platform}-{arch}-{region}.{extension}"
        matches = [item for item in release["assets"] if isinstance(item, dict) and item.get("name") == name]
        if len(matches) > 1:
            raise CindyError("同名 GitHub 资产重复。", 4)
        return matches[0] if matches else None

    def resolve(
        self,
        region: str,
        platform: str,
        arch: str,
        *,
        version: str = "latest",
        channel: str | None = None,
        mode: str = "auto",
        source: str = "cdn",
        manual_sha256: str | None = None,
        signature_only: bool = False,
    ) -> Artifact:
        if region not in CDN or (platform, arch) not in MATRIX:
            raise CindyError("没有对应构建。可用矩阵：darwin-x64、darwin-arm64、win32-x64、linux-x64；区域 cn/global。", 5)
        mode = MODES[platform] if mode == "auto" else mode
        if mode not in KINDS or (platform != "win32" and mode != MODES[platform]) or (platform == "win32" and mode not in {"portable", "installer"}):
            raise CindyError("安装模式与平台不匹配。", 2)
        if version != "latest" and channel is not None:
            raise CindyError("显式版本不能同时指定 channel。", 2)
        if manual_sha256 and not re.fullmatch(r"[0-9a-fA-F]{64}", manual_sha256):
            raise CindyError("sha256 必须为 64 位十六进制。", 2)
        selector = version
        beta = version.endswith("-beta")
        metadata: dict[str, Any] | None = None
        evidence = None
        if version == "latest":
            evidence = channel or "release"
            app = self.manifest(region, platform, arch, evidence)
            match = re.fullmatch(r"v?([0-9]+\.[0-9]+\.[0-9]+)(-beta)?", app["version"])
            if not match:
                raise CindyError("渠道清单中的版本格式无效。", 4)
            version = match[1]
            metadata = app.get("hotfix" if mode == "portable" else "installer")
            if not isinstance(metadata, dict) or not metadata.get("file"):
                raise CindyError("此渠道缺少所选模式的产物。", 5)
        else:
            match = re.fullmatch(r"v?([0-9]+\.[0-9]+\.[0-9]+)(-beta)?", version)
            if not match:
                raise CindyError("版本格式：latest、X.Y.Z、vX.Y.Z、X.Y.Z-beta。", 2)
            version = match[1]
            found = []
            for candidate in ("beta",) if beta else CHANNELS:
                try:
                    app = self.manifest(region, platform, arch, candidate)
                    item = app.get("hotfix" if mode == "portable" else "installer")
                    if app["version"].removeprefix("v").removesuffix("-beta") == version and isinstance(item, dict) and item.get("file"):
                        found.append((candidate, item))
                except CindyError as exc:
                    if exc.code == 4:
                        raise
            if found:
                if len({item.get("sha256") for _, item in found}) > 1:
                    raise CindyError("同一版本产物的清单摘要冲突。", 4)
                evidence, metadata = found[0]
        if platform == "linux" and tuple(int(value) for value in version.split("-")[0].split(".")) < (0, 1, 88):
            raise CindyError("Linux 用户级安装不支持 v0.1.88 之前的版本。", 5)
        asset = None
        if source == "github" or (metadata is None and mode != "portable"):
            try:
                asset = self.asset(self.release(version.removesuffix("-beta"), beta), region, platform, arch, version.removesuffix("-beta"), mode)
            except CindyError as exc:
                if exc.code == 4 or source == "github":
                    raise
        if source == "github" and asset is None:
            raise CindyError("GitHub 没有所选模式的同类型资产；不会切换为安装器。", 5)
        remote = metadata.get("sha256") if metadata else None
        asset_digest = asset.get("digest") if asset else None
        if asset_digest:
            if not isinstance(asset_digest, str) or not asset_digest.startswith("sha256:"):
                raise CindyError("GitHub digest 格式无效。", 4)
            asset_digest = asset_digest[7:]
            if remote and remote.lower() != asset_digest.lower():
                raise CindyError("清单与 GitHub 的同产物摘要不一致。", 4)
            remote = remote or asset_digest
        if remote and (not isinstance(remote, str) or not re.fullmatch(r"[0-9a-fA-F]{64}", remote)):
            raise CindyError("远端 SHA-256 格式无效。", 4)
        manual_sha256 = manual_sha256.lower() if manual_sha256 else None
        if remote and manual_sha256 and remote.lower() != manual_sha256:
            raise CindyError("手动摘要与远端可信摘要冲突。", 4)
        digest = remote.lower() if remote else manual_sha256
        if not digest and not (signature_only and mode == "dmg"):
            raise CindyError("没有所选产物的可信 SHA-256；历史 portable ZIP 不能使用 Setup.exe 的摘要。可提供 --sha256，或显式选择官方 installer。", 4)
        url = self.historical_url(region, platform, arch, version, mode)
        if metadata:
            file = metadata.get("file")
            if not isinstance(file, str) or ".." in PurePosixPath(file).parts:
                raise CindyError("清单中的产物路径无效。", 4)
            url = urljoin(f"{self.cdns[region]}/", file.lstrip("/"))
        if source == "github" and asset:
            url = str(asset.get("browser_download_url", ""))
        if not isinstance(url, str):
            raise CindyError("产物 URL 无效。", 4)
        allowed_url(url, origins=self.origins)
        if urlsplit(url).query:
            raise CindyError("初始产物 URL 不允许含查询凭证；只允许官方重定向内部使用签名查询。", 4)
        size = metadata.get("size") if metadata else (asset.get("size") if asset else None)
        if size is not None and (type(size) is not int or not 0 < size <= 2 * 1024**3):
            raise CindyError("远端产物大小无效。", 4)
        return Artifact(
            region,
            platform,
            arch,
            mode,
            KINDS[mode],
            version,
            selector,
            evidence,
            url,
            digest,
            size,
            "manifest" if metadata and remote else ("github" if asset_digest else ("user" if manual_sha256 else "signature-only")),
        )

    def historical_url(self, region: str, platform: str, arch: str, version: str, mode: str) -> str:
        base = self.cdns[region]
        if mode == "portable":
            return f"{base}/hotfix/{platform}-{arch}/cindy-{version}-hotfix.zip"
        filename = f"cindy-{version}-{arch}.dmg" if mode == "dmg" else (f"cindy-{version}-Setup.exe" if mode == "installer" else f"cindy-{version}-amd64.deb")
        return f"{base}/app/{platform}-{arch}/{filename}"

    def listing(self, regions: list[str], platform: str, arch: str, limit: int) -> dict[str, Any]:
        current: list[dict[str, Any]] = []
        for region in regions:
            for channel in CHANNELS:
                try:
                    current.append({"region": region, "channel": channel, "app": self.manifest(region, platform, arch, channel)})
                except CindyError as exc:
                    current.append({"region": region, "channel": channel, "error": str(exc), "code": exc.code})
        history: list[dict[str, Any]] = []
        for page in range(1, 21):
            if len(history) >= limit:
                break
            values = self.get(f"{self.api}/repos/makecindy/cindy/releases?per_page=100&page={page}", cached=True)
            if not isinstance(values, list):
                raise CindyError("GitHub Releases 列表格式错误。", 4)
            for release in values:
                if release.get("draft"):
                    continue
                assets = [asset["name"] for asset in release.get("assets", []) if any(f"-{platform}-{arch}-{region}." in asset.get("name", "") for region in regions)]
                if assets:
                    history.append({"tag": release.get("tag_name"), "assets": assets})
            if len(values) < 100:
                break
        return {"current": current, "history": history[:limit], "platform": platform, "arch": arch}
