from types import SimpleNamespace

from apps.opspilot.utils.returned_message_gap_pairs import GAP_PAIRS
from apps.opspilot.utils.returned_message_more_pairs import MORE_PAIRS
from apps.opspilot.utils.returned_message_pairs import PAIRS
from apps.opspilot.utils.returned_messages import localize_embedded_text, localize_returned_text


def test_exact_english():
    loader = SimpleNamespace(default_lang="en")
    assert localize_returned_text("供应商不能为空", loader) == "Vendor is required"


def test_chinese_locale_keeps_original():
    loader = SimpleNamespace(default_lang="zh-Hans")
    assert localize_returned_text("供应商不能为空", loader) == "供应商不能为空"


def test_template_keeps_runtime_value():
    loader = SimpleNamespace(default_lang="en")
    text = localize_returned_text("不支持的维护阶段: rebuild", loader)
    assert text == "Unsupported maintenance stage: rebuild"


def test_unknown_sentence_stays_chinese():
    loader = SimpleNamespace(default_lang="en")
    assert localize_returned_text("Pod不存在", loader) == "Pod不存在"


def test_validation_field_prefix_is_translated():
    loader = SimpleNamespace(default_lang="en")
    assert localize_returned_text("vendor:供应商不能为空", loader) == "vendor:Vendor is required"


def test_embedded_sentence_inside_tool_result():
    loader = SimpleNamespace(default_lang="en")
    text = "检查结束。GitHub API认证失败，请检查token是否有效"
    assert localize_embedded_text(text, loader) == "检查结束。GitHub API authentication failed. Check that the token is valid"


def test_tool_result_middleware_translates_message():
    from langchain_core.messages import ToolMessage

    from apps.opspilot.metis.llm.middleware.tool_result_locale import _localize_result

    message = ToolMessage(content="replicas 必须是整数", tool_call_id="1", name="scale")
    translated = _localize_result(message, "en")
    assert translated.content == "replicas must be an integer"
    assert _localize_result(message, "zh-Hans").content == "replicas 必须是整数"


def test_channel_reply_uses_page_language():
    en = SimpleNamespace(default_lang="en")
    zh = SimpleNamespace(default_lang="zh-Hans")
    assert localize_returned_text("未登录", en) == "Not signed in"
    assert localize_returned_text("未登录", zh) == "未登录"
    assert localize_returned_text("不支持的渠道类型: feishu", en) == "Unsupported channel type: feishu"
    assert localize_returned_text("渠道不存在或已下线", en) == "渠道不存在或已下线"


def test_every_template_can_be_formatted():
    loader = SimpleNamespace(default_lang="en")
    for zh, _en in (*PAIRS, *GAP_PAIRS, *MORE_PAIRS):
        if "{" not in zh:
            continue
        sample = zh
        while "{" in sample:
            start = sample.find("{")
            end = sample.find("}", start)
            sample = sample[:start] + "X" + sample[end + 1 :]
        translated = localize_returned_text(sample, loader)
        assert translated != sample
        assert "{" not in translated
