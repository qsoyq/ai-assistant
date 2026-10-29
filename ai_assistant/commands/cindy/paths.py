"""Profile identity and filesystem ownership boundaries."""

from __future__ import annotations

import hashlib
import os
import platform
import re
import shutil
import stat
import subprocess
import sys
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

from .common import CindyError

REGION_DIRS = {"cn": "Cindy", "global": "CindyGlobal", "dev": "CindyDev"}
RESERVED = {"CON", "PRN", "AUX", "NUL", *(f"COM{i}" for i in range(1, 10)), *(f"LPT{i}" for i in range(1, 10))}


def host_platform() -> str:
    return normalize_platform(sys.platform)


def normalize_platform(value: str) -> str:
    result = {"mac": "darwin", "macos": "darwin", "win": "win32", "windows": "win32"}.get(value.lower(), value.lower())
    if result not in {"darwin", "win32", "linux"}:
        raise CindyError("平台可选值：darwin、win32、linux。", 2)
    return result


def normalize_arch(value: str) -> str:
    result = {"intel": "x64", "amd64": "x64", "x86_64": "x64", "aarch64": "arm64"}.get(value.lower(), value.lower())
    if result not in {"x64", "arm64"}:
        raise CindyError("架构可选值：x64、arm64；不接受 arm。", 2)
    return result


def native_arch() -> str:
    if sys.platform == "darwin":
        check = subprocess.run(["/usr/sbin/sysctl", "-n", "hw.optional.arm64"], capture_output=True, text=True, check=False)
        if check.returncode == 0 and check.stdout.strip() == "1":
            return "arm64"
    return normalize_arch(os.environ.get("PROCESSOR_ARCHITEW6432", platform.machine()))


def app_data(home: Path | None = None) -> Path:
    home = home or Path.home()
    if sys.platform == "darwin":
        return home / "Library/Application Support"
    if sys.platform == "win32":
        return Path(os.environ.get("APPDATA", str(home / "AppData/Roaming")))
    return Path(os.environ.get("XDG_CONFIG_HOME", str(home / ".config")))


def state_home() -> Path:
    raw = os.environ.get("AI_ASSISTANT_CINDY_HOME")
    path = Path(raw) if raw else Path(os.environ.get("XDG_STATE_HOME", str(Path.home() / ".local/state"))) / "ai-assistant/cindy"
    if not path.is_absolute():
        raise CindyError("状态目录必须为绝对路径。", 2)
    return path


def runtime_home() -> Path:
    if sys.platform == "darwin":
        return Path.home() / "Library/Caches/ai-assistant/cindy"
    if sys.platform == "win32":
        return Path(os.environ.get("LOCALAPPDATA", str(Path.home() / "AppData/Local"))) / "ai-assistant/cindy-runtime"
    return Path.home() / ".cache/ai-assistant/cindy"


def is_link(path: Path) -> bool:
    try:
        info = path.lstat()
    except FileNotFoundError:
        return False
    return stat.S_ISLNK(info.st_mode) or bool(getattr(info, "st_reparse_tag", 0))


def exists(path: Path) -> bool:
    return os.path.lexists(path)


def identity(path: Path) -> list[int] | None:
    if not exists(path):
        return None
    info = path.lstat()
    return [info.st_dev, info.st_ino, getattr(info, "st_birthtime_ns", 0)]


def outside_git(path: Path) -> None:
    for parent in (path.resolve(), *path.resolve().parents):
        if (parent / ".git").exists() or ((parent / "HEAD").is_file() and (parent / "objects").is_dir() and (parent / "refs").is_dir()):
            raise CindyError(f"含敏感数据的路径不能位于 Git 工作区：{path}", 2)


