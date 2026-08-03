"""Probe chat-model capabilities from an OpenAI-compatible LiteLLM gateway."""

from __future__ import annotations

import concurrent.futures
import json
import re
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, cast

import httpx
import typer
from rich.console import Console
from rich.progress import (
    BarColumn,
    MofNCompleteColumn,
    Progress,
    TextColumn,
    TimeElapsedColumn,
    TimeRemainingColumn,
)

from ai_assistant.commands import version_callback

helptext = """
探测 LiteLLM 网关中的聊天模型、reasoning 和常用 API 能力。
"""

cmd = typer.Typer(help=helptext)

DEFAULT_LEVELS = ("none", "off", "minimal", "low", "medium", "high", "xhigh", "max", "ultra")
NON_CHAT_ID = re.compile(
    r"(?:embedding|image|transcrib|speech|scribe|realtime|whisper|seedance|"
    r"video|audio|asr|elevenlabs|happyhorse|doubao|(?:^|[-/])(?:t2v|i2v|r2v)(?:[-/]|$)|voyage/)",
    re.IGNORECASE,
)
TRANSIENT_STATUS = {408, 429}
SAFE_ERROR_REASONS = {
    "invalid_model": "The gateway rejected this model as a callable chat model.",
    "temporary_unavailable": "No healthy deployment was available at probe time; retry later.",
    "network_error": "Network or timeout error while contacting the gateway.",
}


@dataclass(frozen=True)
class ProbeResponse:
    status: int | None
    duration_ms: int
    error_type: str | None = None
    error_message: str | None = None
    attempts: int = 1
    payload: Any = None

    @property
    def ok(self) -> bool:
        return self.status is not None and 200 <= self.status < 300


def normalize_base_url(value: str) -> str:
    return value.rstrip("/")


def endpoint(base_url: str, path: str) -> str:
    if base_url.endswith("/v1") and path.startswith("/v1/"):
        return base_url + path[3:]
    return base_url + path


def classify_model(model: dict[str, Any]) -> dict[str, Any]:
    model_id = str(model.get("id", ""))
    metadata_value = model.get("metadata")
    metadata = cast(dict[str, Any], metadata_value) if isinstance(metadata_value, dict) else {}
    endpoint_type = str(metadata.get("endpoint_type", "")).lower()
    transport = str(metadata.get("transport", "")).lower()
    if endpoint_type or transport:
        if endpoint_type == "passthrough" or transport not in ("", "http", "https"):
            return {"kind": "excluded", "source": "metadata", "confidence": "high", "reason": endpoint_type or transport}
    if NON_CHAT_ID.search(model_id):
        return {"kind": "excluded", "source": "heuristic", "confidence": "high", "reason": "non_chat_model_name"}
    return {"kind": "chat", "source": "heuristic", "confidence": "low", "reason": "ordinary_model_name"}


def _error_summary(response: httpx.Response) -> str | None:
    try:
        payload = response.json()
    except (ValueError, json.JSONDecodeError):
        return None
    error = payload.get("error", payload) if isinstance(payload, dict) else payload
    if isinstance(error, dict):
        message = error.get("message") or error.get("detail") or error.get("type")
        return str(message)[:300] if message is not None else None
    return str(error)[:300]


def request_json(
    client: httpx.Client,
    url: str,
    token: str,
    payload: dict[str, Any] | None,
    timeout: float,
    retries: int,
    *,
    capture_payload: bool = False,
) -> ProbeResponse:
    started = time.monotonic()
    attempts = 0
    while True:
        attempts += 1
        try:
            response = client.request(
                "POST" if payload is not None else "GET",
                url,
                headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json", "Accept": "application/json"},
                json=payload,
                timeout=timeout,
            )
            if (response.status_code in TRANSIENT_STATUS or response.status_code >= 500) and attempts <= retries + 1:
                time.sleep(min(2.0, 0.5 * (2 ** (attempts - 1))))
                continue
            response_payload = None
            if capture_payload and response.is_success:
                try:
                    response_payload = response.json()
                except (ValueError, json.JSONDecodeError):
                    response_payload = None
            return ProbeResponse(
                response.status_code,
                int((time.monotonic() - started) * 1000),
                "http_error" if response.is_error else None,
                _error_summary(response) if response.is_error else None,
                attempts,
                response_payload,
            )
        except httpx.TimeoutException as exc:
            error_type = "network_error"
            message = type(exc).__name__
        except httpx.RequestError as exc:
            error_type = "network_error"
            message = type(exc).__name__
        if attempts <= retries + 1:
            time.sleep(min(2.0, 0.5 * (2 ** (attempts - 1))))
            continue
        return ProbeResponse(None, int((time.monotonic() - started) * 1000), error_type, message[:300], attempts)


