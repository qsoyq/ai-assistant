"""Real processes, locks, descendants and open files for scoped cold backups."""

from __future__ import annotations

import os
import shutil
import socket
import subprocess
import sys
from contextlib import ExitStack, contextmanager
from functools import partial
from pathlib import Path
from typing import Iterator

import pytest

from ai_assistant.commands.cindy.archive import verify_backup
from ai_assistant.commands.cindy.common import CindyError
from ai_assistant.commands.cindy.data import backup_profile, replace_profile
from ai_assistant.commands.cindy.paths import profile_for
from ai_assistant.commands.cindy.procs import backup_running_state as production_running_state
from ai_assistant.commands.cindy.procs import explicit_profile, require_backup_stopped
from ai_assistant.commands.cindy.state import State


def backup_running_state(target: Path, paths: list[Path], *, observed: dict[int, float] | None = None) -> tuple[str, list[str]]:
    # Library-only fixture names; the production CLI has no override.
    return production_running_state(target, paths, names={"cindydev"}, observed=observed)


pytestmark = pytest.mark.skipif(os.name != "posix", reason="POSIX process evidence; Windows write gate remains closed")

PROGRAM = r"""
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <unistd.h>
int main(int argc, char **argv) {
    int child = 0;
    for (int i = 1; i < argc; i++) {
        if (!strcmp(argv[i], "--hold-file") && i + 1 < argc) {
            FILE *file = fopen(argv[++i], "a");
            if (!file) return 2;
            fputs("live-writer\n", file);
            fflush(file);
        }
        if (!strcmp(argv[i], "--spawn-child")) {
            child = fork();
            if (child == 0) { execl("/bin/sleep", "sleep", "60", NULL); return 3; }
            if (child < 0) return 4;
        }
    }
    printf("%d\n", child);
    fflush(stdout);
    for (;;) pause();
}
"""


@pytest.fixture(scope="module")
def process_program(tmp_path_factory: pytest.TempPathFactory) -> Path:
    compiler = shutil.which("cc")
    if compiler is None:
        pytest.skip("Native C compiler needed for real argv and process-tree evidence")
    root = tmp_path_factory.mktemp("cindy-process-executable")
    source = root / "fixture.c"
    source.write_text(PROGRAM)
    executable = root / "CindyDev"
    result = subprocess.run([compiler, str(source), "-o", str(executable)], capture_output=True, text=True, timeout=60)
    assert result.returncode == 0, result.stderr
    return executable


@contextmanager
def live_process(executable: Path, *args: str, environment: dict[str, str] | None = None) -> Iterator[tuple[subprocess.Popen[str], int]]:
    env = {key: value for key, value in os.environ.items() if key != "XDT_USER_DATA_DIR"}
    env.update(environment or {})
    proc = subprocess.Popen([str(executable), *args], stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, env=env)
    child = 0
    try:
        assert proc.stdout is not None
        line = proc.stdout.readline()
        assert line, proc.communicate(timeout=3)
        child = int(line)
        yield proc, child
    finally:
        if proc.poll() is None:
            proc.terminate()
        proc.wait(timeout=5)
        if child:
            try:
                os.kill(child, 15)
            except ProcessLookupError:
                pass
        if proc.stdout:
            proc.stdout.close()
        if proc.stderr:
            proc.stderr.close()


def lock_profile(root: Path, pid: int) -> None:
    root.mkdir(parents=True, exist_ok=True)
    (root / "SingletonLock").symlink_to(f"{socket.gethostname()}-{pid}")


@pytest.mark.parametrize("form", ["equals", "separate", "environment"])
def test_other_explicit_profile_can_run(tmp_path: Path, process_program: Path, form: str):
    target, other = tmp_path / "global", tmp_path / "cn"
    target.mkdir()
    args = [f"--user-data-dir={other}"] if form == "equals" else (["--user-data-dir", str(other)] if form == "separate" else [])
    environment = {"XDT_USER_DATA_DIR": str(other)} if form == "environment" else {}
    with live_process(process_program, *args, environment=environment):
        assert backup_running_state(target, [other])[0] == "stopped"


@pytest.mark.parametrize("form", ["argument", "environment", "ancestor", "descendant"])
def test_target_profile_is_busy(tmp_path: Path, process_program: Path, form: str):
    target = tmp_path / "global"
    target.mkdir()
    chosen = target.parent if form == "ancestor" else (target / "child" if form == "descendant" else target)
    args = [] if form == "environment" else [f"--user-data-dir={chosen}"]
    environment = {"XDT_USER_DATA_DIR": str(target)} if form == "environment" else {}
    with live_process(process_program, *args, environment=environment):
        assert backup_running_state(target, [])[0] == "busy"


