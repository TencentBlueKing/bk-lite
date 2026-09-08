"""Bounded Ansible failure fields for callbacks and executor logs."""

import re
from typing import Any

FAILURE_TEXT_MAX_CHARS = 200
ANSIBLE_TASK_FAILED_LOG_TEMPLATE = (
    "event=ansible_task_failed task_id=%s task_type=%s error=%s "
    "host=%s host_status=%s exit_code=%s stderr=%s stderr_missing=%s "
    "failed_stage=ansible_execute error_type=%s"
)
_SECRET_ASSIGNMENT_RE = re.compile(
    r"(?i)\b(password|passwd|secret|token|authorization|passphrase|"
    r"private_key(?:_content)?)\s*[:=]\s*\S+"
)
_PEM_BLOCK_RE = re.compile(
    r"-----BEGIN [A-Z ]*PRIVATE KEY-----.*?-----END [A-Z ]*PRIVATE KEY-----",
    re.DOTALL,
)
_AUTH_FAILURE_MARKERS = (
    "permission denied",
    "authentication",
    "auth fail",
    "invalid user",
    "sshpass",
)
_UNREACHABLE_MARKERS = (
    "unreachable",
    "connection timed out",
    "connection refused",
    "no route to host",
    "name or service not known",
)


def sanitize_failure_text(value: Any, *, max_length: int = FAILURE_TEXT_MAX_CHARS) -> str:
    text = _PEM_BLOCK_RE.sub("[omitted]", str(value or ""))
    text = _SECRET_ASSIGNMENT_RE.sub(r"\1=[omitted]", text)
    text = text.replace("\r", " ").replace("\n", " ").strip()
    if len(text) > max_length:
        return text[:max_length]
    return text


def build_task_failure_summary(
    parsed_results: Any,
    *,
    error: str = "",
    exit_code: int | None = None,
) -> dict[str, Any]:
    summary: dict[str, Any] = {}
    items = parsed_results if isinstance(parsed_results, list) else []
    for item in items:
        if not isinstance(item, dict):
            continue
        status = str(item.get("status") or "")
        raw_status = str(item.get("raw_status") or status)
        if status == "success" or raw_status in {"SUCCESS", "CHANGED", "SKIPPED"}:
            continue
        host = str(item.get("host") or "").strip()
        if host:
            summary["failure_host"] = host[:255]
        if raw_status:
            summary["failure_status"] = sanitize_failure_text(raw_status, max_length=32)
        stderr = str(item.get("stderr") or item.get("error_message") or "")
        if stderr:
            summary["failure_stderr"] = sanitize_failure_text(stderr)
        break
    if exit_code not in (None, 0):
        summary["failure_exit_code"] = exit_code
    elif items:
        for item in items:
            if isinstance(item, dict) and item.get("exit_code") not in (None, 0, ""):
                summary["failure_exit_code"] = item.get("exit_code")
                break
    if "failure_stderr" not in summary and error:
        summary["failure_stderr"] = sanitize_failure_text(error)
    return summary


def classify_task_failure(summary: dict[str, Any], error: str = "") -> str:
    host_status = str(summary.get("failure_status") or "").upper()
    text = " ".join(
        str(part or "")
        for part in (error, summary.get("failure_stderr"), summary.get("failure_status"))
    ).lower()
    if host_status.startswith("UNREACHABLE"):
        return "target_unreachable"
    if any(marker in text for marker in _AUTH_FAILURE_MARKERS):
        return "authentication_failed"
    if any(marker in text for marker in _UNREACHABLE_MARKERS):
        return "target_unreachable"
    return "execution_failed"


def log_ansible_task_failed(
    logger,
    *,
    task_id: str,
    task_type: str,
    error: str,
    summary: dict[str, Any],
) -> None:
    sanitized_error = sanitize_failure_text(error)
    stderr = str(summary.get("failure_stderr") or "")
    exit_code = summary.get("failure_exit_code")
    logger.warning(
        ANSIBLE_TASK_FAILED_LOG_TEMPLATE,
        task_id,
        task_type,
        sanitized_error or "-",
        summary.get("failure_host") or "-",
        summary.get("failure_status") or "-",
        "-" if exit_code in (None, "") else exit_code,
        stderr or "-",
        not bool(stderr),
        classify_task_failure(summary, sanitized_error),
    )
