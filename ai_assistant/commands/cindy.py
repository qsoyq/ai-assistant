"""Cindy session-share utilities."""

from __future__ import annotations

import hashlib
import json
import os
import unicodedata
import zipfile
from datetime import UTC, datetime
from io import BytesIO
from pathlib import Path

import typer
from cryptography.exceptions import InvalidTag
from cryptography.hazmat.primitives.ciphers.aead import AESGCM

from ai_assistant.commands import make_typer

helptext = """
Cindy 会话分享文件工具。
"""

cmd = make_typer(helptext)

_MAGIC = b"XDTSHARE"
_PLAIN_HEADER = 12
_ENCRYPTED_HEADER = 60


class CshareError(RuntimeError):
    pass


class PasswordRequiredError(CshareError):
    pass


class PasswordInvalidOrCorruptError(CshareError):
    pass


def read_cshare_input(input_path: Path, *, password: str | None = None) -> bytes:
    """Read a Cindy share file and return its inner ZIP payload."""
    try:
        raw = input_path.read_bytes()
    except OSError as exc:
        raise CshareError(f"cannot read input: {input_path}") from exc
    if len(raw) < _PLAIN_HEADER or raw[:8] != _MAGIC:
        raise CshareError("invalid cshare header")
    if raw[8] > 1:
        raise CshareError("unsupported cshare header version")
    cipher = raw[9]
    if cipher == 0:
        payload = raw[_PLAIN_HEADER:]
    elif cipher == 1:
        if len(raw) < _ENCRYPTED_HEADER:
            raise CshareError("truncated encrypted cshare header")
        if password is None:
            raise PasswordRequiredError("password required")
        log_n, r, p = raw[12], raw[13], raw[14]
        if not 10 <= log_n <= 20 or not 1 <= r <= 32 or not 1 <= p <= 4:
            raise CshareError("invalid scrypt parameters")
        try:
            key = hashlib.scrypt(unicodedata.normalize("NFC", password).encode(), salt=raw[16:32], n=2**log_n, r=r, p=p, dklen=32, maxmem=512 * 1024 * 1024)
            payload = AESGCM(key).decrypt(raw[32:44], raw[60:] + raw[44:60], raw[:44])
        except (InvalidTag, ValueError) as exc:
            raise PasswordInvalidOrCorruptError("password incorrect or file corrupted") from exc
    else:
        raise CshareError("unsupported cshare cipher")
    if not payload.startswith(b"PK\x03\x04"):
        raise CshareError("cshare payload is not a ZIP archive")
    return payload


