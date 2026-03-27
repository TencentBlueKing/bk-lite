"""agent-browser 工具模块

这个模块提供了基于 Vercel Labs agent-browser CLI 的浏览器工具封装，
用于验证 agent-browser 在 OpsPilot tools 中的可集成性。

**主要特性：**
- 通过外部 CLI 执行浏览器命令
- 支持结构化返回 stdout/stderr/exit code
- 在二进制缺失时返回明确错误信息

**使用场景：**
- 快速验证 agent-browser CLI 是否可用
- 调用 open / snapshot / click 等底层浏览器命令
- 为后续巡检能力接入做可行性验证
"""

from apps.opspilot.metis.llm.tools.agent_browser.browser_tool import (
    agent_browser_inspect,
    agent_browser_open_and_screenshot,
    agent_browser_open_wait_and_snapshot,
    agent_browser_run,
    agent_browser_screenshot,
    agent_browser_snapshot,
    agent_browser_wait,
)

CONSTRUCTOR_PARAMS = []

__all__ = [
    "agent_browser_run",
    "agent_browser_screenshot",
    "agent_browser_open_and_screenshot",
    "agent_browser_snapshot",
    "agent_browser_wait",
    "agent_browser_open_wait_and_snapshot",
    "agent_browser_inspect",
]
