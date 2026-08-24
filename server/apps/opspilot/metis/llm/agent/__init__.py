"""DeepAgent 包入口。

子模块（如 ``tool_execution_planner``）必须能在不导入 ``deep_agent`` 的情况下加载。
否则 ``node → tool_runtime → agent.tool_execution_planner → agent.__init__ → deep_agent → node``
会在「先 import node」时形成循环导入，单测按文件收集会失败。
"""

from typing import Any

__all__ = [
    "DeepAgentGraph",
    "DeepAgentRequest",
    "DeepAgentResponse",
    "DeepAgentState",
    "DeepAgentNode",
]

_DEEP_AGENT_EXPORTS = frozenset(__all__)


def __getattr__(name: str) -> Any:
    if name in _DEEP_AGENT_EXPORTS:
        from apps.opspilot.metis.llm.agent import deep_agent as _deep_agent

        return getattr(_deep_agent, name)
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
