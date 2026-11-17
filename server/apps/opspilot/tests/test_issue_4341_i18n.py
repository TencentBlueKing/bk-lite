"""OpsPilot 对话错误码要能按语言取到文案，超时文案保留秒数。"""

import concurrent.futures
from types import SimpleNamespace

from apps.core.utils.loader import LanguageLoader
from apps.opspilot.services.chat_service import ChatService
from apps.opspilot.utils.run_locale import get_run_locale

KEYS = (
    "error.message_required",
    "error.execution_id_required",
    "error.execution_not_found",
    "error.llm_timeout",
    "error.agent_execution_failed",
)

ZH_TIMEOUT = "智能体执行超时（>30s），请稍后重试"
ZH_EXECUTION_FAILED = "智能体执行失败"


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
    assert text.format(seconds=30) == ZH_TIMEOUT
    english = LanguageLoader(app="opspilot", default_lang="en").get("error.llm_timeout")
    assert "30" in english.format(seconds=30)
    assert english.format(seconds=30) != ZH_TIMEOUT


def _prepare_invoke(monkeypatch, *, create_agent):
    from apps.opspilot.services import chat_service as chat_service_module

    monkeypatch.setattr(chat_service_module, "_resolve_agent_execute_timeout", lambda: 30)
    monkeypatch.setattr(chat_service_module, "_is_eventlet_environment", lambda: False)
    monkeypatch.setattr(chat_service_module.LLMModel.objects, "get", lambda *args, **kwargs: SimpleNamespace(id=1))
    monkeypatch.setattr(
        chat_service_module.ChatService,
        "format_chat_server_kwargs",
        staticmethod(lambda kwargs, _model: ({"locale": kwargs.get("locale") or "en"}, {}, {})),
    )
    monkeypatch.setattr(chat_service_module, "create_agent_instance", create_agent)


def _raise_timeout(*_args, **_kwargs):
    raise concurrent.futures.TimeoutError()


def _raise_execution_failed(*_args, **_kwargs):
    raise RuntimeError("agent setup failed")


def test_invoke_chat_timeout_follows_call_locale(monkeypatch):
    _prepare_invoke(monkeypatch, create_agent=_raise_timeout)

    chinese, _, _ = ChatService.invoke_chat({"llm_model": 1, "skill_type": "test", "locale": "zh-Hans"})
    assert chinese["success"] is False
    assert chinese["error_type"] == "TimeoutError"
    assert chinese["message"] == ZH_TIMEOUT
    assert get_run_locale() == "en"

    english, _, _ = ChatService.invoke_chat({"llm_model": 1, "skill_type": "test", "locale": "en"})
    assert english["success"] is False
    assert "30" in english["message"]
    assert english["message"] != ZH_TIMEOUT
    assert get_run_locale() == "en"

    missing, _, _ = ChatService.invoke_chat({"llm_model": 1, "skill_type": "test"})
    assert "30" in missing["message"]
    assert missing["message"] != ZH_TIMEOUT
    assert missing["message"] == english["message"]


def test_invoke_chat_execution_failed_follows_call_locale(monkeypatch):
    _prepare_invoke(monkeypatch, create_agent=_raise_execution_failed)

    chinese, _, _ = ChatService.invoke_chat({"llm_model": 1, "skill_type": "test", "locale": "zh-Hans"})
    assert chinese["success"] is False
    assert chinese["message"] == ZH_EXECUTION_FAILED
    assert "agent setup failed" not in chinese["message"]
    assert get_run_locale() == "en"

    english, _, _ = ChatService.invoke_chat({"llm_model": 1, "skill_type": "test", "locale": "en"})
    assert english["message"] == "Agent execution failed"
    assert english["message"] != ZH_EXECUTION_FAILED

    missing, _, _ = ChatService.invoke_chat({"llm_model": 1, "skill_type": "test"})
    assert missing["message"] == english["message"]


def test_invoke_chat_timeout_keeps_template_when_format_fails(monkeypatch):
    from apps.opspilot.services import chat_service as chat_service_module

    _prepare_invoke(monkeypatch, create_agent=_raise_timeout)
    monkeypatch.setattr(
        chat_service_module.LanguageLoader,
        "get",
        lambda self, key, default=None: "{seconds" if key == "error.llm_timeout" else default,
    )

    result, _, _ = ChatService.invoke_chat({"llm_model": 1, "skill_type": "test", "locale": "zh-Hans"})
    assert result["message"] == "{seconds"
