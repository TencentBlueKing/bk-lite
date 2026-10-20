from apps.core.exceptions.base_app_exception import BaseAppException
from apps.module_link.services.row_message import item_message, safe_exc_text


def test_safe_exc_text_keeps_base_app_message():
    text = "organization [2, 4] 不在当前选择组织范围内"
    assert safe_exc_text(BaseAppException(text)) == text


def test_safe_exc_text_drops_runtime_error_body():
    secret = "SECRET-PAYLOAD-DO-NOT-LOG"
    assert safe_exc_text(RuntimeError(secret)) == ""
    assert secret not in item_message(stage="create_ci", exc=RuntimeError(secret))


def test_item_message_prefers_business_exception():
    assert item_message(stage="create_ci", exc=BaseAppException("cloud 必填")) == "cloud 必填"


def test_item_message_falls_back_to_stage_sentence():
    assert item_message(stage="create_ci", exc=RuntimeError("boom")) == "新建配置项失败"
    assert item_message(stage="unauthorized") == "没有这条实例的操作权限"
    assert item_message(stage="host_missing_ip") == "主机缺少 IP，无法新建"
    assert item_message(stage="missing_org") == "当前组织范围内没有可用的所属组织"
    assert item_message(stage="missing_name") == "实例名为空，无法新建"
    assert item_message(stage="unknown-stage") == ""


def test_item_message_strips_newlines_and_limits_length():
    text = "a\r\nb" + "x" * 300
    out = item_message(exc=BaseAppException(text))
    assert "\n" not in out
    assert "\r" not in out
    assert len(out) == 240
    assert out.startswith("a b")
    assert "  " not in out
