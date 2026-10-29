"""Real temporary files and SQLite snapshots; no user profile fixtures."""

from __future__ import annotations

import io
import json
import os
import shutil
import sqlite3
import stat
import tarfile
from pathlib import Path

import pytest

from ai_assistant.commands.cindy.archive import (
    create_backup,
    read_header,
    safe_member,
    verify_backup,
)
from ai_assistant.commands.cindy.common import CindyError
from ai_assistant.commands.cindy.data import (
    candidates,
    copy_shared,
    replace_profile,
    resolve_target,
)
from ai_assistant.commands.cindy.paths import disjoint, native_arch, profile_for, root_path
from ai_assistant.commands.cindy.schema import schema_versions
from ai_assistant.commands.cindy.state import State, sha256

pytestmark = pytest.mark.skipif(os.name != "posix", reason="POSIX private-storage gate; Windows mutations remain disabled")


def fixture_profile(tmp_path: Path):
    base = tmp_path / "appdata"
    root = base / "Cindy-dev2-test"
    root.mkdir(parents=True)
    (root / "empty").mkdir()
    (root / "secret").write_bytes(b"synthetic-not-a-real-secret")
    (root / "secret").chmod(0o600)
    (root / "executable").write_bytes(b"#!/bin/sh\nexit 0\n")
    (root / "executable").chmod(0o700)
    (root / "Cache").mkdir()
    (root / "Cache" / "cache").write_bytes(b"cache")
    (root / "updates").mkdir()
    (root / "updates" / "update.zip").write_bytes(b"update")
    (root / "SingletonLock").symlink_to("invalid-host-9999999")
    (root / "absolute").symlink_to(tmp_path / "absent")
    (root / "relative").symlink_to("secret")
    (root / "dangling").symlink_to("missing")
    with sqlite3.connect(root / "cindy-fixture.db") as connection:
        connection.execute("CREATE TABLE migration_meta (key TEXT PRIMARY KEY, value TEXT)")
        connection.execute("INSERT INTO migration_meta VALUES ('schema_version', '134')")
    return profile_for(root, base=base)


@pytest.mark.parametrize("compression", ["none", "gzip", "zstd"])
def test_archive_roundtrip_independent_of_index(tmp_path: Path, compression: str):
    if compression == "zstd":
        pytest.importorskip("zstandard")
    profile = fixture_profile(tmp_path)
    source = Path(profile.path)
    path, header = create_backup(profile, tmp_path / "backups", compression=compression, exclude_caches=True)
    assert header["schema"] == {"cindy-fixture.db": 134}
    assert stat.S_IMODE(path.stat().st_mode) == 0o600
    moved = tmp_path / f"external{path.suffix}"
    shutil.copyfile(path, moved)
    destination = tmp_path / "output"
    verified = verify_backup(moved, destination=destination)
    assert verified["archive_sha256"] == sha256(path)
    assert (destination / "secret").read_bytes() == (source / "secret").read_bytes()
    assert stat.S_IMODE((destination / "secret").stat().st_mode) == 0o600
    assert stat.S_IMODE((destination / "executable").stat().st_mode) == 0o700
    assert (destination / "empty").is_dir()
    assert os.readlink(destination / "absolute") == str(tmp_path / "absent")
    assert os.readlink(destination / "dangling") == "missing"
    assert not (destination / "Cache").exists()
    assert not os.path.lexists(destination / "SingletonLock")
    assert not list((destination / "updates").iterdir())
    assert schema_versions(destination) == {"cindy-fixture.db": 134}


def test_equal_length_corruption_without_index_is_rejected(tmp_path: Path):
    profile = fixture_profile(tmp_path)
    path, _ = create_backup(profile, tmp_path / "backups", compression="none")
    external = tmp_path / "external.tar"
    external.write_bytes(path.read_bytes().replace(b"synthetic-not-a-real-secret", b"corrupted-not-a-real-secret", 1))
    with pytest.raises(CindyError, match="摘要不一致"):
        verify_backup(external)


