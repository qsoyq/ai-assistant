"""Private versioned state and per-user process-released exclusion."""

from __future__ import annotations

import hashlib
import json
import os
import uuid
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Iterator

from .common import CindyError
from .paths import is_link, outside_git, private_dir, root_path, runtime_home, state_home


def sync_dir(path: Path) -> None:
    if os.name != "nt":
        descriptor = os.open(path, os.O_RDONLY)
        try:
            os.fsync(descriptor)
        finally:
            os.close(descriptor)


def atomic_json(path: Path, value: dict[str, Any]) -> None:
    private_dir(path.parent)
    if is_link(path):
        raise CindyError(f"状态文件不能是链接：{path}", 6)
    temporary = path.with_name(f".{path.name}.{uuid.uuid4().hex}.tmp")
    try:
        with os.fdopen(os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600), "w", encoding="utf-8") as stream:
            json.dump({"format_version": 1, **value}, stream, ensure_ascii=False, indent=2)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
        sync_dir(path.parent)
    finally:
        temporary.unlink(missing_ok=True)


def read_json(path: Path, *, limit: int = 16 * 1024**2) -> dict[str, Any]:
    if is_link(path):
        raise CindyError(f"状态文件不能是链接：{path}", 6)
    if not path.exists():
        return {"format_version": 1}
    if not path.is_file() or path.stat().st_size > limit:
        raise CindyError(f"状态文件异常：{path}", 6)
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(value, dict) or value.get("format_version") != 1:
            raise ValueError("version")
        return value
    except (ValueError, UnicodeError) as exc:
        raise CindyError(f"状态文件损坏，保留现场：{path}", 6) from exc


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        while block := stream.read(1024 * 1024):
            digest.update(block)
    return digest.hexdigest()


class State:
    def __init__(self, home: Path | None = None, runtime: Path | None = None):
        self.home = root_path(home or state_home())
        self.runtime = root_path(runtime or runtime_home())
        self.backups = self.home / "backups"
        self.journals = self.home / "journal"

    def records(self, name: str) -> dict[str, Any]:
        value = read_json(self.home / f"{name}.json").get("records", {})
        if not isinstance(value, dict):
            raise CindyError(f"登记结构无效：{name}", 6)
        for key, record in value.items():
            if not isinstance(key, str):
                raise CindyError(f"登记键无效：{name}", 6)
            if name == "undo":
                valid = isinstance(record, str) and Path(record).is_absolute()
            else:
                valid = isinstance(record, dict) and isinstance(record.get("path"), str)
                if name in {"installs", "profiles"} and valid:
                    valid = record.get("region") in {"cn", "global", "dev"} and record.get("platform") in {"darwin", "win32", "linux"}
            if not valid:
                raise CindyError(f"登记条目无效，保留现场：{name}", 6)
        return value

    def save_records(self, name: str, records: dict[str, Any]) -> None:
        outside_git(self.home)
        atomic_json(self.home / f"{name}.json", {"records": records})

    def register_profile(self, profile: dict[str, Any]) -> None:
        records = self.records("profiles")
        records[profile["profile_key"]] = profile
        self.save_records("profiles", records)

    def active(self) -> dict[str, Any]:
        records = read_json(self.runtime / "active.json").get("records", {})
        if not isinstance(records, dict):
            raise CindyError("活动事务定位记录损坏。", 6)
        return records

    @contextmanager
    def lock(self, *, recover: bool = False) -> Iterator[None]:
        if os.name == "nt":
            raise CindyError("Windows 写操作/互斥锁尚未通过实机门禁，当前仅开放本地只读命令和帮助。", 5)
        import fcntl

        outside_git(self.home)
        private_dir(self.runtime)
        path = self.runtime / "operation.lock"
        descriptor = os.open(path, os.O_RDWR | os.O_CREAT | getattr(os, "O_NOFOLLOW", 0), 0o600)
        try:
            try:
                fcntl.flock(descriptor, fcntl.LOCK_EX | fcntl.LOCK_NB)
            except BlockingIOError as exc:
                raise CindyError("其他 Cindy CLI 操作正在执行。", 3) from exc
            if not recover and (self.active() or any(self.journals.glob("*.json"))):
                raise CindyError("有未完成事务，请先执行 cindy recover。", 6)
            yield
        finally:
            os.close(descriptor)


def index_update(directory: Path, archive: Path, header: dict[str, Any] | None) -> None:
    path = directory / "index.json"
    records = read_json(path).get("records", {})
    if not isinstance(records, dict):
        raise CindyError("备份索引结构无效。", 6)
    if header is None:
        records.pop(archive.name, None)
    else:
        records[archive.name] = {"sha256": sha256(archive), "header": header}
    atomic_json(path, {"records": records})
