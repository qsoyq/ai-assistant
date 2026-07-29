import hashlib
import json
from io import BytesIO
from pathlib import Path
from typing import cast
from zipfile import ZIP_DEFLATED, ZipFile

import pytest
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from typer.testing import CliRunner

from ai_assistant.commands.cindy import (
    PasswordInvalidOrCorruptError,
    PasswordRequiredError,
    cmd,
    cshare_bytes_to_markdown,
    read_cshare_input,
)
from ai_assistant.commands.main import cmd as root_cmd

runner = CliRunner()


def test_cindy_command_help():
    result = runner.invoke(cmd, ["--help"])
    assert result.exit_code == 0
    assert "Cindy" in result.output


def test_root_registers_cindy_command():
    result = runner.invoke(root_cmd, ["cindy", "--help"])
    assert result.exit_code == 0
    assert "Cindy" in result.output


def _bundle() -> bytes:
    stream = BytesIO()
    with ZipFile(stream, "w", ZIP_DEFLATED) as archive:
        messages = "\n".join(
            [json.dumps({"role": "user", "content": '"hello"', "createdAt": 0}), json.dumps({"role": "assistant", "content": json.dumps([{"type": "text", "text": "world"}]), "createdAt": 1000})]
        )
        entries = {"session.json": b'{"title":"Demo"}', "messages.jsonl": messages.encode(), "media-map.json": b'{"entries":[]}'}
        manifest_entries = []
        for name, data in entries.items():
            archive.writestr(name, data)
            manifest_entries.append({"path": name, "bytes": len(data), "sha256": hashlib.sha256(data).hexdigest()})
        archive.writestr("manifest.json", json.dumps({"formatVersion": 1, "title": "Demo", "entries": manifest_entries}))
    return stream.getvalue()


def _share(payload: bytes, password: str | None = None) -> bytes:
    if password is None:
        return b"XDTSHARE" + bytes([1, 0, 0, 0]) + payload
    salt, iv = b"s" * 16, b"i" * 12
    header = bytearray(b"XDTSHARE" + bytes([1, 1, 0, 0, 15, 8, 1, 0]) + salt + iv + b"\0" * 16)
    key = hashlib.scrypt(password.encode(), salt=salt, n=2**15, r=8, p=1, dklen=32, maxmem=512 * 1024 * 1024)
    sealed = cast(bytes, AESGCM(key).encrypt(iv, payload, bytes(header[:44])))
    header[44:60] = sealed[-16:]
    return bytes(header) + sealed[:-16]


def test_read_cshare_plain_and_render(tmp_path: Path):
    path = tmp_path / "demo.cshare"
    path.write_bytes(_share(_bundle()))
    markdown = cshare_bytes_to_markdown(read_cshare_input(path))
    assert "# Demo" in markdown
    assert "hello" in markdown
    assert "world" in markdown


def test_read_cshare_encrypted_and_requires_password(tmp_path: Path):
    path = tmp_path / "demo.cshare"
    path.write_bytes(_share(_bundle(), "secret"))
    with pytest.raises(PasswordRequiredError):
        read_cshare_input(path)
    assert read_cshare_input(path, password="secret").startswith(b"PK\x03\x04")
    with pytest.raises(PasswordInvalidOrCorruptError):
        read_cshare_input(path, password="wrong")


def test_cli_requires_output_option(tmp_path: Path):
    source = tmp_path / "demo.cshare"
    output = tmp_path / "demo.md"
    source.write_bytes(_share(_bundle()))
    result = runner.invoke(cmd, ["cshare-to-markdown", str(source), "--output", str(output)])
    assert result.exit_code == 0, result.output
    assert output.read_text(encoding="utf-8").startswith("---")


def test_renderer_rejects_unlisted_zip_payload():
    payload = _bundle()
    source = BytesIO(payload)
    target = BytesIO()
    with ZipFile(source) as input_archive, ZipFile(target, "w", ZIP_DEFLATED) as output_archive:
        for info in input_archive.infolist():
            output_archive.writestr(info, input_archive.read(info))
        output_archive.writestr("unexpected.txt", "not declared")
    with pytest.raises(Exception, match="do not match manifest"):
        cshare_bytes_to_markdown(target.getvalue())
