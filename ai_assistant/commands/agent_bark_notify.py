import hashlib
import json
import os
import re
import tempfile
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Literal
from urllib.parse import urlsplit, urlunsplit

import httpx
import typer

from ai_assistant.commands import make_typer

helptext = """
Send Bark notifications from agent lifecycle hooks.

Typical hook command:
  ai-assistant agent-bark-notify hook --runtime codex --event completion

Configuration:
  BARK_DEVICE_KEY is required. Missing or empty means skip and exit 0.
  BARK_GROUP is optional.
  BARK_SERVER defaults to https://api.day.app.
"""

cmd = make_typer(helptext)

Runtime = Literal["auto", "codex", "claude"]
Event = Literal["auto", "completion", "approval_needed", "failed"]
SummaryMode = Literal["fixed", "extract"]

CODEX_ICON_URL = "https://raw.githubusercontent.com/lobehub/lobe-icons/refs/heads/master/packages/static-png/light/codex-color.png"
CLAUDE_CODE_ICON_URL = "https://raw.githubusercontent.com/lobehub/lobe-icons/refs/heads/master/packages/static-png/light/claudecode-color.png"
LODY_ICON_URL = "https://lody.ai/favicon.ico"

DEFAULT_MESSAGES: dict[str, str] = {
    "completion": "任务已完成",
    "approval_needed": "需要你审批当前操作",
    "failed": "本轮因错误停止",
}

MAX_MESSAGE_LENGTH = 80
DEFAULT_SUMMARY_MAX_CHARS = 120
MAX_TRANSCRIPT_BYTES = 1024 * 1024
DEDUP_TTL_SECONDS = 60 * 60
SENSITIVE_KEY_RE = re.compile(r"(?i)\b(authorization|cookie|set-cookie|x-api-key|api[_-]?key|token|secret|password|passwd|bearer)\b")
SENSITIVE_ASSIGNMENT_RE = re.compile(r"(?i)\b([a-z0-9_.-]*(?:token|secret|password|passwd|cookie|authorization|api[_-]?key)[a-z0-9_.-]*)\s*[:=]\s*('[^']*'|\"[^\"]*\"|[^\s,;]+)")
BEARER_RE = re.compile(r"(?i)\bbearer\s+[a-z0-9._~+/=-]+")
FENCED_CODE_RE = re.compile(r"```.*?```", re.DOTALL)
SHELL_PREFIX_RE = re.compile(r"^\s*(?:bash|zsh|sh|fish|python|python3|node|npm|pnpm|yarn|curl|ssh|scp|rsync)\b", re.IGNORECASE)


@dataclass(frozen=True)
class AgentIdentity:
    name: str
    icon_url: str


@dataclass(frozen=True)
class Notification:
    title: str
    body: str
    icon_url: str
    group: str | None
    bark_url: str
    dedupe_key: str


def _read_stdin() -> str:
    try:
        return typer.get_text_stream("stdin").read()
    except OSError:
        return ""


def parse_hook_payload(raw: str) -> dict[str, Any]:
    if not raw.strip():
        return {}
    try:
        value = json.loads(raw)
    except json.JSONDecodeError:
        return {}
    return value if isinstance(value, dict) else {}


def detect_identity(env: dict[str, str]) -> AgentIdentity:
    if env.get("LODY_SESSION_ID") or env.get("LODY_WORKSPACE_SESSION_ID") or env.get("LODY_ELECTRON_BOOTSTRAP") or env.get("__CFBundleIdentifier") == "ai.lody.desktop":
        return AgentIdentity("Lody", LODY_ICON_URL)
    if env.get("CLAUDECODE") or env.get("CLAUDE_CODE") or env.get("CLAUDE_PROJECT_DIR") or env.get("CLAUDE_CONFIG_DIR"):
        return AgentIdentity("Claude Code", CLAUDE_CODE_ICON_URL)
    return AgentIdentity("Codex", CODEX_ICON_URL)


