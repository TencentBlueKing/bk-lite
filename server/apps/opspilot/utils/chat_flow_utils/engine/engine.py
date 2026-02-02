"""
聊天流程执行引擎 - ChatFlowEngine
"""

import json
import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from graphlib import CycleError, TopologicalSorter
from typing import Any, Callable, Dict, List, Optional, Set

from asgiref.sync import sync_to_async
from django.http import StreamingHttpResponse
from django.utils import timezone

from apps.core.logger import opspilot_logger as logger
from apps.opspilot.enum import WorkFlowExecuteType, WorkFlowTaskStatus
from apps.opspilot.models import BotWorkFlow
from apps.opspilot.models.bot_mgmt import WorkFlowConversationHistory, WorkFlowTaskResult

from .core.base_executor import BaseNodeExecutor
from .core.enums import NodeStatus
from .core.models import NodeExecutionContext
from .core.variable_manager import VariableManager
from .node_registry import node_registry


class ChatFlowEngine:
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
            # 自定义事件
            "CUSTOM",
        }
    )

    def __init__(self, instance: BotWorkFlow, start_node_id: str = None, entry_type: str = None):
        self.instance = instance
        self.start_node_id = start_node_id
        self.entry_type = entry_type or WorkFlowExecuteType.OPENAI  # 默认为 openai
        self.variable_manager = VariableManager()
        self.execution_contexts: Dict[str, NodeExecutionContext] = {}

        # 用于跟踪最后执行的节点输出
        self.last_message = None

        # 用于跟踪节点执行顺序
        self.execution_order = 0

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
        self.variable_manager.set_variable("last_message", input_data.get("last_message", ""))
        self.variable_manager.set_variable("flow_input", input_data)

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

    def sse_execute(self, input_data: Dict[str, Any] = None):
        """流程流式执行，支持SSE和AGUI协议，返回 StreamingHttpResponse"""

        if input_data is None:
            input_data = {}

        # 提取执行上下文
        user_id = input_data.get("user_id", "")
        input_message = input_data.get("last_message", "") or input_data.get("message", "")
        session_id = input_data.get("session_id", "")
        entry_type = input_data.get("entry_type", "openai")
        logger.info(f"[SSE-Engine] 开始执行 - flow_id: {self.instance.id}, user_id: {user_id}, entry_type: {entry_type}, 节点数: {len(self.nodes)}")

        # 初始化变量管理器
        self._initialize_variables(input_data)

        # 记录用户输入对话历史
        node_id = input_data.get("node_id", "")
        self._record_conversation_history(user_id, input_message, "user", entry_type, node_id, session_id)

        # 验证流程
        validation_errors = self.validate_flow()
        if validation_errors:
            return self._create_error_response("流程验证失败")

        # 获取起始节点和最后节点
        start_node = self._get_start_node()
        last_node = self.nodes[-1] if self.nodes else None

        # 判断协议类型
        is_agui_protocol = start_node and start_node.get("type") in ["agui", "embedded_chat", "mobile", "web_chat"]
        is_openai_protocol = start_node and start_node.get("type") == "openai"

        # 检查是否需要流式执行
        needs_streaming = (is_agui_protocol or is_openai_protocol) or (last_node and last_node.get("type") == "agents")
        if not needs_streaming:
            return self._create_error_response("当前流程不支持SSE")

        # 查找目标agents节点及前置节点
        target_agent_node, nodes_to_execute_before = self._find_target_agent_node(start_node, last_node, is_agui_protocol, is_openai_protocol)
        if not target_agent_node:
            return self._create_error_response("未找到可执行的agents节点")

        # 为入口节点创建执行上下文记录（入口节点不需要真正执行，但需要记录）
        if start_node:
            self.set_start_node_variable(input_data, start_node)

        # 执行前置节点
        final_input_data = self._execute_prerequisite_nodes(nodes_to_execute_before, input_data)

        # 根据协议类型选择执行方法
        executor = self._get_node_executor(target_agent_node.get("type"))
        execute_method = None
        protocol_type = None

        if is_agui_protocol and hasattr(executor, "agui_execute"):
            execute_method = executor.agui_execute
            protocol_type = "AGUI"
        elif hasattr(executor, "sse_execute"):
            execute_method = executor.sse_execute
            protocol_type = "SSE"

        if execute_method:
            logger.info(f"[SSE-Engine] 使用{protocol_type}协议执行agents节点: {target_agent_node.get('id')}")
        else:
            logger.error(f"[SSE-Engine] agents节点不支持流式执行: {target_agent_node.get('id')}")

        if not execute_method:
            return self._create_error_response("agents节点不支持流式执行")

        # 定义一个嵌套的异步生成器函数 - 完全模仿 agui_chat.py 的工作模式
        async def generate_stream():
            """
            嵌套的异步生成器：直接调用节点的 execute_method 获取流
            """
            accumulated_content = []

            # 使用公共方法创建 agents 节点的执行上下文
            agent_node_id = target_agent_node.get("id")
            agent_context = self._create_node_execution_context(node=target_agent_node, input_data=final_input_data, status=NodeStatus.RUNNING)

            try:
                logger.info(f"[SSE-Engine] 开始流处理 - protocol: {protocol_type}, node: {node_id}")

                # 同步调用 execute_method,它会返回一个异步生成器
                async_execute = sync_to_async(execute_method, thread_sensitive=False)
                stream_generator = await async_execute(target_agent_node.get("id"), target_agent_node, final_input_data)

                logger.info(f"[SSE-Engine] 获得流生成器: {type(stream_generator)}")

                chunk_index = 0
                # 直接迭代异步生成器
                async for chunk in stream_generator:
                    chunk_index += 1
                    # 累积内容用于记录对话历史
                    if chunk.startswith("data: "):
                        try:
                            data_str = chunk[6:].strip()
                            data_json = json.loads(data_str)
                            accumulated_content.append(data_json)
                        except (json.JSONDecodeError, ValueError):
                            pass

                    yield chunk

                logger.info(f"[SSE-Engine] 流处理完成 - 共生成 {chunk_index} 个chunk")

                # 更新 agents 节点执行上下文 - 成功
                final_message = self._extract_final_message(accumulated_content)
                agent_context.end_time = time.time()
                agent_context.status = NodeStatus.COMPLETED
                agent_context.output_data = {"last_message": final_message}

                # 更新节点执行顺序
                self._update_node_execution_order(agent_node_id)

                # 记录系统输出到对话历史
                if accumulated_content:
                    threading.Thread(
                        target=lambda: self._record_conversation_history(user_id, accumulated_content, "bot", entry_type, node_id, session_id),
                        daemon=True,
                    ).start()

                # 检查是否有后续节点
                next_nodes = self._get_next_nodes(target_agent_node.get("id"), {"success": True, "data": {}})

                if next_nodes:
                    # 有后续节点：不在此处记录，让后续节点执行完成后统一记录
                    logger.info(f"[SSE-Engine] 有 {len(next_nodes)} 个后续节点，延迟记录执行结果")
                else:
                    # 没有后续节点：直接记录成功执行结果
                    # 捕获变量，避免闭包延迟绑定问题
                    captured_final_message = final_message
                    captured_start_node_type = start_node.get("type", "") if start_node else None

                    def record_success_result_in_background():
                        try:
                            self._record_execution_result(input_data, captured_final_message, True, captured_start_node_type)
                        except Exception as record_err:
                            logger.error(f"[SSE-Engine] 记录成功执行结果失败: {record_err}")

                    threading.Thread(target=record_success_result_in_background, daemon=True).start()

                # 执行后续节点(在后台异步执行,不阻塞流式响应)
                self._execute_subsequent_nodes_async(target_agent_node, accumulated_content)

            except Exception as e:
                logger.error(f"[SSE-Engine] Stream error: {e}", exc_info=True)

                # 更新 agents 节点执行上下文 - 失败
                agent_context.end_time = time.time()
                agent_context.status = NodeStatus.FAILED
                agent_context.error_message = str(e)

                # 更新节点执行顺序
                self._update_node_execution_order(agent_node_id)

                error_data = {"type": "ERROR", "error": f"流处理错误: {str(e)}", "timestamp": int(time.time() * 1000)}
                yield f"data: {json.dumps(error_data, ensure_ascii=False)}\n\n"

                # 记录失败执行结果到 WorkFlowTaskResult
                # 捕获异常信息，避免闭包引用在 except 块结束后被删除的变量
                error_msg = str(e)
                error_type_name = type(e).__name__

                def record_error_result_in_background():
                    try:
                        error_result = {"success": False, "error": error_msg, "error_type": error_type_name}
                        start_node_type = start_node.get("type", "") if start_node else None
                        self._record_execution_result(input_data, error_result, False, start_node_type)
                    except Exception as record_err:
                        logger.error(f"[SSE-Engine] 记录失败执行结果失败: {record_err}")

                threading.Thread(target=record_error_result_in_background, daemon=True).start()

        # 直接使用嵌套的异步生成器创建 StreamingHttpResponse
        response = StreamingHttpResponse(generate_stream(), content_type="text/event-stream")

        # 设置 SSE 响应头
        response["Cache-Control"] = "no-cache, no-store, must-revalidate"
        response["X-Accel-Buffering"] = "no"
        response["Pragma"] = "no-cache"
        response["Expires"] = "0"
        response["Access-Control-Allow-Origin"] = "*"
        response["Access-Control-Allow-Headers"] = "Cache-Control"
        response["Transfer-Encoding"] = "chunked"

        logger.info(f"[SSE-Engine] 返回 StreamingHttpResponse - protocol: {protocol_type}")
        return response

    def set_start_node_variable(self, input_data: dict[str, Any] | dict[Any, Any], start_node: dict[str, Any]):
        """设置入口节点的执行上下文和变量（入口节点直接标记为完成）"""
        start_node_id = start_node.get("id")

        # 使用公共方法创建执行上下文
        start_context = self._create_node_execution_context(node=start_node, input_data=input_data, status=NodeStatus.COMPLETED)

        # 入口节点直接完成，设置 output_data 和 end_time
        start_context.output_data = input_data
        start_context.end_time = time.time()

        # 更新节点执行顺序
        self._update_node_execution_order(start_node_id)

        logger.info(f"[SSE-Engine] 入口节点已记录: {start_node_id} ({start_node.get('type')})")

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
        self.execution_contexts[node_id] = context

        return context

    def _update_node_execution_order(self, node_id: str) -> int:
        """更新节点执行顺序计数器并保存到变量管理器

        Args:
            node_id: 节点ID

        Returns:
            int: 当前节点的执行顺序编号
        """
        self.execution_order += 1
        self.variable_manager.set_variable(f"node_{node_id}_index", self.execution_order)
        return self.execution_order

    def _find_target_agent_node(self, start_node, last_node, is_agui_protocol: bool, is_openai_protocol: bool):
        """查找目标agents节点及前置节点"""
        if is_agui_protocol or is_openai_protocol:
            return self._find_agent_node_via_bfs(start_node)
        else:
            # 最后节点就是agents
            target_agent_node = last_node
            nodes_to_execute_before = self.nodes[:-1] if len(self.nodes) > 1 else []
            return target_agent_node, nodes_to_execute_before

    def _find_agent_node_via_bfs(self, start_node):
        """使用BFS查找从起始节点可达的第一个agents节点"""
        from collections import deque

        queue = deque([start_node.get("id")])
        visited = {start_node.get("id")}
        path_nodes = []

        while queue:
            current_node_id = queue.popleft()
            next_node_ids = [edge.get("target") for edge in self.edges if edge.get("source") == current_node_id]

            for next_node_id in next_node_ids:
                if next_node_id in visited:
                    continue
                visited.add(next_node_id)

                next_node = self._get_node_by_id(next_node_id)
                if not next_node:
                    continue

                if next_node.get("type") == "agents":
                    return next_node, path_nodes

                path_nodes.append(next_node)
                queue.append(next_node_id)

        logger.error(f"[SSE-Engine] 起始节点是 {start_node.get('type')}，但未找到后续的 agents 节点")
        return None, []

    def _execute_prerequisite_nodes(self, nodes_to_execute_before, input_data: Dict[str, Any]):
        """执行前置节点（非流式）"""
        if not nodes_to_execute_before:
            return input_data

        logger.info(f"[SSE-Engine] 执行 {len(nodes_to_execute_before)} 个前置节点")
        temp_engine_data = input_data.copy()

        for i, node in enumerate(nodes_to_execute_before):
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

    def _create_error_response(self, error_message: str):
        """创建错误的 StreamingHttpResponse"""
        logger.error(f"[SSE-Engine] {error_message}")

        async def error_gen():
            yield f"data: {json.dumps({'result': False, 'error': error_message})}\n\n"
            yield "data: [DONE]\n\n"

        response = StreamingHttpResponse(error_gen(), content_type="text/event-stream")
        response["Cache-Control"] = "no-cache, no-store, must-revalidate"
        response["X-Accel-Buffering"] = "no"
        return response

    def _execute_subsequent_nodes_async(self, agent_node: Dict[str, Any], agent_output: Any):
        """在后台异步执行agents节点之后的节点

        Args:
            agent_node: agents节点配置
            agent_output: agents节点的输出内容
        """

        def execute_in_background():
            """后台线程执行函数"""
            all_success = True  # 跟踪所有节点是否都成功
            last_error_result = None  # 记录最后一个错误信息
            first_input_data = None  # 记录第一个节点的输入数据

            try:
                # 获取后续节点
                next_nodes = self._get_next_nodes(agent_node.get("id"), {"success": True, "data": {}})

                if not next_nodes:
                    logger.info(f"[SSE-Engine] agents节点 {agent_node.get('id')} 没有后续节点")
                    return

                logger.info(f"[SSE-Engine] 开始执行 {len(next_nodes)} 个后续节点: {next_nodes}")

                # 准备输入数据
                # 从累积的内容中提取最终消息
                final_message = self._extract_final_message(agent_output)

                # 更新全局变量
                self.variable_manager.set_variable("last_message", final_message)

                # 准备节点输入
                node_input = {"last_message": final_message}
                first_input_data = node_input.copy()

                # 执行每个后续节点
                for next_node_id in next_nodes:
                    try:
                        next_node = self._get_node_by_id(next_node_id)
                        if not next_node:
                            logger.warning(f"[SSE-Engine] 后续节点不存在: {next_node_id}")
                            continue

                        node_type = next_node.get("type")
                        executor = self._get_node_executor(node_type)

                        if not executor:
                            logger.warning(f"[SSE-Engine] 找不到节点执行器: {node_type}")
                            continue

                        # 使用公共方法创建执行上下文
                        context = self._create_node_execution_context(node=next_node, input_data=node_input, status=NodeStatus.RUNNING)

                        logger.info(f"[SSE-Engine] 执行后续节点: {next_node_id} ({node_type})")

                        # 执行节点
                        result = executor.execute(next_node_id, next_node, node_input)

                        # 更新执行上下文 - 成功
                        context.end_time = time.time()
                        context.status = NodeStatus.COMPLETED
                        context.output_data = result

                        # 更新节点执行顺序
                        self._update_node_execution_order(next_node_id)

                        logger.info(f"[SSE-Engine] 后续节点 {next_node_id} 执行完成: {result}")

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
                    logger.error(f"[SSE-Engine] 记录后续节点执行结果失败: {record_err}")

            except Exception as e:
                logger.error(f"[SSE-Engine] 后续节点执行失败: {str(e)}", exc_info=True)
                # 记录整体后续节点执行错误
                try:
                    error_result = {"success": False, "error": str(e), "error_type": type(e).__name__, "stage": "subsequent_nodes_overall"}
                    self._record_execution_result({}, error_result, False)
                except Exception as record_err:
                    logger.error(f"[SSE-Engine] 记录后续节点整体错误失败: {record_err}")

        # 在后台线程中执行
        thread = threading.Thread(target=execute_in_background, daemon=True, name="SSE-SubsequentNodes")
        thread.start()
        logger.info("[SSE-Engine] 已启动后台线程执行后续节点")

    def _extract_final_message(self, accumulated_content: list) -> str:
        """从累积的流式内容中提取最终消息

        只提取真实的文本内容，过滤掉工具调用相关的事件。

        Args:
            accumulated_content: 累积的数据列表

        Returns:
            最终消息字符串
        """
        if not accumulated_content:
            return ""

        final_msg_parts = []

        for data in accumulated_content:
            if not isinstance(data, dict):
                continue

            data_type = data.get("type", "")
            data_object = data.get("object", "")

            # 跳过 AGUI 协议中的非文本内容事件
            if data_type in self.AGUI_SKIP_TYPES:
                continue

            # 处理 OpenAI 格式的流式响应
            # 格式: {"choices": [{"delta": {"content": "..."}, ...}], "object": "chat.completion.chunk", ...}
            if data_object == "chat.completion.chunk" or "choices" in data:
                choices = data.get("choices")
                if not choices or not isinstance(choices, list):
                    continue
                for choice in choices:
                    if not isinstance(choice, dict):
                        continue
                    delta = choice.get("delta")
                    if not isinstance(delta, dict):
                        continue
                    content = delta.get("content", "")
                    if content:
                        final_msg_parts.append(content)
                continue

            # 处理 AGUI 协议的文本消息内容
            if data_type == "TEXT_MESSAGE_CONTENT":
                delta = data.get("delta", "")
                if delta:
                    final_msg_parts.append(delta)
                continue

            # 处理其他 SSE 协议格式（非 AGUI）
            # 注意：只有在没有 type 字段时才使用 fallback 逻辑
            if not data_type:
                if data_object in ["message", "content", "text"]:
                    content = data.get("content") or data.get("message") or data.get("text", "")
                    if content:
                        final_msg_parts.append(content)
                    continue

                # 尝试直接提取常见字段（仅用于无 type 的数据）
                for key in ["content", "message", "text", "delta"]:
                    value = data.get(key)
                    if value and isinstance(value, str):
                        final_msg_parts.append(value)
                        break

        final_message = "".join(final_msg_parts) if final_msg_parts else ""

        logger.info(f"[SSE-Engine] 提取的最终消息长度: {len(final_message)}")
        return final_message

    def register_node_executor(self, node_type: str, executor: Callable):
        """注册自定义节点执行器

        Args:
            node_type: 节点类型（字符串）
            executor: 执行器函数或类实例，须实现 execute(node_id, node_config, input_data) 方法
        """
        self.custom_node_executors[node_type] = executor

    def get_last_message(self) -> str:
        """获取最后执行的节点输出

        Returns:
            最后一个节点的输出内容
        """
        return self.last_message or ""

    def _record_execution_result(self, input_data: Dict[str, Any], result: Any, success: bool, start_node_type: str = None) -> None:
        """记录工作流执行结果

        Args:
            input_data: 输入数据
            result: 执行结果
            success: 是否执行成功
            start_node_type: 启动节点类型（已废弃，使用 self.entry_type）
        """
        try:
            # 使用实例的 entry_type，优先级：self.entry_type > start_node_type > 默认值
            execute_type = WorkFlowExecuteType.OPENAI  # 默认值
            effective_type = self.entry_type or start_node_type
            if effective_type:
                if effective_type.lower() in [choice[0] for choice in WorkFlowExecuteType.choices]:
                    execute_type = effective_type.lower()

            # 收集所有节点的输出数据（包括失败节点的错误信息）
            output_data = {}
            for node_id, context in self.execution_contexts.items():
                # 从变量管理器获取节点的执行信息
                node_index = self.variable_manager.get_variable(f"node_{node_id}_index")
                node_type = self.variable_manager.get_variable(f"node_{node_id}_type")
                node_name = self.variable_manager.get_variable(f"node_{node_id}_name")
                # 获取用户指定的输出参数名
                output_key = self.variable_manager.get_variable(f"node_{node_id}_output_key") or "last_message"

                # 构建节点数据
                node_data = {
                    "index": node_index,
                    "name": node_name,
                    "type": node_type,
                    "input_data": context.input_data,
                    "status": context.status.value if hasattr(context.status, "value") else str(context.status),
                }

                # 根据节点状态记录输出或错误信息
                if context.output_data:
                    node_data["output"] = context.output_data
                if context.error_message:
                    node_data["error"] = context.error_message
                    # 失败节点：使用用户指定的输出参数名存储错误信息
                    node_data["output"] = {output_key: context.error_message}

                # 只记录有实际数据的节点（有输出或有错误）
                if context.output_data or context.error_message:
                    output_data[node_id] = node_data

            # 确定状态
            status = WorkFlowTaskStatus.SUCCESS if success else WorkFlowTaskStatus.FAIL

            # 准备输入数据字符串（记录第一个输入）
            input_data_str = json.dumps(input_data, ensure_ascii=False)

            # 准备最后输出
            if isinstance(result, dict):
                last_output = json.dumps(result, ensure_ascii=False)
            elif isinstance(result, str):
                last_output = result
            else:
                last_output = str(result)

            # 创建执行结果记录
            WorkFlowTaskResult.objects.create(
                bot_work_flow=self.instance,
                status=status,
                input_data=input_data_str,
                output_data=output_data,
                last_output=last_output,
                execute_type=execute_type,
            )

            logger.info(f"工作流执行结果已记录: flow_id={self.instance.id}, status={status}")

        except Exception as e:
            logger.error(f"记录工作流执行结果失败: {str(e)}")
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

    def _serialize_execution_contexts(self) -> Dict[str, Any]:
        """将 execution_contexts 序列化为可 JSON 化的字典

        处理 NodeStatus 枚举等不可直接序列化的类型

        Returns:
            可 JSON 序列化的执行上下文字典
        """
        result = {}
        for node_id, context in self.execution_contexts.items():
            ctx_dict = {}
            for key, value in context.__dict__.items():
                # 处理枚举类型
                if hasattr(value, "value"):
                    ctx_dict[key] = value.value
                # 处理其他不可序列化的类型
                elif isinstance(value, (str, int, float, bool, list, dict, type(None))):
                    ctx_dict[key] = value
                else:
                    ctx_dict[key] = str(value)
            result[node_id] = ctx_dict
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

        logger.info(f"开始执行流程: flow_id={self.instance.id}, user_id={user_id}")

        # 验证流程
        validation_errors = self.validate_flow()
        if validation_errors:
            return {"success": False, "error": f"流程验证失败: {'; '.join(validation_errors)}", "execution_time": 0}

        try:
            # 初始化变量管理器
            self._initialize_variables(input_data)

            # 获取并验证起始节点
            start_node = self._get_start_node()
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
                    "execution_contexts": self._serialize_execution_contexts(),
                }

                # 记录失败结果到数据库
                self._record_execution_result(input_data, error_record, False, start_node.get("type", ""))

                # 返回简洁的输出格式，与成功时保持一致
                return final_output

        except Exception as e:
            execution_time = time.time() - start_time
            logger.error(f"流程执行失败: flow_id={self.instance.id}, error={str(e)}")

            error_result = {
                "success": False,
                "error": str(e),
                "variables": self.variable_manager.get_all_variables(),
                "execution_contexts": self._serialize_execution_contexts(),
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
            )
        except Exception as e:
            logger.error(f"记录{role}对话历史失败: {str(e)}")

    def _check_chain_result(self, chain_result: Dict[str, Any]) -> tuple:
        """检查节点链执行结果，判断是否有节点执行失败

        递归检查整个执行结果树，找出第一个失败的节点

        Args:
            chain_result: 节点链执行结果

        Returns:
            tuple: (is_success, error_info)
                - is_success: 是否所有节点都执行成功
                - error_info: 如果失败，包含失败节点的信息 {"node_id", "node_type", "error"}
        """
        if not isinstance(chain_result, dict):
            return True, {}

        # 检查当前结果是否失败
        if chain_result.get("success") is False:
            return False, {
                "node_id": chain_result.get("node_id"),
                "node_type": chain_result.get("node_type"),
                "error": chain_result.get("error", "未知错误"),
            }

        # 检查 current_node（如果存在）
        current_node = chain_result.get("current_node")
        if current_node and isinstance(current_node, dict):
            if current_node.get("success") is False:
                return False, {
                    "node_id": current_node.get("node_id"),
                    "node_type": current_node.get("node_type"),
                    "error": current_node.get("error", "未知错误"),
                }

        # 递归检查 next_nodes（如果存在）
        next_nodes = chain_result.get("next_nodes")
        if next_nodes and isinstance(next_nodes, dict):
            for node_id, node_result in next_nodes.items():
                is_success, error_info = self._check_chain_result(node_result)
                if not is_success:
                    return False, error_info

        return True, {}

    def _execute_node_chain(self, node_id: str, input_data: Dict[str, Any], remaining_timeout: float) -> Dict[str, Any]:
        """执行节点链

        Args:
            node_id: 节点ID
            input_data: 输入数据
            remaining_timeout: 剩余超时时间

        Returns:
            执行结果
        """
        visited = set()
        return self._execute_node_recursive(node_id, input_data, visited, remaining_timeout)

    def _execute_node_recursive(self, node_id: str, input_data: Dict[str, Any], visited: Set[str], remaining_timeout: float) -> Dict[str, Any]:
        """递归执行节点

        Args:
            node_id: 节点ID
            input_data: 输入数据
            visited: 已访问节点集合
            remaining_timeout: 剩余超时时间

        Returns:
            执行结果
        """
        # 检查超时
        if remaining_timeout <= 0:
            raise TimeoutError(f"节点执行超时: {node_id}")

        # 防止无限循环
        if node_id in visited:
            logger.warning(f"检测到节点循环访问: {node_id}")
            return {"success": True, "message": f"节点 {node_id} 已访问，跳过执行"}

        visited.add(node_id)

        # 执行当前节点
        node_result = self._execute_single_node(node_id, input_data)
        # 如果节点执行失败，直接返回
        if not node_result.get("success", True):
            return node_result

        # 获取后续节点
        next_nodes = self._get_next_nodes(node_id, node_result)

        if not next_nodes:
            # 没有后续节点，这是最后一个节点，返回当前结果
            return node_result

        # 执行后续节点
        next_results = {}
        remaining_time = remaining_timeout - 1  # 为当前节点预留1秒

        if len(next_nodes) == 1:
            # 单个后续节点，继续递归
            next_node_id = next_nodes[0]
            next_result = self._execute_node_recursive(next_node_id, node_result.get("data", node_result), visited.copy(), remaining_time)
            next_results[next_node_id] = next_result
        else:
            # 多个后续节点，并行执行
            next_results = self._execute_parallel_nodes(next_nodes, node_result.get("data", node_result), remaining_time)

        # 合并结果
        return {"success": True, "current_node": node_result, "next_nodes": next_results}

    def _execute_single_node(self, node_id: str, input_data: Dict[str, Any]) -> Dict[str, Any]:
        """执行单个节点

        Args:
            node_id: 节点ID
            input_data: 输入数据

        Returns:
            节点执行结果
        """
        # 获取节点配置
        node = self._get_node_by_id(node_id)
        if not node:
            return {"success": False, "error": f"节点不存在: {node_id}"}

        node_type = node.get("type", "")

        # 使用公共方法创建执行上下文
        context = self._create_node_execution_context(node=node, input_data=input_data, status=NodeStatus.RUNNING)

        logger.info(f"开始执行节点: {node_id} (类型: {node_type})")

        try:
            # 获取执行器
            executor = self._get_node_executor(node_type)
            if not executor:
                raise ValueError(f"找不到节点类型 {node_type} 的执行器")

            # 根据节点配置处理输入数据
            node_config = node.get("data", {}).get("config", {})
            input_key = node_config.get("inputParams", "last_message")
            output_key = node_config.get("outputParams", "last_message")

            # 检查是否是意图分类节点的目标节点（从意图分类节点路由过来的节点）
            # 如果前一个节点是意图分类节点，使用意图分类节点的前置节点输出
            intent_previous_output = self.variable_manager.get_variable("intent_previous_output")
            if intent_previous_output is not None:
                # 当前节点是意图分类后的目标节点，使用保存的前置节点输出
                logger.info(f"节点 {node_id} 使用意图分类的前置节点输出")
                input_value = intent_previous_output
                # 清除标记，避免影响后续节点
                self.variable_manager.delete_variable("intent_previous_output")
            else:
                # 从全局变量中获取输入值
                input_value = self.variable_manager.get_variable(input_key)
                if input_value is None:
                    # 如果全局变量中没有找到，使用默认值
                    input_value = input_data.get(input_key, "")

            # 准备节点执行的输入数据
            node_input_data = {input_key: input_value}
            # 执行节点
            result = executor.execute(node_id, node, node_input_data)
            # 处理输出数据到全局变量
            if result and isinstance(result, dict):
                # 获取节点的实际输出值
                output_value = result.get(output_key)
                if output_value is not None:
                    # 更新全局变量
                    if output_key == "last_message":
                        # 特殊处理：condition、branch、intent节点的last_message不更新全局变量
                        # 避免覆盖前置节点的输出
                        if node_type not in ["condition", "branch", "intent"]:
                            self.variable_manager.set_variable("last_message", output_value)
                        else:
                            logger.info(f"节点类型 {node_type} 不更新全局变量 last_message")
                    else:
                        # 非last_message的输出直接设置到全局变量
                        logger.info(f"设置全局变量 {output_key}={output_value}")
                        self.variable_manager.set_variable(output_key, output_value)

            # 更新上下文
            context.end_time = time.time()
            context.status = NodeStatus.COMPLETED
            context.output_data = result

            logger.info(f"节点 {node_id} 执行成功")

            # 更新节点执行顺序
            self._update_node_execution_order(node_id)

            # 将节点结果保存到变量管理器（保持原有的节点结果存储机制）
            self.variable_manager.set_variable(f"node_{node_id}_result", result)

            return {
                "success": True,
                "node_id": node_id,
                "node_type": node_type,
                "data": result,
                "execution_time": context.end_time - context.start_time,
            }

        except Exception as e:
            context.end_time = time.time()
            context.status = NodeStatus.FAILED
            context.error_message = str(e)

            # 更新节点执行顺序（失败节点也需要记录顺序）
            self._update_node_execution_order(node_id)

            logger.error(f"节点 {node_id} 执行失败: {str(e)}")

            return {
                "success": False,
                "node_id": node_id,
                "node_type": node_type,
                "error": str(e),
                "execution_time": context.end_time - context.start_time,
            }

    def _execute_parallel_nodes(self, node_ids: List[str], input_data: Dict[str, Any], remaining_timeout: float) -> Dict[str, Any]:
        """并行执行多个节点

        Args:
            node_ids: 节点ID列表
            input_data: 输入数据
            remaining_timeout: 剩余超时时间

        Returns:
            并行执行结果
        """
        logger.info(f"并行执行节点: {node_ids}")

        results = {}
        timeout_per_node = remaining_timeout / len(node_ids)

        with ThreadPoolExecutor(max_workers=min(len(node_ids), self.max_parallel_nodes)) as executor:
            # 提交任务
            futures = {}
            for node_id in node_ids:
                future = executor.submit(self._execute_node_recursive, node_id, input_data, set(), timeout_per_node)  # 每个并行分支使用独立的访问集合
                futures[future] = node_id

            # 收集结果
            for future in as_completed(futures, timeout=remaining_timeout):
                node_id = futures[future]
                try:
                    result = future.result()
                    results[node_id] = result

                except Exception as e:
                    logger.error(f"并行节点 {node_id} 执行失败: {str(e)}")
                    results[node_id] = {"success": False, "error": str(e), "node_id": node_id}

        return results

    def _extract_final_data_from_result(self, result: Dict[str, Any]) -> Any:
        """从复杂的执行结果中提取最终数据

        Args:
            result: 节点执行结果

        Returns:
            最终的数据输出
        """
        if not isinstance(result, dict):
            return result

        # 如果有 next_nodes，说明还有后续节点，取其中最后一个的数据
        if "next_nodes" in result and result["next_nodes"]:
            # 递归查找最深层的数据
            for node_result in result["next_nodes"].values():
                final_data = self._extract_final_data_from_result(node_result)
                if final_data is not None:
                    return final_data

        # 如果没有后续节点，返回当前节点的数据
        if "data" in result:
            return result["data"]

        return None

    def _get_node_executor(self, node_type: str):
        """获取节点执行器

        Args:
            node_type: 节点类型

        Returns:
            节点执行器实例
        """
        # 优先使用自定义执行器
        if node_type in self.custom_node_executors:
            executor = self.custom_node_executors[node_type]
            # 如果是函数，需要包装成执行器类
            if callable(executor) and not hasattr(executor, "execute"):

                class FunctionExecutor(BaseNodeExecutor):
                    def __init__(self, func, variable_manager):
                        super().__init__(variable_manager)
                        self.func = func

                    def execute(self, node_id: str, node_config: Dict[str, Any], input_data: Dict[str, Any]) -> Any:
                        return self.func(node_id, node_config, input_data)

                return FunctionExecutor(executor, self.variable_manager)
            return executor

        # 使用注册表中的执行器
        executor_class = node_registry.get_executor(node_type)
        if executor_class:
            # 对于分支节点，需要传递起始节点ID
            if node_type in ["condition", "branch"]:
                return executor_class(self.variable_manager, self.start_node_id)
            else:
                return executor_class(self.variable_manager)

        return None

    def _get_next_nodes(self, node_id: str, node_result: Dict[str, Any]) -> List[str]:
        """获取后续节点

        Args:
            node_id: 当前节点ID
            node_result: 节点执行结果

        Returns:
            后续节点ID列表
        """
        next_nodes = []

        for edge in self.edges:
            if edge.get("source") == node_id:
                # 检查边的条件
                if self._should_follow_edge(edge, node_result):
                    target = edge.get("target")
                    if target:
                        next_nodes.append(target)

        return next_nodes

    def _should_follow_edge(self, edge: Dict[str, Any], node_result: Dict[str, Any]) -> bool:
        """判断是否应该沿着这条边执行

        Args:
            edge: 边定义
            node_result: 节点执行结果

        Returns:
            是否应该执行
        """
        source_handle = edge.get("sourceHandle", "")

        # 检查是否是意图分类节点的路由边（通过sourceHandle匹配意图结果）
        intent_result = node_result.get("data", {}).get("intent_result")
        if intent_result:
            # 这是意图分类节点，检查边的sourceHandle是否匹配意图结果
            if source_handle and source_handle == intent_result:
                logger.info(f"意图路由匹配: sourceHandle={source_handle}, 意图结果={intent_result}")
                return True
            elif source_handle:
                logger.debug(f"意图路由不匹配: sourceHandle={source_handle}, 意图结果={intent_result}")
                return False
            else:
                # 没有sourceHandle的边，默认不跟随（意图节点必须有明确的sourceHandle）
                logger.debug("意图分类节点的边缺少sourceHandle，不跟随")
                return False

        # 检查是否是分支节点的条件边
        if source_handle.lower() in ["true", "false"]:
            # 这是一条分支边，需要根据分支节点的执行结果判断
            condition_result = node_result["data"].get("condition_result")
            if condition_result is not None:
                if source_handle.lower() == "true" and condition_result:
                    logger.info(f"分支边判断: true路径匹配，条件结果: {condition_result}")
                    return True
                elif source_handle.lower() == "false" and not condition_result:
                    logger.info(f"分支边判断: false路径匹配，条件结果: {condition_result}")
                    return True
                else:
                    logger.info(f"分支边判断: 路径不匹配，sourceHandle: {source_handle}, 条件结果: {condition_result}")
                    return False
            else:
                logger.warning(f"分支边缺少条件结果，edge: {edge.get('id', 'unknown')}")
                return False

        # 默认跟随边（对于非分支、非意图节点的普通边）
        return True

    def _parse_nodes(self, flow_json: Dict[str, Any]) -> List[Dict[str, Any]]:
        """解析节点定义"""
        return flow_json.get("nodes", [])

    def _parse_edges(self, flow_json: Dict[str, Any]) -> List[Dict[str, Any]]:
        """解析边定义"""
        return flow_json.get("edges", [])

    def _identify_entry_nodes(self) -> List[str]:
        """识别入口节点（没有输入边的节点）"""
        all_nodes = {node["id"] for node in self.nodes}
        target_nodes = {edge["target"] for edge in self.edges}
        return list(all_nodes - target_nodes)

    def _build_topology(self) -> TopologicalSorter:
        """构建拓扑排序器用于检测循环依赖"""
        topology = TopologicalSorter()

        # 添加所有节点
        for node in self.nodes:
            topology.add(node["id"])

        # 添加依赖关系
        for edge in self.edges:
            topology.add(edge["target"], edge["source"])

        return topology

    def _get_node_by_id(self, node_id: str) -> Optional[Dict[str, Any]]:
        """根据ID获取节点（O(1) 复杂度）"""
        return self._node_map.get(node_id)

    def get_execution_summary(self) -> Dict[str, Any]:
        """获取执行摘要"""
        return {
            "flow_id": str(self.instance.id),
            "total_nodes": len(self.nodes),
            "total_edges": len(self.edges),
            "entry_nodes": self.entry_nodes,
            "execution_contexts": self._serialize_execution_contexts(),
            "variables": self.variable_manager.get_all_variables(),
        }


# 向后兼容别名
ChatFlowClient = ChatFlowEngine