def failure_category(response: ProbeResponse) -> str:
    message = (response.error_message or "").lower()
    if response.error_type == "network_error" or response.status is None:
        return "network_error"
    if response.status in TRANSIENT_STATUS or response.status >= 500 or "cooldown" in message or "no deployments available" in message:
        return "temporary_unavailable"
    if any(term in message for term in ("invalid model", "invalid model name", "model name", "document model")):
        return "invalid_model"
    return "unsupported" if response.status is not None and 400 <= response.status < 500 else "unknown_error"


def result(response: ProbeResponse, accepted: str = "accepted", rejected: str = "rejected") -> dict[str, Any]:
    status = accepted if response.ok else rejected if response.status is not None and 400 <= response.status < 500 else "error"
    output: dict[str, Any] = {"status": status, "httpStatus": response.status, "durationMs": response.duration_ms, "attempts": response.attempts}
    if not response.ok:
        category = failure_category(response)
        output["failure"] = {"category": category, "reason": SAFE_ERROR_REASONS.get(category, "The gateway did not accept this capability probe.")}
    return output


def payload_for(wire_api: str, model: str, feature: str | None = None, level: str | None = None) -> dict[str, Any]:
    if wire_api == "responses":
        payload: dict[str, Any] = {"model": model, "input": "Reply exactly: ok", "max_output_tokens": 16}
        if level is not None:
            payload["reasoning"] = {"effort": level}
        if feature == "streaming":
            payload["stream"] = True
        elif feature == "tools":
            payload["tools"] = [{"type": "function", "name": "probe", "description": "Probe tool", "parameters": {"type": "object", "properties": {}}}]
        elif feature == "structured":
            payload["text"] = {
                "format": {
                    "type": "json_schema",
                    "name": "probe",
                    "schema": {"type": "object", "properties": {"ok": {"type": "boolean"}}, "required": ["ok"], "additionalProperties": False},
                    "strict": True,
                }
            }
        return payload
    payload = {"model": model, "messages": [{"role": "user", "content": "Reply exactly: ok"}], "max_tokens": 16}
    if level is not None:
        payload["reasoning_effort"] = level
    if feature == "streaming":
        payload["stream"] = True
    elif feature == "tools":
        payload["tools"] = [{"type": "function", "function": {"name": "probe", "description": "Probe tool", "parameters": {"type": "object", "properties": {}}}}]
    elif feature == "structured":
        payload["response_format"] = {
            "type": "json_schema",
            "json_schema": {"name": "probe", "schema": {"type": "object", "properties": {"ok": {"type": "boolean"}}, "required": ["ok"], "additionalProperties": False}, "strict": True},
        }
    return payload


def probe_model(client: httpx.Client, model: dict[str, Any], base_url: str, token: str, wire_api: str, levels: tuple[str, ...], timeout: float, retries: int) -> dict[str, Any]:
    model_id = str(model["id"])
    chosen: str | None = None
    chat_result: dict[str, Any] = {}
    for candidate in ("chat", "responses") if wire_api == "auto" else (wire_api,):
        path = "/v1/chat/completions" if candidate == "chat" else "/v1/responses"
        response = request_json(client, endpoint(base_url, path), token, payload_for(candidate, model_id), timeout, retries)
        chat_result = result(response)
        if response.ok:
            chosen = candidate
            break
        if wire_api != "auto" or response.status not in (404, 405):
            break
    base: dict[str, Any] = {"id": model_id, "classification": classify_model(model), "chat": chat_result, "reasoning": {"levels": {}}, "features": {}}
    if chosen is None:
        return base
    path = "/v1/chat/completions" if chosen == "chat" else "/v1/responses"
    base["chat"]["wireApi"] = chosen
    base["reasoning"]["levels"] = {level: result(request_json(client, endpoint(base_url, path), token, payload_for(chosen, model_id, level=level), timeout, retries)) for level in levels}
    base["features"] = {
        feature: result(request_json(client, endpoint(base_url, path), token, payload_for(chosen, model_id, feature=feature), timeout, retries)) for feature in ("streaming", "tools", "structured")
    }
    return base