def root_path(path: Path, *, sensitive: bool = True) -> Path:
    path = path.expanduser().absolute()
    if is_link(path):
        raise CindyError(f"操作根不能是符号链接、junction 或 reparse point：{path}", 2)
    result = path.resolve()
    forbidden = {Path(result.anchor), Path.home().resolve(), app_data().resolve(), Path("/Applications"), (Path.home() / "Applications").resolve()}
    if result in forbidden or (result.exists() and os.path.ismount(result)):
        raise CindyError(f"拒绝操作容器或挂载根：{result}", 2)
    if sys.platform != "win32":
        import psutil

        partitions = [part for part in psutil.disk_partitions(all=True) if result == Path(part.mountpoint) or Path(part.mountpoint) in result.parents]
        if partitions:
            filesystem = max(partitions, key=lambda part: len(part.mountpoint)).fstype.lower()
            if filesystem in {"nfs", "nfs4", "smbfs", "cifs", "afpfs", "sshfs", "fuse.sshfs"}:
                raise CindyError("不支持网络文件系统上的数据或安装事务。", 2)
    if sensitive:
        outside_git(result)
    return result


def disjoint(first: Path, second: Path) -> None:
    first, second = first.resolve(), second.resolve()
    if first == second or first in second.parents or second in first.parents:
        raise CindyError(f"路径不能互相包含：{first} / {second}", 2)


def private_dir(path: Path) -> None:
    if is_link(path):
        raise CindyError(f"私有目录不能是链接：{path}", 2)
    if sys.platform == "win32":
        raise CindyError("Windows 私有 DACL/运行锁尚未通过实机门禁；当前仅开放只读查询。", 5)
    path.mkdir(mode=0o700, parents=True, exist_ok=True)
    if not path.is_dir() or path.stat().st_uid != os.getuid():
        raise CindyError(f"目录不属于当前用户：{path}", 6)
    path.chmod(0o700)


def check_space(path: Path, amount: int) -> None:
    while not path.exists():
        path = path.parent
    if shutil.disk_usage(path).free < amount + max(amount // 10, 256 * 1024**2):
        raise CindyError(f"可用空间不足：{path}")


def safe_id(value: str) -> str:
    if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._-]{0,95}", value) or value.split(".")[0].upper() in RESERVED or value.endswith("."):
        raise CindyError("ID 只能使用 1-96 位字母、数字、点、下划线和连字符，不能是保留名。", 2)
    return value


def keychain_identity(path: Path) -> str:
    marker = path / "keychain-identity"
    if not exists(marker):
        return "absent"
    if is_link(marker) or marker.stat().st_size > 1024:
        raise CindyError("keychain-identity 标记异常。", 6)
    value = marker.read_text(encoding="utf-8")
    # The trailing newline distinguishes a complete marker from a torn claim.
    if value not in {"Cindy\n", "CindyDev\n"}:
        raise CindyError("keychain-identity 标记无法识别或尚未完整写入。", 6)
    return value.removesuffix("\n")


@dataclass(frozen=True)
class Profile:
    region: str
    kind: str
    name: str
    path: str
    app_data: str
    platform: str
    arch: str
    keychain_identity: str
    profile_key: str

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def profile_for(path: Path | None = None, region: str | None = None, *, base: Path | None = None) -> Profile:
    base = (base or app_data()).resolve()
    if path is None:
        if region not in REGION_DIRS:
            raise CindyError("必须指定 --region 或 --path。", 2)
        path = base / REGION_DIRS[region]
    path = root_path(path)
    guessed = None
    isolated = False
    for candidate, name in REGION_DIRS.items():
        if path.name == name or path.name == f"{name}-dev2" or path.name.startswith(f"{name}-dev2-"):
            guessed = candidate
            isolated = path.name != name
            break
    if region and guessed and region != guessed:
        raise CindyError("目录名与指定区域冲突。", 2)
    region = region or guessed
    if region not in REGION_DIRS:
        raise CindyError("自定义目录无法推断区域，请同时指定 --region。", 2)
    kind = ("isolated" if isolated else "main") if path.parent == base and guessed else "custom"
    key = hashlib.sha256(f"{host_platform()}:{region}:{path}".encode()).hexdigest()
    return Profile(region, kind, path.name, str(path), str(base), host_platform(), native_arch(), keychain_identity(path), key)


def discovered_profiles(base: Path | None = None) -> list[Path]:
    base = base or app_data()
    result = [base / name for name in REGION_DIRS.values()]
    if base.is_dir():
        result.extend(path for path in base.iterdir() if any(path.name == f"{name}-dev2" or path.name.startswith(f"{name}-dev2-") for name in REGION_DIRS.values()) and not is_link(path))
    return result
