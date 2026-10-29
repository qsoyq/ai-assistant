"""Exercise actual rename, flock and process death on disposable directories."""

from __future__ import annotations

import json
import os
import shutil
import socket
import subprocess
import sys
from pathlib import Path

import pytest

from ai_assistant.commands.cindy.common import CindyError
from ai_assistant.commands.cindy.paths import identity
from ai_assistant.commands.cindy.procs import running_state
from ai_assistant.commands.cindy.state import State
from ai_assistant.commands.cindy.transaction import Transaction, pending_transactions

pytestmark = pytest.mark.skipif(os.name != "posix", reason="POSIX transactions only; Windows mutation gate is closed")

SCRIPT = """
import os, sys
from pathlib import Path
from ai_assistant.commands.cindy.state import State
from ai_assistant.commands.cindy.transaction import Transaction
state = State(Path(sys.argv[1]), Path(sys.argv[2]))
def observe(phase):
    if phase == sys.argv[4]:
        os._exit(77)
with state.lock():
    tx = Transaction(state, Path(sys.argv[3]), observer=observe)
    (tx.new / 'content').write_text('new')
    tx.activate(lambda: None)
"""


@pytest.mark.parametrize(
    "phase,expected", [("preparing", "old"), ("prepared", "old"), ("renamed-old", "old"), ("old-moved", "old"), ("renamed-new", "new"), ("activated", "new"), ("cleanup-pending", "new")]
)
def test_real_process_death_and_idempotent_recovery(tmp_path: Path, phase: str, expected: str):
    state = State(tmp_path / "state", tmp_path / "runtime")
    target = tmp_path / "profile"
    target.mkdir()
    (target / "content").write_text("old")
    child = subprocess.run([sys.executable, "-c", SCRIPT, str(state.home), str(state.runtime), str(target), phase], capture_output=True, text=True, timeout=15)
    assert child.returncode == 77, child.stderr
    with state.lock(recover=True):
        for tx in pending_transactions(state):
            tx.recover()
    assert (target / "content").read_text() == expected
    assert not pending_transactions(state)
    assert not state.active()


def test_external_target_is_never_overwritten(tmp_path: Path):
    state = State(tmp_path / "state", tmp_path / "runtime")
    target = tmp_path / "profile"
    target.mkdir()
    (target / "content").write_text("old")
    child = subprocess.run([sys.executable, "-c", SCRIPT, str(state.home), str(state.runtime), str(target), "renamed-old"], capture_output=True, timeout=15)
    assert child.returncode == 77
    target.mkdir()
    (target / "foreign").write_text("external")
    tx = pending_transactions(state)[0]
    with pytest.raises(CindyError, match="冲突"):
        tx.recover()
    assert (target / "foreign").read_text() == "external"
    assert (tx.old / "content").read_text() == "old"


def test_flock_is_shared_across_state_homes_and_released_on_exit(tmp_path: Path):
    runtime = tmp_path / "runtime"
    state = State(tmp_path / "one", runtime)
    script = """
import sys
from pathlib import Path
from ai_assistant.commands.cindy.common import CindyError
from ai_assistant.commands.cindy.state import State
try:
    with State(Path(sys.argv[1]), Path(sys.argv[2])).lock():
        pass
except CindyError as e:
    sys.exit(e.code)
"""
    with state.lock():
        result = subprocess.run([sys.executable, "-c", script, str(tmp_path / "two"), str(runtime)], timeout=10)
        assert result.returncode == 3
    result = subprocess.run([sys.executable, "-c", script, str(tmp_path / "two"), str(runtime)], timeout=10)
    assert result.returncode == 0


def test_process_lock_real_pid_and_expired_pid(tmp_path: Path):
    import psutil

    child = subprocess.Popen([sys.executable, "-c", "import time;time.sleep(30)"])
    try:
        name = psutil.Process(child.pid).name().lower()
        (tmp_path / "SingletonLock").symlink_to(f"{socket.gethostname()}-{child.pid}")
        assert running_state([tmp_path], names={name})[0] == "busy"
    finally:
        child.terminate()
        child.wait(timeout=10)
    (tmp_path / "SingletonLock").unlink()
    (tmp_path / "SingletonLock").symlink_to(f"{socket.gethostname()}-{child.pid}")
    assert running_state([tmp_path], names={"no-such-fixture-name"})[0] == "stopped"
    (tmp_path / "SingletonLock").unlink()
    (tmp_path / "SingletonLock").symlink_to("another-host-123")
    assert running_state([tmp_path], names={"no-such-fixture-name"})[0] == "unknown"
    (tmp_path / "SingletonLock").unlink()
    executable = tmp_path / "fixture-agent"
    shutil.copyfile("/bin/sleep", executable)
    executable.chmod(0o700)
    if sys.platform == "darwin":
        signed = subprocess.run(["/usr/bin/codesign", "--force", "--sign", "-", str(executable)], capture_output=True, timeout=30)
        assert signed.returncode == 0, signed.stderr
    engine = subprocess.Popen([str(executable), "30"])
    try:
        _, reasons = running_state([tmp_path])
        assert any(str(engine.pid) in reason for reason in reasons)
    finally:
        engine.terminate()
        engine.wait(timeout=10)


def test_uninstall_transaction_only_removes_its_own_root(tmp_path: Path):
    state = State(tmp_path / "state", tmp_path / "runtime")
    target = tmp_path / "app"
    target.mkdir()
    (target / "program").write_text("synthetic")
    user_data = tmp_path / "user-data"
    user_data.mkdir()
    (user_data / "keep").write_text("keep")
    state.save_records("installs", {"fixture": {"path": str(target), "region": "cn", "platform": sys.platform}})
    tx = Transaction(state, target, operation="uninstall", metadata={"uninstall": "fixture"})
    tx.activate_delete(lambda: None)
    assert not target.exists()
    assert (user_data / "keep").read_text() == "keep"
    assert not state.records("installs")
    assert not state.active()


def test_journal_wrapper_identity_is_not_a_delete_authorization(tmp_path: Path):
    state = State(tmp_path / "state", tmp_path / "runtime")
    target = tmp_path / "profile"
    target.mkdir()
    tx = Transaction(state, target)
    original = tx.wrapper
    alien = tmp_path / "alien"
    alien.mkdir()
    value = json.loads(tx.journal.read_text())
    value["wrapper"] = str(alien)
    tx.journal.write_text(json.dumps(value))
    with pytest.raises(CindyError):
        Transaction.load(state, tx.journal)
    assert alien.exists() and original.exists()
    assert identity(target) == tx.data["old_id"]