def fetch_models(client: httpx.Client, base_url: str, token: str, timeout: float, retries: int) -> list[dict[str, Any]]:
    response = request_json(client, endpoint(base_url, "/v1/models"), token, None, timeout, retries, capture_payload=True)
    if not response.ok:
        raise RuntimeError(f"GET /v1/models failed: {response.status}")
    payload = response.payload
    data = payload.get("data") if isinstance(payload, dict) else None
    if not isinstance(data, list):
        raise RuntimeError("/v1/models response has no data array")
    return [item for item in data if isinstance(item, dict) and item.get("id")]


def markdown_report(report: dict[str, Any]) -> str:
    lines = [
        "# Chat Model Capability Report",
        "",
        f"Generated: `{report['generatedAt']}`",
        "",
        "## Summary",
        "",
        f"- Listed: {report['summary']['listed']}",
        f"- Excluded non-chat: {report['summary']['excluded']}",
        f"- Chat candidates: {report['summary']['chatCandidates']}",
        f"- Chat supported: {report['summary']['chatSupported']}",
        "",
        "## Models",
        "",
        "| Model | Chat | Wire API | Reasoning accepted | Features |",
        "|---|---|---|---|---|",
    ]
    for item in report["models"]:
        if item["classification"]["kind"] == "excluded":
            continue
        accepted = [level for level, value in item["reasoning"]["levels"].items() if value["status"] == "accepted"]
        features = ", ".join(f"{name}={value['status']}" for name, value in item.get("features", {}).items()) or "-"
        lines.append(f"| `{item['id']}` | {item['chat']['status']} | {item['chat'].get('wireApi', '-')} | {', '.join(accepted) or '-'} | {features} |")
    failures = [item for item in report["models"] if item["classification"]["kind"] == "chat" and item.get("chat", {}).get("status") != "accepted"]
    lines += ["", "## Unavailable or Anomalous Models", ""]
    if failures:
        lines += ["| Model | HTTP | Category | Reason | Retry |", "|---|---:|---|---|---|"]
        for item in failures:
            chat = item["chat"]
            failure = chat.get("failure", {})
            retry = "yes" if failure.get("category") in {"network_error", "temporary_unavailable"} else "no"
            lines.append(
                f"| `{item['id']}` | {chat.get('httpStatus', '-')} | `{failure.get('category', 'unknown_error')}` | {failure.get('reason', 'The gateway did not accept this capability probe.')} | {retry} |"
            )
    else:
        lines.append("No chat candidates failed the probe.")
    lines += ["", "## Notes", "", "`plan` is not a model API capability and is not probed.", ""]
    return "\n".join(lines)


def _stderr_is_tty() -> bool:
    stream = typer.get_text_stream("stderr")
    return bool(getattr(stream, "isatty", lambda: False)())


def _model_attempts(item: dict[str, Any]) -> int:
    attempts = int(item.get("chat", {}).get("attempts", 0))
    attempts += sum(int(value.get("attempts", 0)) for value in item.get("reasoning", {}).get("levels", {}).values())
    attempts += sum(int(value.get("attempts", 0)) for value in item.get("features", {}).values())
    return attempts


def _model_duration_ms(item: dict[str, Any]) -> int:
    duration = int(item.get("chat", {}).get("durationMs", 0))
    duration += sum(int(value.get("durationMs", 0)) for value in item.get("reasoning", {}).get("levels", {}).values())
    duration += sum(int(value.get("durationMs", 0)) for value in item.get("features", {}).values())
    return duration


def _verbose_line(item: dict[str, Any]) -> str:
    chat = item.get("chat", {})
    failure = chat.get("failure", {}).get("category", "-")
    return f"model={item['id']} status={chat.get('status', 'unknown')} chat={chat.get('wireApi', '-')} attempts={_model_attempts(item)} durationMs={_model_duration_ms(item)} failure={failure}"


def _progress(no_progress: bool) -> Progress | None:
    if no_progress or not _stderr_is_tty():
        return None
    return Progress(
        TextColumn("{task.description}"),
        BarColumn(),
        MofNCompleteColumn(),
        TimeElapsedColumn(),
        TimeRemainingColumn(),
        console=Console(file=typer.get_text_stream("stderr")),
    )


