"""DeepAgent middleware and lightweight-path assembly helpers extracted from node.py."""
from __future__ import annotations

import re
from pathlib import Path

from langchain_core.messages import AIMessage


class DeepAgentAssemblyMixin:
    """Mixin for ToolsNodes; extracted without behavior change."""

    def _build_interrupt_on(self, graph_request, tools) -> dict | None:
        """approval_config -> deepagents interrupt_on（人工审批 HITL）。

        approval_config.tools 为空且启用 = 对所有业务工具审批（排除 deepagents 内置工具）。
        启用时还会并入 metadata.approval.required 的工具（如 exec_in_pod）。
        审批关闭时不并入，避免 RCA 诊断命令被无条件 HITL。
        """
        approval = getattr(graph_request, "approval_config", None)
        if not approval or not getattr(approval, "enabled", False):
            return None
        named = list(getattr(approval, "tools", None) or [])
        required_meta = self._approval_required_tool_names(tools)
        if named:
            target_names = list(dict.fromkeys([*named, *required_meta]))
        else:
            target_names = [t.name for t in (tools or []) if getattr(t, "name", None) and t.name not in self.DEEPAGENT_BUILTIN_TOOL_NAMES]
        if not target_names:
            return None
        return {name: True for name in target_names}

    @staticmethod
    def _approval_required_tool_names(tools) -> list[str]:
        names = []
        for item in tools or []:
            name = getattr(item, "name", None)
            meta = getattr(item, "metadata", None)
            if not name or not isinstance(meta, dict):
                continue
            approval_meta = meta.get("approval")
            if isinstance(approval_meta, dict) and approval_meta.get("required"):
                names.append(name)
        return names

    @staticmethod
    def _should_use_lightweight_direct_reply(tools, skill_sources) -> bool:
        """无业务工具且无技能包时走轻量直答，避免规划器 + DeepAgent 内置工具烧 token。"""
        if any(getattr(tool, "name", None) for tool in (tools or [])):
            return False
        return not bool(skill_sources)

    @staticmethod
    def _should_use_lightweight_after_empty_plan(plan) -> bool:
        """规划器判定无需执行步骤时，跳过 DeepAgent/FS（含已启用技能包的寒暄场景）。"""
        return not bool(getattr(plan, "steps", None))

    _MARKDOWN_TABLE_RE = re.compile(r"\|[^\n]+\|\s*\n\s*\|?\s*:?-{3,}", re.MULTILINE)

    _STEP_STUB_RE = re.compile(r"^执行结果\s*\d+\s*$")

    @classmethod
    def _planned_step_already_answered(cls, messages) -> bool:
        """单步已写出给用户看的正文时，跳过总结轮，避免再复述一遍。"""
        for message in reversed(messages or []):
            if not isinstance(message, AIMessage):
                continue
            if getattr(message, "tool_calls", None):
                continue
            text = str(getattr(message, "content", "") or "").strip()
            if not text:
                continue
            if cls._MARKDOWN_TABLE_RE.search(text):
                return True
            if cls._STEP_STUB_RE.match(text):
                return False
            return len(text) >= 15
        return False

    @staticmethod
    def _plan_is_skills_only(candidate_plan) -> bool:
        """整份计划是否仅依赖技能运行时（无业务工具名）。"""
        from apps.opspilot.metis.llm.agent.tool_execution_planner import USE_SKILLS_TOOL_NAME

        steps = list(getattr(candidate_plan, "steps", None) or [])
        if not steps:
            return False
        for step in steps:
            tools = [str(name) for name in (getattr(step, "tools", None) or []) if str(name)]
            if not tools:
                return False
            if any(name != USE_SKILLS_TOOL_NAME for name in tools):
                return False
        return True

    @staticmethod
    def _skill_package_script_lines(package: dict) -> list[str]:
        pkg_id = str(package.get("package_id") or package.get("name") or "").strip()
        if not pkg_id:
            return []
        extracted = package.get("extracted_root")
        scripts_dir = None
        if isinstance(extracted, Path):
            scripts_dir = extracted / "scripts"
        elif extracted:
            scripts_dir = Path(str(extracted)) / "scripts"
        names: list[str] = []
        if scripts_dir is not None and scripts_dir.is_dir():
            names = sorted(path.name for path in scripts_dir.glob("*.py") if path.is_file() and not path.name.startswith("_"))
        if not names:
            return [f"- python3 /skills/{pkg_id}/scripts/<脚本>.py"]
        return [f"- python3 /skills/{pkg_id}/scripts/{name}" for name in names]

    @staticmethod
    def _skill_only_step_guidance(packages: list | None = None) -> str:
        """纯技能步的硬约束：直跑脚本，禁止扫包/探环境。"""
        package_hints: list[str] = []
        for package in packages or []:
            if not isinstance(package, dict):
                continue
            package_hints.extend(DeepAgentAssemblyMixin._skill_package_script_lines(package))
        hint_lines = "\n".join(package_hints) if package_hints else "- python3 /skills/<包名>/scripts/<脚本>.py"
        return (
            "【技能包执行】连接参数已由平台注入，禁止 echo/$VAR/env/python -c 探测。"
            "禁止反复 read_file/ls/grep 扫技能包。"
            "禁止 --help/-h，禁止 2>&1 | head 或任何管道/重定向；用法已在本提示，不要先探命令。"
            "必须使用下列真实脚本路径，禁止发明文件名。"
            "直接 execute 查询，例如："
            'python3 /skills/ad-domain-ops/scripts/ad_search.py --query "*" --type user --limit 10 --attrs sAMAccountName。'
            "脚本 ok=true（含空结果）后立即用一张表回答并结束本步。"
            "401、凭据无效、连接失败、解密失败或脚本 AttributeError 等实现异常时不要重试，把错误原样告诉用户并结束本步。"
            "403 仅在可换查询范围时最多改参 1 次，否则把权限错误告诉用户。\n"
            f"可用脚本：\n{hint_lines}"
        )

    @staticmethod
    def _planned_tool_step_guidance() -> str:
        """业务工具步：与技能步共用停手契约，但不收掉本步多个计划工具。"""
        return (
            "【工具执行】只调用本步骤计划/可见工具。"
            "未计划工具会被拒绝，不要改调其他工具，也不要当作步骤失败去重规划。"
            "工具已返回结构化结果（含空列表）即终态，不要把空当失败反复换参。"
            "resolve_k8s_target_from_alert 对同一参数只调用一次；返回 resolved=false、"
            "lookup_exhausted 或 namespace 为空时不要重试，直接结束本步。"
            "401、kubeconfig 无效、连接参数缺失或解密失败时不要改参重试，把错误原样告诉用户并结束本步。"
            "工具抛出 AttributeError/TypeError 等实现异常时不要重试，把错误告诉用户。"
            "403 仅在可换 namespace 或实例时最多改参 1 次，否则把权限错误告诉用户。"
            "工具成功后用一两句话直接回答用户并结束本步，禁止再写第二份重复说明。"
        )

    @staticmethod
    def _build_lightweight_system_prompt(user_system_message: str = "", *, skills_available: bool = False) -> str:
        role = (user_system_message or "").strip() or "你是运维助手。"
        if skills_available:
            return f"{role}\n\n" "直接用中文简洁回答用户。" "本轮不需要调用工具或读取技能文件，不要假装调用工具或读写文件。" "严禁泄露密码、密钥、令牌等敏感信息。"
        return f"{role}\n\n" "直接用中文简洁回答用户。" "当前没有可用工具与技能，不要假装调用工具或读写文件。" "严禁泄露密码、密钥、令牌等敏感信息。"

    PLANNED_EXECUTION_STEP_PROMPT_SUFFIX = (
        "\n\n【分步工具执行】外部规划器已经拆分任务。"
        "每次只完成当前步骤，只调用当前可见工具；不要自行创建待办、子任务或重复规划。"
        "工具证据足够后立即结束当前步骤。"
        "需要向用户提问时可使用交互工具；"
        "但可用工具查到的定位信息（例如缺 namespace 时先反查 Pod/Events）禁止直接问用户。"
    )

    def _build_legacy_deep_agent_middleware(self, token_usage_accumulator, graph_request) -> list:
        from apps.opspilot.metis.llm.common.token_usage import TokenUsageAccumulator
        from apps.opspilot.metis.llm.middleware.context_window import ContextWindowMiddleware
        from apps.opspilot.metis.llm.middleware.token_usage import TokenUsageTrackingMiddleware

        isolated_llm = self.get_llm_client(graph_request, disable_stream=True, isolated=True)
        legacy_middleware = [ContextWindowMiddleware(graph_request=graph_request, isolated_llm=isolated_llm)]
        if isinstance(token_usage_accumulator, TokenUsageAccumulator):
            legacy_middleware.append(TokenUsageTrackingMiddleware(token_usage_accumulator))
        return legacy_middleware

    @staticmethod
    def _build_planned_execution_tool_visibility(*, skill_sources, skills_only_plan, registered_tools) -> tuple[set, set]:
        from apps.opspilot.metis.llm.middleware.tool_runtime import (
            PLANNED_EXECUTION_ALWAYS_ON_BUSINESS_TOOLS,
            PLANNED_EXECUTION_ALWAYS_VISIBLE_FS_TOOLS,
            PLANNED_EXECUTION_HIDDEN_DEEPAGENT_TOOLS,
        )

        always_visible: set = set()
        hidden_tools = set(PLANNED_EXECUTION_HIDDEN_DEEPAGENT_TOOLS)
        if skill_sources and not skills_only_plan:
            always_visible |= set(PLANNED_EXECUTION_ALWAYS_VISIBLE_FS_TOOLS)
        if skills_only_plan:
            hidden_tools.discard("execute")
            always_visible.add("execute")
        always_visible |= {
            name for name in PLANNED_EXECUTION_ALWAYS_ON_BUSINESS_TOOLS if any(getattr(tool, "name", "") == name for tool in registered_tools)
        }
        return always_visible, hidden_tools

    def _build_planned_execution_runtime_middleware(
        self,
        *,
        registered_tools,
        active_tools,
        always_visible,
        hidden_tools,
        skills_only_plan,
        graph_request,
        token_usage_accumulator,
    ):
        from apps.opspilot.metis.llm.common.token_usage import TokenUsageAccumulator
        from apps.opspilot.metis.llm.middleware.context_window import ContextWindowMiddleware
        from apps.opspilot.metis.llm.middleware.planned_execution_limits import (
            PlannedExecutionLimitMiddleware,
            get_planned_execution_run_model_call_limit,
            resolve_planned_execution_soft_budget_ratio,
            resolve_planned_execution_token_budget,
        )
        from apps.opspilot.metis.llm.middleware.token_usage import TokenUsageTrackingMiddleware
        from apps.opspilot.metis.llm.middleware.tool_runtime import (
            SkillExecutionGuardMiddleware,
            ToolExceptionAsResultMiddleware,
            ToolResultCompactionMiddleware,
            ToolVisibilityMiddleware,
        )

        visibility_middleware = ToolVisibilityMiddleware(
            business_tools=registered_tools,
            active_tools=active_tools,
            hidden_tools=hidden_tools,
            always_visible_tools=always_visible,
            allow_unregistered_tools=False,
            include_always_visible=True,
        )
        limit_middleware = PlannedExecutionLimitMiddleware(
            run_limit=get_planned_execution_run_model_call_limit(),
            token_budget=resolve_planned_execution_token_budget(graph_request),
            soft_budget_ratio=resolve_planned_execution_soft_budget_ratio(graph_request),
            accumulator=(token_usage_accumulator if isinstance(token_usage_accumulator, TokenUsageAccumulator) else None),
        )
        skill_guard = SkillExecutionGuardMiddleware(enabled=skills_only_plan)
        isolated_llm = self.get_llm_client(graph_request, disable_stream=True, isolated=True)
        runtime_middleware = [
            visibility_middleware,
            skill_guard,
            ToolExceptionAsResultMiddleware(),
            ToolResultCompactionMiddleware(),
            ContextWindowMiddleware(graph_request=graph_request, isolated_llm=isolated_llm),
            limit_middleware,
        ]
        if isinstance(token_usage_accumulator, TokenUsageAccumulator):
            runtime_middleware.append(TokenUsageTrackingMiddleware(token_usage_accumulator))
        return runtime_middleware, visibility_middleware, limit_middleware, skill_guard

    @staticmethod
    def _append_planned_execution_step_prompt(final_system_prompt: str) -> str:
        return final_system_prompt + DeepAgentAssemblyMixin.PLANNED_EXECUTION_STEP_PROMPT_SUFFIX

    @staticmethod
    def _build_deep_agent_kwargs(
        *,
        llm,
        registered_tools,
        final_system_prompt,
        runtime_middleware,
        backend,
        skill_sources,
        interrupt_on,
    ) -> dict:
        agent_kwargs = {
            "model": llm,
            "tools": registered_tools,
            "system_prompt": final_system_prompt,
        }
        if runtime_middleware:
            agent_kwargs["middleware"] = runtime_middleware
        if backend is not None:
            agent_kwargs["backend"] = backend
        if skill_sources:
            agent_kwargs["skills"] = skill_sources
        if interrupt_on:
            agent_kwargs["interrupt_on"] = interrupt_on
        return agent_kwargs


