import pydantic.root_model  # noqa

import asyncio

import pytest
from django.core.cache import cache

from apps.opspilot.metis.llm.agent.chatbot_workflow import ChatBotWorkflowGraph, ChatBotWorkflowRequest
from apps.opspilot.metis.llm.agent.lats_agent import LatsAgentGraph, LatsAgentRequest
from apps.opspilot.metis.llm.agent.plan_and_execute_agent import PlanAndExecuteAgentGraph, PlanAndExecuteAgentRequest
from apps.opspilot.metis.llm.agent.react_agent import ReActAgentGraph, ReActAgentRequest
from apps.opspilot.models import SkillTypeChoices
from apps.opspilot.services import approval as approval_svc
from apps.opspilot.utils import agent_factory

pytestmark = pytest.mark.django_db


@pytest.fixture(autouse=True)
def real_locmem_cache(settings, use_dummy_cache_backend):
    """The global autouse fixture swaps in DummyCache (drops all writes).

    Approval logic genuinely round-trips through django cache, so override it
    with a real in-process LocMemCache. Depending on use_dummy_cache_backend
    guarantees this runs *after* it, winning the last write to settings.CACHES.
    LocMemCache is process-global, so it is also visible across threads (used
    by the polling test).
    """
    settings.CACHES = {
        "default": {
            "BACKEND": "django.core.cache.backends.locmem.LocMemCache",
            "LOCATION": "approval-test",
        }
    }
    cache.clear()
    yield
    cache.clear()


# ---------------------------------------------------------------------------
# services/approval.py  — real django cache, pure signal logic
# ---------------------------------------------------------------------------


class TestApprovalCacheKey:
    def test_key_structure(self):
        key = approval_svc._get_approval_cache_key("exec1", "node2", "call3")
        assert key == "approval:exec1:node2:call3"

    def test_key_uses_prefix_constant(self):
        key = approval_svc._get_approval_cache_key("e", "n", "t")
        assert key.startswith(approval_svc.APPROVAL_CACHE_PREFIX + ":")


class TestSubmitGetClear:
    def setup_method(self):
        cache.clear()

    def test_submit_then_get_roundtrip(self):
        payload = approval_svc.submit_approval_decision(
            "e1", "n1", "c1", "approve", reason="looks safe", decided_by="alice"
        )
        # payload returned contains decision + reason + decided_by + decided_at(ms)
        assert payload["decision"] == "approve"
        assert payload["reason"] == "looks safe"
        assert payload["decided_by"] == "alice"
        assert isinstance(payload["decided_at"], int) and payload["decided_at"] > 0

        fetched = approval_svc.get_approval_decision("e1", "n1", "c1")
        assert fetched == payload

    def test_get_missing_returns_none(self):
        assert approval_svc.get_approval_decision("nope", "nope", "nope") is None

    def test_clear_removes_decision(self):
        approval_svc.submit_approval_decision("e2", "n2", "c2", "reject")
        assert approval_svc.get_approval_decision("e2", "n2", "c2") is not None
        approval_svc.clear_approval_decision("e2", "n2", "c2")
        assert approval_svc.get_approval_decision("e2", "n2", "c2") is None

    def test_submit_defaults(self):
        payload = approval_svc.submit_approval_decision("e3", "n3", "c3", "reject")
        assert payload["reason"] == ""
        assert payload["decided_by"] == ""


class TestWaitForApprovalUnattended:
    """无人值守分支：立即返回，不轮询。"""

    def setup_method(self):
        cache.clear()

    def _run(self, **kwargs):
        return asyncio.run(approval_svc.wait_for_approval("e", "n", "c", **kwargs))

    def test_unattended_allow(self):
        res = self._run(trigger_type="unattended", unattended_strategy="allow")
        assert res["decision"] == "approve"
        assert res["source"] == "auto"

    def test_unattended_deny(self):
        res = self._run(trigger_type="unattended", unattended_strategy="deny")
        assert res["decision"] == "reject"
        assert res["source"] == "auto"

    def test_unattended_skip_default(self):
        res = self._run(trigger_type="unattended", unattended_strategy="skip")
        assert res["decision"] == "skip"
        assert res["source"] == "auto"


