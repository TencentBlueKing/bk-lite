"""OpsPilot 对话错误码要能按语言取到文案，超时文案保留秒数。"""

from apps.core.utils.loader import LanguageLoader

KEYS = (
    "error.message_required",
    "error.execution_id_required",
    "error.execution_not_found",
    "error.llm_timeout",
    "error.agent_execution_failed",
)


def test_chat_error_keys_exist_in_both_languages():
    zh = LanguageLoader(app="opspilot", default_lang="zh-Hans")
    en = LanguageLoader(app="opspilot", default_lang="en")
    for key in KEYS:
        zh_text = zh.get(key)
        en_text = en.get(key)
        assert isinstance(zh_text, str) and zh_text
        assert isinstance(en_text, str) and en_text
        assert zh_text != en_text


def test_llm_timeout_keeps_the_elapsed_seconds():
    text = LanguageLoader(app="opspilot", default_lang="zh-Hans").get("error.llm_timeout")
    assert text.format(seconds=30) == "智能体执行超时（>30s），请稍后重试"
    english = LanguageLoader(app="opspilot", default_lang="en").get("error.llm_timeout")
    assert "30" in english.format(seconds=30)
