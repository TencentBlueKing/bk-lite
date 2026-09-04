"""DeepAgent middleware and lightweight-path assembly helpers extracted from node.py."""
from __future__ import annotations

import re
from pathlib import Path

from langchain_core.messages import AIMessage, ToolMessage

from apps.opspilot.metis.llm.agent.tool_execution_planner import is_pod_restart_reason_query
from apps.opspilot.metis.llm.chain.entity import HIDE_PLANNED_STEP_TEXT_KEY


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
    _EVIDENCE_NOTE_RE = re.compile(r"日志获取完成|关键证据确认|证据链已闭环|本步证据")
    _INVESTIGATION_DUMP_RE = re.compile(r"事件描述|事件总结|涉及对象清单|异常对象名单|链路分析|数据分析|调查结论|诊断结论")
    _RCA_REQUIRED_HEADINGS = ("事件概述", "异常对象清单", "根因分析", "修复建议")
    _RESTART_REASON_REQUIRED_HEADINGS = ("对象与结论", "证据", "原因")
    HIDE_PLANNED_STEP_TEXT_KEY = HIDE_PLANNED_STEP_TEXT_KEY

    @classmethod
    def _iter_planned_assistant_text(cls, messages):
        for message in messages or []:
            if not isinstance(message, AIMessage):
                continue
            if getattr(message, "tool_calls", None):
                continue
            text = str(getattr(message, "content", "") or "").strip()
            if text:
                yield text

    @classmethod
    def _planned_output_has_markdown_table(cls, messages) -> bool:
        return any(cls._MARKDOWN_TABLE_RE.search(text) for text in cls._iter_planned_assistant_text(messages))

    @classmethod
    def _looks_like_repeated_investigation(cls, text: str) -> bool:
        """同一份正文里反复贴事件/清单/结论，还不是一份终稿。"""
        body = text or ""
        return body.count("事件概述") >= 2 or body.count("事件描述") >= 2 or body.count("调查结论") >= 2 or body.count("异常对象清单") >= 2

    @classmethod
    def _looks_like_complete_rca_report(cls, text: str) -> bool:
        """助手「输出格式」：以 RCA 报告为标题，含事件概述/清单/根因/修复，且未重复粘贴。"""
        body = text or ""
        if "RCA 报告" not in body:
            return False
        if cls._looks_like_repeated_investigation(body):
            return False
        return all(heading in body for heading in cls._RCA_REQUIRED_HEADINGS)

    @classmethod
    def _looks_like_complete_restart_reason_report(cls, text: str) -> bool:
        """重启原因助手终稿：时间基准可省略，禁止套告警 RCA 标题。"""
        body = text or ""
        if "RCA 报告" in body:
            return False
        if cls._looks_like_repeated_investigation(body):
            return False
        return all(heading in body for heading in cls._RESTART_REASON_REQUIRED_HEADINGS)

    @staticmethod
    def _planned_report_mode(*, user_message: str = "", agent_system_prompt: str = "") -> str:
        """分步终稿模板：重启原因 / 告警 RCA / 其它，互不套用。"""
        prompt = agent_system_prompt or ""
        if is_pod_restart_reason_query(user_message, prompt):
            return "restart_reason"
        if "Kubernetes 集群 RCA 助手" in prompt or "告警怎么读" in prompt:
            return "alert_rca"
        if "输出格式" in prompt and "RCA 报告" in prompt:
            return "alert_rca"
        return "default"

    @classmethod
    def _looks_like_step_investigation_dump(cls, text: str) -> bool:
        """分步调查草稿（事件描述/链路分析/调查结论），不是输出格式里的 RCA。"""
        body = text or ""
        if cls._looks_like_complete_rca_report(body):
            return False
        return bool(cls._INVESTIGATION_DUMP_RE.search(body))

    @classmethod
    def _looks_like_evidence_note(cls, text: str) -> bool:
        """取证过程要点或调查草稿，还不是助手「输出格式」里的完整 RCA 报告。"""
        body = text or ""
        if cls._looks_like_complete_rca_report(body) or cls._looks_like_complete_restart_reason_report(body):
            return False
        if cls._looks_like_step_investigation_dump(body) or cls._looks_like_repeated_investigation(body):
            return True
        return bool(cls._EVIDENCE_NOTE_RE.search(body))

    @classmethod
    def _summarize_planned_step_messages(cls, messages) -> str:
        """步间摘要：调查草稿改留工具结果，避免后续步把整份报告再贴一遍。"""
        ai_text = ""
        for message in reversed(list(messages or [])):
            if isinstance(message, AIMessage) and not getattr(message, "tool_calls", None):
                ai_text = str(getattr(message, "content", "") or "").strip()
                if ai_text:
                    break
        if ai_text and not cls._looks_like_evidence_note(ai_text) and not cls._looks_like_step_investigation_dump(ai_text):
            return ai_text[:1200]
        tool_bits: list[str] = []
        for message in messages or []:
            if not isinstance(message, ToolMessage):
                continue
            name = str(getattr(message, "name", "") or "tool")
            tool_bits.append(f"{name}: {str(getattr(message, 'content', '') or '')[:400]}")
        if tool_bits:
            return "；".join(tool_bits)[:1200]
        if ai_text:
            return ai_text[:200]
        return "步骤已完成"

    @classmethod
    def _planned_step_already_answered(cls, messages) -> bool:
        """步骤已写出给用户看的正文时，跳过总结轮，避免再复述一遍。"""
        for text in reversed(list(cls._iter_planned_assistant_text(messages))):
            if cls._looks_like_evidence_note(text):
                return False
            if cls._looks_like_complete_rca_report(text):
                return True
            if cls._looks_like_complete_restart_reason_report(text):
                return True
            if any(heading in text for heading in cls._RCA_REQUIRED_HEADINGS):
                return False
            if cls._MARKDOWN_TABLE_RE.search(text):
                return True
            if cls._STEP_STUB_RE.match(text):
                return False
            return len(text) >= 15
        return False

    @classmethod
    def _should_skip_planned_summary(cls, messages, *, completed_step_count: int) -> bool:
        """单步已作答，或多步里已经出现过完整表格时，不再跑总结轮。"""
        if not cls._planned_step_already_answered(messages):
            return False
        if completed_step_count <= 1:
            return True
        texts = list(cls._iter_planned_assistant_text(messages))
        if any(cls._looks_like_complete_rca_report(text) or cls._looks_like_complete_restart_reason_report(text) for text in texts):
            return True
        return cls._planned_output_has_markdown_table(messages)

    @classmethod
    def _select_visible_planned_messages(cls, messages, *, summary_ran: bool) -> list:
        """分步过程只给用户看一份终稿：工具结果保留，正文只留最后一份作答。

        summary_ran 保留调用契约；有无 summary 都取 answers[-1]，避免中间表盖掉更晚的无表终稿。
        """
        visible: list = []
        answers: list = []
        stubs: list = []
        for message in messages or []:
            if isinstance(message, AIMessage) and not getattr(message, "tool_calls", None):
                text = str(getattr(message, "content", "") or "").strip()
                if not text:
                    continue
                if cls._STEP_STUB_RE.match(text):
                    stubs.append(message)
                    continue
                answers.append(message)
                continue
            visible.append(message)
        chosen = None
        if answers:
            chosen = answers[-1]
        elif stubs:
            chosen = stubs[-1]
        if chosen is not None:
            visible.append(chosen)
        return visible

    @staticmethod
    def _set_hide_planned_step_text(graph_request, hidden: bool) -> None:
        extra = getattr(graph_request, "extra_config", None)
        if extra is None:
            graph_request.extra_config = extra = {}
        extra[HIDE_PLANNED_STEP_TEXT_KEY] = bool(hidden)

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

    _K8S_CLOCK_RULES = (
        "仅当用户问今天或某时间窗的重启次数（不是告警 RCA）时："
        "累计 restart_count 不是该时间窗次数，禁止写成「今天重启了 N 次」；此时只保留一张表，口径必须对齐该时间窗。"
        "用户问按重启时间排序或最近重启的 Pod 时，以 last_restart_time 为准，禁止按累计 restart_count 排序。"
        "若与前面累计名单矛盾，只保留时间窗结论，不要再贴口径不同的第二张表。"
    )

    @classmethod
    def _planned_last_step_tail(cls, *, user_message: str = "", agent_system_prompt: str = "") -> str:
        mode = cls._planned_report_mode(user_message=user_message, agent_system_prompt=agent_system_prompt)
        if mode == "restart_reason":
            return (
                "本步给出用户可见的最终答案，只输出一份重启原因报告，不要按排查步骤重复粘贴。"
                "按助手约定写：时间基准、对象与结论、证据、原因、建议与待确认；证据没有的章节可省略。"
                "禁止写「# RCA 报告」，禁止套告警复盘的事件概述、异常对象清单、根因分析、修复建议模板。"
                "标题之前不要写定位说明、步骤结果或客套话。"
                "禁止输出「事件描述」「事件总结」「涉及对象清单」「异常对象名单」「链路分析」「数据分析」「调查结论」「诊断结论」。"
                "禁止改成「日志获取完成」「关键证据确认」这类要点列表。"
                "解读 collect_pod_restart_evidence：死因看 finished_at、last_state、events 和 previous_tail，不要把当前轮尾巴当上一轮死因。"
                f"{cls._K8S_CLOCK_RULES}"
            )
        if mode == "alert_rca":
            return (
                "本步给出用户可见的最终答案，只输出一份报告，不要按排查步骤重复粘贴。"
                "必须以「# RCA 报告」作为第一行，然后按系统提示「输出格式」写完整中文 Markdown，章节顺序为："
                "事件概述、异常对象清单、根因分析、修复建议、待确认项。"
                "标题之前不要写定位说明、步骤结果或客套话。"
                "异常对象清单必须是 Markdown 表，列名为：对象、状态/现象、重启次数、关键事件、是否已定位。"
                "禁止输出「事件描述」「事件总结」「涉及对象清单」「异常对象名单」「链路分析」「数据分析」「调查结论」「诊断结论」。"
                "禁止改成「日志获取完成」「关键证据确认」这类要点列表。"
                "已知具体 Pod 的重启原因时，以 diagnose 的 last_state、previous 日志和定点事件为准，不要把当前轮日志当成上一轮死因。"
                f"{cls._K8S_CLOCK_RULES}"
            )
        return (
            "本步给出用户可见的最终答案，只输出一份报告，不要按排查步骤重复粘贴。"
            "按系统提示写最终答案，不要套「# RCA 报告」或「事件概述 / 异常对象清单」告警复盘模板。"
            "标题之前不要写定位说明、步骤结果或客套话。"
            "禁止输出「事件描述」「事件总结」「涉及对象清单」「异常对象名单」「链路分析」「数据分析」「调查结论」「诊断结论」。"
            "禁止改成「日志获取完成」「关键证据确认」这类要点列表。"
            "已知具体 Pod 的重启原因时，以 last_state、previous 日志和定点事件为准，不要把当前轮日志当成上一轮死因。"
            f"{cls._K8S_CLOCK_RULES}"
        )

    @classmethod
    def _planned_summary_guidance(cls, *, user_message: str = "", agent_system_prompt: str = "") -> str:
        mode = cls._planned_report_mode(user_message=user_message, agent_system_prompt=agent_system_prompt)
        if mode == "restart_reason":
            return (
                "现在向用户给出最终答案。当前没有可用工具，不要继续调用工具。"
                "按助手约定写一份重启原因报告：时间基准、对象与结论、证据、原因、建议与待确认；没有的章节可省略。"
                "禁止写「# RCA 报告」或告警复盘的事件概述、异常对象清单。"
                "标题之前不要写定位说明或步骤结果。"
                "若步骤里已经写过完整重启原因报告，不要重写，最多一两句。"
                "禁止再贴互相矛盾的名单；累计 restart_count 不要写成时间窗次数。"
            )
        if mode == "alert_rca":
            return (
                "现在向用户给出最终答案。当前没有可用工具，不要继续调用工具。"
                "必须以「# RCA 报告」作为第一行，再按"
                "「事件概述、异常对象清单、根因分析、修复建议、待确认项」只写一份完整 Markdown 报告，"
                "异常对象清单表必须保留；标题之前不要写定位说明或步骤结果。"
                "不要写事件描述、涉及对象清单、链路分析、调查结论；不要重复粘贴多份同类章节。"
                "禁止改成「日志获取完成」「关键证据确认」要点列表。"
                "若步骤里已经写过以「# RCA 报告」起笔且未重复粘贴的完整报告，不要重写，最多一两句。"
                "禁止再贴互相矛盾的名单；累计 restart_count 不要写成时间窗次数。"
            )
        return (
            "现在向用户给出最终答案。当前没有可用工具，不要继续调用工具。"
            "按系统提示写最终答案，不要套「# RCA 报告」告警复盘模板。"
            "不要写事件描述、涉及对象清单、链路分析、调查结论；不要重复粘贴多份同类章节。"
            "禁止改成「日志获取完成」「关键证据确认」要点列表。"
            "若步骤里已经写过完整答案，不要重写，最多一两句。"
            "禁止再贴互相矛盾的名单；累计 restart_count 不要写成时间窗次数。"
        )

    @classmethod
    def _planned_tool_step_guidance(
        cls,
        *,
        is_last_step: bool = False,
        user_message: str = "",
        agent_system_prompt: str = "",
    ) -> str:
        """业务工具步：与技能步共用停手契约，但不收掉本步多个计划工具。"""
        if is_last_step:
            tail = cls._planned_last_step_tail(user_message=user_message, agent_system_prompt=agent_system_prompt)
        else:
            tail = (
                "本步证据只给后续步骤用，不要输出 Markdown 表或最终结论。"
                "不要写事件概述、事件描述、异常对象清单、根因分析、修复建议、调查结论。"
                "一两句话说明本步拿到了什么即可。"
                "用户问今天或某时间窗时，禁止把累计 restart_count 写成该时间窗的次数。"
                "用户问按重启时间排序或最近重启的 Pod 时，以 last_restart_time 为准，禁止按累计 restart_count 排序。"
                "已知具体 Pod 的重启原因时，优先看 last_state 和 previous 日志。"
            )
        return (
            "【工具执行】只调用本步骤计划/可见工具。"
            "未计划工具会被拒绝，不要改调其他工具，也不要当作步骤失败去重规划。"
            "工具已返回结构化结果（含空列表）即终态，不要把空当失败反复换参。"
            "日志工具对同一 Pod 只调用一次；返回截断、压缩、空日志或没有 previous 都是有效证据，禁止降低 lines 重试。"
            "resolve_k8s_target_from_alert 对同一参数只调用一次；返回 resolved=false、"
            "lookup_exhausted 或 namespace 为空时不要重试，直接结束本步。"
            "401、kubeconfig 无效、连接参数缺失或解密失败时不要改参重试，把错误原样告诉用户并结束本步。"
            "工具抛出 AttributeError/TypeError 等实现异常时不要重试，把错误告诉用户。"
            "403 仅在可换 namespace 或实例时最多改参 1 次，否则把权限错误告诉用户。"
            f"{tail}"
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
        "给用户只保留一份与问题口径一致的结论；过程步骤不要输出互相矛盾的表。"
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
        from apps.opspilot.metis.llm.agent.tool_execution_planner import planned_execution_compact_limits_for_request
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

        max_tool_chars, max_ai_chars = planned_execution_compact_limits_for_request(graph_request)

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
            ToolResultCompactionMiddleware(max_tool_chars=max_tool_chars, max_ai_chars=max_ai_chars),
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
_planned_output_has_markdown_table = DeepAgentAssemblyMixin._planned_output_has_markdown_table
_should_skip_planned_summary = DeepAgentAssemblyMixin._should_skip_planned_summary
_select_visible_planned_messages = DeepAgentAssemblyMixin._select_visible_planned_messages
_set_hide_planned_step_text = DeepAgentAssemblyMixin._set_hide_planned_step_text
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