def test_torn_tail_and_wrong_index_rejected(tmp_path: Path):
    profile = fixture_profile(tmp_path)
    path, _ = create_backup(profile, tmp_path / "backups", compression="none")
    index = path.parent / "index.json"
    value = json.loads(index.read_text())
    value["records"][path.name]["sha256"] = "0" * 64
    index.write_text(json.dumps(value))
    with pytest.raises(CindyError, match="索引"):
        verify_backup(path)
    index.unlink()
    path.write_bytes(path.read_bytes()[:2048])
    with pytest.raises(CindyError):
        verify_backup(path)


@pytest.mark.parametrize("name", ["../escape", "/absolute", "data//duplicate", "C:/drive", "x:stream", "a/../b", "CON.txt", "trailing.", "a\\b"])
def test_unsafe_paths(name: str):
    with pytest.raises(CindyError):
        safe_member(name)


def test_source_output_overlap_git_and_symlink_root(tmp_path: Path):
    profile = fixture_profile(tmp_path)
    with pytest.raises(CindyError):
        create_backup(profile, Path(profile.path) / "backups")
    repository = tmp_path / "repository"
    repository.mkdir()
    (repository / ".git").write_text("gitdir: unrelated")
    with pytest.raises(CindyError, match="Git"):
        root_path(repository / "backup")
    link = tmp_path / "link"
    link.symlink_to(profile.path)
    with pytest.raises(CindyError):
        root_path(link)
    with pytest.raises(CindyError):
        disjoint(tmp_path / "one", tmp_path / "one/two")


def test_region_identity_and_isolated_target_not_main(tmp_path: Path):
    profile = fixture_profile(tmp_path)
    assert profile.region == "cn" and profile.kind == "isolated"
    with pytest.raises(CindyError):
        profile_for(Path(profile.path), "global", base=Path(profile.app_data))
    with pytest.raises(CindyError):
        profile_for(tmp_path / "CindyUnrecognized")
    archive, header = create_backup(profile, tmp_path / "backups", compression="none")
    state = State(tmp_path / "state", tmp_path / "runtime")
    # appData is deliberately not this fixture's synthetic base: do not silently relocate.
    with pytest.raises(CindyError, match="之间迁移"):
        resolve_target(header, state, tmp_path / "Cindy", True)
    assert archive.exists()
    header["profile"]["arch"] = "x64" if native_arch() == "arm64" else "arm64"
    with pytest.raises(CindyError, match="架构"):
        resolve_target(header, state, None, False)


def test_shared_copy_never_moves_current_tree(tmp_path: Path):
    source, new = tmp_path / "current", tmp_path / "new"
    source.mkdir()
    new.mkdir()
    (source / "shared-system-skills").mkdir()
    (source / "shared-system-skills/file").write_text("current")
    (new / "shared-system-skills").mkdir()
    (new / "shared-system-skills/file").write_text("archived")
    copy_shared(source, new)
    assert (source / "shared-system-skills/file").read_text() == "current"
    assert (new / "shared-system-skills/file").read_text() == "current"


def test_custom_restore_and_reset_with_real_auto_backups(tmp_path: Path):
    root = tmp_path / "custom"
    root.mkdir()
    (root / "message").write_text("before")
    profile = profile_for(root, "global")
    state = State(tmp_path / "state", tmp_path / "runtime")
    path, _ = create_backup(profile, state.backups, compression="none")
    state.register_profile(profile.to_dict())
    (root / "message").write_text("after")
    # The injected check still inspects real processes; its accepted executable set is fixture-specific.
    from ai_assistant.commands.cindy.procs import running_state

    def check():
        assert running_state([], names={"cindy-test-no-such-executable"})[0] == "stopped"

    with state.lock():
        replace_profile(profile, state, archive=path, check=check)
    assert (root / "message").read_text() == "before"
    backups = candidates(state.backups)
    assert len(backups) == 2
    undo = Path(state.records("undo")[profile.profile_key])
    verify_backup(undo, destination=tmp_path / "undo")
    assert (tmp_path / "undo/message").read_text() == "after"
    with state.lock():
        replace_profile(profile, state, check=check)
    assert root.is_dir() and not list(root.iterdir())
    assert not state.active()


