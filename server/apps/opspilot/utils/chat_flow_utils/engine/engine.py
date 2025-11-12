"""
聊天流程执行引擎 - ChatFlowEngine
"""
import json
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from graphlib import CycleError, TopologicalSorter
from typing import Any, Callable, Dict, List, Optional, Set

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
    def sse_execute(self, input_data: Dict[str, Any] = None, timeout: int = None):  # noqa: C901
        """流程流式执行，仅支持最后节点为agent且首节点为openai时"""
        if input_data is None:
            input_data = {}
        if timeout is None:
            timeout = self.execution_timeout

        # 获取用户ID和输入消息
        user_id = input_data.get("user_id", "")
        input_message = input_data.get("last_message", "") or input_data.get("message", "")
        # 获取入口类型，默认为 openai（SSE方式通常是openai类型）
        entry_type = input_data.get("entry_type", "openai")

        # 记录用户输入（排除celery定时触发）
        if user_id and input_message and entry_type != "celery":
            try:
                user_conversation = WorkFlowConversationHistory.objects.create(
                    bot_id=self.instance.bot_id,
                    user_id=user_id,
                    conversation_role="user",
                    conversation_content=input_message,
                    conversation_time=timezone.now(),
                    entry_type=entry_type,
                )
                logger.info(f"[SSE] 记录用户输入对话历史: conversation_id={user_conversation.id}, entry_type={entry_type}")
            except Exception as e:
                logger.error(f"[SSE] 记录用户输入对话历史失败: {str(e)}")

        # 验证流程
        validation_errors = self.validate_flow()
        if validation_errors:

            def err_gen():
                yield f"data: {json.dumps({'result': False, 'error': '流程验证失败'})}\n\n"
                yield "data: [DONE]\n\n"

            return err_gen()

        # 获取最后节点
        last_node = self.nodes[-1] if self.nodes else None
        if last_node.get("type") == "agents":
            # 先执行前置所有节点（非流式）
            if len(self.nodes) > 1:
                # 执行除最后一个节点外的所有节点
                previous_nodes = self.nodes[:-1]
                temp_engine_data = input_data.copy()

                # 按顺序执行前置节点
                for i, node in enumerate(previous_nodes):
                    node_id = node.get("id")
                    executor = self._get_node_executor(node.get("type"))

                    logger.info(f"执行前置节点 {node_id} (类型: {node.get('type')})")
                    result = executor.execute(node_id, node, temp_engine_data)

                    # 更新变量管理器和输入数据
                    self.variable_manager.set_variable(f"node_{node_id}_output", result)

                    # 将结果传递给下一个节点（使用最后输出的key作为下一个节点的输入）
                    if isinstance(result, dict):
                        temp_engine_data.update(result)

                # 用前置节点的执行结果作为最后节点的输入
                final_input_data = temp_engine_data
            else:
                final_input_data = input_data

            # 最后一个节点走sse_execute
            executor = self._get_node_executor(last_node.get("type"))
            if hasattr(executor, "sse_execute"):
                # 包装生成器以收集完整输出
                def wrapped_generator():
                    accumulated_output = []  # 累积完整输出内容

                    try:
                        for chunk in executor.sse_execute(last_node.get("id"), last_node, final_input_data):
                            # 流式输出给客户端
                            yield chunk

                            # 收集输出内容（排除 [DONE] 标记）
                            if chunk and not chunk.strip().endswith("[DONE]"):
                                # 解析 SSE 数据格式: "data: {...}\n\n"
                                if chunk.startswith("data: "):
                                    try:
                                        data_str = chunk[6:].strip()  # 去掉 "data: " 前缀
                                        if data_str:
                                            data_json = json.loads(data_str)
                                            # 提取实际内容（根据不同的响应格式）
                                            content = data_json.get("content") or data_json.get("message") or data_json.get("text", "")
                                            if content:
                                                accumulated_output.append(content)
                                    except json.JSONDecodeError:
                                        # 如果不是JSON格式，直接添加原始内容
                                        accumulated_output.append(data_str)

                        # 流式输出完成后，记录完整的系统输出（排除celery定时触发）
                        if user_id and accumulated_output and entry_type != "celery":
                            try:
                                full_output = "".join(accumulated_output)
                                bot_conversation = WorkFlowConversationHistory.objects.create(
                                    bot_id=self.instance.bot_id,
                                    user_id=user_id,
                                    conversation_role="bot",
                                    conversation_content=full_output,
                                    conversation_time=timezone.now(),
                                    entry_type=entry_type,
                                )
                                logger.info(
                                    f"[SSE] 记录系统输出对话历史: conversation_id={bot_conversation.id}, "
                                    f"output_length={len(full_output)}, entry_type={entry_type}"
                                )
                            except Exception as e:
                                logger.error(f"[SSE] 记录系统输出对话历史失败: {str(e)}")

                    except Exception as e:
                        logger.error(f"[SSE] 流式执行过程中出错: {str(e)}")
                        yield f"data: {json.dumps({'result': False, 'error': str(e)})}\n\n"
                        yield "data: [DONE]\n\n"

                return wrapped_generator()

        # 其他情况不支持流式，直接抛异常
        def err_gen():
            yield f"data: {json.dumps({'result': False, 'error': '当前流程不支持SSE'})}\n\n"
            yield "data: [DONE]\n\n"

        return err_gen()

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
            )

            logger.info(f"工作流执行结果已记录: flow_id={self.instance.id}, status={status}, execute_type={execute_type}")

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
        logger.info(f"开始执行流程 {self.instance.id}")

        # 获取用户ID和输入消息
        user_id = input_data.get("user_id", "")
        input_message = input_data.get("last_message", "") or input_data.get("message", "")

        # 验证流程
        validation_errors = self.validate_flow()
        if validation_errors:
            return {"success": False, "error": f"流程验证失败: {'; '.join(validation_errors)}", "execution_time": 0}

        try:
            # 初始化变量管理器 - 根据新的设计简化全局变量
            self.variable_manager.set_variable("flow_id", str(self.instance.id))

            # 初始化 last_message 为输入的 message 值
            initial_message = input_data.get("last_message", "")
            self.variable_manager.set_variable("last_message", initial_message)

            # 存储完整的输入数据供特殊需要时使用
            self.variable_manager.set_variable("flow_input", input_data)

            # 确定起始节点
            if self.start_node_id:
                # 如果指定了起始节点，直接使用
                chosen_start_node = self.start_node_id
            elif self.entry_nodes:
                # 如果没有指定起始节点但有入口节点，选择第一个
                chosen_start_node = self.entry_nodes[0]
            else:
                error_result = {"success": False, "error": "没有找到起始节点", "execution_time": time.time() - start_time}
                self._record_execution_result(input_data, error_result, False)
                return error_result

            # 验证选择的起始节点是否存在
            start_node = self._get_node_by_id(chosen_start_node)
            if not start_node:
                error_result = {"success": False, "error": f"指定的起始节点不存在: {chosen_start_node}", "execution_time": time.time() - start_time}
                self._record_execution_result(input_data, error_result, False)
                return error_result

            # 获取起始节点类型作为入口类型
            start_node_type = start_node.get("type", "")
            # 使用起始节点类型作为 entry_type，如果不在支持的类型中则默认为 restful
            entry_type = start_node_type if start_node_type in [choice[0] for choice in WorkFlowExecuteType.choices] else "restful"

            # 记录用户输入（排除celery定时触发）
            if user_id and input_message and entry_type != "celery":
                try:
                    user_conversation = WorkFlowConversationHistory.objects.create(
                        bot_id=self.instance.bot_id,
                        user_id=user_id,
                        conversation_role="user",
                        conversation_content=input_message,
                        conversation_time=timezone.now(),
                        entry_type=entry_type,
                    )
                    logger.info(f"记录用户输入对话历史: conversation_id={user_conversation.id}, entry_type={entry_type}")
                except Exception as e:
                    logger.error(f"记录用户输入对话历史失败: {str(e)}")

            # 从选择的起始节点开始执行
            self._execute_node_chain(chosen_start_node, input_data, timeout - (time.time() - start_time))

            execution_time = time.time() - start_time
            logger.info(f"流程执行完成，耗时 {execution_time:.2f} 秒")

            # 获取最终的 last_message 作为主要输出结果
            final_last_message = self.variable_manager.get_variable("last_message")

            # 记录系统输出（排除celery定时触发）
            if user_id and final_last_message and entry_type != "celery":
                try:
                    # 将输出结果转换为字符串
                    if isinstance(final_last_message, dict):
                        output_content = json.dumps(final_last_message, ensure_ascii=False)
                    elif isinstance(final_last_message, str):
                        output_content = final_last_message
                    else:
                        output_content = str(final_last_message)

                    bot_conversation = WorkFlowConversationHistory.objects.create(
                        bot_id=self.instance.bot_id,
                        user_id=user_id,
                        conversation_role="bot",
                        conversation_content=output_content,
                        conversation_time=timezone.now(),
                        entry_type=entry_type,
                    )
                    logger.info(f"记录系统输出对话历史: conversation_id={bot_conversation.id}, entry_type={entry_type}")
                except Exception as e:
                    logger.error(f"记录系统输出对话历史失败: {str(e)}")

            # 记录成功的执行结果
            self._record_execution_result(input_data, final_last_message, True, start_node_type)

            return final_last_message

        except Exception as e:
            execution_time = time.time() - start_time
            logger.error(f"流程执行失败: {str(e)}")
            error_result = {
                "success": False,
                "error": str(e),
                "variables": self.variable_manager.get_all_variables(),
                "execution_contexts": {k: v.__dict__ for k, v in self.execution_contexts.items()},
                "execution_time": execution_time,
            }

            # 记录失败的执行结果
            start_node_type = None
            if self.entry_nodes:
                start_node = self._get_node_by_id(self.entry_nodes[0])
                if start_node:
                    start_node_type = start_node.get("type", "")
            self._record_execution_result(input_data, error_result, False, start_node_type)

            return error_result

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

            # 处理输出数据到全局变量
            if result and isinstance(result, dict):
                # 获取节点的实际输出值
                output_value = result.get(output_key)
                if output_value is not None:
                    # 更新全局变量
                    if output_key == "last_message":
                        # 特殊处理：condition节点的last_message不更新全局变量
                        if node_type not in ["condition", "branch"]:
                            self.variable_manager.set_variable("last_message", output_value)
                    else:
                        # 非last_message的输出直接设置到全局变量
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
