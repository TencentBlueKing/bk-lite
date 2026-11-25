from datetime import datetime, timezone
from types import SimpleNamespace

import fitz
import pytest

from apps.opspilot.services.history_analysis_pdf import render_analysis_pdf


@pytest.mark.parametrize(
    ("locale", "scope", "expected"),
    [
        ("cn", {"scope": "sessions", "channel_types": ["platform", "workflow"]}, "平台 / 编排中心"),
        ("en", {"scope": "range", "start": "2026-01-01", "end": "2026-01-02", "channel_types": ["workbench"]}, "Workbench"),
        ("cn", {"scope": "range", "start": "2026-01-01", "end": "2026-01-02", "channel_id": 17}, "渠道 #17"),
    ],
)
def test_report_scope_in_exported_pdf(locale, scope, expected):
    task = SimpleNamespace(
        name="报告",
        skill=SimpleNamespace(name="助手"),
        objective="overview",
        focus="",
        locale=locale,
        scope=scope,
        conversation_count=2,
        question_count=3,
        creator="alice",
        created_at=datetime.now(timezone.utc),
        findings=[],
    )
    with fitz.open(stream=render_analysis_pdf(task), filetype="pdf") as document:
        assert expected in "".join(page.get_text() for page in document)
