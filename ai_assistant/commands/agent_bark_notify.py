import hashlib
import json
import os
import re
import subprocess
import tempfile
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from typing import Any, Literal, TypeGuard
from urllib.parse import urlsplit, urlunsplit

import httpx
import typer

from ai_assistant.commands import make_typer

helptext = """
Send Bark notifications from agent lifecycle hooks.

Typical hook command:
  ai-assistant agent-bark-notify hook --runtime codex --event completion
  ai-assistant agent-bark-notify hook --runtime openclaw --event completion --summary-mode extract

Configuration:
  BARK_DEVICE_KEY is required. Missing or empty means skip and exit 0.
  BARK_GROUP is optional and overrides the computed Bark group.
  BARK_SERVER defaults to https://api.day.app.
  AI_ASSISTANT_AGENT_BARK_NOTIFY_GROUP_MODE selects the computed group when BARK_GROUP is unset: agent, project, or project-branch.
  AI_ASSISTANT_AGENT_BARK_NOTIFY_AUDIT_LOG=1 enables local JSONL audit logging.
  AI_ASSISTANT_AGENT_BARK_NOTIFY_AUDIT_LOG_FILE overrides the audit log path.

OpenClaw plugin install and service env guide:
  ai-assistant plugins install-guide agent-bark-notify --target openclaw
  ai-assistant plugins config-snippet agent-bark-notify --target openclaw
"""

cmd = make_typer(helptext)

Runtime = Literal["auto", "codex", "claude", "openclaw"]
Event = Literal["auto", "completion", "approval_needed", "failed"]
SummaryMode = Literal["fixed", "extract"]
GroupMode = Literal["agent", "project", "project-branch"]


class GroupModeOption(str, Enum):
    agent = "agent"
    project = "project"
    project_branch = "project-branch"


CODEX_ICON_URL = "https://raw.githubusercontent.com/lobehub/lobe-icons/refs/heads/master/packages/static-png/light/codex-color.png"
CLAUDE_CODE_ICON_URL = "https://raw.githubusercontent.com/lobehub/lobe-icons/refs/heads/master/packages/static-png/light/claudecode-color.png"
OPENCLAW_ICON_URL = "https://raw.githubusercontent.com/lobehub/lobe-icons/refs/heads/master/packages/static-png/light/openclaw-color.png"
LODY_ICON_URL = "https://lody.ai/favicon.ico"

DEFAULT_MESSAGES: dict[str, str] = {
    "completion": "任务已完成",
    "approval_needed": "需要你审批当前操作",
    "failed": "本轮因错误停止",
}
EVENT_LABELS: dict[str, str] = {
    "completion": "Done",
    "approval_needed": "Approval",
    "failed": "Failed",
}

MAX_MESSAGE_LENGTH = 80
DEFAULT_SUMMARY_MAX_CHARS = 120
MAX_TRANSCRIPT_BYTES = 1024 * 1024
DEDUP_TTL_SECONDS = 60 * 60
TITLE_TEMPLATE_ENV = "AI_ASSISTANT_AGENT_BARK_NOTIFY_TITLE_TEMPLATE"
DEFAULT_TITLE_TEMPLATE = "[{agent}][{event}][{project}][{branch}][{session}]"
GROUP_MODE_ENV = "AI_ASSISTANT_AGENT_BARK_NOTIFY_GROUP_MODE"
GROUP_MODE_CHOICES: tuple[GroupMode, ...] = ("agent", "project", "project-branch")
AUDIT_LOG_ENV = "AI_ASSISTANT_AGENT_BARK_NOTIFY_AUDIT_LOG"
AUDIT_LOG_FILE_ENV = "AI_ASSISTANT_AGENT_BARK_NOTIFY_AUDIT_LOG_FILE"
DEFAULT_AUDIT_LOG_PATH = Path("~/.ai-assistant/agent-bark-notify.log")
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


def identity_for_runtime(runtime: str, env: dict[str, str]) -> AgentIdentity:
    if runtime == "openclaw":
        return AgentIdentity("OpenClaw", OPENCLAW_ICON_URL)
    if runtime == "claude":
        return AgentIdentity("Claude Code", CLAUDE_CODE_ICON_URL)
    if runtime == "codex":
        return AgentIdentity("Codex", CODEX_ICON_URL)
    return detect_identity(env)


