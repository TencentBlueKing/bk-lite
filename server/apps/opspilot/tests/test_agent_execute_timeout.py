"""
测试 _resolve_agent_execute_timeout() 整轮 agent 执行超时预算解析（commit eeebc787f / Issue #3718）

行为契约（与 chat_service._resolve_agent_execute_timeout 的 docstring 一致）：
- 优先读取 AGENT_EXECUTE_TIMEOUT；
- 兼容旧的 LLM_INVOKE_TIMEOUT（向后兼容回退）；
- 两者都未设置时默认 300 秒（覆盖一整轮多轮 LLM + 工具调用，独立于单次 LLM 调用超时）。

注：这是行为级测试（直接调用函数），与 test_chat_service_llm_timeout.py 的源码级
    字符串校验互补。revert 解耦修复（还原为固定读取 LLM_INVOKE_TIMEOUT,"60"）后，
    test_default_is_300 与 test_agent_var_takes_priority 应失败。
"""

import pytest

from apps.opspilot.services.chat_service import _resolve_agent_execute_timeout


@pytest.fixture(autouse=True)
def _clear_timeout_env(monkeypatch):
    """每个用例前清空两个超时环境变量，避免外部环境污染。"""
    monkeypatch.delenv("AGENT_EXECUTE_TIMEOUT", raising=False)
    monkeypatch.delenv("LLM_INVOKE_TIMEOUT", raising=False)


class TestResolveAgentExecuteTimeout:
    def test_default_is_300(self):
        """两个环境变量都未设置时，整轮 agent 预算默认 300 秒。"""
        assert _resolve_agent_execute_timeout() == 300

    def test_agent_var_takes_priority(self, monkeypatch):
        """AGENT_EXECUTE_TIMEOUT 优先于 LLM_INVOKE_TIMEOUT 与默认值。"""
        monkeypatch.setenv("AGENT_EXECUTE_TIMEOUT", "120")
        monkeypatch.setenv("LLM_INVOKE_TIMEOUT", "60")
        assert _resolve_agent_execute_timeout() == 120

    def test_falls_back_to_llm_invoke_timeout(self, monkeypatch):
        """未设置 AGENT_EXECUTE_TIMEOUT 时，回退到 LLM_INVOKE_TIMEOUT（向后兼容）。

        说明：该回退意味着若运维仅为「单次 LLM 调用」配置了 LLM_INVOKE_TIMEOUT，
        整轮 agent 预算会被一并收敛到同一值——本测试固化当前契约，对应的设计权衡
        见 code review 报告。
        """
        monkeypatch.setenv("LLM_INVOKE_TIMEOUT", "90")
        assert _resolve_agent_execute_timeout() == 90

    def test_returns_int_type(self, monkeypatch):
        """返回值必须为 int，供 future.result(timeout=...) 直接使用。"""
        monkeypatch.setenv("AGENT_EXECUTE_TIMEOUT", "200")
        result = _resolve_agent_execute_timeout()
        assert isinstance(result, int)
        assert result == 200

    def test_empty_string_env_falls_through(self, monkeypatch):
        """空字符串视为未设置（`or` 短路），回退到下一优先级。"""
        monkeypatch.setenv("AGENT_EXECUTE_TIMEOUT", "")
        monkeypatch.setenv("LLM_INVOKE_TIMEOUT", "")
        assert _resolve_agent_execute_timeout() == 300