class TestWaitForApprovalInteractive:
    def setup_method(self):
        cache.clear()

    def test_returns_user_decision_when_present(self):
        # Pre-populate a decision so the very first poll succeeds.
        approval_svc.submit_approval_decision("ei", "ni", "ci", "approve", reason="ok", decided_by="bob")
        res = asyncio.run(
            approval_svc.wait_for_approval(
                "ei", "ni", "ci", timeout_seconds=5, poll_interval=0.01, trigger_type="interactive"
            )
        )
        assert res["decision"] == "approve"
        assert res["reason"] == "ok"
        assert res["source"] == "user"
        assert res["decided_by"] == "bob"
        # decision must be consumed (cleared) after read
        assert approval_svc.get_approval_decision("ei", "ni", "ci") is None

    def test_timeout_fallback_skip(self):
        res = asyncio.run(
            approval_svc.wait_for_approval(
                "et", "nt", "ct", timeout_seconds=0, poll_interval=0.01, trigger_type="interactive",
                timeout_fallback="skip",
            )
        )
        assert res["decision"] == "skip"
        assert res["source"] == "timeout"

    def test_timeout_fallback_deny(self):
        res = asyncio.run(
            approval_svc.wait_for_approval(
                "et2", "nt2", "ct2", timeout_seconds=0, poll_interval=0.01, trigger_type="interactive",
                timeout_fallback="deny",
            )
        )
        assert res["decision"] == "reject"
        assert res["source"] == "timeout"

    def test_timeout_fallback_allow(self):
        res = asyncio.run(
            approval_svc.wait_for_approval(
                "et3", "nt3", "ct3", timeout_seconds=0, poll_interval=0.01, trigger_type="interactive",
                timeout_fallback="allow",
            )
        )
        assert res["decision"] == "approve"
        assert res["source"] == "timeout"

    def test_polls_until_decision_appears(self):
        # Inject a decision shortly after wait starts, on a background thread,
        # to exercise the polling loop (not just the first-iteration shortcut).
        import threading
        import time

        def inject():
            time.sleep(0.05)
            approval_svc.submit_approval_decision("ep", "np", "cp", "reject", reason="late")

        t = threading.Thread(target=inject)
        t.start()
        try:
            res = asyncio.run(
                approval_svc.wait_for_approval(
                    "ep", "np", "cp", timeout_seconds=5, poll_interval=0.02, trigger_type="interactive"
                )
            )
        finally:
            t.join()
        assert res["decision"] == "reject"
        assert res["reason"] == "late"
        assert res["source"] == "user"


# ---------------------------------------------------------------------------
# utils/agent_factory.py
# ---------------------------------------------------------------------------


class TestCreateAgentInstance:
    def test_basic_tool(self):
        graph, request = agent_factory.create_agent_instance(SkillTypeChoices.BASIC_TOOL, {})
        assert isinstance(graph, ReActAgentGraph)
        assert isinstance(request, ReActAgentRequest)

    def test_plan_execute(self):
        graph, request = agent_factory.create_agent_instance(SkillTypeChoices.PLAN_EXECUTE, {})
        assert isinstance(graph, PlanAndExecuteAgentGraph)
        assert isinstance(request, PlanAndExecuteAgentRequest)

    def test_lats(self):
        graph, request = agent_factory.create_agent_instance(SkillTypeChoices.LATS, {})
        assert isinstance(graph, LatsAgentGraph)
        assert isinstance(request, LatsAgentRequest)

    def test_default_falls_back_to_chatbot(self):
        # KNOWLEDGE_TOOL (and any unrecognized) → ChatBot workflow default branch
        graph, request = agent_factory.create_agent_instance(SkillTypeChoices.KNOWLEDGE_TOOL, {})
        assert isinstance(graph, ChatBotWorkflowGraph)
        assert isinstance(request, ChatBotWorkflowRequest)

    def test_kwargs_passed_into_request(self):
        graph, request = agent_factory.create_agent_instance(
            SkillTypeChoices.BASIC_TOOL, {"user_message": "hello", "temperature": 0.1}
        )
        assert request.user_message == "hello"
        assert request.temperature == 0.1