def detect_runtime(runtime: Runtime, env: dict[str, str], payload: dict[str, Any]) -> str:
    if runtime != "auto":
        return runtime
    if env.get("LODY_SESSION_ID") or env.get("LODY_WORKSPACE_SESSION_ID") or env.get("LODY_ELECTRON_BOOTSTRAP") or env.get("__CFBundleIdentifier") == "ai.lody.desktop":
        return "lody"
    if env.get("CLAUDECODE") or env.get("CLAUDE_CODE") or env.get("CLAUDE_PROJECT_DIR") or env.get("CLAUDE_CONFIG_DIR"):
        return "claude"
    if env.get("OPENCLAW_SESSION_ID") or env.get("OPENCLAW_WORKSPACE_DIR") or env.get("OPENCLAW_GATEWAY_PORT"):
        return "openclaw"
    if env.get("CODEX_CI") or env.get("CODEX_THREAD_ID"):
        return "codex"
    source = str(payload.get("source") or payload.get("runtime") or "").lower()
    if "openclaw" in source:
        return "openclaw"
    if "claude" in source:
        return "claude"
    if "codex" in source:
        return "codex"
    return "codex"


def detect_event(event: Event, payload: dict[str, Any]) -> str | None:
    if event != "auto":
        return event

    hook_event = str(payload.get("hook_event_name") or payload.get("event") or payload.get("event_name") or payload.get("type") or "")
    if hook_event in {"PermissionRequest", "approval_needed", "approval-needed", "approval:needed", "before_tool_call"}:
        return "approval_needed"
    if hook_event in {"agent_end", "agent:end"}:
        return "completion" if payload.get("success") is not False else "failed"
    if hook_event in {"message_sent", "message:sent"}:
        return "completion" if payload.get("success") is not False else "failed"
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
    for key in ("project_name", "workspace_name", "repository", "repo", "agentId", "agent_id", "name"):
        raw_name = payload.get(key)
        if isinstance(raw_name, str) and raw_name.strip():
            return raw_name.strip()

    env = os.environ
    for key in ("AI_ASSISTANT_AGENT_BARK_NOTIFY_PROJECT_NAME", "OPENCLAW_WORKSPACE_NAME", "CODEX_WORKSPACE_NAME", "CODEX_PROJECT_NAME", "LODY_WORKSPACE_NAME", "LODY_PROJECT_NAME"):
        raw_name = env.get(key)
        if raw_name and raw_name.strip():
            return raw_name.strip()

    raw = payload.get("cwd") or payload.get("workspace") or payload.get("workspaceDir") or payload.get("project_path")
    if isinstance(raw, str) and raw:
        return Path(raw).name
    return (cwd or Path.cwd()).name


def _path_from_payload(payload: dict[str, Any], cwd: Path | None = None) -> Path:
    for key in ("cwd", "workspace", "workspaceDir", "project_path"):
        raw = payload.get(key)
        if isinstance(raw, str) and raw:
            return Path(raw)
    return cwd or Path.cwd()


def cwd_basename(payload: dict[str, Any], cwd: Path | None = None) -> str:
    raw = payload.get("cwd")
    if isinstance(raw, str) and raw:
        return Path(raw).name
    return (cwd or Path.cwd()).name


def branch_name(payload: dict[str, Any], env: dict[str, str], cwd: Path | None = None) -> str:
    for key in ("branch_name", "branch", "git_branch", "ref_name"):
        raw_name = payload.get(key)
        if isinstance(raw_name, str) and raw_name.strip():
            return raw_name.strip().removeprefix("refs/heads/")

    for key in ("AI_ASSISTANT_AGENT_BARK_NOTIFY_BRANCH_NAME", "CODEX_BRANCH_NAME", "GIT_BRANCH", "BRANCH_NAME"):
        raw_name = env.get(key)
        if raw_name and raw_name.strip():
            return raw_name.strip().removeprefix("refs/heads/")

    repo_path = _path_from_payload(payload, cwd)
    try:
        result = subprocess.run(
            ["git", "-C", str(repo_path), "branch", "--show-current"],
            check=False,
            capture_output=True,
            text=True,
            timeout=1,
        )
    except (OSError, subprocess.SubprocessError):
        return ""
    if result.returncode != 0:
        return ""
    return result.stdout.strip()


