"""分步执行由 OpsPilot 编排，仅组装需要的原生文件/技能中间件。"""

from deepagents.middleware.filesystem import FilesystemMiddleware
from deepagents.middleware.patch_tool_calls import PatchToolCallsMiddleware
from deepagents.middleware.skills import SkillsMiddleware
from langchain.agents import create_agent
from langchain.agents.middleware import HumanInTheLoopMiddleware


def result_token_limit_for_request(request):
    # 原生以 4 字符/token 估算；用现有单消息额度约束其字符上限，
    # 避免中文结果在下一层小窗口裁剪时再次丢失。不是新的动态预算策略。
    trim = getattr(request, "message_trim_config", None)
    single = trim.get("max_single_message_tokens", 4000) if isinstance(trim, dict) else getattr(trim, "max_single_message_tokens", 4000)
    return min(20000, max(1, int(single or 4000) // 4))


def create_planned_agent(*, model, tools, backend, system_prompt=None, middleware=(), skills=None, interrupt_on=None, result_token_limit=1000):
    native = []
    if skills:
        native.append(SkillsMiddleware(backend=backend, sources=skills))
    native.extend(
        [
            FilesystemMiddleware(backend=backend, tool_token_limit_before_evict=result_token_limit),
            PatchToolCallsMiddleware(),
            *middleware,
        ]
    )
    if interrupt_on:
        native.append(HumanInTheLoopMiddleware(interrupt_on=interrupt_on))
    # ContextWindowMiddleware 已负责 OpsPilot 工作窗口与摘要；不重复安装上游摘要器。
    return create_agent(model=model, tools=tools, system_prompt=system_prompt, middleware=native)
