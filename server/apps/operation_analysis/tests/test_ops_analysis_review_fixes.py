"""评审要求的行为回归：短执行文案、pdf 错误码、邮件语言、NATS 日志。"""

from types import SimpleNamespace

import pytest
from django.utils import translation

from apps.operation_analysis.common.get_nats_source_data import NatsSourceError
from apps.operation_analysis.services.dashboard_report_renderer import (
    MAX_PDF_BYTES,
    PDF_GENERATE_FAILED_ERROR_CODE,
    PDF_TOO_LARGE_ERROR_CODE,
    DashboardPdfValidationError,
    DashboardRenderError,
    validate_pdf,
)
from apps.operation_analysis.services.user_messages import oa_message, override_for_creator
from apps.operation_analysis.views import datasource_view

pytestmark = pytest.mark.unit


def test_render_error_persists_short_message_and_keeps_detail_on_str():
    error = DashboardRenderError("Chromium 启动失败", error_code="chromium_launch_failed")
    assert str(error) == "Chromium 启动失败"
    assert error.persisted_message() == "报告 PDF 生成失败"
    assert "safe_message" not in error.__dict__

    with translation.override("en"):
        assert error.persisted_message() == "Failed to generate the report PDF"
        assert "Chromium" not in error.persisted_message()


def test_pdf_too_large_uses_explicit_code_not_translated_text():
    classified = DashboardPdfValidationError("The file is simply too big")
    assert classified.error_code == PDF_GENERATE_FAILED_ERROR_CODE
    assert classified.persisted_message() == "报告 PDF 校验失败"

    copied = DashboardPdfValidationError("PDF 文件超过 20 MB: 1 bytes")
    assert copied.error_code == PDF_GENERATE_FAILED_ERROR_CODE

    flagged = DashboardPdfValidationError("too big", error_code=PDF_TOO_LARGE_ERROR_CODE)
    assert flagged.error_code == "pdf_too_large"


def test_validate_pdf_marks_oversize_without_reading_the_sentence():
    path = SimpleNamespace(is_file=lambda: True, stat=lambda: SimpleNamespace(st_size=MAX_PDF_BYTES + 1))
    with translation.override("en"):
        with pytest.raises(DashboardPdfValidationError) as error:
            validate_pdf(path)
        assert error.value.error_code == PDF_TOO_LARGE_ERROR_CODE
        assert error.value.persisted_message() == "Report PDF validation failed"
        assert "20 MB" not in error.value.persisted_message()
        assert "20 MB" in str(error.value)


class _LocaleQuery:
    def __init__(self, row):
        self.row = row

    def filter(self, **kwargs):
        return self

    def only(self, *args):
        return self

    def first(self):
        return self.row


def test_mail_locale_follows_account_when_auth_user_locale_is_stale(monkeypatch):
    account = SimpleNamespace(locale="en")
    auth_user = SimpleNamespace(locale="zh-CN")

    class AccountUser:
        objects = _LocaleQuery(account)

    class AuthUser:
        objects = _LocaleQuery(auth_user)

    import apps.base.models as auth_models
    import apps.system_mgmt.models as account_models

    monkeypatch.setattr(account_models, "User", AccountUser)
    monkeypatch.setattr(auth_models, "User", AuthUser)

    with translation.override("zh-hans"):
        with override_for_creator("alice", "domain.com"):
            text = oa_message("messages.email_manual_line", "本次为手动测试发送，无计划周期。")
    assert text == "This is a manual test send with no schedule."


def test_nats_query_failure_log_includes_details(caplog):
    error = NatsSourceError(
        "namespace_server_missing",
        namespace_name="demo",
        namespace_id=9,
        path="monitor/query",
    )
    with caplog.at_level("ERROR", logger="operation_analysis"):
        datasource_view._log_source_query_failure(
            datasource_id=3,
            name="alerts",
            namespace="monitor",
            path="query",
            error=error,
        )
    assert any(
        "code=namespace_server_missing" in message
        and "namespace_name=demo" in message
        and "namespace_id=9" in message
        and "target_path=monitor/query" in message
        for message in caplog.messages
    )
    assert "namespace_server_missing" == str(error)
