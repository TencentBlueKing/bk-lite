"""
聊天流程执行引擎 - ChatFlowEngine
"""

import json
import threading
import time
import uuid
from datetime import datetime
from datetime import timezone as dt_timezone
from graphlib import CycleError
from typing import Any, Callable, Dict, List, Optional

from asgiref.sync import sync_to_async
from django.http import StreamingHttpResponse
from django.utils import timezone

from apps.core.logger import opspilot_logger as logger
from apps.opspilot.enum import WorkFlowExecuteType, WorkFlowTaskStatus
from apps.opspilot.models import BotWorkFlow
from apps.opspilot.models.bot_mgmt import WorkFlowConversationHistory, WorkFlowTaskNodeResult, WorkFlowTaskResult
from apps.opspilot.utils.execution_interrupt import is_interrupt_requested, is_interrupt_requested_async

from .core.base_executor import BaseNodeExecutor  # noqa: F401  (保留以兼容历史 from .engine import ...)
from .core.enums import NodeStatus
from .core.models import NodeExecutionContext
from .core.node_result import NodeResult  # noqa: F401  (类型化节点契约，供门面/测试引用)
from .core.variable_manager import VariableManager  # noqa: F401
from .flow_graph import FlowGraphMixin
from .node_registry import node_registry  # noqa: F401  (保留以兼容历史 from .engine import node_registry)
from .node_runner import NodeRunnerMixin
from .sse_responder import SSEResponderMixin