def detect_runtime(runtime: Runtime, env: dict[str, str], payload: dict[str, Any]) -> str:
    if runtime != "auto":
        return runtime
    if env.get("CLAUDECODE") or env.get("CLAUDE_CODE") or env.get("CLAUDE_PROJECT_DIR") or env.get("CLAUDE_CONFIG_DIR"):
        return "claude"
    if env.get("CODEX_CI") or env.get("CODEX_THREAD_ID"):
        return "codex"
    source = str(payload.get("source") or payload.get("runtime") or "").lower()
    if "claude" in source:
        return "claude"
    if "codex" in source:
        return "codex"
    return "codex"


def detect_event(event: Event, payload: dict[str, Any]) -> str | None:
    if event != "auto":
        return event

    hook_event = str(payload.get("hook_event_name") or payload.get("event") or payload.get("event_name") or payload.get("type") or "")
    if hook_event in {"PermissionRequest"}:
        return "approval_needed"
    if hook_event == "Notification":
        message = str(payload.get("message") or payload.get("notification_type") or payload.get("reason") or "")
        if "permission" in message.lower() or "approval" in message.lower():
            return "approval_needed"
        return None
    if hook_event == "Stop":
        return "completion"
    if hook_event in {"StopFailure", "SessionEnd"} and str(payload.get("reason") or payload.get("status") or "").lower() in {"failed", "error"}:
        return "failed"
    return None


def project_name(payload: dict[str, Any], cwd: Path | None = None) -> str:
    raw = payload.get("cwd") or payload.get("workspace") or payload.get("project_path")
    if isinstance(raw, str) and raw:
        return Path(raw).name
    return (cwd or Path.cwd()).name


def safe_message(event: str, message: str | None) -> str:
    body = (message or DEFAULT_MESSAGES.get(event) or "任务状态已更新").strip()
    body = body.replace("\n", " ")
    if len(body) > MAX_MESSAGE_LENGTH:
        return f"{body[: MAX_MESSAGE_LENGTH - 1]}…"
    return body


def _strip_url_query(value: str) -> str:
    def replace(match: re.Match[str]) -> str:
        raw_url = match.group(0)
        split = urlsplit(raw_url)
        return urlunsplit((split.scheme, split.netloc, split.path, "", split.fragment))

    return re.sub(r"https?://[^\s<>'\")]+", replace, value)


def _extract_text(value: Any) -> str | None:
    if isinstance(value, str):
        return value
    if isinstance(value, list):
        parts = [_extract_text(item) for item in value]
        return " ".join(part for part in parts if part)
    if isinstance(value, dict):
        for key in ("text", "content", "message"):
            text = _extract_text(value.get(key))
            if text:
                return text
    return None