def cshare_bytes_to_markdown(zip_bytes: bytes, *, include_tools: bool = False, include_meta: bool = False, extract_media_dir: Path | None = None) -> str:
    """Validate a Cindy share ZIP and render its visible messages as Markdown."""
    try:
        archive = zipfile.ZipFile(BytesIO(zip_bytes))
    except zipfile.BadZipFile as exc:
        raise CshareError("invalid ZIP payload") from exc
    infos = archive.infolist()
    if len(infos) > 10_000 or sum(info.file_size for info in infos) > 256 * 1024 * 1024:
        raise CshareError("ZIP exceeds safety limits")
    names = {info.filename for info in infos}
    if any(name.startswith("/") or ".." in Path(name).parts for name in names):
        raise CshareError("unsafe ZIP entry path")
    if any((info.external_attr >> 16) & 0o170000 == 0o120000 for info in infos):
        raise CshareError("symbolic links are not allowed in ZIP entries")
    if not {"manifest.json", "session.json", "messages.jsonl"} <= names:
        raise CshareError("missing required share entries")
    try:
        manifest = json.loads(archive.read("manifest.json"))
        session = json.loads(archive.read("session.json"))
    except (KeyError, json.JSONDecodeError) as exc:
        raise CshareError("invalid share metadata") from exc
    entries = manifest.get("entries")
    if not isinstance(entries, list):
        raise CshareError("manifest entries must be a list")
    declared: set[str] = set()
    for entry in entries:
        if not isinstance(entry, dict) or not isinstance(entry.get("path"), str) or not isinstance(entry.get("bytes"), int) or not isinstance(entry.get("sha256"), str):
            raise CshareError("invalid manifest entry")
        entry_path = entry["path"]
        declared.add(entry_path)
        if entry_path not in names:
            raise CshareError("manifest entry is missing from ZIP")
        data = archive.read(entry_path)
        if len(data) != entry["bytes"] or hashlib.sha256(data).hexdigest() != entry["sha256"]:
            raise CshareError("manifest integrity check failed")
    payload_names = {name for name in names if not name.endswith("/") and name != "manifest.json"}
    if declared != payload_names:
        raise CshareError("ZIP entries do not match manifest")
    if extract_media_dir:
        extract_media_dir.mkdir(parents=True, exist_ok=True)
        for info in infos:
            if info.filename.startswith("media/") and not info.is_dir():
                target = extract_media_dir / Path(info.filename).name
                target.write_bytes(archive.read(info))
    messages = []
    for line in archive.read("messages.jsonl").decode().splitlines():
        row = json.loads(line)
        if row.get("role") not in {"user", "assistant"} and not include_tools:
            continue
        content = _render_content(row.get("content", ""))
        if not content:
            continue
        stamp = datetime.fromtimestamp(row.get("createdAt", 0) / 1000, tz=UTC).strftime("%Y-%m-%d %H:%M UTC")
        role = {"user": "用户", "assistant": "助手"}.get(row.get("role"), str(row.get("role")))
        messages.append(f"## {role} · {stamp}\n\n{content}")
    title = manifest.get("title") or session.get("title") or "Cindy Session"
    front = ["---", f"title: {json.dumps(title, ensure_ascii=False)}", f"source_format: cshare-v{manifest.get('formatVersion', 1)}", f"message_count: {len(messages)}"]
    if include_meta:
        front.append(f"agent: {manifest.get('agentKind', '')}")
    return "\n".join([*front, "---", "", f"# {title}", "", "\n\n".join(messages), ""])


def _render_content(raw: object) -> str:
    try:
        value = json.loads(raw) if isinstance(raw, str) else raw
    except json.JSONDecodeError:
        return str(raw)
    if isinstance(value, str):
        return value
    if isinstance(value, list):
        text = [part["text"] for part in value if isinstance(part, dict) and part.get("type") in {"text", "input_text", "output_text"} and isinstance(part.get("text"), str)]
        return "\n\n".join(text) if text else f"```json\n{json.dumps(value, ensure_ascii=False, indent=2)}\n```"
    return f"```json\n{json.dumps(value, ensure_ascii=False, indent=2)}\n```"


@cmd.command("cshare-to-markdown")
def cshare_to_markdown(
    input_path: Path,
    output: Path = typer.Option(..., "--output", "-o"),
    password_env: str | None = None,
    include_tools: bool = False,
    include_meta: bool = False,
    extract_media: Path | None = None,
    verify_only: bool = False,
) -> None:
    """Convert a Cindy .cshare or legacy .xdtshare file to Markdown."""
    password = os.environ.get(password_env) if password_env else None
    try:
        markdown = cshare_bytes_to_markdown(read_cshare_input(input_path, password=password), include_tools=include_tools, include_meta=include_meta, extract_media_dir=extract_media)
    except PasswordRequiredError:
        password = typer.prompt("Password", hide_input=True)
        markdown = cshare_bytes_to_markdown(read_cshare_input(input_path, password=password), include_tools=include_tools, include_meta=include_meta, extract_media_dir=extract_media)
    except CshareError as exc:
        typer.echo(str(exc), err=True)
        raise typer.Exit(1) from exc
    if verify_only:
        typer.echo("verified")
        return
    output.parent.mkdir(parents=True, exist_ok=True)
    temporary = output.with_suffix(f"{output.suffix}.tmp")
    temporary.write_text(markdown, encoding="utf-8")
    temporary.replace(output)
