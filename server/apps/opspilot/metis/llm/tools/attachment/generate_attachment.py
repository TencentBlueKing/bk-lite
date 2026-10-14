import threading
import time

from langchain_core.runnables import RunnableConfig
from langchain_core.tools import tool

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


def claim_attachment_run(token: str) -> bool:
    """同一轮只允许真正生成一次。模型并行或反复调用时，后续调用直接跳过。"""
    if not token:
        return True
    now = time.monotonic()
    with _ATTACHMENT_RUN_LOCK:
        expired = [key for key, started in _ATTACHMENT_RUNS_STARTED.items() if now - started > _ATTACHMENT_RUN_TTL_SECONDS]
        for key in expired:
            _ATTACHMENT_RUNS_STARTED.pop(key, None)
        if token in _ATTACHMENT_RUNS_STARTED:
            return False
        _ATTACHMENT_RUNS_STARTED[token] = now
        return True


def release_attachment_run(token: str) -> None:
    if not token:
        return
    with _ATTACHMENT_RUN_LOCK:
        _ATTACHMENT_RUNS_STARTED.pop(token, None)


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
            priors.extend(WorkflowAttachmentAsset.objects.filter(execution_id=execution_id).values_list("filename", flat=True))
        normalized_filename = version_attachment_filename(normalized_filename, priors)
    run_token = str(configurable.get("attachment_run_token") or "")
    if not claim_attachment_run(run_token):
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
