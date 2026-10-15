import re
import threading
import time

from django.core.cache import cache
from langchain_core.runnables import RunnableConfig
from langchain_core.tools import tool

from apps.core.logger import opspilot_logger as logger
from apps.opspilot.models import WorkflowAttachmentAsset
from apps.opspilot.services.workflow_attachment_service import (
    build_attachment_bytes,
    build_signed_attachment_download_url,
    build_workflow_attachment_id,
    create_workflow_attachment_asset,
    lock_revision_attachment_type,
    normalize_attachment_file_type,
    version_attachment_filename,
)

_ATTACHMENT_RUN_LOCK = threading.Lock()
_ATTACHMENT_RUNS_STARTED: dict[str, float] = {}
_ATTACHMENT_RUN_TTL_SECONDS = 3600
_ATTACHMENT_RUN_CACHE_PREFIX = "opspilot:attachment-run:"
_ATTACHMENT_RUN_TOKEN_RE = re.compile(r"[^A-Za-z0-9_.:-]")


def _attachment_run_cache_key(token: str) -> str:
    safe = _ATTACHMENT_RUN_TOKEN_RE.sub("_", token)[:200]
    return f"{_ATTACHMENT_RUN_CACHE_PREFIX}{safe}"


def _purge_expired_attachment_runs(now: float) -> None:
    expired = [key for key, started in _ATTACHMENT_RUNS_STARTED.items() if now - started > _ATTACHMENT_RUN_TTL_SECONDS]
    for key in expired:
        _ATTACHMENT_RUNS_STARTED.pop(key, None)


def _claim_local_attachment_run(token: str) -> bool:
    now = time.monotonic()
    with _ATTACHMENT_RUN_LOCK:
        _purge_expired_attachment_runs(now)
        if token in _ATTACHMENT_RUNS_STARTED:
            return False
        _ATTACHMENT_RUNS_STARTED[token] = now
        return True


def _remember_attachment_run(token: str) -> None:
    now = time.monotonic()
    with _ATTACHMENT_RUN_LOCK:
        _purge_expired_attachment_runs(now)
        _ATTACHMENT_RUNS_STARTED[token] = now


def claim_attachment_run(token: str) -> bool:
    """同一轮只允许真正生成一次。

    非空 token 用 cache.add 做跨进程原子占位；共享缓存（Redis）下其他 worker 不能再次占位。
    缓存后端不落盘时降级为进程内字典，只保证本进程去重。空 token 无法跨进程识别，直接拒绝。
    """
    normalized = str(token or "").strip()
    if not normalized:
        logger.warning("attachment run claim rejected reason=empty_token")
        return False
    key = _attachment_run_cache_key(normalized)
    try:
        added = cache.add(key, "1", _ATTACHMENT_RUN_TTL_SECONDS)
        stored = cache.get(key) is not None
    except Exception as exc:
        logger.warning(
            "attachment run claim degraded backend=process_local error_type=%s",
            type(exc).__name__,
        )
        return _claim_local_attachment_run(normalized)
    if stored:
        if not added:
            return False
        _remember_attachment_run(normalized)
        return True
    logger.debug("attachment run claim degraded backend=process_local")
    return _claim_local_attachment_run(normalized)


def release_attachment_run(token: str) -> None:
    normalized = str(token or "").strip()
    if not normalized:
        return
    try:
        cache.delete(_attachment_run_cache_key(normalized))
    except Exception as exc:
        logger.warning(
            "attachment run claim release degraded error_type=%s",
            type(exc).__name__,
        )
    with _ATTACHMENT_RUN_LOCK:
        _ATTACHMENT_RUNS_STARTED.pop(normalized, None)


CONSTRUCTOR_PARAMS = []


@tool()
def generate_attachment_file(
    filename: str,
    content: str,
    file_type: str = "md",
    title: str = "",
    config: RunnableConfig = None,
) -> dict:
    """Generate a new downloadable file and return its download URL.

    Call this tool only when the user explicitly asks to generate, export, save, or write
    a new file, document, or report. Do not call it because the user mentioned a file,
    uploaded a file, or asked what an existing file contains. Answer those in text.

    After a successful call, briefly summarize what was generated. Do NOT paste the download
    URL, file:// links, /api/proxy paths, or placeholder tokens such as "加密token" into the
    chat or the file body; the UI renders the download button.

    When to call this tool:
    - User says "generate a report / write a file / export data / save as PDF" etc.
    - User wants new content delivered as a downloadable file rather than inline text.

    Parameters:
    - filename: Desired file name including extension (e.g. "report.md", "data.xlsx").
    - content:  Complete file content to save. For xlsx/csv pass raw data; for md/txt/pdf
                pass the full Markdown or plain-text body.
    - file_type: File format — "txt", "md", "pdf", "docx", "pptx", "xlsx", or "csv".
                 Defaults to "md". Use "txt" for a text file; do not substitute md.
                 Use "pptx" when the user asks for PPT/PowerPoint. Never downgrade pptx to docx.
    - title:    Optional document title used as a header in PDF/Word output.
    """

    configurable = (config or {}).get("configurable", {}) if isinstance(config, dict) else {}
    execution_id = str(configurable.get("execution_id", "") or "")
    source_node_id = str(configurable.get("node_id", "") or "")
    flow_id = str(configurable.get("flow_id", "") or "")
    created_by = str(configurable.get("user_id", "") or "")
    attachment_id = build_workflow_attachment_id(
        execution_id=execution_id,
        source_node_id=source_node_id,
        requested_attachment_id=str(configurable.get("attachment_id", "") or "").strip(),
    )

    history_priors = [str(name) for name in (configurable.get("prior_attachment_filenames") or []) if str(name).strip()]
    file_type, filename = lock_revision_attachment_type(file_type, filename, history_priors)
    normalized_type, normalized_filename, mime_type = normalize_attachment_file_type(file_type, filename)
    if configurable.get("attachment_versioning"):
        priors = list(history_priors)
        if execution_id:
            db_names = WorkflowAttachmentAsset.objects.filter(execution_id=execution_id).order_by("id").values_list("filename", flat=True)
            priors.extend(db_names)
        normalized_filename = version_attachment_filename(normalized_filename, priors)
    run_token = str(configurable.get("attachment_run_token") or "").strip()
    if not run_token:
        # 没有轮次 token 时无法做跨进程去重，仍生成文件，避免无 token 的直接调用被静默跳过。
        logger.warning(
            "attachment run claim skipped reason=empty_token execution_id=%s",
            execution_id,
        )
    elif not claim_attachment_run(run_token):
        return {
            "skipped": True,
            "message": "本轮已生成文件。同一次回复不要再生成第二个文件，也不要调用 request_user_choice。用户之后的新修改仍要重新生成。",
        }
    try:
        attachment_bytes = build_attachment_bytes(content=content, file_type=normalized_type, title=title or normalized_filename)
        asset = create_workflow_attachment_asset(
            execution_id=execution_id,
            attachment_id=attachment_id,
            filename=normalized_filename,
            content_bytes=attachment_bytes,
            mime_type=mime_type,
            source_node_id=source_node_id,
            flow_id=flow_id,
            created_by=created_by,
        )
    except Exception:
        release_attachment_run(run_token)
        raise
    return {
        "attachment_id": asset.attachment_id,
        "filename": asset.filename,
        "file_url": build_signed_attachment_download_url(asset),
        "mime_type": asset.mime_type,
        "attachment_asset_id": asset.id,
        "message": "文件已生成。同一次回复不要再生成第二个文件。用户下一条若要求修改，再生成一次。",
    }