def _extract_dict(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _looks_like_raw_json(text: str) -> bool:
    stripped = text.strip()
    if not stripped:
        return True
    if (stripped.startswith("{") and stripped.endswith("}")) or (stripped.startswith("[") and stripped.endswith("]")):
        return True
    return stripped.count('":') >= 3 and stripped.count("{") + stripped.count("[") >= 1


def _truncate_summary(text: str, max_chars: int) -> str:
    limit = max(1, max_chars)
    if len(text) <= limit:
        return text
    if limit == 1:
        return "…"
    return f"{text[: limit - 1].rstrip()}…"


def clean_summary_text(text: str | None, max_chars: int) -> str | None:
    if not text:
        return None
    body = FENCED_CODE_RE.sub(" ", text)
    body = BEARER_RE.sub("Bearer [REDACTED]", body)
    body = SENSITIVE_ASSIGNMENT_RE.sub(lambda m: f"{m.group(1)}=[REDACTED]", body)
    body = _strip_url_query(body)
    body = " ".join(body.split())
    body = body.strip("` \t\r\n")
    if not body or _looks_like_raw_json(body):
        return None
    if SENSITIVE_KEY_RE.search(body) and "[REDACTED]" not in body:
        return None
    return _truncate_summary(body, max_chars)


def _assistant_text_from_transcript_item(item: dict[str, Any]) -> str | None:
    role = str(item.get("role") or "").lower()
    item_type = str(item.get("type") or "").lower()
    message = item.get("message")
    if isinstance(message, dict):
        role = str(message.get("role") or role).lower()
        if role == "assistant":
            return _extract_text(message.get("content"))
    if role == "assistant":
        return _extract_text(item.get("content") or item.get("text") or item.get("message"))
    if item_type in {"assistant", "final", "assistant_message"}:
        return _extract_text(item.get("content") or item.get("text") or item.get("message"))
    return None


def _read_transcript_messages(transcript_path: str | None) -> list[str]:
    if not transcript_path:
        return []
    path = Path(transcript_path)
    if not path.is_file():
        return []
    try:
        raw = path.read_bytes()[:MAX_TRANSCRIPT_BYTES].decode(errors="replace")
    except OSError:
        return []

    messages: list[str] = []
    try:
        value = json.loads(raw)
    except json.JSONDecodeError:
        value = None
    if isinstance(value, list):
        for item in value:
            if isinstance(item, dict):
                text = _assistant_text_from_transcript_item(item)
                if text:
                    messages.append(text)
        return messages
    if isinstance(value, dict):
        for key in ("messages", "items", "events"):
            nested = value.get(key)
            if isinstance(nested, list):
                for item in nested:
                    if isinstance(item, dict):
                        text = _assistant_text_from_transcript_item(item)
                        if text:
                            messages.append(text)
                return messages
        text = _assistant_text_from_transcript_item(value)
        return [text] if text else []

    for line in raw.splitlines():
        if not line.strip():
            continue
        try:
            item = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(item, dict):
            text = _assistant_text_from_transcript_item(item)
            if text:
                messages.append(text)
    return messages


def _safe_tool_detail(tool_input: dict[str, Any]) -> str | None:
    for key in ("path", "file_path", "file", "cwd", "workspace", "project_path"):
        value = tool_input.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
    for key in ("command", "cmd"):
        value = tool_input.get(key)
        if not isinstance(value, str) or not value.strip():
            continue
        command = " ".join(value.split())
        if len(command) > 80 or SENSITIVE_KEY_RE.search(command):
            return None
        if SHELL_PREFIX_RE.search(command):
            return None
        return command
    return None


def extract_summary(runtime: str, event: str, payload: dict[str, Any], max_chars: int) -> str | None:
    if event == "completion":
        for candidate in (
            _extract_text(payload.get("last_assistant_message")),
            *reversed(_read_transcript_messages(_extract_text(payload.get("transcript_path")))),
        ):
            summary = clean_summary_text(candidate, max_chars)
            if summary:
                return summary
        return None

    if event == "approval_needed":
        tool_input = _extract_dict(payload.get("tool_input"))
        description = clean_summary_text(_extract_text(tool_input.get("description")), max_chars)
        if description:
            return description
        tool_name = _extract_text(payload.get("tool_name"))
        detail = _safe_tool_detail(tool_input)
        if tool_name and detail:
            summary = clean_summary_text(f"{tool_name}: {detail}", max_chars)
            if summary:
                return summary
        message = clean_summary_text(_extract_text(payload.get("message")), max_chars)
        if message:
            return message
        return None

    return None


def build_dedupe_key(runtime: str, event: str, payload: dict[str, Any], body: str) -> str:
    session = payload.get("session_id") or payload.get("conversation_id") or payload.get("transcript_path") or ""
    stable_payload = {
        "hook_event_name": payload.get("hook_event_name") or payload.get("event") or payload.get("event_name") or payload.get("type"),
        "session_id": session,
        "tool_name": payload.get("tool_name"),
        "cwd": payload.get("cwd"),
        "body": body,
    }
    digest = hashlib.sha256(json.dumps(stable_payload, sort_keys=True, ensure_ascii=False).encode()).hexdigest()[:16]
    return f"{runtime}:{event}:{session}:{digest}"


def _dedupe_dir(env: dict[str, str]) -> Path:
    base = env.get("AI_ASSISTANT_AGENT_BARK_NOTIFY_STATE_DIR")
    if base:
        return Path(base)
    return Path(tempfile.gettempdir()) / "ai-assistant-agent-bark-notify"


def already_sent(dedupe_key: str, env: dict[str, str], *, now: float | None = None) -> bool:
    now = now if now is not None else time.time()
    state_dir = _dedupe_dir(env)
    state_dir.mkdir(parents=True, exist_ok=True)
    for path in state_dir.iterdir():
        try:
            if now - path.stat().st_mtime > DEDUP_TTL_SECONDS:
                path.unlink()
        except OSError:
            continue
    path = state_dir / hashlib.sha256(dedupe_key.encode()).hexdigest()
    if path.exists():
        return True
    path.write_text(str(int(now)))
    return False


def build_notification(
    *,
    runtime: str,
    event: str,
    message: str | None,
    env: dict[str, str],
    payload: dict[str, Any],
    cwd: Path | None = None,
) -> Notification | None:
    device_key = env.get("BARK_DEVICE_KEY", "").strip()
    if not device_key:
        return None

    identity = detect_identity(env)
    body = safe_message(event, message)
    title = f"[{identity.name}] [{project_name(payload, cwd)}]"
    bark_server = env.get("BARK_SERVER") or "https://api.day.app"
    dedupe_key = build_dedupe_key(runtime, event, payload, body)
    return Notification(
        title=title,
        body=body,
        icon_url=identity.icon_url,
        group=env.get("BARK_GROUP") or None,
        bark_url=f"{bark_server.rstrip('/')}/{device_key}",
        dedupe_key=dedupe_key,
    )


def send_bark(notification: Notification) -> None:
    data = {
        "title": notification.title,
        "body": notification.body,
        "icon": notification.icon_url,
    }
    if notification.group:
        data["group"] = notification.group
    with httpx.Client(timeout=10) as client:
        client.post(notification.bark_url, data=data).raise_for_status()


@cmd.command()
def hook(
    runtime: Runtime = typer.Option("auto", "--runtime", help="Hook runtime: codex, claude, or auto."),
    event: Event = typer.Option("auto", "--event", help="Notification event override."),
    message: str | None = typer.Option(None, "--message", help="Override short notification body."),
    summary_mode: SummaryMode = typer.Option("fixed", "--summary-mode", help="Notification summary mode: fixed or extract."),
    summary_max_chars: int = typer.Option(DEFAULT_SUMMARY_MAX_CHARS, "--summary-max-chars", min=1, help="Maximum extractive summary length."),
    dry_run: bool = typer.Option(False, "--dry-run", help="Print notification summary without sending Bark request."),
    no_dedupe: bool = typer.Option(False, "--no-dedupe", help="Disable duplicate suppression."),
) -> None:
    """Read hook JSON from stdin and send a best-effort Bark notification."""
    env = dict(os.environ)
    payload = parse_hook_payload(_read_stdin())
    resolved_runtime = detect_runtime(runtime, env, payload)
    resolved_event = detect_event(event, payload)
    if resolved_event is None:
        if dry_run:
            typer.echo("skip: unsupported hook event")
        return

    resolved_message = message
    if resolved_message is None and summary_mode == "extract":
        resolved_message = extract_summary(resolved_runtime, resolved_event, payload, summary_max_chars)

    notification = build_notification(
        runtime=resolved_runtime,
        event=resolved_event,
        message=resolved_message,
        env=env,
        payload=payload,
    )
    if notification is None:
        if dry_run:
            typer.echo("skip: BARK_DEVICE_KEY is missing")
        return

    if not no_dedupe and already_sent(notification.dedupe_key, env):
        if dry_run:
            typer.echo("skip: duplicate notification")
        return

    if dry_run:
        typer.echo(json.dumps({"title": notification.title, "body": notification.body, "icon": notification.icon_url, "group": notification.group, "url": notification.bark_url}, ensure_ascii=False))
        return

    try:
        send_bark(notification)
    except httpx.HTTPError as e:
        typer.echo(f"Bark notification failed: {e}", err=True)


if __name__ == "__main__":
    cmd()