@cmd.callback(invoke_without_command=True)
def main(
    ctx: typer.Context,
    base_url: str = typer.Option(..., "--base-url", help="OpenAI-compatible LiteLLM 网关地址"),
    api_key: str = typer.Option(..., "--api-key", help="LiteLLM 网关 API key；不会写入报告"),
    concurrency: int = typer.Option(4, "--concurrency", min=1, help="并发探测模型数"),
    timeout: float = typer.Option(30.0, "--timeout", min=0.1, help="单次请求超时时间（秒）"),
    retries: int = typer.Option(2, "--retries", min=0, help="瞬态失败的重试次数"),
    wire_api: str = typer.Option("auto", "--wire-api", help="使用 auto、chat 或 responses"),
    reasoning_levels: str = typer.Option(",".join(DEFAULT_LEVELS), "--reasoning-levels", help="逗号分隔的 reasoning levels"),
    max_models: int | None = typer.Option(None, "--max-models", min=0, help="最多探测多少个聊天模型"),
    output_dir: Path = typer.Option(Path("model-capability-report"), "--output-dir", help="报告输出目录"),
    output_format: str = typer.Option("both", "--format", help="输出 json、md 或 both"),
    dry_run: bool = typer.Option(False, "--dry-run", help="只获取并分类模型，不发送能力探测请求"),
    verbose: bool = typer.Option(False, "--verbose", help="在 stderr 输出每个模型的探测摘要"),
    no_progress: bool = typer.Option(False, "--no-progress", help="关闭 TTY 中的动态进度条"),
    _: bool = typer.Option(False, "--version", "-v", "-V", callback=version_callback),
) -> None:
    if ctx.invoked_subcommand is not None:
        return
    if wire_api not in {"auto", "chat", "responses"}:
        raise typer.BadParameter("--wire-api must be auto, chat, or responses")
    if output_format not in {"json", "md", "both"}:
        raise typer.BadParameter("--format must be json, md, or both")
    levels = tuple(level.strip() for level in reasoning_levels.split(",") if level.strip())
    base_url = normalize_base_url(base_url)
    with httpx.Client() as client:
        models = fetch_models(client, base_url, api_key, timeout, retries)
        classified = [(model, classify_model(model)) for model in models]
        candidates = [model for model, classification in classified if classification["kind"] == "chat"]
        if max_models is not None:
            candidates = candidates[:max_models]
        if dry_run:
            probed = [
                {"id": model["id"], "classification": classification, "chat": {"status": "not_run"}, "reasoning": {"levels": {}}, "features": {}}
                for model, classification in classified
                if classification["kind"] == "chat"
            ]
            if verbose:
                for item in probed:
                    typer.echo(_verbose_line(item), err=True)
        else:
            with concurrent.futures.ThreadPoolExecutor(max_workers=concurrency) as pool:
                futures = {pool.submit(probe_model, client, model, base_url, api_key, wire_api, levels, timeout, retries): model["id"] for model in candidates}
                probed = []
                progress = _progress(no_progress)
                if progress is not None:
                    progress.start()
                    progress_task = progress.add_task("Probing models", total=len(futures))
                else:
                    progress_task = None
                try:
                    for future in concurrent.futures.as_completed(futures):
                        item = future.result()
                        probed.append(item)
                        if progress is not None and progress_task is not None:
                            progress.advance(progress_task)
                        if verbose:
                            typer.echo(_verbose_line(item), err=True)
                finally:
                    if progress is not None:
                        progress.stop()
    by_id = {item["id"]: item for item in probed}
    output_models = [
        by_id.get(model["id"], {"id": model["id"], "classification": classification, "chat": {"status": "excluded"}, "reasoning": {"levels": {}}, "features": {}})
        for model, classification in classified
    ]
    report = {
        "generatedAt": datetime.now(timezone.utc).isoformat(),
        "source": {"wireApi": wire_api, "concurrency": concurrency, "timeout": timeout, "reasoningLevels": list(levels)},
        "summary": {
            "listed": len(models),
            "excluded": len(models) - len(candidates),
            "chatCandidates": len(candidates),
            "chatSupported": sum(item.get("chat", {}).get("status") == "accepted" for item in probed),
        },
        "models": output_models,
    }
    output_dir.mkdir(parents=True, exist_ok=True)
    if output_format in {"json", "both"}:
        (output_dir / "model-capabilities.json").write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    if output_format in {"md", "both"}:
        (output_dir / "model-capabilities.md").write_text(markdown_report(report), encoding="utf-8")
    typer.echo(json.dumps(report["summary"], ensure_ascii=False))


if __name__ == "__main__":
    cmd()
