"""Tests for httpx-disable-verify, requests-disable-verify, disable-ssl-verify.

Each install/uninstall/status flow is exercised against a fresh tmp directory
so the host site-packages are never touched.
"""

from pathlib import Path

import pytest
from typer.testing import CliRunner

from ai_assistant.commands import disable_ssl_verify, httpx_disable_verify, requests_disable_verify

runner = CliRunner()

PARAMS = [
    pytest.param(
        httpx_disable_verify.cmd,
        httpx_disable_verify.PTH_FILENAME,
        id="httpx",
    ),
    pytest.param(
        requests_disable_verify.cmd,
        requests_disable_verify.PTH_FILENAME,
        id="requests",
    ),
]


@pytest.mark.parametrize("cmd, pth_filename", PARAMS)
def test_status_reports_uninstalled_on_empty_dir(tmp_path: Path, cmd, pth_filename: str):
    result = runner.invoke(cmd, ["status", "--target", str(tmp_path)])
    assert result.exit_code == 0
    assert "状态: 未安装" in result.output


@pytest.mark.parametrize("cmd, pth_filename", PARAMS)
def test_install_writes_pth_and_status_reports_installed(tmp_path: Path, cmd, pth_filename: str):
    install_result = runner.invoke(cmd, ["install", "--target", str(tmp_path), "--yes"])
    assert install_result.exit_code == 0, install_result.output
    pth = tmp_path / pth_filename
    assert pth.exists()
    content = pth.read_text(encoding="utf-8")
    assert content.startswith("import os; exec(")

    status_result = runner.invoke(cmd, ["status", "--target", str(tmp_path)])
    assert status_result.exit_code == 0
    assert "状态: 已安装" in status_result.output


@pytest.mark.parametrize("cmd, pth_filename", PARAMS)
def test_install_overwrites_existing_pth_without_error(tmp_path: Path, cmd, pth_filename: str):
    pth = tmp_path / pth_filename
    pth.write_text("stale content", encoding="utf-8")

    result = runner.invoke(cmd, ["install", "--target", str(tmp_path), "--yes"])
    assert result.exit_code == 0
    assert "已覆盖" in result.output
    # Stale content should be replaced by the real patch payload.
    assert "stale content" not in pth.read_text(encoding="utf-8")


@pytest.mark.parametrize("cmd, pth_filename", PARAMS)
def test_install_aborts_when_user_declines_confirmation(tmp_path: Path, cmd, pth_filename: str):
    # No --yes: typer.confirm reads from stdin; "n" declines.
    result = runner.invoke(cmd, ["install", "--target", str(tmp_path)], input="n\n")
    assert result.exit_code == 0
    assert "已取消" in result.output
    assert not (tmp_path / pth_filename).exists()


@pytest.mark.parametrize("cmd, pth_filename", PARAMS)
def test_uninstall_removes_pth(tmp_path: Path, cmd, pth_filename: str):
    pth = tmp_path / pth_filename
    pth.write_text("placeholder", encoding="utf-8")

    result = runner.invoke(cmd, ["uninstall", "--target", str(tmp_path)])
    assert result.exit_code == 0
    assert "已卸载" in result.output
    assert not pth.exists()


@pytest.mark.parametrize("cmd, pth_filename", PARAMS)
def test_uninstall_missing_pth_errors_without_quiet(tmp_path: Path, cmd, pth_filename: str):
    result = runner.invoke(cmd, ["uninstall", "--target", str(tmp_path)])
    assert result.exit_code == 1
    assert "pth 不存在" in result.output


@pytest.mark.parametrize("cmd, pth_filename", PARAMS)
def test_uninstall_quiet_swallows_missing_pth(tmp_path: Path, cmd, pth_filename: str):
    result = runner.invoke(cmd, ["uninstall", "--target", str(tmp_path), "--quiet"])
    assert result.exit_code == 0


# ---------------------------------------------------------------------------
# Aggregate disable-ssl-verify command
# ---------------------------------------------------------------------------


def test_aggregate_install_writes_both_pth_files(tmp_path: Path):
    result = runner.invoke(
        disable_ssl_verify.cmd,
        ["install", "--target", str(tmp_path), "--yes"],
    )
    assert result.exit_code == 0
    assert (tmp_path / httpx_disable_verify.PTH_FILENAME).exists()
    assert (tmp_path / requests_disable_verify.PTH_FILENAME).exists()


def test_aggregate_status_reports_both(tmp_path: Path):
    runner.invoke(
        disable_ssl_verify.cmd,
        ["install", "--target", str(tmp_path), "--yes"],
    )
    result = runner.invoke(disable_ssl_verify.cmd, ["status", "--target", str(tmp_path)])
    assert result.exit_code == 0
    assert "httpx-disable-verify status" in result.output
    assert "requests-disable-verify status" in result.output
    assert result.output.count("状态: 已安装") == 2


def test_aggregate_uninstall_removes_both(tmp_path: Path):
    runner.invoke(
        disable_ssl_verify.cmd,
        ["install", "--target", str(tmp_path), "--yes"],
    )
    result = runner.invoke(disable_ssl_verify.cmd, ["uninstall", "--target", str(tmp_path)])
    assert result.exit_code == 0
    assert not (tmp_path / httpx_disable_verify.PTH_FILENAME).exists()
    assert not (tmp_path / requests_disable_verify.PTH_FILENAME).exists()


def test_aggregate_uninstall_continues_after_first_missing(tmp_path: Path):
    # Only requests pth exists; httpx pth is missing — aggregate should still
    # remove the existing one and report a non-zero overall exit code.
    (tmp_path / requests_disable_verify.PTH_FILENAME).write_text("placeholder", encoding="utf-8")
    result = runner.invoke(disable_ssl_verify.cmd, ["uninstall", "--target", str(tmp_path)])
    assert result.exit_code == 1
    assert not (tmp_path / requests_disable_verify.PTH_FILENAME).exists()
    assert "pth 不存在" in result.output
    assert "已卸载" in result.output
