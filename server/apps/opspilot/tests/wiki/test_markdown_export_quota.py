"""markdown_export_service 配额与审计单元测试。

覆盖:
- 页面数 < max_pages:正常导出
- 页面数 > max_pages:抛 QuotaExceededError("max_pages")
- 内容 > max_bytes:抛 QuotaExceededError("max_bytes")
- max_pages=0 时:不抛错,空 zip
"""

from types import SimpleNamespace
from unittest.mock import patch

import pytest

from apps.opspilot.services.wiki import markdown_export_service as export_mod
from apps.opspilot.services.wiki.markdown_export_service import QuotaExceededError, build_markdown_export_zip


def _fake_page(id_, title="Page"):
    return SimpleNamespace(
        id=id_,
        title=title,
        current_version_id=1,
        current_version=SimpleNamespace(body="正文"),
        page_type="concept",
        status="active",
        contribution="ai",
        tags=[],
    )


def test_quota_max_pages_raises():
    """页面数 > max_pages:抛 QuotaExceededError("max_pages")。"""
    pages = [_fake_page(i) for i in range(3)]
    with patch.object(export_mod, "active_pages_for_export", return_value=pages):
        with pytest.raises(QuotaExceededError) as exc:
            build_markdown_export_zip(SimpleNamespace(id=1), max_pages=2, max_bytes=10 * 1024 * 1024)
    assert exc.value.code == "max_pages"
    assert "3" in exc.value.message and "2" in exc.value.message


def test_quota_max_bytes_raises():
    """内容 > max_bytes:抛 QuotaExceededError("max_bytes")。"""
    long_body = "x" * 200

    class FakePage:
        def __init__(self, id_, body):
            self.id = id_
            self.title = f"P{id_}"
            self.current_version_id = 1
            self.current_version = SimpleNamespace(body=body)
            self.page_type = "concept"
            self.status = "active"
            self.contribution = "ai"
            self.tags = []

    pages = [FakePage(1, long_body), FakePage(2, long_body)]
    # max_bytes 设到很小(< zip 头大小),确保抛错
    with patch.object(export_mod, "active_pages_for_export", return_value=pages):
        with pytest.raises(QuotaExceededError) as exc:
            build_markdown_export_zip(SimpleNamespace(id=1), max_pages=100, max_bytes=10)
    assert exc.value.code == "max_bytes"


def test_quota_within_limit_succeeds():
    """页面数 + 内容都在限制内:成功导出。"""
    pages = [_fake_page(i, f"Page {i}") for i in range(2)]
    with patch.object(export_mod, "active_pages_for_export", return_value=pages):
        content, count = build_markdown_export_zip(SimpleNamespace(id=1), max_pages=10, max_bytes=10 * 1024 * 1024)
    assert count == 2
    assert isinstance(content, bytes) and len(content) > 0


def test_default_quota_constants():
    """默认配额常量存在且为正数。"""
    assert export_mod.DEFAULT_MAX_EXPORT_PAGES > 0
    assert export_mod.DEFAULT_MAX_EXPORT_BYTES > 0
