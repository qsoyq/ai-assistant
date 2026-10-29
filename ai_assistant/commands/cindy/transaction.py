"""Recoverable same-volume directory transactions; identity determines commit."""

from __future__ import annotations

import os
import shutil
import uuid
from pathlib import Path
from typing import Any, Callable

from .common import CindyError
from .paths import exists, identity, is_link, private_dir, root_path
from .state import State, atomic_json, read_json, sync_dir

Observer = Callable[[str], None]


def remove_owned(path: Path) -> None:
    if is_link(path) or path.is_file():
        path.unlink()
    elif path.exists():
        # A restored directory can legitimately be read-only. Do not chmod through links.
        for directory, subdirs, _ in os.walk(path, followlinks=False):
            current = Path(directory)
            if os.path.ismount(current) or any(os.path.ismount(current / name) for name in subdirs):
                raise CindyError("事务目录内出现挂载点，拒绝递归删除。", 6)
            current.chmod(current.stat().st_mode | 0o700)
            subdirs[:] = [name for name in subdirs if not is_link(current / name)]
        shutil.rmtree(path)


def rename_new(source: Path, destination: Path) -> None:
    if exists(destination):
        raise CindyError(f"目标已被外部创建，拒绝覆盖：{destination}", 6)
    # Linux renameat2/macOS renamex_np provide an actual no-replace operation.
    import ctypes
    import sys

    libc = ctypes.CDLL(None, use_errno=True)
    if sys.platform == "darwin":
        result = libc.renamex_np(os.fsencode(source), os.fsencode(destination), 4)
    elif sys.platform == "linux":
        result = libc.renameat2(-100, os.fsencode(source), -100, os.fsencode(destination), 1)
    else:
        raise CindyError("此平台尚未通过事务门禁。", 5)
    if result:
        error = ctypes.get_errno()
        raise OSError(error, os.strerror(error), str(destination))
    sync_dir(destination.parent)


