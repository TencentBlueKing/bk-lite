"""Approval and user-choice tool builders extracted from node.py."""
from __future__ import annotations

import time
import uuid

from langchain_core.callbacks import adispatch_custom_event, dispatch_custom_event
from langchain_core.runnables import RunnableConfig
from langchain_core.tools import StructuredTool
from pydantic import BaseModel as PydanticBaseModel
from pydantic import Field as PydanticField

from apps.core.logger import opspilot_logger as logger
from apps.opspilot.metis.llm.chain.k8s_report_tools import build_a2ui_report_contract
from apps.opspilot.services.approval import wait_for_approval
from apps.opspilot.utils.user_choice import wait_for_choice


class ApprovalToolsMixin:
    """Mixin for ToolsNodes; extracted without behavior change."""

    def _build_approval_tool(self):
        """构建 request_human_approval 工具，供 LLM 在判断操作高危时主动调用"""

        class ApprovalToolInput(PydanticBaseModel):
            action: str = PydanticField(description="即将执行的操作描述，包括工具名和关键参数")
            reason: str = PydanticField(description="为什么需要人工审批（风险说明）")
            risk_level: str = PydanticField(default="medium", description="风险等级: low / medium / high / critical")

        async def _request_approval(action: str, reason: str, risk_level: str = "medium") -> str:
            # 从 RunnableConfig 中获取上下文信息（通过闭包不可行，工具执行时由 ToolNode 调用）
            # 使用唯一标识作为 tool_call_id 的替代
            request_id = str(uuid.uuid4())[:8]
            # 从当前执行上下文获取 execution_id
            # 注意：ToolNode 执行工具时不传 config，所以用模块级的上下文
            execution_id = getattr(_request_approval, "_execution_id", "") or str(int(time.time() * 1000))
            node_id = getattr(_request_approval, "_node_id", "skill_test")

            approval_request_data = {
                "execution_id": execution_id,
                "node_id": node_id,
                "tool_call_id": f"approval_{request_id}",
                "tool_name": action,
                "tool_args": {"reason": reason, "risk_level": risk_level},
                "timeout_seconds": 300,
            }
            try:
                dispatch_custom_event("approval_request", approval_request_data)
            except Exception as e:
                logger.warning(f"[approval_tool] 发射 approval_request 事件失败: {e}")

            logger.info(f"[approval_tool] 审批请求已发射: action={action}, risk={risk_level}, id={request_id}")

            decision_info = await wait_for_approval(
                execution_id=execution_id,
                node_id=node_id,
                tool_call_id=f"approval_{request_id}",
                timeout_seconds=300,
                poll_interval=1.0,
                trigger_type="interactive",
                unattended_strategy="skip",
                timeout_fallback="deny",
            )

            decision = decision_info["decision"]
            dec_reason = decision_info.get("reason", "")
            logger.info(f"[approval_tool] 审批决策: decision={decision}, reason={dec_reason}")

            if decision == "approve":
                return f"已批准。你现在可以继续执行操作: {action}"
            else:
                return f"操作被拒绝: {action}。原因: {dec_reason}" if dec_reason else f"操作被拒绝: {action}。请告知用户操作未被批准。"

        approval_tool = StructuredTool.from_function(
            coroutine=_request_approval,
            name="request_human_approval",
            description=("当你判断即将执行的操作具有较高风险（如修改系统配置、删除数据、重启服务等），" "应先调用此工具请求人工审批。描述你要做什么以及为什么需要审批。" "收到审批结果后，根据结果决定是否继续执行实际操作。"),
            args_schema=ApprovalToolInput,
        )
        # 存储执行上下文的引用，在 build_react_nodes 中设置
        approval_tool._request_approval_func = _request_approval
        return approval_tool

    def _build_choice_tool(self):
        """构建 request_user_choice 工具，供 LLM 需要向用户提问时调用"""
        from typing import List, Literal, Optional

        from langchain_core.tools import StructuredTool
        from pydantic import BaseModel as PydanticBaseModel
        from pydantic import Field as PydanticField

        class AskUserInput(PydanticBaseModel):
            question: str = PydanticField(description="完整的一句问句，具体、引用用户原话或当前上下文里的关键词。脱离上下文用户也能看懂。")
            question_type: Literal["single_select", "multi_select", "confirm", "text"] = PydanticField(
                description="single_select=N选1; multi_select=N选若干; confirm=是/否; text=开放式输入"
            )
            options: Optional[List[str]] = PydanticField(
                default=None,
                description="single_select/multi_select 必填，2~4项，每项不超40字符。confirm/text 必须为 None。",
            )

        async def _ask_user(
            question: str,
            question_type: str,
            options: Optional[List[str]] = None,
            config: RunnableConfig = None,
        ) -> str:
            from apps.opspilot.metis.llm.tools.common.user_choice_guard import validate_user_choice_options
            from apps.opspilot.metis.llm.tools.kubernetes.user_choice_guard import build_kubernetes_cluster_choice_guard

            configurable = getattr(_ask_user, "_configurable", {}) or {}
            guard = build_kubernetes_cluster_choice_guard(
                question=question,
                options=options,
                configurable=configurable,
            )
            guard_message = validate_user_choice_options(
                question_type=question_type,
                options=options,
                guard=guard,
            )
            if guard_message:
                logger.warning("[choice_tool] 已阻止不可信的用户选择请求: %s", guard_message)
                return guard_message

            choice_id = str(uuid.uuid4())[:8]
            execution_id = getattr(_ask_user, "_execution_id", "") or str(int(time.time() * 1000))
            node_id = getattr(_ask_user, "_node_id", "skill_test")

            # Convert to internal options format based on question_type
            if question_type == "confirm":
                options_data = [
                    {"key": "yes", "label": "是", "description": "", "recommended": False},
                    {"key": "no", "label": "否", "description": "", "recommended": False},
                ]
                multiple = False
            elif question_type == "text":
                # Text mode: no predefined options, user types freely
                options_data = []
                multiple = False
            else:
                # single_select / multi_select
                options_data = [{"key": opt, "label": opt, "description": "", "recommended": False} for opt in (options or [])]
                multiple = question_type == "multi_select"

            effective_min_select = 1 if not multiple else 1
            effective_max_select = 1 if not multiple else len(options_data)
            default_keys = [options_data[0]["key"]] if options_data else []

            choice_request_data = {
                "execution_id": execution_id,
                "node_id": node_id,
                "choice_id": choice_id,
                "a2ui": build_a2ui_report_contract(
                    component="user-choice",
                    event_name="user_choice_request",
                    actions=[{"key": "submit_choice", "label": "提交选择"}],
                ),
                "title": question,
                "description": "",
                "options": options_data,
                "multiple": multiple,
                "min_select": effective_min_select,
                "max_select": effective_max_select,
                "timeout_seconds": 120,
                "default_keys": default_keys,
                "display_hint": "text" if question_type == "text" else "auto",
            }

            # 深 agent 包装节点里 sync dispatch 可能因缺 parent run id 静默失败；
            # 优先 adispatch，保证修复闭环的选择卡一定能推到前端。
            try:
                await adispatch_custom_event("user_choice_request", choice_request_data, config=config)
            except Exception:
                try:
                    dispatch_custom_event("user_choice_request", choice_request_data, config=config)
                except Exception:
                    pass

            logger.info(f"[choice_tool] 提问已发射: question={question[:50]}, " f"type={question_type}, id={choice_id}")

            result = await wait_for_choice(
                execution_id=execution_id,
                node_id=node_id,
                choice_id=choice_id,
                options=options_data,
                default_keys=default_keys,
                timeout_seconds=120,
                poll_interval=1.0,
                trigger_type="interactive",
            )

            selected = result["selected"]
            source = result["source"]

            # Dispatch result event to notify frontend
            result_payload = {
                "execution_id": execution_id,
                "node_id": node_id,
                "choice_id": choice_id,
                "selected": selected,
                "source": source,
            }
            try:
                await adispatch_custom_event("user_choice_result", result_payload, config=config)
            except Exception:
                try:
                    dispatch_custom_event("user_choice_result", result_payload, config=config)
                except Exception:
                    pass

            # Build response text for LLM
            if question_type == "text":
                # For text mode, selected[0] is the raw user input
                answer_text = selected[0] if selected else ""
            elif question_type == "confirm":
                answer_text = "是" if "yes" in selected else "否"
            else:
                # single/multi select - selected keys ARE the labels
                answer_text = ", ".join(selected)

            if source == "user":
                return f"用户回答: {answer_text}。请根据用户的回答继续执行下一步操作，不要停止。"
            else:
                return f"用户未在规定时间内回答，已使用默认选项: {answer_text}。请根据默认值继续操作。"

        choice_tool = StructuredTool.from_function(
            coroutine=_ask_user,
            name="request_user_choice",
            description=(
                "向用户提一个澄清问题或让用户从选项中做出选择。\n"
                "【强制】任何需要用户做选择的场景都必须调用此工具，严禁用纯文本列出选项让用户打字回复。\n"
                "在调用之前，先确认你已经做完了所有自己能做的探索。\n\n"
                "━━━ 应当调用的场景 ━━━\n"
                "1. 存在多个目标/实例且用户未明确指定范围时（必须先通过搜索/查询工具确认有多个结果，再让用户选择。不能跳过查询直接问）\n"
                "2. 请求存在多种合理解读，选错会导致返工\n"
                "3. 需要只有用户掌握的信息（偏好、业务规则、场景背景）\n"
                "4. 任务完成后让用户选择下一步操作\n\n"
                "━━━ 禁止调用的场景 ━━━\n"
                "A. 自己能查到答案的不要问（用工具查）\n"
                "B. 用户原始消息里已经给过约束的不要再问\n"
                "C. 不确定的细节不影响最终结果的，自己做主\n"
                "D. 一次只问一个回合，不要连环追问（同一件事只问一次）\n"
                "E. 寒暄性、确认性的问题不要问（hello/你好 → 直接回复文本，不调任何工具）\n"
                "F. 第一步就让用户选集群/实例是不允许的，必须先用搜索工具确认目标位置\n"
                "G. 用户没有提出 K8s/技术操作需求时，不要主动问是否要做检查\n\n"
                "━━━ 参数选择 ━━━\n"
                "能让用户点按钮就别让用户打字。\n"
                "- single_select: N选1，options 2~4项\n"
                "- multi_select: N选若干\n"
                "- confirm: 是/否（options 设为 None）\n"
                "- text: 开放式输入（options 设为 None）\n\n"
                "question 必须是完整问句，脱离上下文也能看懂。选项必须来自实际查询结果，不得编造。"
            ),
            args_schema=AskUserInput,
        )
        choice_tool._request_choice_func = _ask_user
        return choice_tool


# Backward-compat module-level aliases (tests patch chain.node.*)
_build_approval_tool = ApprovalToolsMixin._build_approval_tool
_build_choice_tool = ApprovalToolsMixin._build_choice_tool