class ChatFlowEngine(FlowGraphMixin, NodeRunnerMixin, SSEResponderMixin):
    # AGUI 协议中需要过滤的事件类型（工具调用相关和运行状态相关）
    # 用于 _extract_final_message 方法提取真实文本内容时过滤
    AGUI_SKIP_TYPES = frozenset(
        {
            # 工具调用相关事件
            "TOOL_CALL_START",
            "TOOL_CALL_ARGS",
            "TOOL_CALL_END",
            "TOOL_CALL_RESULT",
            # 运行状态事件
            "RUN_STARTED",
            "RUN_FINISHED",
            "RUN_ERROR",
            # 消息边界事件（不包含实际内容）
            "TEXT_MESSAGE_START",
            "TEXT_MESSAGE_END",
            # 注意：CUSTOM 类型不在此过滤，需要处理 browser_step_progress 事件
        }
    )

    def __init__(self, instance: BotWorkFlow, start_node_id: str = None, entry_type: str = None, execution_id: str = None):
        self.instance = instance
        self.start_node_id = start_node_id
        self.entry_type = entry_type or WorkFlowExecuteType.OPENAI  # 默认为 openai
        self.execution_id = execution_id or str(uuid.uuid4())
        self.task_result: Optional[WorkFlowTaskResult] = None
        self.variable_manager = VariableManager()
        self.execution_contexts: Dict[str, NodeExecutionContext] = {}

        # 用于跟踪最后执行的节点输出
        self.last_message = None

        # 用于跟踪节点执行顺序
        self.execution_order = 0

        # 守护引擎级共享状态（execution_order / execution_contexts）的可重入锁。
        # 并行分支（_execute_parallel_nodes 的线程池）会并发调用 _update_node_execution_order
        # 与写入 execution_contexts，需串行化以避免计数错乱或字典写入竞争。
        self._state_lock = threading.RLock()

        # 解析流程图
        self.nodes = self._parse_nodes(instance.flow_json)
        self.edges = self._parse_edges(instance.flow_json)

        # 构建节点ID到节点的映射字典（用于 O(1) 查找）
        self._node_map: Dict[str, Dict[str, Any]] = {node.get("id"): node for node in self.nodes if node.get("id")}

        # 识别所有入口节点（没有父节点的节点）
        self.entry_nodes = self._identify_entry_nodes()

        # 构建完整拓扑图（用于验证）
        self.full_topology = self._build_topology()

        # 自定义节点执行器映射（支持字符串类型）
        self.custom_node_executors: Dict[str, Callable] = {}

        # 执行配置
        self.max_parallel_nodes = 5
        self.max_retry_count = 3
        self.execution_timeout = 300  # 5分钟超时

    def _initialize_variables(self, input_data: Dict[str, Any]):
        """初始化变量管理器

        Args:
            input_data: 输入数据
        """
        self.variable_manager.set_variable("flow_id", str(self.instance.id))
        self.variable_manager.set_variable("execution_id", self.execution_id)
        self.variable_manager.set_variable("last_message", input_data.get("last_message", ""))
        self.variable_manager.set_variable("flow_input", input_data)

    @staticmethod
    def _to_datetime(timestamp: Optional[float]):
        if not timestamp:
            return None
        return datetime.fromtimestamp(timestamp, tz=dt_timezone.utc)

    def _check_interrupt_requested(self) -> bool:
        return is_interrupt_requested(self.execution_id)

    async def _check_interrupt_requested_async(self) -> bool:
        return await is_interrupt_requested_async(self.execution_id)

    def _finalize_interrupted_execution(self, input_data: Dict[str, Any], result: Any = None, start_node_type: str = None) -> None:
        task_result = self._ensure_execution_result_started(input_data, start_node_type)
        output_data = self._build_execution_output_data()
        if isinstance(result, dict):
            last_output = json.dumps(result, ensure_ascii=False)
        elif isinstance(result, str):
            last_output = result
        else:
            last_output = str(result or "execution interrupted")

        task_result.status = WorkFlowTaskStatus.INTERRUPTED
        task_result.input_data = json.dumps(input_data, ensure_ascii=False)
        task_result.output_data = output_data
        task_result.last_output = last_output
        task_result.execute_type = self._get_execute_type(start_node_type)
        task_result.finished_at = timezone.now()
        task_result.save(update_fields=["status", "input_data", "output_data", "last_output", "execute_type", "finished_at"])

        WorkFlowTaskNodeResult.objects.filter(execution_id=self.execution_id, task_result__isnull=True).update(task_result=task_result)

    def _interrupt_result(self, message: str = "执行已中断") -> Dict[str, Any]:
        return {"success": False, "interrupted": True, "error": message, "execution_id": self.execution_id}

    def _raise_if_interrupted(self, input_data: Optional[Dict[str, Any]] = None, start_node_type: str = None) -> None:
        if not self._check_interrupt_requested():
            return
        result = self._interrupt_result()
        if input_data is not None:
            self._finalize_interrupted_execution(input_data, result, start_node_type)
        raise InterruptedError(result["error"])

    def _record_node_execution_result(self, node_id: str, context: NodeExecutionContext) -> None:
        """记录节点执行明细（幂等 upsert）"""
        if not node_id or not context:
            return

        try:
            status = context.status.value if hasattr(context.status, "value") else str(context.status)
            node_index = self.variable_manager.get_variable(f"node_{node_id}_index")
            node_type = self.variable_manager.get_variable(f"node_{node_id}_type") or ""
            node_name = self.variable_manager.get_variable(f"node_{node_id}_name") or ""

            duration_ms = None
            if context.start_time and context.end_time:
                duration_ms = int((context.end_time - context.start_time) * 1000)

            defaults = {
                "node_name": node_name,
                "node_type": node_type,
                "node_index": node_index,
                "status": status,
                "input_data": context.input_data or {},
                "output_data": context.output_data or {},
                "error_message": context.error_message,
                "start_time": self._to_datetime(context.start_time),
                "end_time": self._to_datetime(context.end_time),
                "duration_ms": duration_ms,
            }
            if self.task_result:
                defaults["task_result"] = self.task_result

            WorkFlowTaskNodeResult.objects.update_or_create(
                execution_id=self.execution_id,
                node_id=node_id,
                defaults=defaults,
            )
        except Exception as e:
            logger.exception(f"记录节点执行明细失败: execution_id={self.execution_id}, node_id={node_id}, error={str(e)}")

    def _get_execute_type(self, start_node_type: str = None) -> str:
        """获取执行类型"""
        execute_type = WorkFlowExecuteType.OPENAI
        effective_type = self.entry_type or start_node_type
        if effective_type and effective_type.lower() in [choice[0] for choice in WorkFlowExecuteType.choices]:
            execute_type = effective_type.lower()
        return execute_type

    def _ensure_execution_result_started(self, input_data: Dict[str, Any], start_node_type: str = None) -> WorkFlowTaskResult:
        """确保执行主记录在任务开始时创建"""
        if self.task_result:
            return self.task_result

        task_result = WorkFlowTaskResult.objects.filter(bot_work_flow=self.instance, execution_id=self.execution_id).order_by("-id").first()
        if task_result:
            self.task_result = task_result
            return task_result

        self.task_result = WorkFlowTaskResult.objects.create(
            bot_work_flow=self.instance,
            execution_id=self.execution_id,
            status=WorkFlowTaskStatus.RUNNING,
            input_data=json.dumps(input_data, ensure_ascii=False),
            output_data={},
            execute_type=self._get_execute_type(start_node_type),
        )
        return self.task_result

    def _build_execution_output_data(self) -> Dict[str, Any]:
        """构建执行结果摘要"""
        total_nodes = len(self.execution_contexts)
        completed_nodes = 0
        failed_nodes = 0
        running_nodes = 0
        pending_nodes = 0
        final_node_id = None
        final_node_index = -1
        final_node_name = ""
        final_node_type = ""
        failed_node_id = None
        failed_node_name = ""
        failed_node_type = ""
        failed_error = ""

        for node_id, context in self.execution_contexts.items():
            node_index = self.variable_manager.get_variable(f"node_{node_id}_index")
            node_type = self.variable_manager.get_variable(f"node_{node_id}_type") or ""
            node_name = self.variable_manager.get_variable(f"node_{node_id}_name") or ""
            status_value = context.status.value if hasattr(context.status, "value") else str(context.status)

            if status_value == NodeStatus.COMPLETED.value:
                completed_nodes += 1
            elif status_value == NodeStatus.FAILED.value:
                failed_nodes += 1
                failed_node_id = node_id
                failed_node_name = node_name
                failed_node_type = node_type
                failed_error = context.error_message or ""
            elif status_value == NodeStatus.RUNNING.value:
                running_nodes += 1
            else:
                pending_nodes += 1

            if isinstance(node_index, int) and node_index > final_node_index:
                final_node_index = node_index
                final_node_id = node_id
                final_node_name = node_name
                final_node_type = node_type

        return {
            "summary": {
                "execution_id": self.execution_id,
                "total_nodes": total_nodes,
                "completed_nodes": completed_nodes,
                "failed_nodes": failed_nodes,
                "running_nodes": running_nodes,
                "pending_nodes": pending_nodes,
                "final_node": {
                    "node_id": final_node_id,
                    "node_name": final_node_name,
                    "node_type": final_node_type,
                    "node_index": final_node_index if final_node_index >= 0 else None,
                },
                "failed_node": {
                    "node_id": failed_node_id,
                    "node_name": failed_node_name,
                    "node_type": failed_node_type,
                    "error": failed_error,
                }
                if failed_node_id
                else None,
            }
        }

    async def _record_node_execution_result_async(self, node_id: str, context: NodeExecutionContext) -> None:
        """异步记录节点执行明细（用于 async 上下文）

        使用 sync_to_async 包装同步的 ORM 操作，避免在异步上下文中直接调用同步数据库操作。
        注意：使用 thread_sensitive=False 避免在 LangGraph 异步节点中触发
        "You cannot submit onto CurrentThreadExecutor from its own thread" 错误。
        """
        await sync_to_async(self._record_node_execution_result, thread_sensitive=False)(node_id, context)

    async def _record_execution_result_async(self, input_data: Dict[str, Any], result: Any, success: bool, start_node_type: str = None) -> None:
        """异步记录工作流执行结果（用于 async 上下文）

        注意：使用 thread_sensitive=False 避免在 LangGraph 异步节点中触发
        "You cannot submit onto CurrentThreadExecutor from its own thread" 错误。
        """
        await sync_to_async(self._record_execution_result, thread_sensitive=False)(input_data, result, success, start_node_type)

    def _get_start_node(self) -> Optional[Dict[str, Any]]:
        """获取起始节点

        Returns:
            起始节点字典，如果没有则返回none
        """
        if self.start_node_id:
            return self._get_node_by_id(self.start_node_id)
        return self.nodes[0] if self.nodes else None

    def _determine_entry_type(self, start_node: Optional[Dict[str, Any]]) -> str:
        """确定入口类型

        Args:
            start_node: 起始节点

        Returns:
            入口类型字符串
        """
        if not start_node:
            return "restful"
        start_node_type = start_node.get("type", "")
        return start_node_type if start_node_type in [choice[0] for choice in WorkFlowExecuteType.choices] else "restful"

    def _prepare_sse_execution(
        self, input_data: Dict[str, Any]
    ) -> tuple[Optional[Dict[str, Any]], Optional[Dict[str, Any]], str, str, str, str, bool, bool, Optional[StreamingHttpResponse]]:
        """准备 SSE 执行上下文"""
        user_id = input_data.get("user_id", "")
        input_message = input_data.get("last_message", "") or input_data.get("message", "")
        session_id = input_data.get("session_id", "")
        entry_type = input_data.get("entry_type", "openai")
        logger.info(f"[SSE-Engine] 开始执行 - flow_id: {self.instance.id}, user_id: {user_id}, entry_type: {entry_type}, 节点数: {len(self.nodes)}")

        self._initialize_variables(input_data)

        node_id = input_data.get("node_id", "")
        self._record_conversation_history(user_id, input_message, "user", entry_type, node_id, session_id)

        validation_errors = self.validate_flow()
        if validation_errors:
            return None, None, user_id, entry_type, session_id, node_id, False, False, self._create_error_response("流程验证失败")

        start_node = self._get_start_node()
        start_node_type = start_node.get("type", "") if start_node else None
        self._ensure_execution_result_started(input_data, start_node_type)
        self._raise_if_interrupted(input_data, start_node_type)

        last_node = self.nodes[-1] if self.nodes else None
        is_agui_protocol = start_node and start_node.get("type") in ["agui", "embedded_chat", "mobile", "web_chat"]
        is_openai_protocol = start_node and start_node.get("type") == "openai"
        needs_streaming = (is_agui_protocol or is_openai_protocol) or (last_node and last_node.get("type") == "agents")
        if not needs_streaming:
            self._record_execution_result(
                input_data,
                {"success": False, "error": "当前流程不支持SSE"},
                False,
                start_node_type,
            )
            return (
                None,
                None,
                user_id,
                entry_type,
                session_id,
                node_id,
                is_agui_protocol,
                is_openai_protocol,
                self._create_error_response("当前流程不支持SSE"),
            )

        return start_node, last_node, user_id, entry_type, session_id, node_id, is_agui_protocol, is_openai_protocol, None

    def _resolve_sse_target_agent(
        self,
        input_data: Dict[str, Any],
        start_node: Optional[Dict[str, Any]],
        last_node: Optional[Dict[str, Any]],
        is_agui_protocol: bool,
        is_openai_protocol: bool,
    ) -> tuple[Optional[Dict[str, Any]], Dict[str, Any], Optional[StreamingHttpResponse]]:
        """解析 SSE 目标 agents 节点与最终输入数据"""
        target_agent_node, nodes_to_execute_before = self._find_target_agent_node(start_node, last_node, is_agui_protocol, is_openai_protocol)

        mapped_input_data = input_data
        if start_node:
            mapped_input_data = self.set_start_node_variable(input_data, start_node)

        final_input_data = self._execute_prerequisite_nodes(nodes_to_execute_before, mapped_input_data)

        if target_agent_node:
            return target_agent_node, final_input_data, None

        intent_node = None
        for node in nodes_to_execute_before:
            if node.get("type") == "intent_classification":
                intent_node = node
                break

        if intent_node:
            intent_result = final_input_data.get("intent_result")
            if intent_result:
                target_agent_node = self._find_agent_by_intent(intent_node.get("id"), intent_result)
                logger.info(f"[SSE-Engine] 意图分类结果: {intent_result!r}, 目标节点: {target_agent_node.get('id') if target_agent_node else None}")

        if target_agent_node:
            return target_agent_node, final_input_data, None

        start_node_type = start_node.get("type", "") if start_node else None
        self._record_execution_result(
            input_data,
            {"success": False, "error": "未找到可执行的agents节点（意图路由失败）"},
            False,
            start_node_type,
        )
        return None, final_input_data, self._create_error_response("未找到可执行的agents节点（意图路由失败）")

    def _resolve_sse_execute_method(
        self,
        input_data: Dict[str, Any],
        start_node: Optional[Dict[str, Any]],
        target_agent_node: Dict[str, Any],
        is_agui_protocol: bool,
    ):
        """解析 agents 节点的流式执行方法"""
        executor = self._get_node_executor(target_agent_node.get("type"))
        if is_agui_protocol and hasattr(executor, "agui_execute"):
            execute_method = executor.agui_execute
        elif hasattr(executor, "sse_execute"):
            execute_method = executor.sse_execute
        else:
            execute_method = None

        if execute_method:
            return execute_method, None

        logger.error(f"[SSE-Engine] agents节点不支持流式执行: {target_agent_node.get('id')}")
        self._record_execution_result(
            input_data,
            {"success": False, "error": "agents节点不支持流式执行"},
            False,
            start_node.get("type", "") if start_node else None,
        )
        return None, self._create_error_response("agents节点不支持流式执行")

    def sse_execute(self, input_data: Dict[str, Any] = None):
        """流程流式执行，支持SSE和AGUI协议，返回 StreamingHttpResponse"""

        if input_data is None:
            input_data = {}

        (
            start_node,
            last_node,
            user_id,
            entry_type,
            session_id,
            node_id,
            is_agui_protocol,
            is_openai_protocol,
            error_response,
        ) = self._prepare_sse_execution(input_data)
        if error_response:
            return error_response

        target_agent_node, final_input_data, error_response = self._resolve_sse_target_agent(
            input_data,
            start_node,
            last_node,
            is_agui_protocol,
            is_openai_protocol,
        )
        if error_response:
            return error_response

        execute_method, error_response = self._resolve_sse_execute_method(
            input_data,
            start_node,
            target_agent_node,
            is_agui_protocol,
        )
        if error_response:
            return error_response

        # 定义一个嵌套的异步生成器函数 - 完全模仿 agui_chat.py 的工作模式
        async def generate_stream():
            """
            嵌套的异步生成器：直接调用节点的 execute_method 获取流
            """
            accumulated_content = []

            # 使用公共方法创建 agents 节点的执行上下文
            agent_node_id = target_agent_node.get("id")

            # 构建 agents 节点的输入数据（仿照 _execute_single_node 的逻辑）
            agent_input_data = self._build_agent_input_data(target_agent_node, final_input_data)

            agent_context = await self._create_node_execution_context_async(
                node=target_agent_node,
                input_data=agent_input_data,
                status=NodeStatus.RUNNING,
            )

            try:
                # 同步调用 execute_method,它会返回一个异步生成器
                async_execute = sync_to_async(execute_method, thread_sensitive=False)
                stream_generator = await async_execute(target_agent_node.get("id"), target_agent_node, agent_input_data)

                # 直接迭代异步生成器
                async for chunk in stream_generator:
                    if await self._check_interrupt_requested_async():
                        interrupt_data = {"type": "INTERRUPTED", "error": "执行已中断", "timestamp": int(time.time() * 1000)}
                        yield f"data: {json.dumps(interrupt_data, ensure_ascii=False)}\n\n"
                        await self._record_execution_result_async(
                            input_data,
                            self._interrupt_result(),
                            False,
                            start_node.get("type", "") if start_node else None,
                        )
                        return
                    # 累积内容用于记录对话历史
                    if chunk.startswith("data: "):
                        try:
                            data_str = chunk[6:].strip()
                            data_json = json.loads(data_str)
                            accumulated_content.append(data_json)
                        except (json.JSONDecodeError, ValueError):
                            pass

                    yield chunk

                # 更新 agents 节点执行上下文 - 成功
                final_message = self._extract_final_message(accumulated_content)
                agent_context.end_time = time.time()
                agent_context.status = NodeStatus.COMPLETED

                # 使用节点配置的 outputParams 作为输出 key
                agent_config = target_agent_node.get("data", {}).get("config", {})
                agent_output_key = agent_config.get("outputParams", "last_message")
                agent_context.output_data = {agent_output_key: final_message}

                # 提取 browser_use 步骤信息并保存到 output_data
                browser_steps = self._extract_browser_steps(accumulated_content)
                if browser_steps:
                    agent_context.output_data["browser_steps"] = browser_steps

                # 更新节点执行顺序
                self._update_node_execution_order(agent_node_id)
                await self._record_node_execution_result_async(agent_node_id, agent_context)

                # 记录系统输出到对话历史（流已结束，使用异步版本）
                if accumulated_content:
                    await self._record_conversation_history_async(
                        user_id,
                        accumulated_content,
                        "bot",
                        entry_type,
                        node_id,
                        session_id,
                    )

                # 检查是否有后续节点
                next_nodes = self._get_next_nodes(target_agent_node.get("id"), {"success": True, "data": {}})

                if await self._check_interrupt_requested_async():
                    await self._record_execution_result_async(
                        input_data,
                        self._interrupt_result(),
                        False,
                        start_node.get("type", "") if start_node else None,
                    )
                elif next_nodes:
                    # 有后续节点：不在此处记录，让后续节点执行完成后统一记录
                    pass
                else:
                    # 没有后续节点：记录成功执行结果
                    # 注意：必须使用异步版本，因为当前在 async 上下文中
                    await self._record_execution_result_async(
                        input_data,
                        final_message,
                        True,
                        start_node.get("type", "") if start_node else None,
                    )

                # 执行后续节点：在 async 流内串行 await，避免与 SSE 生成器并发修改
                # 共享状态（variable_manager / execution_contexts），同时保证后续节点
                # 工作不会因进程/请求结束被静默丢弃。
                await self._execute_subsequent_nodes_async(target_agent_node, accumulated_content)

            except Exception as e:
                logger.error(f"[SSE-Engine] Stream error: {e}", exc_info=True)

                # 更新 agents 节点执行上下文 - 失败
                agent_context.end_time = time.time()
                agent_context.status = NodeStatus.FAILED
                agent_context.error_message = str(e)

                # 更新节点执行顺序
                self._update_node_execution_order(agent_node_id)
                await self._record_node_execution_result_async(agent_node_id, agent_context)

                error_data = {"type": "ERROR", "error": f"流处理错误: {str(e)}", "timestamp": int(time.time() * 1000)}
                yield f"data: {json.dumps(error_data, ensure_ascii=False)}\n\n"

                # 记录失败执行结果到 WorkFlowTaskResult
                # 注意：必须使用异步版本，因为当前在 async 上下文中
                await self._record_execution_result_async(
                    input_data,
                    {"success": False, "error": str(e), "error_type": type(e).__name__},
                    False,
                    start_node.get("type", "") if start_node else None,
                )

        # 直接使用嵌套的异步生成器创建 StreamingHttpResponse
        return self._create_sse_stream_response(generate_stream)

    def set_start_node_variable(self, input_data: dict[str, Any] | dict[Any, Any], start_node: dict[str, Any]) -> dict[str, Any]:
        """设置入口节点的执行上下文和变量（入口节点直接标记为完成）

        入口节点负责将输入消息映射到配置的 outputParams 键名，供后续节点使用。
        例如：agui 节点配置 outputParams="agui_msg"，则将 last_message 的值映射到 agui_msg。

        Returns:
            映射后的输出数据，包含 outputParams 配置的键名
        """
        start_node_id = start_node.get("id")
        node_config = start_node.get("data", {}).get("config", {})

        # 获取入口节点的输入输出参数配置
        input_key = node_config.get("inputParams", "last_message")
        output_key = node_config.get("outputParams", "last_message")

        # 获取输入消息（优先使用 inputParams 配置的键，其次 last_message，最后 message）
        input_message = input_data.get(input_key) or input_data.get("last_message") or input_data.get("message", "")

        # 构建精简的输入数据（只保留 inputParams 配置的参数）
        filtered_input = {input_key: input_message}

        # 构建精简的输出数据（只保留 outputParams 配置的参数）
        filtered_output = {output_key: input_message}

        # 使用公共方法创建执行上下文（使用精简的输入数据）
        start_context = self._create_node_execution_context(node=start_node, input_data=filtered_input, status=NodeStatus.COMPLETED)

        # 入口节点直接完成，设置 output_data 和 end_time
        start_context.output_data = filtered_output
        start_context.end_time = time.time()

        # 更新节点执行顺序
        self._update_node_execution_order(start_node_id)
        self._record_node_execution_result(start_node_id, start_context)

        return filtered_output

    def _create_node_execution_context(
        self,
        node: Dict[str, Any],
        input_data: Dict[str, Any],
        status: NodeStatus = NodeStatus.RUNNING,
    ) -> NodeExecutionContext:
        """创建节点执行上下文并注册变量（公共方法）

        Args:
            node: 节点配置
            input_data: 输入数据
            status: 初始状态，默认 RUNNING

        Returns:
            NodeExecutionContext: 创建的执行上下文
        """
        node_id = node.get("id")
        node_type = node.get("type")
        node_name = node.get("data", {}).get("label", "") or node.get("data", {}).get("name", "") or node_id

        # 创建执行上下文
        context = NodeExecutionContext(node_id=node_id, flow_id=str(self.instance.id))
        context.start_time = time.time()
        context.status = status
        context.input_data = input_data

        # 保存节点信息到变量管理器
        self.variable_manager.set_variable(f"node_{node_id}_type", node_type)
        self.variable_manager.set_variable(f"node_{node_id}_name", node_name)

        # 保存输出参数名（用于失败时也使用用户指定的输出参数名）
        node_config = node.get("data", {}).get("config", {})
        output_key = node_config.get("outputParams", "last_message")
        self.variable_manager.set_variable(f"node_{node_id}_output_key", output_key)

        # 注册到 execution_contexts
        with self._state_lock:
            self.execution_contexts[node_id] = context
        self._record_node_execution_result(node_id, context)

        return context

    async def _create_node_execution_context_async(
        self,
        node: Dict[str, Any],
        input_data: Dict[str, Any],
        status: NodeStatus = NodeStatus.RUNNING,
    ) -> NodeExecutionContext:
        """异步创建节点执行上下文并注册变量（用于 async 上下文）

        与 _create_node_execution_context 功能相同，但使用异步方式记录节点执行结果，
        避免在异步上下文中直接调用同步数据库操作。

        Args:
            node: 节点配置
            input_data: 输入数据
            status: 初始状态，默认 RUNNING

        Returns:
            NodeExecutionContext: 创建的执行上下文
        """
        node_id = node.get("id")
        node_type = node.get("type")
        node_name = node.get("data", {}).get("label", "") or node.get("data", {}).get("name", "") or node_id

        # 创建执行上下文
        context = NodeExecutionContext(node_id=node_id, flow_id=str(self.instance.id))
        context.start_time = time.time()
        context.status = status
        context.input_data = input_data

        # 保存节点信息到变量管理器
        self.variable_manager.set_variable(f"node_{node_id}_type", node_type)
        self.variable_manager.set_variable(f"node_{node_id}_name", node_name)

        # 保存输出参数名（用于失败时也使用用户指定的输出参数名）
        node_config = node.get("data", {}).get("config", {})
        output_key = node_config.get("outputParams", "last_message")
        self.variable_manager.set_variable(f"node_{node_id}_output_key", output_key)

        # 注册到 execution_contexts
        with self._state_lock:
            self.execution_contexts[node_id] = context
        await self._record_node_execution_result_async(node_id, context)

        return context

    def _update_node_execution_order(self, node_id: str) -> int:
        """更新节点执行顺序计数器并保存到变量管理器

        Args:
            node_id: 节点ID

        Returns:
            int: 当前节点的执行顺序编号
        """
        with self._state_lock:
            self.execution_order += 1
            order = self.execution_order
        self.variable_manager.set_variable(f"node_{node_id}_index", order)
        return order

    def _find_target_agent_node(self, start_node, last_node, is_agui_protocol: bool, is_openai_protocol: bool):
        """查找目标agents节点及前置节点"""
        if is_agui_protocol or is_openai_protocol:
            return self._find_agent_node_via_bfs(start_node)
        else:
            # 最后节点就是agents
            target_agent_node = last_node
            nodes_to_execute_before = self.nodes[:-1] if len(self.nodes) > 1 else []
            return target_agent_node, nodes_to_execute_before

    def _execute_prerequisite_nodes(self, nodes_to_execute_before, input_data: Dict[str, Any]):
        """执行前置节点（非流式）"""
        if not nodes_to_execute_before:
            return input_data

        temp_engine_data = input_data.copy()

        for i, node in enumerate(nodes_to_execute_before):
            self._raise_if_interrupted(input_data, node.get("type", ""))
            node_id = node.get("id")
            node_type = node.get("type")
            executor = self._get_node_executor(node_type)

            # 使用公共方法创建执行上下文
            context = self._create_node_execution_context(node=node, input_data=temp_engine_data, status=NodeStatus.RUNNING)

            try:
                result = executor.execute(node_id, node, temp_engine_data)

                # 更新执行上下文 - 成功
                context.end_time = time.time()
                context.status = NodeStatus.COMPLETED
                context.output_data = result

                # 更新节点执行顺序
                self._update_node_execution_order(node_id)
                self._record_node_execution_result(node_id, context)

                self.variable_manager.set_variable(f"node_{node_id}_output", result)
                if isinstance(result, dict):
                    temp_engine_data.update(result)
            except Exception as e:
                # 更新执行上下文 - 失败
                context.end_time = time.time()
                context.status = NodeStatus.FAILED
                context.error_message = str(e)

                # 更新节点执行顺序
                self._update_node_execution_order(node_id)
                self._record_node_execution_result(node_id, context)

                logger.exception(f"[SSE-Engine] 前置节点 {node_id} ({node_type}) 执行失败: {str(e)}")
                # 记录错误到 WorkFlowTaskResult
                error_result = {
                    "success": False,
                    "error": str(e),
                    "error_type": type(e).__name__,
                    "failed_node_id": node_id,
                    "failed_node_type": node_type,
                }
                self._record_execution_result(input_data, error_result, False, node_type)
                # 重新抛出异常，让上层处理
                raise

        return temp_engine_data

    def _build_agent_input_data(self, agent_node: Dict[str, Any], base_input_data: Dict[str, Any]) -> Dict[str, Any]:
        """构建 agents 节点的输入数据

        仿照 _execute_single_node 的逻辑，确保 agents 节点获取正确的输入参数，
        特别是从意图分类节点路由过来时。

        Args:
            agent_node: agents 节点配置
            base_input_data: 基础输入数据（来自前置节点执行结果）

        Returns:
            构建好的 agents 节点输入数据
        """
        agent_config = agent_node.get("data", {}).get("config", {})
        input_key = agent_config.get("inputParams", "last_message")

        # 检查是否是从意图分类节点路由过来的（intent_previous_output）
        intent_previous_output = self.variable_manager.get_variable("intent_previous_output")
        if intent_previous_output is not None:
            # 当前节点是意图分类后的目标节点，使用保存的前置节点输出
            input_value = intent_previous_output
            # 清除标记，避免影响后续节点
            self.variable_manager.delete_variable("intent_previous_output")
            # 截断日志输出，避免过长
            log_value = input_value[:100] + "..." if isinstance(input_value, str) and len(input_value) > 100 else input_value
            logger.info(f"[SSE-Engine] 使用 intent_previous_output: {log_value}")
        else:
            # 优先从 variable_manager 获取，其次从 base_input_data 获取
            input_value = self.variable_manager.get_variable(input_key)
            if input_value is None:
                input_value = base_input_data.get(input_key, "")

        # 构建精确的输入数据，确保包含正确的 input_key
        agent_input_data = {input_key: input_value}
        # 保留其他必要字段（如 user_id, session_id, flow_input 等），但不覆盖 input_key
        for k, v in base_input_data.items():
            if k not in agent_input_data:
                agent_input_data[k] = v

        # 日志输出
        log_input = input_value[:100] + "..." if isinstance(input_value, str) and len(input_value) > 100 else input_value
        logger.info(f"[SSE-Engine] agents输入 keys={list(agent_input_data.keys())}, {input_key}={log_input}")

        return agent_input_data

    async def _execute_subsequent_nodes_async(self, agent_node: Dict[str, Any], agent_output: Any):
        """执行 agents 节点之后的后续节点

        在 SSE 异步生成器内被 await，确保：
        - 不与仍在迭代的流并发修改共享状态（variable_manager / execution_contexts），消除竞态；
        - 后续节点工作不会因为请求/进程结束而被静默丢弃。

        内部的同步逻辑（含 ORM 写入）通过 sync_to_async(thread_sensitive=False) 在工作线程中执行，
        避免在异步上下文中直接调用同步数据库操作。

        Args:
            agent_node: agents节点配置
            agent_output: agents节点的输出内容
        """

        def execute_subsequent_nodes():
            """同步执行后续节点（在工作线程中运行）"""
            all_success = True  # 跟踪所有节点是否都成功
            last_error_result = None  # 记录最后一个错误信息

            try:
                # 获取后续节点
                next_nodes = self._get_next_nodes(agent_node.get("id"), {"success": True, "data": {}})

                if not next_nodes:
                    return

                # 准备输入数据
                # 从累积的内容中提取最终消息
                final_message = self._extract_final_message(agent_output)

                agent_config = agent_node.get("data", {}).get("config", {})
                agent_output_key = agent_config.get("outputParams", "last_message")

                # 与同步执行链路保持一致：使用当前节点的 outputParams 作为后续节点输入来源
                if agent_output_key == "last_message":
                    self.variable_manager.set_variable("last_message", final_message)
                    node_input = {"last_message": final_message}
                else:
                    self.variable_manager.set_variable(agent_output_key, final_message)
                    node_input = {agent_output_key: final_message}
                first_input_data = node_input.copy()

                # 执行每个后续节点
                for next_node_id in next_nodes:
                    if self._check_interrupt_requested():
                        self._finalize_interrupted_execution(first_input_data or {}, self._interrupt_result(), self.entry_type)
                        return
                    node_type = ""
                    try:
                        next_node = self._get_node_by_id(next_node_id)
                        if not next_node:
                            logger.warning(f"[SSE-Engine] 后续节点不存在: {next_node_id}")
                            continue

                        node_type = next_node.get("type", "")
                        executor = self._get_node_executor(node_type)

                        if not executor:
                            logger.warning(f"[SSE-Engine] 找不到节点执行器: {node_type}")
                            continue

                        # 使用公共方法创建执行上下文
                        context = self._create_node_execution_context(node=next_node, input_data=node_input, status=NodeStatus.RUNNING)

                        # 执行节点
                        result = executor.execute(next_node_id, next_node, node_input)

                        # 更新执行上下文 - 成功
                        context.end_time = time.time()
                        context.status = NodeStatus.COMPLETED
                        context.output_data = result

                        # 更新节点执行顺序
                        self._update_node_execution_order(next_node_id)
                        self._record_node_execution_result(next_node_id, context)

                        # 更新输入为下一个节点准备
                        if result and isinstance(result, dict):
                            node_input.update(result)

                    except Exception as e:
                        all_success = False
                        # 更新执行上下文 - 失败
                        if next_node_id in self.execution_contexts:
                            context = self.execution_contexts[next_node_id]
                            context.end_time = time.time()
                            context.status = NodeStatus.FAILED
                            context.error_message = str(e)

                            # 更新节点执行顺序
                            self._update_node_execution_order(next_node_id)
                            self._record_node_execution_result(next_node_id, context)

                        logger.exception(f"[SSE-Engine] 后续节点 {next_node_id} 执行失败: {str(e)}")
                        # 记录错误信息，稍后统一记录
                        last_error_result = {
                            "success": False,
                            "error": str(e),
                            "error_type": type(e).__name__,
                            "failed_node_id": next_node_id,
                            "failed_node_type": node_type,
                            "stage": "subsequent_node",
                        }
                        # 继续执行其他节点
                        continue

                # 所有后续节点执行完成后，统一记录执行结果
                try:
                    if all_success:
                        # 全部成功
                        self._record_execution_result(first_input_data or {}, node_input, True)  # 最后一个节点的输出作为最终结果
                    else:
                        # 有失败节点
                        self._record_execution_result(first_input_data or {}, last_error_result or {"error": "后续节点执行失败"}, False)
                except Exception as record_err:
                    logger.exception(f"[SSE-Engine] 记录后续节点执行结果失败: {record_err}")

            except Exception as e:
                logger.error(f"[SSE-Engine] 后续节点执行失败: {str(e)}", exc_info=True)
                # 记录整体后续节点执行错误
                try:
                    error_result = {"success": False, "error": str(e), "error_type": type(e).__name__, "stage": "subsequent_nodes_overall"}
                    self._record_execution_result({}, error_result, False)
                except Exception as record_err:
                    logger.exception(f"[SSE-Engine] 记录后续节点整体错误失败: {record_err}")

        # 在 async 上下文中通过工作线程执行同步逻辑（含 ORM），并 await 其完成，
        # 保证串行执行、状态隔离且工作不被丢弃。
        await sync_to_async(execute_subsequent_nodes, thread_sensitive=False)()

    def _record_execution_result(self, input_data: Dict[str, Any], result: Any, success: bool, start_node_type: str = None) -> None:
        """记录工作流执行结果

        Args:
            input_data: 输入数据
            result: 执行结果
            success: 是否执行成功
            start_node_type: 启动节点类型（已废弃，使用 self.entry_type）
        """
        try:
            task_result = self._ensure_execution_result_started(input_data, start_node_type)
            interrupted = isinstance(result, dict) and result.get("interrupted")
            if task_result.status == WorkFlowTaskStatus.INTERRUPTED and not interrupted:
                logger.info("跳过执行结果覆盖，执行已中断: execution_id=%s", self.execution_id)
                return

            output_data = self._build_execution_output_data()

            # 确定状态
            status = WorkFlowTaskStatus.INTERRUPTED if interrupted else (WorkFlowTaskStatus.SUCCESS if success else WorkFlowTaskStatus.FAIL)

            # 准备输入数据字符串（记录第一个输入）
            input_data_str = json.dumps(input_data, ensure_ascii=False)

            # 准备最后输出
            if isinstance(result, dict):
                last_output = json.dumps(result, ensure_ascii=False)
            elif isinstance(result, str):
                last_output = result
            else:
                last_output = str(result)

            task_result.status = status
            task_result.input_data = input_data_str
            task_result.output_data = output_data
            task_result.last_output = last_output
            task_result.execute_type = self._get_execute_type(start_node_type)
            task_result.finished_at = timezone.now()
            task_result.save(update_fields=["status", "input_data", "output_data", "last_output", "execute_type", "finished_at"])

            WorkFlowTaskNodeResult.objects.filter(execution_id=self.execution_id, task_result__isnull=True).update(task_result=task_result)

        except Exception as e:
            logger.exception(f"记录工作流执行结果失败: execution_id={self.execution_id}, success={success}, error={str(e)}")
            # 记录失败不影响主流程

    def validate_flow(self) -> List[str]:
        """验证流程定义

        Returns:
            错误列表，空列表表示无错误
        """
        errors = []

        # 检查是否有节点
        if not self.nodes:
            errors.append("流程中没有节点")
            return errors

        # 检查是否有入口节点
        if not self.entry_nodes:
            errors.append("流程中没有入口节点")

        # 检查循环依赖
        try:
            list(self.full_topology.static_order())
        except CycleError:
            errors.append("流程存在循环依赖")

        # 检查节点类型是否支持
        supported_types = set(node_registry.get_supported_types())
        supported_types.update(self.custom_node_executors.keys())
        for node in self.nodes:
            node_type = node.get("type", "")
            if node_type not in supported_types:
                errors.append(f"不支持的节点类型: {node_type} (节点ID: {node.get('id', 'unknown')})")

        return errors

    def _summarize_execution_contexts(self) -> Dict[str, Any]:
        """生成执行上下文的脱敏摘要，用于持久化错误结果。

        仅保留排查所需的元信息（节点状态、错误信息、耗时、输入/输出的键名），
        绝不回显完整的 input_data / output_data，避免将提示词、用户数据、
        记忆等敏感内容写入数据库。
        """
        result = {}
        for node_id, context in self.execution_contexts.items():
            status = context.status
            result[node_id] = {
                "status": getattr(status, "value", status),
                "error_message": context.error_message,
                "start_time": context.start_time,
                "end_time": context.end_time,
                "input_keys": sorted(context.input_data.keys()) if isinstance(context.input_data, dict) else [],
                "output_keys": sorted(context.output_data.keys()) if isinstance(context.output_data, dict) else [],
            }
        return result

    def execute(self, input_data: Dict[str, Any] = None, timeout: int = None) -> Dict[str, Any]:
        """执行流程

        Args:
            input_data: 输入数据
            timeout: 执行超时时间（秒），默认使用配置值

        Returns:
            执行结果
        """
        if input_data is None:
            input_data = {}
        if timeout is None:
            timeout = self.execution_timeout

        start_time = time.time()
        user_id = input_data.get("user_id", "")
        input_message = input_data.get("last_message", "") or input_data.get("message", "")

        # 验证流程
        validation_errors = self.validate_flow()
        if validation_errors:
            return {"success": False, "error": f"流程验证失败: {'; '.join(validation_errors)}", "execution_time": 0}

        try:
            # 初始化变量管理器
            self._initialize_variables(input_data)

            # 获取并验证起始节点
            start_node = self._get_start_node()
            self._ensure_execution_result_started(input_data, start_node.get("type", "") if start_node else None)
            self._raise_if_interrupted(input_data, start_node.get("type", "") if start_node else None)
            chosen_start_node = self.start_node_id or (self.entry_nodes[0] if self.entry_nodes else None)
            if not chosen_start_node or not start_node:
                error_msg = "没有找到起始节点" if not chosen_start_node else f"指定的起始节点不存在: {chosen_start_node}"
                error_result = {
                    "success": False,
                    "error": error_msg,
                    "execution_time": time.time() - start_time,
                }
                self._record_execution_result(input_data, error_result, False)
                return error_result

            # 确定入口类型并记录用户输入
            entry_type = self._determine_entry_type(start_node)
            node_id = input_data.get("node_id", "")
            session_id = input_data.get("session_id", "")
            self._record_conversation_history(user_id, input_message, "user", entry_type, node_id, session_id)

            # 执行节点链
            chain_result = self._execute_node_chain(chosen_start_node, input_data, timeout - (time.time() - start_time))

            if self._check_interrupt_requested():
                interrupt_result = self._interrupt_result()
                self._record_execution_result(input_data, interrupt_result, False, start_node.get("type", ""))
                return interrupt_result

            # 获取执行结果并记录
            execution_time = time.time() - start_time

            # 检查节点链执行结果，判断是否有节点执行失败
            is_success, error_info = self._check_chain_result(chain_result)

            if is_success:
                # 所有节点执行成功
                final_last_message = self.variable_manager.get_variable("last_message")

                # 记录系统输出
                self._record_conversation_history(user_id, final_last_message, "bot", entry_type, node_id, session_id)
                self._record_execution_result(input_data, final_last_message, True, start_node.get("type", ""))

                return final_last_message
            else:
                # 有节点执行失败
                failed_node_id = error_info.get("node_id")
                error_message = error_info.get("error", "节点执行失败")

                # 尝试从失败节点的执行上下文中获取输出数据
                # 如果失败节点有部分输出，使用该输出；否则使用错误信息
                failed_context = self.execution_contexts.get(failed_node_id)
                if failed_context and failed_context.output_data:
                    # 失败节点有输出数据（可能是部分执行的结果）
                    final_output = failed_context.output_data
                else:
                    # 没有输出数据，构造包含错误信息的输出
                    # 保持与成功时一致的简洁格式，但包含错误信息
                    final_output = {"error": error_message, "failed_node_id": failed_node_id, "failed_node_type": error_info.get("node_type")}

                # 记录失败时的对话历史（bot 输出为错误信息）
                error_output_message = f"工作流执行失败: {error_message}"
                self._record_conversation_history(user_id, error_output_message, "bot", entry_type, node_id, session_id)

                # 构造用于记录的完整错误结果（包含详细信息用于调试）
                error_record = {
                    "success": False,
                    "error": error_message,
                    "failed_node_id": failed_node_id,
                    "failed_node_type": error_info.get("node_type"),
                    "execution_time": execution_time,
                    "execution_contexts": self._summarize_execution_contexts(),
                }

                # 记录失败结果到数据库
                self._record_execution_result(input_data, error_record, False, start_node.get("type", ""))

                # 返回简洁的输出格式，与成功时保持一致
                return final_output

        except Exception as e:
            execution_time = time.time() - start_time
            logger.exception(f"流程执行失败: flow_id={self.instance.id}, error={str(e)}")

            if isinstance(e, InterruptedError):
                interrupt_result = self._interrupt_result(str(e))
                start_node_type = None
                if self.entry_nodes:
                    start_node = self._get_node_by_id(self.entry_nodes[0])
                    if start_node:
                        start_node_type = start_node.get("type", "")
                self._record_execution_result(input_data, interrupt_result, False, start_node_type)
                return interrupt_result

            # 仅持久化脱敏摘要：不回显完整变量状态（提示词/用户数据/记忆）与
            # 完整执行上下文，避免敏感数据落库。
            error_result = {
                "success": False,
                "error": str(e),
                "variable_keys": sorted(self.variable_manager.get_all_variables().keys()),
                "execution_contexts": self._summarize_execution_contexts(),
                "execution_time": execution_time,
            }

            # 记录失败结果
            start_node_type = None
            if self.entry_nodes:
                start_node = self._get_node_by_id(self.entry_nodes[0])
                if start_node:
                    start_node_type = start_node.get("type", "")
            self._record_execution_result(input_data, error_result, False, start_node_type)

            return error_result

    def _record_conversation_history(self, user_id: str, message: Any, role: str, entry_type: str, node_id: str = "", session_id: str = ""):
        """记录对话历史

        Args:
            user_id: 用户ID
            message: 消息内容
            role: 角色 (user/bot)
            entry_type: 入口类型
            node_id: 节点ID
        """
        if not user_id or not message or entry_type == "celery":
            return

        try:
            # 转换消息为字符串
            if isinstance(message, dict):
                content = json.dumps(message, ensure_ascii=False)
            elif isinstance(message, str):
                content = message
            else:
                content = str(message)

            WorkFlowConversationHistory.objects.create(
                bot_id=self.instance.bot_id,
                node_id=node_id,
                user_id=user_id,
                conversation_role=role,
                conversation_content=content,
                conversation_time=timezone.now(),
                entry_type=entry_type,
                session_id=session_id,
                execution_id=self.execution_id,
            )
        except Exception as e:
            logger.exception(f"记录{role}对话历史失败: execution_id={self.execution_id}, user_id={user_id}, error={str(e)}")

    async def _record_conversation_history_async(
        self, user_id: str, message: Any, role: str, entry_type: str, node_id: str = "", session_id: str = ""
    ):
        """记录对话历史（异步版本，用于 async 上下文）"""
        await sync_to_async(self._record_conversation_history, thread_sensitive=False)(user_id, message, role, entry_type, node_id, session_id)


# 向后兼容别名
ChatFlowClient = ChatFlowEngine
