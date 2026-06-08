from __future__ import annotations

import base64
import uuid


def build_generated_file_download_event(*, filename: str, content_bytes: bytes, mime_type: str) -> dict[str, str]:
    return {
        "download_id": str(uuid.uuid4())[:8],
        "filename": filename,
        "content_base64": base64.b64encode(content_bytes).decode("utf-8"),
        "mime_type": mime_type,
    }