def test_archive_limit_and_candidate_sorting(tmp_path: Path):
    profile = fixture_profile(tmp_path)
    with pytest.raises(CindyError):
        create_backup(profile, tmp_path / "backups", max_entries=1)
    path, _ = create_backup(profile, tmp_path / "backups", compression="none")
    with pytest.raises(CindyError):
        verify_backup(path, max_bytes=1)
    assert len(candidates(path.parent, "cn")) == 1
    assert candidates(path.parent, "global") == []


def test_malicious_link_ancestor_rejected_before_writing_outside(tmp_path: Path):
    profile = fixture_profile(tmp_path)
    valid, _ = create_backup(profile, tmp_path / "backups", compression="none")
    raw_header = read_header(valid)
    malicious = tmp_path / "malicious.tar"
    with tarfile.open(malicious, "w") as archive:
        data = json.dumps(raw_header).encode()
        header = tarfile.TarInfo("cindy-backup.json")
        header.size = len(data)
        archive.addfile(header, io.BytesIO(data))
        link = tarfile.TarInfo("data/link")
        link.type = tarfile.SYMTYPE
        link.linkname = str(tmp_path / "outside")
        archive.addfile(link)
        content = tarfile.TarInfo("data/link/escaped")
        content.size = 1
        archive.addfile(content, io.BytesIO(b"x"))
    with pytest.raises(CindyError):
        verify_backup(malicious, destination=tmp_path / "extract")
    assert not (tmp_path / "outside").exists()


def test_owned_partial_can_be_cleared_but_unknown_partial_is_untouched(tmp_path: Path):
    from ai_assistant.commands.cindy.data import delete_backups

    profile = fixture_profile(tmp_path)
    directory = tmp_path / "backups"

    def interrupted_after_verification():
        raise CindyError("fixture interruption", 6)

    with pytest.raises(CindyError):
        create_backup(profile, directory, compression="none", check=interrupted_after_verification)
    unknown = directory / "cindy-unknown.tar.partial"
    unknown.write_bytes(b"unknown")
    assert not candidates(directory)
    owned = candidates(directory, include_partial=True)
    assert len(owned) == 1 and owned[0]["partial"]
    assert candidates(directory, "global", include_partial=True) == []
    delete_backups(owned, directory)
    assert unknown.read_bytes() == b"unknown"
    assert not candidates(directory, include_partial=True)


def test_tar_extension_metadata_and_hidden_payload_are_bounded(tmp_path: Path):
    profile = fixture_profile(tmp_path)
    path, _ = create_backup(profile, tmp_path / "backups", compression="none")
    hidden = tmp_path / "hidden.tar"
    hidden.write_bytes(path.read_bytes() + b"hidden-payload")
    with pytest.raises(CindyError):
        verify_backup(hidden)
    giant = tmp_path / "giant.tar"
    header = tarfile.TarInfo("pax")
    header.type = tarfile.XHDTYPE
    header.size = 1024**3
    giant.write_bytes(header.tobuf())
    with pytest.raises(CindyError, match="元数据"):
        read_header(giant)


def test_keychain_marker_requires_known_complete_identity(tmp_path: Path):
    root = tmp_path / "fixture"
    root.mkdir()
    marker = root / "keychain-identity"
    for invalid in ("Cindy", "CindyDev", "unknown\n", "CindyDev\nextra"):
        marker.write_text(invalid)
        with pytest.raises(CindyError):
            profile_for(root, "cn")
    marker.write_text("CindyDev\n")
    assert profile_for(root, "cn").keychain_identity == "CindyDev"


def test_prune_verifies_retained_backup_before_deleting_older_files(tmp_path: Path):
    from typer.testing import CliRunner

    from ai_assistant.commands.cindy import cmd

    profile = fixture_profile(tmp_path)
    directory = tmp_path / "state/backups"
    older, _ = create_backup(profile, directory, compression="none")
    newest, _ = create_backup(profile, directory, compression="none")
    newest.write_bytes(newest.read_bytes().replace(b"synthetic-not-a-real-secret", b"corrupted-not-a-real-secret", 1))
    result = CliRunner().invoke(cmd, ["data", "prune", "--keep", "1", "--yes"], env={"HOME": str(tmp_path), "AI_ASSISTANT_CINDY_HOME": str(tmp_path / "state")})
    assert result.exit_code == 4, result.output
    assert older.exists() and newest.exists()