def test_profile_argument_symlink_cannot_hide_target(tmp_path: Path, process_program: Path):
    target = tmp_path / "global"
    target.mkdir()
    alias = tmp_path / "alias"
    alias.symlink_to(target, target_is_directory=True)
    with live_process(process_program, f"--user-data-dir={alias}"):
        assert backup_running_state(target, [])[0] == "busy"


def test_lock_argument_conflict_is_unknown(tmp_path: Path, process_program: Path):
    target, other = tmp_path / "global", tmp_path / "cn"
    with live_process(process_program, f"--user-data-dir={tmp_path / 'conflicting'}") as (proc, _):
        lock_profile(other, proc.pid)
        assert backup_running_state(target, [other])[0] == "unknown"


def test_observed_identity_does_not_survive_pid_reuse(tmp_path: Path):
    observed = {os.getpid(): 0.0}
    assert backup_running_state(tmp_path / "global", [], observed=observed)[0] == "stopped"


def test_environment_override_to_target_blocks_other_argument(tmp_path: Path, process_program: Path):
    target, other = tmp_path / "global", tmp_path / "cn"
    with live_process(process_program, f"--user-data-dir={other}", environment={"XDT_USER_DATA_DIR": str(target)}):
        assert backup_running_state(target, [other])[0] == "busy"


@pytest.mark.parametrize("args", [[], ["--user-data-dir"], ["--user-data-dir=relative"], ["--user-data-dir=/one", "--user-data-dir=/two"]])
def test_unknown_and_ambiguous_processes_refused(tmp_path: Path, process_program: Path, args: list[str]):
    with live_process(process_program, *args):
        assert backup_running_state(tmp_path / "global", [])[0] == "unknown"


def test_live_lock_and_descendants_supply_actual_profile(tmp_path: Path, process_program: Path):
    target, other = tmp_path / "global", tmp_path / "cn"
    with live_process(process_program, "--spawn-child") as (proc, child):
        assert child
        lock_profile(other, proc.pid)
        assert backup_running_state(target, [other])[0] == "stopped"
        assert backup_running_state(other, [other])[0] == "busy"
        # A second root claiming the same owner is not proof of isolation.
        lock_profile(tmp_path / "second", proc.pid)
        assert backup_running_state(target, [other, tmp_path / "second"])[0] == "unknown"


def test_unbound_child_not_exempted_by_parent_argument(tmp_path: Path, process_program: Path):
    with live_process(process_program, f"--user-data-dir={tmp_path / 'cn'}", "--spawn-child"):
        assert backup_running_state(tmp_path / "global", [])[0] == "unknown"


def test_reparented_child_remains_tracked(tmp_path: Path, process_program: Path):
    observed: dict[int, float] = {}
    target, other = tmp_path / "global", tmp_path / "cn"
    with live_process(process_program, "--spawn-child") as (proc, child):
        lock_profile(other, proc.pid)
        assert backup_running_state(target, [other], observed=observed)[0] == "stopped"
        assert child in observed
        proc.terminate()
        proc.wait(timeout=5)
        assert backup_running_state(target, [other], observed=observed)[0] == "unknown"


@pytest.mark.parametrize("kind", ["foreign", "malformed", "regular", "live-non-cindy", "stale"])
def test_target_lock_evidence(tmp_path: Path, kind: str):
    target = tmp_path / "global"
    target.mkdir()
    lock = target / "SingletonLock"
    if kind == "regular":
        lock.write_text("unexpected")
    elif kind == "live-non-cindy":
        lock.symlink_to(f"{socket.gethostname()}-{os.getpid()}")
    else:
        lock.symlink_to({"foreign": "another-host-123", "malformed": "broken", "stale": f"{socket.gethostname()}-2147483647"}[kind])
    expected = "busy" if kind == "live-non-cindy" else ("stopped" if kind == "stale" else "unknown")
    assert backup_running_state(target, [])[0] == expected


def test_non_cindy_external_open_file_blocks(tmp_path: Path, process_program: Path):
    root = tmp_path / "global"
    root.mkdir()
    program = tmp_path / "external-writer"
    shutil.copyfile(process_program, program)
    program.chmod(0o700)
    if sys.platform == "darwin":
        result = subprocess.run(["/usr/bin/codesign", "--force", "--sign", "-", str(program)], capture_output=True, timeout=30)
        assert result.returncode == 0, result.stderr
    with live_process(program, "--hold-file", str(root / "data")):
        assert backup_running_state(root, [])[0] == "busy"


@pytest.mark.parametrize("shared", [False, True])
def test_cn_main_and_actual_shared_contents_remain_global(tmp_path: Path, process_program: Path, shared: bool):
    base = tmp_path / "app-data"
    target = base / ("CindyGlobal" if shared else "Cindy")
    target.mkdir(parents=True)
    if shared:
        (target / "shared-content").mkdir()
    profile = profile_for(target, "global" if shared else "cn", base=base)
    with live_process(process_program, f"--user-data-dir={tmp_path / 'other'}"):
        with pytest.raises(CindyError) as failed:
            require_backup_stopped(profile)
        assert failed.value.code == 3
        assert "所有 Cindy" in str(failed.value)


