import os
import tempfile
from pathlib import Path

import pytest
import typer
from typer.testing import CliRunner

from ai_assistant.commands.ssl import (
    _require_command,
    _resolve_cert_path,
    _trust_certificate_on_linux,
    _trust_certificate_on_macos,
    _trust_certificate_on_windows,
    cmd,
)

runner = CliRunner()


def _make_executable_script(script_path: Path, script_content: str) -> None:
    script_path.write_text(script_content, encoding="utf-8")
    script_path.chmod(0o755)


def test_resolve_cert_path_rejects_missing_file(tmp_path: Path):
    missing_path = tmp_path / "missing.crt"

    with pytest.raises(typer.BadParameter, match="证书文件不存在"):
        _resolve_cert_path(missing_path)


def test_require_command_prints_install_guide_when_missing(monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]):
    monkeypatch.setenv("PATH", "")

    with pytest.raises(typer.Exit) as exc_info:
        _require_command("openssl")

    assert exc_info.value.exit_code == 1
    captured = capsys.readouterr()
    assert "警告：缺少依赖命令 `openssl`。" in captured.err
    assert "brew install openssl@3" in captured.err
    assert "winget install ShiningLight.OpenSSL.Light" in captured.err


def test_generate_cleans_temp_config_when_openssl_missing(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    temp_dir = tmp_path / "temp"
    temp_dir.mkdir()
    output_dir = tmp_path / "ssl"

    monkeypatch.setenv("PATH", "")
    monkeypatch.setattr(tempfile, "tempdir", str(temp_dir))

    result = runner.invoke(cmd, ["generate", "--output-dir", str(output_dir)], input="\n\n\n\n")

    assert result.exit_code == 1
    assert not list(temp_dir.glob("*.cnf"))
    assert output_dir.exists()
    assert not list(output_dir.iterdir())


def test_trust_certificate_on_macos_calls_security(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    cert_path = tmp_path / "server.crt"
    cert_path.write_text("dummy cert", encoding="utf-8")

    args_output_path = tmp_path / "security-args.txt"
    security_script_path = tmp_path / "security"
    _make_executable_script(
        security_script_path,
        f"""#!/bin/sh
printf '%s\n' "$@" > "{args_output_path}"
""",
    )

    monkeypatch.setenv("PATH", f"{tmp_path}{os.pathsep}{os.environ['PATH']}")

    _trust_certificate_on_macos(cert_path, "system")

    called_args = args_output_path.read_text(encoding="utf-8").splitlines()
    assert called_args == [
        "add-trusted-cert",
        "-d",
        "-r",
        "trustRoot",
        "-k",
        "/Library/Keychains/System.keychain",
        str(cert_path),
    ]


def test_trust_certificate_on_windows_calls_certutil(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    cert_path = tmp_path / "server.crt"
    cert_path.write_text("dummy cert", encoding="utf-8")

    args_output_path = tmp_path / "certutil-args.txt"
    certutil_script_path = tmp_path / "certutil"
    _make_executable_script(
        certutil_script_path,
        f"""#!/bin/sh
printf '%s\n' "$@" > "{args_output_path}"
""",
    )

    monkeypatch.setenv("PATH", f"{tmp_path}{os.pathsep}{os.environ['PATH']}")

    _trust_certificate_on_windows(cert_path, "user")

    called_args = args_output_path.read_text(encoding="utf-8").splitlines()
    assert called_args == [
        "-user",
        "-addstore",
        "Root",
        str(cert_path),
    ]


def test_trust_certificate_on_linux_copies_cert_and_refreshes_store(tmp_path: Path):
    cert_path = tmp_path / "my cert.pem"
    cert_content = "dummy cert"
    cert_path.write_text(cert_content, encoding="utf-8")

    refresh_marker_path = tmp_path / "refresh-called.txt"
    refresh_script_path = tmp_path / "refresh-ca"
    _make_executable_script(
        refresh_script_path,
        f"""#!/bin/sh
printf 'ok' > "{refresh_marker_path}"
""",
    )

    target_directory = tmp_path / "ca-certificates"

    _trust_certificate_on_linux(cert_path, trust_store=(target_directory, [str(refresh_script_path)]))

    copied_cert_path = target_directory / "my-cert.crt"
    assert copied_cert_path.read_text(encoding="utf-8") == cert_content
    assert refresh_marker_path.read_text(encoding="utf-8") == "ok"


def test_trust_certificate_on_linux_prints_install_guide_when_store_command_missing(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
):
    cert_path = tmp_path / "server.crt"
    cert_path.write_text("dummy cert", encoding="utf-8")
    monkeypatch.setenv("PATH", "")

    with pytest.raises(typer.Exit) as exc_info:
        _trust_certificate_on_linux(cert_path, trust_store=None)

    assert exc_info.value.exit_code == 1
    captured = capsys.readouterr()
    assert "update-ca-certificates" in captured.err
    assert "update-ca-trust" in captured.err
