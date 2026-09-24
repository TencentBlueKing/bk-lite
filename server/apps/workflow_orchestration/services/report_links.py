from __future__ import annotations

from typing import Any
from urllib.parse import urlencode

from django.conf import settings
from django.core import signing

REPORT_LINK_SALT = "workflow-orchestration.report-link.v1"
REPORT_LINK_TTL_SECONDS = 24 * 60 * 60


def build_report_download_link(*, artifact_id: str, execution_id: str, team: int) -> str:
    token = signing.dumps(
        {
            "artifact_id": str(artifact_id),
            "execution_id": str(execution_id),
            "team": int(team),
        },
        salt=REPORT_LINK_SALT,
        compress=True,
    )
    path = f"/workflow_orchestration/api/artifacts/shared/?{urlencode({'token': token})}"
    base = str(getattr(settings, "WEB_BASE_URL", "") or "").rstrip("/")
    return f"{base}{path}" if base else path


def read_report_download_link(token: str) -> dict[str, Any]:
    if not isinstance(token, str) or not token:
        raise ValueError("报告下载链接无效")
    try:
        payload = signing.loads(token, salt=REPORT_LINK_SALT, max_age=REPORT_LINK_TTL_SECONDS)
    except signing.SignatureExpired as error:
        raise ValueError("报告下载链接已过期") from error
    except signing.BadSignature as error:
        raise ValueError("报告下载链接无效") from error
    if (
        not isinstance(payload, dict)
        or not str(payload.get("artifact_id") or "")
        or not str(payload.get("execution_id") or "")
        or isinstance(payload.get("team"), bool)
        or not isinstance(payload.get("team"), int)
    ):
        raise ValueError("报告下载链接无效")
    return payload
