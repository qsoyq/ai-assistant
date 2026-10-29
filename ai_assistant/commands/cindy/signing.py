"""Read-only application identity checks and system trash integration."""

from __future__ import annotations

import json
import plistlib
import re
import struct
import subprocess
import sys
from pathlib import Path
from typing import Any

from .common import CindyError
from .paths import is_link

# Verified against official regional bundles in the design's 2026-10-29 survey.
MAC_IDENTITIES = {"cn": ("NTC4BJ542G", "com.xd.cindycn"), "global": ("SX9RG894L5", "com.xd.cindy")}


def run_checked(args: list[str]) -> subprocess.CompletedProcess[str]:
    result = subprocess.run(args, capture_output=True, text=True, timeout=120, check=False)
    if result.returncode:
        raise CindyError(f"系统校验失败：{Path(args[0]).name}（退出码 {result.returncode}）。", 4)
    return result


def mac_info(app: Path) -> dict[str, Any]:
    path = app / "Contents/Info.plist"
    if is_link(app) or is_link(path) or path.stat().st_size > 1024**2:
        raise CindyError("app 或 Info.plist 无效。", 4)
    with path.open("rb") as stream:
        value = plistlib.load(stream)
    if not isinstance(value, dict):
        raise CindyError("Info.plist 格式错误。", 4)
    return value


def verify_mac(app: Path, region: str, version: str | None = None, arch: str | None = None) -> dict[str, Any]:
    if sys.platform != "darwin":
        raise CindyError("macOS 签名只能在 macOS 校验。", 5)
    info = mac_info(app)
    team, bundle = MAC_IDENTITIES[region]
    run_checked(["/usr/bin/codesign", "--verify", "--deep", "--strict", str(app)])
    run_checked(["/usr/sbin/spctl", "--assess", "--type", "execute", str(app)])
    signing = run_checked(["/usr/bin/codesign", "-dv", "--verbose=4", str(app)])
    found = re.search(r"^TeamIdentifier=(.+)$", signing.stderr, re.MULTILINE)
    if not found or found[1] != team or info.get("CFBundleIdentifier") != bundle:
        raise CindyError("签名 TeamID 或区域 bundle ID 不符。", 4)
    actual = str(info.get("CFBundleShortVersionString", ""))
    if version is not None and actual != version:
        raise CindyError(f"app 版本不符：请求 {version}，实际 {actual}。", 4)
    executable = info.get("CFBundleExecutable")
    if not isinstance(executable, str) or Path(executable).name != executable:
        raise CindyError("app 可执行文件名无效。", 4)
    if arch:
        architectures = run_checked(["/usr/bin/lipo", "-archs", str(app / "Contents/MacOS" / executable)]).stdout.split()
        if ("arm64" if arch == "arm64" else "x86_64") not in architectures:
            raise CindyError("app 的 Mach-O 架构不匹配。", 4)
    return {"version": actual, "bundle_id": bundle, "team": team, "exe": executable}


def trash_app(path: Path) -> None:
    from Foundation import NSURL, NSFileManager

    result = NSFileManager.defaultManager().trashItemAtURL_resultingItemURL_error_(NSURL.fileURLWithPath_(str(path)), None, None)
    if not result[0]:
        raise CindyError("新 app 已提交，旧 app 无法移至系统废纸篓；保留 old，运行 recover 收尾。", 6)


def asar_version(path: Path) -> str | None:
    if not path.is_file() or is_link(path):
        return None
    try:
        with path.open("rb") as stream:
            prefix = stream.read(16)
            if len(prefix) != 16:
                return None
            _, header_size, _, json_size = struct.unpack("<4I", prefix)
            if not 0 < json_size <= 16 * 1024**2 or header_size < json_size + 8:
                return None
            header = json.loads(stream.read(json_size))
            package = header["files"]["package.json"]
            offset, size = int(package["offset"]), int(package["size"])
            if offset < 0 or not 0 < size <= 1024**2:
                return None
            stream.seek(8 + header_size + offset)
            value = json.loads(stream.read(size)).get("version")
            return value if isinstance(value, str) else None
    except (OSError, ValueError, KeyError, struct.error):
        return None


def actual_version(path: Path, platform: str) -> str | None:
    if platform == "darwin":
        try:
            return str(mac_info(path)["CFBundleShortVersionString"])
        except (OSError, ValueError, KeyError, CindyError):
            return None
    if platform == "linux":
        info = path / "current/resources/linux-build-info"
        if info.is_file() and not is_link(info) and info.stat().st_size < 4096:
            fields = info.read_text().splitlines()
            if len(fields) == 5 and fields[0] == "cindy-linux-v1":
                return fields[1]
        return None
    return asar_version(path / "resources/app.asar")