class Transaction:
    def __init__(self, state: State, target: Path, *, operation: str = "restore", observer: Observer | None = None, metadata: dict[str, Any] | None = None):
        self.state = state
        self.target = root_path(target)
        self.observer = observer
        self.id = uuid.uuid4().hex
        self.wrapper = self.target.parent / f".cindy-txn-{self.id}"
        self.journal = state.journals / f"{self.id}.json"
        self.data: dict[str, Any] = {
            "id": self.id,
            "operation": operation,
            "target": str(self.target),
            "parent_id": identity(self.target.parent),
            "wrapper": str(self.wrapper),
            "wrapper_id": None,
            "old_id": identity(self.target),
            "new_id": None,
            "phase": "preparing",
            "metadata": metadata or {},
        }
        if not self.target.parent.is_dir():
            raise CindyError("目标父目录必须已存在。", 2)
        self.save("preparing")
        active = state.active()
        active[self.id] = str(self.journal)
        atomic_json(state.runtime / "active.json", {"records": active})
        self.wrapper.mkdir(mode=0o700)
        private_dir(self.wrapper)
        self.data["wrapper_id"] = identity(self.wrapper)
        private_dir(self.new)
        self.save("preparing")

    @property
    def new(self) -> Path:
        return self.wrapper / ("new.app" if self.data["operation"] == "install" and self.target.suffix == ".app" else "new")

    @property
    def old(self) -> Path:
        return self.wrapper / "old"

    def save(self, phase: str) -> None:
        self.data["phase"] = phase
        atomic_json(self.journal, self.data)
        if self.observer:
            self.observer(phase)

    def activate(self, check: Callable[[], None]) -> None:
        check()
        if identity(self.target) != self.data["old_id"]:
            raise CindyError("当前目录身份已变化。", 6)
        self.data["new_id"] = identity(self.new)
        self.save("prepared")
        if exists(self.target):
            self.save("moving-old")
            rename_new(self.target, self.old)
            if self.observer:
                self.observer("renamed-old")
        self.save("old-moved")
        check()
        self.save("activating")
        rename_new(self.new, self.target)
        if self.observer:
            self.observer("renamed-new")
        self.save("activated")
        check()
        self.finish()

    def activate_delete(self, check: Callable[[], None]) -> None:
        check()
        if identity(self.target) != self.data["old_id"] or self.data["old_id"] is None:
            raise CindyError("卸载目录身份发生变化。", 6)
        self.save("deleting")
        rename_new(self.target, self.old)
        self.save("activated")
        check()
        self.finish()

    def publish_metadata(self) -> None:
        metadata = self.data["metadata"]
        if "profile" in metadata:
            self.state.register_profile(metadata["profile"])
        if "install" in metadata:
            record = metadata["install"]
            record["directory_id"] = identity(self.target)
            records = self.state.records("installs")
            records[record["id"]] = record
            self.state.save_records("installs", records)
        if "uninstall" in metadata:
            records = self.state.records("installs")
            records.pop(metadata["uninstall"], None)
            self.state.save_records("installs", records)
        if "pre_backup" in metadata:
            records = self.state.records("undo")
            records[metadata["profile"]["profile_key"]] = metadata["pre_backup"]
            self.state.save_records("undo", records)

    def finish(self) -> None:
        self.save("cleanup-pending")
        self.publish_metadata()
        if exists(self.old):
            if identity(self.old) != self.data["old_id"]:
                raise CindyError("旧目录身份不符，保留现场。", 6)
            if self.data["operation"] == "install" and self.target.suffix == ".app":
                from .signing import trash_app

                trash_app(self.old)
            else:
                remove_owned(self.old)
        self.close()

    def close(self) -> None:
        mountpoint = self.data.get("mountpoint")
        if mountpoint:
            mount = Path(mountpoint)
            if mount != self.wrapper / "mount":
                raise CindyError("挂载点记录不属于本事务。", 6)
            if os.path.ismount(mount):
                import subprocess

                result = subprocess.run(["/usr/bin/hdiutil", "detach", str(mount)], capture_output=True, timeout=120, check=False)
                if result.returncode:
                    raise CindyError(f"无法卸载本次只读镜像，保留事务：{mount}", 6)
        if self.wrapper.exists():
            if self.data["wrapper_id"] is None or identity(self.wrapper) != self.data["wrapper_id"]:
                raise CindyError("事务包装目录身份不符。", 6)
            remove_owned(self.wrapper)
        self.save("done")
        active = self.state.active()
        active.pop(self.id, None)
        atomic_json(self.state.runtime / "active.json", {"records": active})
        self.journal.unlink()
        sync_dir(self.journal.parent)

    @classmethod
    def load(cls, state: State, journal: Path) -> Transaction:
        data = read_json(journal)
        required = {"id", "target", "wrapper", "parent_id", "wrapper_id", "old_id", "new_id", "phase", "operation", "metadata"}
        if not required <= data.keys():
            raise CindyError(f"事务记录缺失字段：{journal}", 6)
        result = cls.__new__(cls)
        result.state, result.data, result.journal, result.observer = state, data, journal, None
        result.id = data["id"]
        result.target = root_path(Path(data["target"]))
        result.wrapper = Path(data["wrapper"])
        if not isinstance(result.id, str) or len(result.id) != 32 or any(c not in "0123456789abcdef" for c in result.id):
            raise CindyError("事务 ID 无效。", 6)
        if result.wrapper != result.target.parent / f".cindy-txn-{result.id}" or identity(result.target.parent) != data["parent_id"]:
            raise CindyError("事务路径或父目录身份冲突。", 6)
        if exists(result.wrapper) and identity(result.wrapper) != data["wrapper_id"]:
            raise CindyError("事务目录身份冲突。", 6)
        return result

    def recover(self) -> str:
        if self.data["phase"] == "done" and not exists(self.wrapper):
            active = self.state.active()
            active.pop(self.id, None)
            atomic_json(self.state.runtime / "active.json", {"records": active})
            self.journal.unlink(missing_ok=True)
            return "已收尾"
        current = identity(self.target)
        if self.data["operation"] == "uninstall" and current is None and (identity(self.old) == self.data["old_id"] or self.data["phase"] in {"activated", "cleanup-pending"}):
            self.finish()
            return "卸载已提交，已收尾"
        if self.data["new_id"] is not None and current == self.data["new_id"]:
            self.finish()
            return "已提交，已收尾"
        if self.data["phase"] in {"activated", "cleanup-pending"}:
            raise CindyError("已提交目标发生变化，不自动回滚或清理。", 6)
        if exists(self.old):
            if current is not None or identity(self.old) != self.data["old_id"]:
                raise CindyError("恢复目标冲突，不覆盖外来目录。", 6)
            rename_new(self.old, self.target)
        elif current != self.data["old_id"]:
            raise CindyError("原目录缺失或身份变化，保留现场。", 6)
        self.close()
        return "未提交，已回滚"


def pending_transactions(state: State) -> list[Transaction]:
    entries = state.active()
    journals = {str(path): path for path in state.journals.glob("*.json")}
    for path in entries.values():
        if not isinstance(path, str) or not Path(path).is_file():
            raise CindyError("活动事务定位记录与 journal 不一致。", 6)
        journals[path] = Path(path)
    return [Transaction.load(State(path.parent.parent, state.runtime), path) for path in journals.values()]