def session_name(payload: dict[str, Any], env: dict[str, str]) -> str:
    for key in ("session_name", "conversation_name", "thread_name", "workspace_session_name"):
        raw_name = payload.get(key)
        if isinstance(raw_name, str) and raw_name.strip():
            return raw_name.strip()

    for key in ("AI_ASSISTANT_AGENT_BARK_NOTIFY_SESSION_NAME", "OPENCLAW_SESSION_NAME", "CODEX_SESSION_NAME", "LODY_SESSION_NAME"):
        raw_name = env.get(key)
        if raw_name and raw_name.strip():
            return raw_name.strip()
    return ""


def safe_message(event: str, message: str | None) -> str:
    body = (message or DEFAULT_MESSAGES.get(event) or "任务状态已更新").strip()
    body = body.replace("\n", " ")
    if len(body) > MAX_MESSAGE_LENGTH:
        return f"{body[: MAX_MESSAGE_LENGTH - 1]}…"
    return body


def event_label(event: str) -> str:
    return EVENT_LABELS.get(event, "Update")


class _SafeTitleVars(dict[str, str]):
    def __missing__(self, key: str) -> str:
        return "{" + key + "}"


def _default_title(values: dict[str, str]) -> str:
    parts = [values[key] for key in ("agent", "event", "project", "branch", "session") if values.get(key)]
    return "".join(f"[{part}]" for part in parts)


def notification_title(*, runtime: str, identity: AgentIdentity, event: str, payload: dict[str, Any], env: dict[str, str], cwd: Path | None = None) -> str:
    values = _SafeTitleVars(
        agent=identity.name,
        event=event_label(event),
        project=project_name(payload, cwd),
        runtime=runtime,
        cwd_basename=cwd_basename(payload, cwd),
        branch=branch_name(payload, env, cwd),
        session=session_name(payload, env),
    )
    configured_template = env.get(TITLE_TEMPLATE_ENV, "").strip()
    if not configured_template:
        title = _default_title(values)
        return title or _default_title(_SafeTitleVars(agent=identity.name, event=event_label(event)))
    try:
        title = configured_template.format_map(values)
    except ValueError:
        title = _default_title(values)
    return " ".join(title.split()) or _default_title(values)


def _strip_url_query(value: str) -> str:
    def replace(match: re.Match[str]) -> str:
        raw_url = match.group(0)
        split = urlsplit(raw_url)
        return urlunsplit((split.scheme, split.netloc, split.path, "", split.fragment))

    return re.sub(r"https?://[^\s<>'\")]+", replace, value)


def _redact_url(value: str) -> str:
    def replace(match: re.Match[str]) -> str:
        raw_url = match.group(0)
        split = urlsplit(raw_url)
        return urlunsplit((split.scheme, split.netloc, "/[REDACTED]", "", ""))

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


def _hash_value(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value)
    if not text:
        return None
    return hashlib.sha256(text.encode()).hexdigest()[:16]


def _hook_event_name(payload: dict[str, Any]) -> str | None:
    value = payload.get("hook_event_name") or payload.get("event") or payload.get("event_name") or payload.get("type")
    return str(value) if value is not None else None


def _env_value(env: dict[str, str], key: str, default: str = "") -> str:
    value = env.get(key, default).strip()
    if len(value) >= 2 and value[0] == value[-1] and value[0] in {"'", '"'}:
        return value[1:-1].strip()
    return value


def _is_group_mode(value: str) -> TypeGuard[GroupMode]:
    return value in GROUP_MODE_CHOICES


def _group_mode_error(value: str) -> typer.BadParameter:
    choices = ", ".join(GROUP_MODE_CHOICES)
    return typer.BadParameter(f"{GROUP_MODE_ENV} must be one of: {choices}; got {value!r}")


def resolve_group_mode(cli_group_mode: GroupModeOption | None, env: dict[str, str]) -> GroupMode:
    if cli_group_mode is not None:
        value = cli_group_mode.value
        if _is_group_mode(value):
            return value
        raise _group_mode_error(value)

    env_value = _env_value(env, GROUP_MODE_ENV)
    if not env_value:
        return "agent"
    if _is_group_mode(env_value):
        return env_value
    raise _group_mode_error(env_value)