# Backward-compat module-level aliases (tests patch chain.node.*)
_build_interrupt_on = DeepAgentAssemblyMixin._build_interrupt_on
_build_lightweight_system_prompt = DeepAgentAssemblyMixin._build_lightweight_system_prompt
_plan_is_skills_only = DeepAgentAssemblyMixin._plan_is_skills_only
_planned_step_already_answered = DeepAgentAssemblyMixin._planned_step_already_answered
_planned_tool_step_guidance = DeepAgentAssemblyMixin._planned_tool_step_guidance
_should_use_lightweight_after_empty_plan = DeepAgentAssemblyMixin._should_use_lightweight_after_empty_plan
_should_use_lightweight_direct_reply = DeepAgentAssemblyMixin._should_use_lightweight_direct_reply
_skill_only_step_guidance = DeepAgentAssemblyMixin._skill_only_step_guidance
_skill_package_script_lines = DeepAgentAssemblyMixin._skill_package_script_lines
_build_legacy_deep_agent_middleware = DeepAgentAssemblyMixin._build_legacy_deep_agent_middleware
_build_planned_execution_tool_visibility = DeepAgentAssemblyMixin._build_planned_execution_tool_visibility
_build_planned_execution_runtime_middleware = DeepAgentAssemblyMixin._build_planned_execution_runtime_middleware
_append_planned_execution_step_prompt = DeepAgentAssemblyMixin._append_planned_execution_step_prompt
_build_deep_agent_kwargs = DeepAgentAssemblyMixin._build_deep_agent_kwargs
