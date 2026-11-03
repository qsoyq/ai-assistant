"""Conservative process evidence. Never terminates a process."""

from __future__ import annotations

import os
import socket
from pathlib import Path
from typing import Iterable

from .common import CindyError
from .paths import Profile, discovered_profiles, exists, is_link

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


def overlaps(first: Path, second: Path) -> bool:
    return first == second or first in second.parents or second in first.parents


def explicit_profile(argv: list[str]) -> Path | None:
    """Only accept one absolute Chromium profile argument; ambiguity is unsafe."""
    values: list[str] = []
    for index, argument in enumerate(argv):
        if argument == "--user-data-dir":
            values.append(argv[index + 1] if index + 1 < len(argv) else "")
        elif argument.startswith("--user-data-dir="):
            values.append(argument.split("=", 1)[1])
    if not values:
        return None
    if len(values) != 1 or not Path(values[0]).is_absolute():
        raise ValueError("目录参数重复、缺失或不是绝对路径")
    return Path(values[0]).resolve()


def backup_running_state(target: Path, paths: Iterable[Path], *, names: set[str] | None = None, observed: dict[int, float] | None = None) -> tuple[str, list[str]]:
    """Scoped cold-backup evidence. No region or executable-name exemption."""
    import psutil

    target = target.resolve()
    roots = {target, *(path.resolve() for path in paths)}
    accepted = NAMES if names is None else names
    busy: list[str] = []
    unknown: list[str] = []
    owners: dict[int, set[Path]] = {}
    for root in roots:
        lock = root / "SingletonLock"
        if not exists(lock):
            continue
        try:
            host, raw_pid = os.readlink(lock).rsplit("-", 1)
            pid = int(raw_pid)
            if host != socket.gethostname() or pid <= 0:
                raise ValueError("异机或无效 PID")
            if psutil.pid_exists(pid):
                if overlaps(target, root):
                    busy.append(f"目标目录存在存活 SingletonLock：进程 {pid}")
                proc = psutil.Process(pid)
                name = proc.name().lower()
                owner_executable = Path(proc.exe()).resolve()
                if not (name in accepted or (names is None and name.startswith("cindy")) or any(path in owner_executable.parents for path in roots)):
                    raise ValueError("锁 PID 不是可识别的 Cindy 进程")
                if proc.create_time() > lock.lstat().st_mtime:
                    raise ValueError("锁早于当前进程，可能发生 PID 复用")
                owners.setdefault(pid, set()).add(root)
        except psutil.NoSuchProcess:
            continue
        except (OSError, ValueError, psutil.AccessDenied):
            unknown.append(f"无法核对 Profile 锁：{root}")

    processes = {}
    for proc in psutil.process_iter(["name", "exe", "ppid", "uids"]):
        try:
            # Do not scan other users' arbitrary files. Their live profile locks still block.
            uids = proc.info.get("uids")
            if uids is not None and uids.effective != os.getuid():
                continue
            processes[proc.pid] = proc
        except psutil.NoSuchProcess:
            continue
        except psutil.AccessDenied:
            unknown.append(f"无法核对进程身份：{proc.pid}")

    related_pids = {
        pid
        for pid, proc in processes.items()
        if (proc.info.get("name") or "").lower() in accepted
        or (names is None and (proc.info.get("name") or "").lower().startswith("cindy"))
        or (proc.info.get("exe") and any(root in Path(proc.info["exe"]).resolve().parents for root in roots))
        or pid in owners
    }
    for pid, proc in processes.items():
        try:
            executable = Path(proc.info["exe"]).resolve() if proc.info.get("exe") else None
            lineage = [pid]
            ancestor = proc.info.get("ppid")
            while ancestor in processes and ancestor not in lineage:
                lineage.append(ancestor)
                ancestor = processes[ancestor].info.get("ppid")
            related = any(item in related_pids for item in lineage)
            if observed is not None:
                related = related or observed.get(pid) == proc.create_time()
                if related:
                    # Remember descendants across reparenting; never reuse evidence for a recycled PID.
                    observed[pid] = proc.create_time()
            if executable is not None and overlaps(target, executable):
                busy.append(f"目标内的引擎仍运行：进程 {pid}")
            # Also detect visible external writers and orphaned children, regardless of name.
            if pid != os.getpid():
                try:
                    if any(overlaps(target, Path(item.path).resolve()) for item in proc.open_files()):
                        busy.append(f"进程 {pid} 仍占用目标内文件")
                except psutil.AccessDenied:
                    if related:
                        unknown.append(f"无法检查相关进程文件占用：{pid}")
            if not related:
                continue
            if not proc.info.get("name") or executable is None:
                unknown.append(f"相关进程身份不完整：{pid}")
                continue
            argv = proc.cmdline()
            if not argv:
                unknown.append(f"无法读取相关进程启动参数：{pid}")
                continue
            selected = explicit_profile(argv)
            # Any absolute argument inside the target is sufficient to refuse, not to allow.
            if any(Path(arg).is_absolute() and overlaps(target, Path(arg).resolve()) for arg in argv):
                busy.append(f"相关进程参数涉及目标目录：{pid}")
            if selected is not None and overlaps(target, selected):
                busy.append(f"相关进程显式使用目标目录：{pid}")
            override = proc.environ().get("XDT_USER_DATA_DIR")
            overridden = None
            if override:
                if not Path(override).is_absolute():
                    raise ValueError("环境目录不是绝对路径")
                overridden = Path(override).resolve()
                if overlaps(target, overridden):
                    busy.append(f"相关进程环境指向目标 Profile：{pid}")
            bound = next((owners[item] for item in lineage if item in owners), set())
            if bound:
                if len(bound) != 1 or any(value is not None and value not in bound for value in (selected, overridden)):
                    unknown.append(f"相关进程 Profile 归属冲突：{pid}")
                elif overlaps(target, next(iter(bound))):
                    busy.append(f"目标 Profile 的主进程或子进程仍运行：{pid}")
                continue
            # Without an actual lock, a dev environment override wins over Chromium argv.
            selected = overridden or selected
            if selected is None:
                unknown.append(f"相关进程无法证明属于其他 Profile：{pid}")
            elif overlaps(target, selected):
                busy.append(f"相关进程使用目标 Profile：{pid}")
        except psutil.NoSuchProcess:
            continue
        except (psutil.AccessDenied, OSError, ValueError):
            unknown.append(f"无法可靠核对相关进程：{pid}")
    return ("busy", busy) if busy else (("unknown", unknown) if unknown else ("stopped", []))


def require_backup_stopped(profile: Profile, extra: Iterable[Path] = (), *, observed: dict[int, float] | None = None, names: set[str] | None = None) -> None:
    target = Path(profile.path)
    paths = [*discovered_profiles(Path(profile.app_data)), *extra, target]
    # CN's shared storage is inside its main root. Never exempt it, even if empty.
    shared = target.is_dir() and any(item.name.startswith("shared-") and not is_link(item) for item in target.iterdir())
    if (profile.region == "cn" and profile.kind == "main") or shared:
        require_stopped(paths)
        return
    status, reasons = backup_running_state(target, paths, observed=observed, names=names)
    if status != "stopped":
        raise CindyError(f"请退出使用目标 Profile 的实例及子进程；归属不明也不能备份；状态 {status}：{'；'.join(reasons)}", 3 if status == "busy" else 6)


def require_stopped(extra: Iterable[Path] = ()) -> None:
    status, reasons = running_state([*discovered_profiles(), *extra])
    if status != "stopped":
        raise CindyError(f"请完全退出所有 Cindy；状态 {status}：{'；'.join(reasons)}", 3 if status == "busy" else 6)