def notification_group(
    *,
    identity: AgentIdentity,
    payload: dict[str, Any],
    env: dict[str, str],
    group_mode: GroupMode,
    cwd: Path | None = None,
) -> str | None:
    configured_group = _env_value(env, "BARK_GROUP")
    if configured_group:
        return configured_group

    if group_mode == "agent":
        return identity.name

    project = project_name(payload, cwd).strip()
    if group_mode == "project":
        return project or identity.name

    if not project:
        return identity.name
    branch = branch_name(payload, env, cwd).strip()
    if not branch:
        return project
    return f"{project}@{branch}"


def _session_id(payload: dict[str, Any]) -> str | None:
    value = payload.get("session_id") or payload.get("sessionId") or payload.get("sessionKey") or payload.get("conversation_id") or payload.get("transcript_path")
    return str(value) if value is not None else None


def _audit_enabled(env: dict[str, str]) -> bool:
    return _env_value(env, AUDIT_LOG_ENV).lower() in {"1", "true", "yes", "on"}


def _audit_log_path(env: dict[str, str]) -> Path:
    configured = _env_value(env, AUDIT_LOG_FILE_ENV)
    if configured:
        return Path(configured).expanduser()
    return DEFAULT_AUDIT_LOG_PATH.expanduser()


def _safe_error_message(error: BaseException) -> str:
    message = " ".join(str(error).split())
    message = BEARER_RE.sub("Bearer [REDACTED]", message)
    message = SENSITIVE_ASSIGNMENT_RE.sub(lambda m: f"{m.group(1)}=[REDACTED]", message)
    message = _redact_url(message)
    return _truncate_summary(message, 200)


def _write_audit_record(env: dict[str, str], record: dict[str, Any]) -> None:
    if not _audit_enabled(env):
        return
    try:
        path = _audit_log_path(env)
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("a", encoding="utf-8") as f:
            f.write(json.dumps(record, ensure_ascii=False, sort_keys=True))
            f.write("\n")
    except OSError:
        return


def _new_audit_record(
    *,
    runtime: str,
    event: str | None,
    payload: dict[str, Any],
    summary_mode: SummaryMode,
    cwd: Path | None = None,
) -> dict[str, Any]:
    return {
        "time": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        "runtime": runtime,
        "event": event,
        "hook_event_name": _hook_event_name(payload),
        "status": None,
        "project": project_name(payload, cwd),
        "session_id_hash": _hash_value(_session_id(payload)),
        "dedupe_key_hash": None,
        "summary_mode": summary_mode,
        "title": None,
        "body_len": None,
    }


def _finish_audit_record(
    env: dict[str, str],
    record: dict[str, Any],
    *,
    status: str,
    notification: Notification | None = None,
    error: BaseException | None = None,
) -> None:
    record["status"] = status
    if notification is not None:
        record["dedupe_key_hash"] = _hash_value(notification.dedupe_key)
        record["title"] = notification.title
        record["body_len"] = len(notification.body)
    if error is not None:
        record["error_class"] = error.__class__.__name__
        record["error_message"] = _safe_error_message(error)
    _write_audit_record(env, record)


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


def _approval_tool_summary(tool_name: str | None, detail: str | None, max_chars: int) -> str | None:
    if not tool_name and not detail:
        return None
    if tool_name and detail:
        return clean_summary_text(f"{tool_name} 需要审批：{detail}", max_chars)
    if tool_name:
        return clean_summary_text(f"{tool_name} 需要审批", max_chars)
    return clean_summary_text(f"需要审批：{detail}", max_chars)


def extract_summary(runtime: str, event: str, payload: dict[str, Any], max_chars: int) -> str | None:
    if event == "completion":
        for candidate in (
            _extract_text(payload.get("last_assistant_message")),
            _extract_text(payload.get("lastAssistantMessage")),
            _extract_text(payload.get("content")),
            _extract_text(payload.get("message")),
            _extract_text(payload.get("summary")),
            _extract_text(payload.get("error")),
            *reversed(_read_transcript_messages(_extract_text(payload.get("transcript_path")))),
            *reversed(_read_transcript_messages(_extract_text(payload.get("transcriptPath")))),
        ):
            summary = clean_summary_text(candidate, max_chars)
            if summary:
                return summary
        return None

    if event == "approval_needed":
        tool_input = _extract_dict(payload.get("tool_input"))
        if not tool_input:
            tool_input = _extract_dict(payload.get("params"))
        require_approval = _extract_dict(payload.get("requireApproval"))
        approval = _extract_dict(payload.get("approval"))
        for candidate in (
            _extract_text(require_approval.get("description")),
            _extract_text(approval.get("description")),
            _extract_text(payload.get("description")),
            _extract_text(payload.get("title")),
        ):
            summary = clean_summary_text(candidate, max_chars)
            if summary:
                return summary
        description = clean_summary_text(_extract_text(tool_input.get("description")), max_chars)
        if description:
            return description
        tool_name = _extract_text(payload.get("tool_name") or payload.get("toolName"))
        detail = _safe_tool_detail(tool_input)
        summary = _approval_tool_summary(tool_name, detail, max_chars)
        if summary:
            return summary
        message = clean_summary_text(_extract_text(payload.get("message")), max_chars)
        if message:
            return message
        return None

    return None