class TestNormalizeLlmErrorMessage:
    @pytest.mark.parametrize(
        "raw, expected_substr",
        [
            ("HTTP Error code: 502 bad gateway", "502"),
            ("Error code: 503 overloaded", "503"),
            ("Error code: 504 timed out", "504"),
            ("Error code: 401 unauthorized", "401"),
            ("Error code: 429 too many", "429"),
        ],
    )
    def test_openai_error_codes(self, raw, expected_substr):
        out = agent_factory.normalize_llm_error_message(raw)
        assert expected_substr in out
        assert out != f"流式处理错误: {raw}"

    def test_anthropic_authentication_error(self):
        out = agent_factory.normalize_llm_error_message("authentication_error: bad key")
        assert "Anthropic" in out and "密钥" in out

    def test_anthropic_invalid_x_api_key(self):
        out = agent_factory.normalize_llm_error_message("invalid x-api-key supplied")
        assert "Anthropic" in out

    def test_anthropic_rate_limit(self):
        out = agent_factory.normalize_llm_error_message("rate_limit_error occurred")
        assert "频率超限" in out

    def test_anthropic_overloaded(self):
        out = agent_factory.normalize_llm_error_message("overloaded_error here")
        assert "过载" in out

    def test_anthropic_invalid_request_includes_original(self):
        raw = "invalid_request_error: missing field"
        out = agent_factory.normalize_llm_error_message(raw)
        assert raw in out

    def test_connection_branch_includes_original(self):
        raw = "Connection refused by host"
        out = agent_factory.normalize_llm_error_message(raw)
        assert "连接失败" in out and raw in out

    def test_timeout_branch(self):
        out = agent_factory.normalize_llm_error_message("request timeout reached")
        assert "连接失败" in out

    def test_fallback_branch(self):
        raw = "some totally unknown failure"
        out = agent_factory.normalize_llm_error_message(raw)
        assert out == f"流式处理错误: {raw}"


class TestCreateSseResponseHeaders:
    def test_headers_contract(self):
        headers = agent_factory.create_sse_response_headers()
        assert headers["Cache-Control"] == "no-cache, no-store, must-revalidate"
        assert headers["X-Accel-Buffering"] == "no"
        assert headers["Transfer-Encoding"] == "chunked"
        assert headers["Access-Control-Allow-Origin"] == "*"
        assert headers["Expires"] == "0"


class TestRunAsyncGeneratorInLoop:
    def test_yields_all_items_in_order(self):
        async def gen():
            for i in range(3):
                yield f"chunk-{i}"

        results = list(agent_factory.run_async_generator_in_loop(gen))
        assert results == ["chunk-0", "chunk-1", "chunk-2"]

    def test_empty_generator(self):
        async def gen():
            if False:
                yield "never"

        results = list(agent_factory.run_async_generator_in_loop(gen))
        assert results == []


class TestCreateAsyncWrapperForSyncGenerator:
    def test_wraps_sync_generator(self):
        def sync_gen():
            yield "a"
            yield "b"
            yield "c"

        async def collect():
            out = []
            async for chunk in agent_factory.create_async_wrapper_for_sync_generator(sync_gen()):
                out.append(chunk)
            return out

        assert asyncio.run(collect()) == ["a", "b", "c"]

    def test_wraps_empty_sync_generator(self):
        def sync_gen():
            return
            yield  # pragma: no cover

        async def collect():
            out = []
            async for chunk in agent_factory.create_async_wrapper_for_sync_generator(sync_gen()):
                out.append(chunk)
            return out

        assert asyncio.run(collect()) == []
