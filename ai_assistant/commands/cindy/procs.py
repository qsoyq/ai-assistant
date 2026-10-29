"""Conservative process evidence. Never terminates a process."""

from __future__ import annotations

import os
import socket
from pathlib import Path
from typing import Iterable

from .common import CindyError
from .paths import discovered_profiles, exists

NAMES = {"cindy", "cindy.exe", "cindydev", "cindydev.exe", "electron", "electron.exe"}


def running_state(paths: Iterable[Path], *, names: set[str] | None = None) -> tuple[str, list[str]]:
    import psutil

    accepted = names if names is not None else NAMES
    paths = list(paths)
    roots = [path.resolve() for path in paths]
    reasons: list[str] = []
    unknown: list[str] = []
    for path in paths:
        lock = path / "SingletonLock"
        if exists(lock):
            try:
                host, pid = os.readlink(lock).rsplit("-", 1)
                if host != socket.gethostname():
                    unknown.append(f"异机锁：{path}")
                elif psutil.pid_exists(int(pid)):
                    proc = psutil.Process(int(pid))
                    if proc.name().lower() in accepted or Path(proc.exe()).name.lower() in accepted:
                        reasons.append(f"{path} 被进程 {pid} 使用")
            except psutil.NoSuchProcess:
                pass
            except (OSError, ValueError, psutil.AccessDenied):
                unknown.append(f"无法核对锁：{path}")
    for proc in psutil.process_iter(["name", "exe"]):
        try:
            name = (proc.info["name"] or "").lower()
            executable = Path(proc.info["exe"]).resolve() if proc.info.get("exe") else None
            owned_engine = names is None and executable is not None and any(root in executable.parents for root in roots)
            if name in accepted or owned_engine or (names is None and name.startswith("cindy") and "helper" in name):
                reasons.append(f"发现相关进程 {proc.pid}（{name}）")
        except psutil.NoSuchProcess:
            pass
        except psutil.AccessDenied:
            unknown.append(f"无法核对进程 {proc.pid}")
    return ("busy", reasons) if reasons else (("unknown", unknown) if unknown else ("stopped", []))


def require_stopped(extra: Iterable[Path] = ()) -> None:
    status, reasons = running_state([*discovered_profiles(), *extra])
    if status != "stopped":
        raise CindyError(f"请完全退出所有 Cindy；状态 {status}：{'；'.join(reasons)}", 3 if status == "busy" else 6)