def build_dedupe_key(runtime: str, event: str, payload: dict[str, Any], body: str) -> str:
    session = payload.get("session_id") or payload.get("sessionId") or payload.get("sessionKey") or payload.get("conversation_id") or payload.get("transcript_path") or ""
    stable_payload = {
        "hook_event_name": payload.get("hook_event_name") or payload.get("event") or payload.get("event_name") or payload.get("type"),
        "session_id": session,
        "message_id": payload.get("messageId") or payload.get("message_id"),
        "conversation_id": payload.get("conversationId") or payload.get("conversation_id"),
        "tool_name": payload.get("tool_name") or payload.get("toolName"),
        "cwd": payload.get("cwd") or payload.get("workspaceDir"),
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
    group_mode: GroupMode = "agent",
    cwd: Path | None = None,
) -> Notification | None:
    device_key = _env_value(env, "BARK_DEVICE_KEY")
    if not device_key:
        return None

    identity = identity_for_runtime(runtime, env)
    body = safe_message(event, message)
    title = notification_title(runtime=runtime, identity=identity, event=event, payload=payload, env=env, cwd=cwd)
    bark_server = _env_value(env, "BARK_SERVER", "https://api.day.app")
    dedupe_key = build_dedupe_key(runtime, event, payload, body)
    return Notification(
        title=title,
        body=body,
        icon_url=identity.icon_url,
        group=notification_group(identity=identity, payload=payload, env=env, group_mode=group_mode, cwd=cwd),
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
    runtime: Runtime = typer.Option("auto", "--runtime", help="Hook runtime: codex, claude, openclaw, or auto."),
    event: Event = typer.Option("auto", "--event", help="Notification event override."),
    message: str | None = typer.Option(None, "--message", help="Override short notification body."),
    group_mode: GroupModeOption | None = typer.Option(None, "--group-mode", help="Bark group mode: agent, project, or project-branch."),
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
    resolved_group_mode = resolve_group_mode(group_mode, env)
    audit_record = _new_audit_record(runtime=resolved_runtime, event=resolved_event, payload=payload, summary_mode=summary_mode)
    try:
        if resolved_event is None:
            _finish_audit_record(env, audit_record, status="skipped_unsupported_event")
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
            group_mode=resolved_group_mode,
        )
        if notification is None:
            _finish_audit_record(env, audit_record, status="skipped_missing_device_key")
            if dry_run:
                typer.echo("skip: BARK_DEVICE_KEY is missing")
            return

        if not no_dedupe and already_sent(notification.dedupe_key, env):
            _finish_audit_record(env, audit_record, status="skipped_duplicate", notification=notification)
            if dry_run:
                typer.echo("skip: duplicate notification")
            return

        if dry_run:
            _finish_audit_record(env, audit_record, status="sent", notification=notification)
            typer.echo(
                json.dumps({"title": notification.title, "body": notification.body, "icon": notification.icon_url, "group": notification.group, "url": notification.bark_url}, ensure_ascii=False)
            )
            return

        try:
            send_bark(notification)
        except httpx.HTTPError as e:
            _finish_audit_record(env, audit_record, status="bark_http_error", notification=notification, error=e)
            typer.echo(f"Bark notification failed: {e}", err=True)
            return
        _finish_audit_record(env, audit_record, status="sent", notification=notification)
    except Exception as e:
        _finish_audit_record(env, audit_record, status="hook_exception", error=e)
        typer.echo(f"Bark hook failed: {e}", err=True)
        return


if __name__ == "__main__":
    cmd()
