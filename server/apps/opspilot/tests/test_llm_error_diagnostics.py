import pytest

from apps.opspilot.metis.llm.common.llm_error_diagnostics import (
    LLM_ERROR_AUTH,
    LLM_ERROR_BLOCKED,
    LLM_ERROR_EMPTY,
    LLM_ERROR_TIMEOUT,
    LLM_ERROR_UNREACHABLE,
    classify_llm_error,
    format_llm_empty_response_log,
    format_llm_failure_log,
    summarize_llm_endpoint,
)


def test_classify_llm_error_detects_unreachable_connection_refused():
    exc = ConnectionRefusedError("Connection refused")
    result = classify_llm_error(exc)
    assert result["code"] == LLM_ERROR_UNREACHABLE
    assert result["unreachable"] is True
    assert "无法连接" in result["user_message"]


def test_classify_llm_error_detects_api_connection_error_by_type_name():
    class APIConnectionError(Exception):
        pass

    result = classify_llm_error(APIConnectionError("Failed to connect to host"))
    assert result["code"] == LLM_ERROR_UNREACHABLE
    assert result["unreachable"] is True


def test_classify_llm_error_detects_timeout():
    result = classify_llm_error(TimeoutError("Request timed out after 300s"))
    assert result["code"] == LLM_ERROR_TIMEOUT
    assert result["unreachable"] is False


def test_classify_llm_error_detects_auth_status():
    class AuthError(Exception):
        status_code = 401

    result = classify_llm_error(AuthError("Unauthorized"))
    assert result["code"] == LLM_ERROR_AUTH


def test_classify_llm_error_does_not_treat_waf_block_as_auth():
    class Forbidden(Exception):
        status_code = 403

    result = classify_llm_error(Forbidden("Error code: 403 - Your request was blocked."))
    assert result["code"] == LLM_ERROR_BLOCKED
    assert result["unreachable"] is False
    assert "鉴权失败" not in result["user_message"]
    assert "拦截" in result["user_message"]


def test_classify_llm_error_keeps_plain_403_as_auth():
    class Forbidden(Exception):
        status_code = 403

    result = classify_llm_error(Forbidden("Access denied"))
    assert result["code"] == LLM_ERROR_AUTH


def test_format_llm_failure_log_is_grep_friendly():
    classification = classify_llm_error(ConnectionError("connection refused"))
    line = format_llm_failure_log(
        stage="lightweight_direct_reply",
        classification=classification,
        endpoint=summarize_llm_endpoint(model="qwen", api_base="http://127.0.0.1:8000/v1"),
    )
    assert "LLM 调用失败" in line
    assert "category=LLM_UNREACHABLE" in line
    assert "unreachable=True" in line
    assert "model=qwen" in line
    assert "api_base=http://127.0.0.1:8000/v1" in line


def test_format_llm_empty_response_log():
    line = format_llm_empty_response_log(
        stage="agui_stream",
        endpoint={"model": "gpt", "api_base": "https://example/v1"},
        extra="llm_calls=0",
    )
    assert "LLM 调用完成但返回空内容" in line
    assert f"category={LLM_ERROR_EMPTY}" in line
    assert "llm_calls=0" in line


@pytest.mark.asyncio
async def test_agui_stream_logs_and_codes_unreachable_error(monkeypatch, caplog):
    import logging

    from apps.opspilot.metis.llm.chain.entity import BasicLLMRequest
    from apps.opspilot.metis.llm.chain.graph import BasicGraph

    class _BoomGraph(BasicGraph):
        async def compile_graph(self, _request):
            class _Compiled:
                async def astream_events(self, *_args, **_kwargs):
                    raise ConnectionRefusedError("Connection refused to llm")
                    yield  # pragma: no cover

            return _Compiled()

    async def _never(_eid):
        return False

    monkeypatch.setattr(
        "apps.opspilot.metis.llm.chain.graph.is_interrupt_requested_async",
        _never,
    )

    request = BasicLLMRequest(
        openai_api_base="http://127.0.0.1:9/v1",
        openai_api_key="sk-test",
        model="local-model",
        system_message_prompt="hi",
        user_message="你好",
    )
    with caplog.at_level(logging.ERROR):
        payloads = []
        async for line in _BoomGraph().agui_stream(request):
            if line.startswith("data: "):
                import json

                payloads.append(json.loads(line[6:].strip()))

    assert any(p.get("type") == "RUN_ERROR" and p.get("code") == LLM_ERROR_UNREACHABLE for p in payloads)
    assert any("LLM 调用失败" in r.message and "LLM_UNREACHABLE" in r.message for r in caplog.records)
