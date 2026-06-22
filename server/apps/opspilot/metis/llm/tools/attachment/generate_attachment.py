from langchain_core.runnables import RunnableConfig
from langchain_core.tools import tool

from apps.opspilot.services.workflow_attachment_service import (
    build_attachment_bytes,
    build_signed_attachment_download_url,
    build_workflow_attachment_id,
    create_workflow_attachment_asset,
    normalize_attachment_file_type,
)

CONSTRUCTOR_PARAMS = []


@tool()
def generate_attachment_file(
    filename: str,
    content: str,
    file_type: str = "md",
    title: str = "",
    config: RunnableConfig = None,
) -> dict:
    """Generate a downloadable file attachment and return its download URL.

    **IMPORTANT: You MUST call this tool whenever the user asks to generate, create, produce,
    save, or export any file, document, report, or attachment — regardless of file format.**

    Do NOT output file content as plain text in your response. Always use this tool so the
    user receives a downloadable link. After calling this tool, briefly summarize what was
    generated and present the returned download URL to the user.

    When to call this tool:
    - User says "generate a report / create a file / export data / save as PDF" etc.
    - User wants any content delivered as a downloadable file rather than inline text.

    Parameters:
    - filename: Desired file name including extension (e.g. "report.md", "data.xlsx").
    - content:  Complete file content to save. For xlsx/csv pass raw data; for md/txt/pdf
                pass the full Markdown or plain-text body.
    - file_type: File format — "md", "pdf", "xlsx", "docx", "txt", "csv", "html", etc.
                 Defaults to "md" (Markdown).
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

    normalized_type, normalized_filename, mime_type = normalize_attachment_file_type(file_type, filename)
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
    return {
        "attachment_id": asset.attachment_id,
        "filename": asset.filename,
        "file_url": build_signed_attachment_download_url(asset),
        "mime_type": asset.mime_type,
        "file_knowledge_id": asset.file_knowledge_id,
    }
