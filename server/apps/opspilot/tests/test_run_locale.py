"""同线程先后使用不同页面语言时，后一轮不能读到上一轮的 locale。"""

import asyncio
import json
import threading
from contextlib import nullcontext
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest
from asgiref.sync import ThreadSensitiveContext, sync_to_async

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


@pytest.mark.parametrize("request_context", [False, True])
@pytest.mark.parametrize("fail_first", [False, True])
def test_invoke_chat_from_sync_bridge_can_run_async_middleware(monkeypatch, request_context, fail_first):
    """NATS 等异步入口的同步调用不得把执行器占用状态带入 Agent 线程。"""
    from apps.opspilot.metis.llm.middleware.conversation_skill_package import ConversationSkillPackageMiddleware
    from apps.opspilot.metis.llm.tools.kubernetes import cluster
    from apps.opspilot.services import chat_service as chat_service_module
    from nats_client.utils import database_sync_to_async

    seen = []
    executor_threads = []
    monkeypatch.setenv("AGENT_EXECUTE_TIMEOUT", "1")
    core = MagicMock()
    core.api_client.call_api.return_value = ({"gitVersion": "v1.28.0", "platform": "linux/amd64"},)
    monkeypatch.setattr(cluster, "prepare_context", lambda config: None)
    monkeypatch.setattr(cluster.client, "CoreV1Api", lambda: core)

    class _Graph:
        async def execute(self, _request):
            seen.append(get_run_locale())
            executor_thread = await sync_to_async(threading.current_thread, thread_sensitive=True)()
            executor_threads.append(executor_thread)
            result = await ConversationSkillPackageMiddleware().aafter_model({"messages": []}, SimpleNamespace())
            assert result is None
            tool_result = await cluster.verify_kubernetes_connection.ainvoke({})
            assert await sync_to_async(threading.current_thread, thread_sensitive=True)() is executor_thread
            if fail_first and get_run_locale() == "zh-Hans":
                raise RuntimeError("graph failed after tool")
            return _chat_result(tool_result)

    monkeypatch.setattr(chat_service_module.LLMModel.objects, "get", lambda *args, **kwargs: SimpleNamespace(id=1))
    monkeypatch.setattr(
        ChatService,
        "format_chat_server_kwargs",
        staticmethod(lambda kwargs, _model: ({"locale": kwargs.get("locale") or "en"}, {}, {})),
    )
    monkeypatch.setattr(chat_service_module, "create_agent_instance", lambda *_args: (_Graph(), SimpleNamespace()))

    async def run():
        async with ThreadSensitiveContext() if request_context else nullcontext():
            for locale in ("zh-Hans", "en"):
                result, _, _ = await database_sync_to_async(ChatService.invoke_chat, thread_sensitive=True)(
                    {"llm_model": 1, "skill_type": "test", "locale": locale}
                )
                if fail_first and locale == "zh-Hans":
                    assert result["success"] is False
                    assert result["error_type"] == "RuntimeError"
                    assert result["error"] == "graph failed after tool"
                else:
                    assert result["success"] is True, result
                    assert json.loads(result["message"])["connection_status"] == "成功"
                assert get_run_locale() == "en"

    asyncio.run(run())
    assert seen == ["zh-Hans", "en"]
    assert core.list_namespace.call_count == 2
    assert len(executor_threads) == 2
    assert all(not thread.is_alive() for thread in executor_threads)


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
