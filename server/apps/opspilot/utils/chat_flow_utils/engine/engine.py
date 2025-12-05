"""
聊天流程执行引擎 - ChatFlowEngine
"""

import json
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
                    logger.info(f"[SSE-Engine] Yielding chunk #{chunk_index}, length: {len(chunk)}")
                    yield chunk

                logger.info(f"[SSE-Engine] 流处理完成 - 共生成 {chunk_index} 个chunk")

            except Exception as e:
                logger.error(f"[SSE-Engine] Stream error: {e}", exc_info=True)
                error_data = {"type": "ERROR", "error": f"流处理错误: {str(e)}", "timestamp": int(time.time() * 1000)}
                yield f"data: {json.dumps(error_data, ensure_ascii=False)}\n\n"

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

            result = executor.execute(node_id, node, temp_engine_data)

            self.variable_manager.set_variable(f"node_{node_id}_output", result)
            if isinstance(result, dict):
                temp_engine_data.update(result)

        return temp_engine_data

    def _create_streaming_generator(
        self,
        execute_method,
        target_agent_node,
        final_input_data: Dict[str, Any],
        user_id: str,
        entry_type: str,
        is_agui_protocol: bool,
        node_id: str = "",
    ):
        """创建流式输出生成器（支持异步）"""

        async def wrapped_async_generator():
            """异步包装生成器，用于AGUI协议"""
            accumulated_output = []

            try:
                # 在异步上下文中调用同步的 execute_method，使用 sync_to_async
                # 将同步方法包装为异步方法
                async_execute = sync_to_async(execute_method, thread_sensitive=False)
                async_gen = await async_execute(target_agent_node.get("id"), target_agent_node, final_input_data)

                chunk_count = 0
                async for chunk in async_gen:
                    chunk_count += 1
                    chunk_str = chunk.decode("utf-8") if isinstance(chunk, bytes) else str(chunk)

                    # 过滤统计信息
                    if chunk_str.startswith("# STATS:"):
                        continue

                    # 立即 yield,确保流式输出
                    logger.debug(f"[SSE-Engine-AGUI] Yielding chunk #{chunk_count}, length: {len(chunk_str)}")
                    yield chunk

                    # 收集输出内容
                    self._accumulate_output(chunk_str, accumulated_output, is_agui_protocol)

                logger.info(f"[SSE-Engine-AGUI] 流式输出完成 - 总共 {chunk_count} 个chunk")

                # 记录完整输出 - 在异步上下文中使用 sync_to_async
                await sync_to_async(self._record_bot_output, thread_sensitive=False)(
                    user_id, accumulated_output, entry_type, node_id, final_input_data["session_id"]
                )

            except Exception as e:
                logger.error(f"[SSE-Engine] 流式执行过程中出错: {str(e)}")
                logger.exception(e)
                yield f"data: {json.dumps({'result': False, 'error': str(e)})}\n\n"
                yield "data: [DONE]\n\n"

        # AGUI协议返回异步生成器
        if is_agui_protocol:
            return wrapped_async_generator()

        # 非AGUI协议也返回异步生成器（统一处理）
        async def wrapped_sse_generator():
            """异步包装生成器，用于SSE/OpenAI协议"""
            accumulated_output = []

            try:
                # 在异步上下文中调用同步的 execute_method
                async_execute = sync_to_async(execute_method, thread_sensitive=False)
                async_gen = await async_execute(target_agent_node.get("id"), target_agent_node, final_input_data)

                async for chunk in async_gen:
                    chunk_str = chunk.decode("utf-8") if isinstance(chunk, bytes) else str(chunk)

                    # 过滤统计信息
                    if chunk_str.startswith("# STATS:"):
                        continue

                    yield chunk

                    # 收集输出内容
                    self._accumulate_output(chunk_str, accumulated_output, is_agui_protocol)

                # 记录完整输出 - 在异步上下文中使用 sync_to_async
                await sync_to_async(self._record_bot_output, thread_sensitive=False)(
                    user_id, accumulated_output, entry_type, node_id, final_input_data["session_id"]
                )

            except Exception as e:
                logger.error(f"[SSE-Engine] 流式执行过程中出错: {str(e)}")
                logger.exception(e)
                yield f"data: {json.dumps({'result': False, 'error': str(e)})}\n\n"
                yield "data: [DONE]\n\n"

        return wrapped_sse_generator()

    def _accumulate_output(self, chunk_str: str, accumulated_output: List[str], is_agui_protocol: bool):
        """累积输出内容"""
        if chunk_str and not chunk_str.strip().endswith("[DONE]"):
            if chunk_str.startswith("data: "):
                data_str = chunk_str[6:].strip()
                try:
                    if data_str:
                        data_json = json.loads(data_str)
                        if is_agui_protocol:
                            if data_json.get("type") == "TEXT_MESSAGE_CONTENT":
                                delta = data_json.get("delta", "")
                                if delta:
                                    accumulated_output.append(delta)
                        else:
                            content = data_json.get("content") or data_json.get("message") or data_json.get("text", "")
                            if content:
                                accumulated_output.append(content)
                except json.JSONDecodeError:
                    accumulated_output.append(data_str)

    def _record_bot_output(self, user_id: str, accumulated_output: List[str], entry_type: str, node_id: str = "", session_id: str = ""):
        """记录机器人输出对话历史"""
        if user_id and accumulated_output and entry_type != "celery":
            try:
                full_output = "".join(accumulated_output)
                WorkFlowConversationHistory.objects.create(
                    bot_id=self.instance.bot_id,
                    node_id=node_id,
                    user_id=user_id,
                    conversation_role="bot",
                    conversation_content=full_output,
                    conversation_time=timezone.now(),
                    entry_type=entry_type,
                    session_id=session_id,
                )
            except Exception as e:
                logger.error(f"[SSE] 记录系统输出对话历史失败: {str(e)}")

    def _create_error_generator(self, error_message: str):
        """创建错误生成器"""
        logger.error(f"[SSE-Engine] {error_message}")

        def err_gen():
            yield f"data: {json.dumps({'result': False, 'error': error_message})}\n\n"
            yield "data: [DONE]\n\n"

        return err_gen()

    def _create_error_response(self, error_message: str):
        """创建错误的 StreamingHttpResponse"""
        from django.http import StreamingHttpResponse

        logger.error(f"[SSE-Engine] {error_message}")

        async def error_gen():
            yield f"data: {json.dumps({'result': False, 'error': error_message})}\n\n"
            yield "data: [DONE]\n\n"

        response = StreamingHttpResponse(error_gen(), content_type="text/event-stream")
        response["Cache-Control"] = "no-cache, no-store, must-revalidate"
        response["X-Accel-Buffering"] = "no"
        return response

    """聊天流程执行引擎"""

    def __init__(self, instance: BotWorkFlow, start_node_id: str = None):
        self.instance = instance
        self.start_node_id = start_node_id
        self.variable_manager = VariableManager()
        self.execution_contexts: Dict[str, NodeExecutionContext] = {}

        # 用于跟踪最后执行的节点输出
        self.last_message = None

        # 用于跟踪节点执行顺序
        self.execution_order = 0

        # 解析流程图
        self.nodes = self._parse_nodes(instance.flow_json)
        self.edges = self._parse_edges(instance.flow_json)

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
            start_node_type: 启动节点类型
        """
        try:
            # 确定执行类型
            execute_type = WorkFlowExecuteType.OPENAI  # 默认值
            if start_node_type:
                if start_node_type.lower() in [choice[0] for choice in WorkFlowExecuteType.choices]:
                    execute_type = start_node_type.lower()

            # 收集所有节点的输出数据
            output_data = {}
            for node_id, context in self.execution_contexts.items():
                if context.output_data:
                    # 从变量管理器获取节点的执行信息
                    node_index = self.variable_manager.get_variable(f"node_{node_id}_index")
                    node_type = self.variable_manager.get_variable(f"node_{node_id}_type")
                    node_name = self.variable_manager.get_variable(f"node_{node_id}_name")

                    output_data[node_id] = {
                        "index": node_index,
                        "name": node_name,
                        "type": node_type,
                        "input_data": context.input_data,
                        "output": context.output_data,
                    }

            # 确定状态
            status = WorkFlowTaskStatus.SUCCESS if success else WorkFlowTaskStatus.FAIL

            # 准备输入数据字符串（记录第一个输入）
            input_data_str = json.dumps(input_data, ensure_ascii=False)

            # 准备最后输出
            last_output = ""
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
                session_id=input_data.get("session_id", ""),
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
                error_result = {"success": False, "error": error_msg, "execution_time": time.time() - start_time}
                self._record_execution_result(input_data, error_result, False)
                return error_result

            # 确定入口类型并记录用户输入
            entry_type = self._determine_entry_type(start_node)
            node_id = input_data.get("node_id", "")
            session_id = input_data.get("session_id", "")
            self._record_conversation_history(user_id, input_message, "user", entry_type, node_id, session_id)

            # 执行节点链
            self._execute_node_chain(chosen_start_node, input_data, timeout - (time.time() - start_time))

            # 获取执行结果并记录
            execution_time = time.time() - start_time
            final_last_message = self.variable_manager.get_variable("last_message")

            logger.info("===== 流程执行完成 =====")
            logger.info(f"flow_id={self.instance.id}, 耗时={execution_time:.2f}秒")
            logger.info(f"最终 last_message 值: {final_last_message}")
            logger.info(f"所有变量: {self.variable_manager.get_all_variables()}")
            logger.info("========================")

            # 记录系统输出
            self._record_conversation_history(user_id, final_last_message, "bot", entry_type, node_id, session_id)
            self._record_execution_result(input_data, final_last_message, True, start_node.get("type", ""))

            return final_last_message

        except Exception as e:
            execution_time = time.time() - start_time
            logger.error(f"流程执行失败: flow_id={self.instance.id}, error={str(e)}")

            error_result = {
                "success": False,
                "error": str(e),
                "variables": self.variable_manager.get_all_variables(),
                "execution_contexts": {k: v.__dict__ for k, v in self.execution_contexts.items()},
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

        # 创建执行上下文
        context = NodeExecutionContext(node_id=node_id, flow_id=str(self.instance.id))
        context.start_time = time.time()
        context.status = NodeStatus.RUNNING
        context.input_data = input_data
        self.execution_contexts[node_id] = context

        node_type = node.get("type", "")
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

            # 从全局变量中获取输入值
            input_value = self.variable_manager.get_variable(input_key)
            if input_value is None:
                # 如果全局变量中没有找到，使用默认值
                input_value = input_data.get(input_key, "")

            # 准备节点执行的输入数据
            node_input_data = {input_key: input_value}

            # 执行节点
            result = executor.execute(node_id, node, node_input_data)

            logger.info(f"节点 {node_id} 执行结果: result={result}, output_key={output_key}")

            # 处理输出数据到全局变量
            if result and isinstance(result, dict):
                # 获取节点的实际输出值
                output_value = result.get(output_key)
                logger.info(f"节点 {node_id} 输出值: output_key={output_key}, output_value={output_value}")
                if output_value is not None:
                    # 更新全局变量
                    if output_key == "last_message":
                        # 特殊处理：condition节点的last_message不更新全局变量
                        if node_type not in ["condition", "branch"]:
                            logger.info(f"更新全局变量 last_message={output_value}")
                            self.variable_manager.set_variable("last_message", output_value)
                    else:
                        # 非last_message的输出直接设置到全局变量
                        logger.info(f"设置全局变量 {output_key}={output_value}")
                        self.variable_manager.set_variable(output_key, output_value)

            # 更新上下文
            context.end_time = time.time()
            context.status = NodeStatus.COMPLETED
            context.output_data = result

            logger.info(f"节点 {node_id} 执行成功")

            # 增加执行顺序计数
            self.execution_order += 1

            # 获取节点名称
            node_name = node.get("data", {}).get("label", "") or node.get("data", {}).get("name", "") or node_id

            # 将节点结果保存到变量管理器（保持原有的节点结果存储机制）
            self.variable_manager.set_variable(f"node_{node_id}_result", result)

            # 记录节点执行信息（顺序、类型、名称）
            self.variable_manager.set_variable(f"node_{node_id}_index", self.execution_order)
            self.variable_manager.set_variable(f"node_{node_id}_type", node_type)
            self.variable_manager.set_variable(f"node_{node_id}_name", node_name)

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
        # 检查是否是分支节点的条件边
        source_handle = edge.get("sourceHandle", "").lower()
        if source_handle in ["true", "false"]:
            # 这是一条分支边，需要根据分支节点的执行结果判断
            condition_result = node_result["data"].get("condition_result")
            if condition_result is not None:
                if source_handle == "true" and condition_result:
                    logger.info(f"分支边判断: true路径匹配，条件结果: {condition_result}")
                    return True
                elif source_handle == "false" and not condition_result:
                    logger.info(f"分支边判断: false路径匹配，条件结果: {condition_result}")
                    return True
                else:
                    logger.info(f"分支边判断: 路径不匹配，sourceHandle: {source_handle}, 条件结果: {condition_result}")
                    return False
            else:
                logger.warning(f"分支边缺少条件结果，edge: {edge.get('id', 'unknown')}")
                return False
        # 默认跟随边（对于非分支节点的普通边）
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
        """根据ID获取节点"""
        for node in self.nodes:
            if node.get("id") == node_id:
                return node
        return None

    def get_execution_summary(self) -> Dict[str, Any]:
        """获取执行摘要"""
        return {
            "flow_id": str(self.instance.id),
            "total_nodes": len(self.nodes),
            "total_edges": len(self.edges),
            "entry_nodes": self.entry_nodes,
            "execution_contexts": {k: v.__dict__ for k, v in self.execution_contexts.items()},
            "variables": self.variable_manager.get_all_variables(),
        }


# 向后兼容别名
ChatFlowClient = ChatFlowEngine
