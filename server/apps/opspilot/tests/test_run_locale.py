"""同线程先后使用不同页面语言时，后一轮不能读到上一轮的 locale。"""

import asyncio
from types import SimpleNamespace

from apps.opspilot.services.chat_service import ChatService
from apps.opspilot.utils.run_locale import get_run_locale, reset_run_locale, set_run_locale


def _chat_result(message="ok"):
    return SimpleNamespace(
        message=message,
        total_tokens=0,
        prompt_tokens=0,
        completion_tokens=0,
        llm_call_count=0,
        token_usage_calls=[],
        finish_reason="stop",
        output_truncated=False,
        browser_steps=[],
    )


def test_same_thread_locales_do_not_leak():
    assert get_run_locale() == "en"
    token = set_run_locale("zh-Hans")
    try:
        assert get_run_locale() == "zh-Hans"
        raise RuntimeError("stop")
    except RuntimeError:
        pass
    finally:
        reset_run_locale(token)
    assert get_run_locale() == "en"

    token = set_run_locale("zh-Hant")
    try:
        assert get_run_locale() == "zh-Hant"
    finally:
        reset_run_locale(token)
    assert get_run_locale() == "en"


def test_invoke_chat_locales_do_not_leak_on_the_same_thread(monkeypatch):
    seen = []

    class _Graph:
        async def execute(self, _request):
            seen.append(get_run_locale())
            return _chat_result()

    from apps.opspilot.services import chat_service as chat_service_module

    monkeypatch.setattr(chat_service_module.LLMModel.objects, "get", lambda *args, **kwargs: SimpleNamespace(id=1))
    monkeypatch.setattr(
        chat_service_module.ChatService,
        "format_chat_server_kwargs",
        staticmethod(lambda kwargs, _model: ({"locale": kwargs.get("locale") or "en"}, {}, {})),
    )
    monkeypatch.setattr(
        chat_service_module,
        "create_agent_instance",
        lambda _skill_type, _chat_kwargs: (_Graph(), SimpleNamespace()),
    )

    first, _, _ = ChatService.invoke_chat({"llm_model": 1, "skill_type": "test", "locale": "zh-Hans"})
    assert first["success"] is True
    assert get_run_locale() == "en"

    second, _, _ = ChatService.invoke_chat({"llm_model": 1, "skill_type": "test", "locale": "zh-Hant"})
    assert second["success"] is True
    assert seen == ["zh-Hans", "zh-Hant"]
    assert get_run_locale() == "en"


def test_invoke_chat_resets_locale_when_agent_setup_fails(monkeypatch):
    from apps.opspilot.services import chat_service as chat_service_module

    monkeypatch.setattr(chat_service_module.LLMModel.objects, "get", lambda *args, **kwargs: SimpleNamespace(id=1))
    monkeypatch.setattr(
        chat_service_module.ChatService,
        "format_chat_server_kwargs",
        staticmethod(lambda kwargs, _model: ({"locale": kwargs.get("locale") or "en"}, {}, {})),
    )

    def _boom(_skill_type, _chat_kwargs):
        raise RuntimeError("agent setup failed")

    monkeypatch.setattr(chat_service_module, "create_agent_instance", _boom)

    failed, _, _ = ChatService.invoke_chat({"llm_model": 1, "skill_type": "test", "locale": "zh-Hans"})
    assert failed["success"] is False
    assert get_run_locale() == "en"

    seen = []

    class _Graph:
        async def execute(self, _request):
            seen.append(get_run_locale())
            return _chat_result()

    monkeypatch.setattr(
        chat_service_module,
        "create_agent_instance",
        lambda _skill_type, _chat_kwargs: (_Graph(), SimpleNamespace()),
    )
    followed, _, _ = ChatService.invoke_chat({"llm_model": 1, "skill_type": "test", "locale": "en"})
    assert followed["success"] is True
    assert seen == ["en"]
    assert get_run_locale() == "en"


def test_agui_and_sse_streams_do_not_leak_locale(monkeypatch):
    from apps.opspilot.utils import agui_chat, sse_chat

    seen = []

    class _Graph:
        async def agui_stream(self, _request, **_kwargs):
            seen.append(get_run_locale())
            if False:
                yield ""

    monkeypatch.setattr(agui_chat, "_prepare_agui_chat_kwargs", lambda params: {"locale": params.get("locale")})
    monkeypatch.setattr(agui_chat, "create_agent_instance", lambda *_args, **_kwargs: (_Graph(), SimpleNamespace(extra_config={})))
    monkeypatch.setattr(sse_chat, "_prepare_stream_prerequisites", lambda params: ("basic", {"locale": params.get("locale")}))
    monkeypatch.setattr(sse_chat, "create_agent_instance", lambda *_args, **_kwargs: (_Graph(), SimpleNamespace()))

    async def _agui(locale):
        gen = agui_chat._generate_agui_stream(
            {"locale": locale, "llm_model": 1},
            "skill",
            "basic",
            False,
            {"content": []},
            {},
            "127.0.0.1",
            "hi",
            None,
            None,
        )
        async for _line in gen:
            pass

    async def _sse(locale):
        gen = sse_chat.create_stream_generator(
            {"locale": locale, "llm_model": 1, "show_think": False},
            "skill",
            {},
            "127.0.0.1",
            "hi",
        )
        async for _line in gen:
            pass

    async def _run():
        await _agui("zh-Hans")
        assert get_run_locale() == "en"
        await _agui("zh-Hant")
        assert get_run_locale() == "en"
        await _sse("zh-Hans")
        assert get_run_locale() == "en"
        await _sse("en")
        assert get_run_locale() == "en"

    asyncio.run(_run())
    assert seen == ["zh-Hans", "zh-Hant", "zh-Hans", "en"]
    assert get_run_locale() == "en"