def test_backup_allows_other_locked_profile_and_preserves_shared_link(tmp_path: Path, process_program: Path):
    target, other, shared = tmp_path / "fixture", tmp_path / "other", tmp_path / "shared"
    target.mkdir()
    shared.mkdir()
    (target / "data").write_text("synthetic")
    (shared / "not-in-backup").write_text("outside")
    (target / "shared-system-skills").symlink_to(shared, target_is_directory=True)
    state = State(tmp_path / "state", tmp_path / "runtime")
    state.register_profile(profile_for(other, "cn").to_dict())
    with live_process(process_program) as (proc, _):
        lock_profile(other, proc.pid)
        profile = profile_for(target, "global", base=tmp_path / "app-data")
        with state.lock():
            archive, _ = backup_profile(profile, state, compression="none", check=partial(require_backup_stopped, profile, [other], names={"cindydev"}))
        verify_backup(archive, destination=tmp_path / "extract")
        assert (tmp_path / "extract/shared-system-skills").is_symlink()
        assert os.readlink(tmp_path / "extract/shared-system-skills") == str(shared)
        # Global reset/restoration and their automatic backups remain globally gated.
        for source in (None, archive):
            with state.lock(), pytest.raises(CindyError) as failed:
                replace_profile(profile_for(target, "global"), state, archive=source)
            assert failed.value.code == 3
    assert (target / "data").read_text() == "synthetic"


def test_stale_lock_cannot_exempt_reused_live_pid(tmp_path: Path, process_program: Path):
    target, other = tmp_path / "global", tmp_path / "cn"
    with live_process(process_program) as (proc, _):
        lock_profile(other, proc.pid)
        os.utime(other / "SingletonLock", (1, 1), follow_symlinks=False)
        assert backup_running_state(target, [other])[0] == "unknown"


def test_unrelated_lock_with_non_cindy_pid_is_not_ownership_proof(tmp_path: Path):
    other = tmp_path / "other"
    lock_profile(other, os.getpid())
    assert backup_running_state(tmp_path / "global", [other])[0] == "unknown"


def test_recheck_prevents_publication_after_process_starts(tmp_path: Path, process_program: Path):
    target = tmp_path / "fixture"
    target.mkdir()
    (target / "data").write_text("synthetic")
    profile = profile_for(target, "global", base=tmp_path / "app-data")
    state = State(tmp_path / "state", tmp_path / "runtime")
    with ExitStack() as stack:
        calls = 0

        def check():
            nonlocal calls
            calls += 1
            require_backup_stopped(profile, names={"cindydev"})
            if calls == 1:
                # Start a real target instance only after the first check has passed.
                stack.enter_context(live_process(process_program, f"--user-data-dir={target}"))

        with pytest.raises(CindyError) as failed:
            backup_profile(profile, state, compression="none", check=check)
        assert failed.value.code == 3
    assert not list(state.backups.glob("*.tar"))
    assert list(state.backups.glob("*.partial"))
    assert not state.records("profiles")


def test_real_cli_uses_scoped_check_and_refuses_target_before_archive(tmp_path: Path, process_program: Path):
    target = tmp_path / "fixture"
    target.mkdir()
    (target / "data").write_text("synthetic")
    with live_process(process_program, f"--user-data-dir={target}"):
        result = subprocess.run(
            [sys.executable, "-c", "from ai_assistant.commands.cindy import cmd; cmd()", "data", "backup", "--region", "global", "--path", str(target), "--compress", "none"],
            env={**os.environ, "HOME": str(tmp_path), "AI_ASSISTANT_CINDY_HOME": str(tmp_path / "state")},
            capture_output=True,
            text=True,
            timeout=30,
        )
        assert result.returncode == 3, result.stderr
        assert "目标 Profile" in result.stderr
        assert result.stdout == ""
    assert not (tmp_path / "state/backups").exists()


def test_busy_backup_does_not_publish(tmp_path: Path, process_program: Path):
    target = tmp_path / "fixture"
    target.mkdir()
    (target / "data").write_text("synthetic")
    state = State(tmp_path / "state", tmp_path / "runtime")
    with live_process(process_program, f"--user-data-dir={target}"):
        with pytest.raises(CindyError) as failed:
            backup_profile(profile_for(target, "global"), state, compression="none")
        assert failed.value.code == 3
    assert not state.backups.exists()


@pytest.mark.parametrize("argv", [["--user-data-dir"], ["--user-data-dir="], ["--user-data-dir=relative"], ["--user-data-dir=/one", "--user-data-dir=/two"]])
def test_explicit_profile_requires_one_absolute_path(argv: list[str]):
    with pytest.raises(ValueError):
        explicit_profile(argv)
