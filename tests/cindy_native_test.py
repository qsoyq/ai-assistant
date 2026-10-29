"""macOS feasibility checks on generated, unsigned, disposable application images."""

from __future__ import annotations

import plistlib
import subprocess
import sys
from pathlib import Path

import pytest

from ai_assistant.commands.cindy.common import CindyError
from ai_assistant.commands.cindy.install import install_mac
from ai_assistant.commands.cindy.paths import native_arch
from ai_assistant.commands.cindy.procs import running_state
from ai_assistant.commands.cindy.releases import Artifact
from ai_assistant.commands.cindy.state import State, sha256

pytestmark = pytest.mark.skipif(sys.platform != "darwin", reason="Native macOS image tools; never runs on other platforms")


def test_unsigned_dmg_mount_reject_and_cleanup(tmp_path: Path):
    image_source = tmp_path / "source"
    app = image_source / "Fixture.app"
    (app / "Contents/MacOS").mkdir(parents=True)
    program = app / "Contents/MacOS/Fixture"
    program.write_text("#!/bin/sh\nexit 0\n")
    program.chmod(0o700)
    with (app / "Contents/Info.plist").open("wb") as stream:
        plistlib.dump({"CFBundleExecutable": "Fixture", "CFBundleIdentifier": "invalid.synthetic.fixture", "CFBundlePackageType": "APPL", "CFBundleShortVersionString": "0.0.1"}, stream)
    package = tmp_path / "fixture.dmg"
    created = subprocess.run(["/usr/bin/hdiutil", "create", "-quiet", "-format", "UDZO", "-srcfolder", str(image_source), str(package)], capture_output=True, text=True, timeout=60)
    assert created.returncode == 0, created.stderr
    digest = sha256(package)
    artifact = Artifact("cn", "darwin", native_arch(), "dmg", "dmg", "0.0.1", "0.0.1", None, "https://hotfix.cindy.com.cn/fixture.dmg", digest, package.stat().st_size, "user")
    state = State(tmp_path / "state", tmp_path / "runtime")
    sibling = tmp_path / "not-an-install"
    sibling.write_text("untouched")

    def check():
        assert running_state([], names={"cindy-test-fixture-no-process"})[0] == "stopped"

    with state.lock(), pytest.raises(CindyError) as failed:
        install_mac(artifact, package, tmp_path / "target.app", "fixture", state, check=check)
    assert failed.value.code == 4
    assert "系统校验失败" in str(failed.value)
    assert not (tmp_path / "target.app").exists()
    assert sibling.read_text() == "untouched"
    assert sha256(package) == digest
    assert not state.active()
    assert not list(state.journals.glob("*.json"))
    assert not list(tmp_path.glob(".cindy-txn-*"))
    assert not state.records("installs")
