"""
节点执行 协作器 (NodeRunnerMixin)

F026: 从 ChatFlowEngine 拆出“同步执行模型”相关逻辑——节点链递归执行、
单节点执行、并行分支执行、执行器解析以及节点链结果校验。

F031: 单节点执行的结果构造改用类型化的 NodeResult（ok/output/error），
随后通过 to_dict() 还原为与历史完全一致的内部 dict 契约，
保证下游 (_check_chain_result / _record_execution_result / _get_next_nodes) 行为不变。
node_result 为引擎内部契约，绝不流式输出。

注意：节点执行明细的持久化 (_record_node_execution_result) 仍由宿主类
ChatFlowEngine 提供，以保留其对模块级 ORM 名称的引用（便于测试 patch）。
并发相关的 _state_lock / 执行顺序计数同样由宿主类维护。
"""

import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Any, Dict, List, Set

from apps.core.logger import opspilot_logger as logger

from .core.base_executor import BaseNodeExecutor
from .core.enums import NodeStatus
from .core.node_result import NodeResult
from .node_registry import node_registry


class NodeRunnerMixin:
    """同步执行模型协作器（节点链 / 单节点 / 并行分支）。"""

    def _check_chain_result(self, chain_result: Dict[str, Any]) -> tuple:
        """检查节点链执行结果，判断是否有节点执行失败

        递归检查整个执行结果树，找出第一个失败的节点

        Args:
            chain_result: 节点链执行结果（内部 dict 契约）

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
            执行结果（内部 dict 契约）
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
            执行结果（内部 dict 契约）
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
        # 如果节点执行失败，直接返回（通过 NodeResult 兼容读取 success 语义）
        if not NodeResult.from_dict(node_result).ok:
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
            节点执行结果（内部 dict 契约）
        """
        # 获取节点配置
        node = self._get_node_by_id(node_id)
        if not node:
            return NodeResult(ok=False, error=f"节点不存在: {node_id}").to_dict()

        node_type = node.get("type", "")
        self._raise_if_interrupted(input_data, node_type)

        # 使用公共方法创建执行上下文
        context = self._create_node_execution_context(node=node, input_data=input_data, status=NodeStatus.RUNNING)

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

            # 节点以 in-band {"success": False} 表达业务失败（如 agent 节点 LLM 调用失败、意图越界）。
            # 必须转成失败的 NodeResult，否则 _check_chain_result 只看包装层 success=True 会把失败
            # 当成功——错误结果被当正常回复发给用户、WorkFlowTaskResult 被误记为成功
            # （同步执行路径：celery / nats / 第三方渠道，非流式）。
            if isinstance(result, dict) and result.get("success") is False:
                context.end_time = time.time()
                context.status = NodeStatus.FAILED
                error_text = result.get("error") or result.get(output_key) or "节点执行失败"
                context.error_message = str(error_text)
                context.output_data = result
                self._update_node_execution_order(node_id)
                self._record_node_execution_result(node_id, context)
                logger.warning(f"节点 {node_id}({node_type}) 业务失败: {error_text}")
                return NodeResult(
                    ok=False,
                    node_id=node_id,
                    node_type=node_type,
                    error=str(error_text),
                    execution_time=context.end_time - context.start_time,
                ).to_dict()

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
                        # 非last_message的输出直接设置到全局变量
                        self.variable_manager.set_variable(output_key, output_value)

            # 更新上下文
            context.end_time = time.time()
            context.status = NodeStatus.COMPLETED
            context.output_data = result

            # 更新节点执行顺序
            self._update_node_execution_order(node_id)
            self._record_node_execution_result(node_id, context)

            # 将节点结果保存到变量管理器（保持原有的节点结果存储机制）
            self.variable_manager.set_variable(f"node_{node_id}_result", result)

            return NodeResult(
                ok=True,
                node_id=node_id,
                node_type=node_type,
                output=result,
                execution_time=context.end_time - context.start_time,
            ).to_dict()

        except Exception as e:
            context.end_time = time.time()
            context.status = NodeStatus.FAILED
            context.error_message = str(e)

            # 更新节点执行顺序（失败节点也需要记录顺序）
            self._update_node_execution_order(node_id)
            self._record_node_execution_result(node_id, context)

            logger.exception(f"节点 {node_id} 执行失败: {str(e)}")

            return NodeResult(
                ok=False,
                node_id=node_id,
                node_type=node_type,
                error=str(e),
                execution_time=context.end_time - context.start_time,
            ).to_dict()

    def _execute_parallel_nodes(self, node_ids: List[str], input_data: Dict[str, Any], remaining_timeout: float) -> Dict[str, Any]:
        """并行执行多个节点

        Args:
            node_ids: 节点ID列表
            input_data: 输入数据
            remaining_timeout: 剩余超时时间

        Returns:
            并行执行结果（内部 dict 契约）
        """
        results = {}
        timeout_per_node = remaining_timeout / len(node_ids)

        with ThreadPoolExecutor(max_workers=min(len(node_ids), self.max_parallel_nodes)) as executor:
            # 提交任务
            futures = {}
            for node_id in node_ids:
                if self._check_interrupt_requested():
                    break
                future = executor.submit(self._execute_node_recursive, node_id, input_data, set(), timeout_per_node)  # 每个并行分支使用独立的访问集合
                futures[future] = node_id

            # 收集结果
            for future in as_completed(futures, timeout=remaining_timeout):
                node_id = futures[future]
                try:
                    result = future.result()
                    results[node_id] = result

                except Exception as e:
                    logger.exception(f"并行节点 {node_id} 执行失败: {str(e)}")
                    results[node_id] = NodeResult(ok=False, node_id=node_id, error=str(e)).to_dict()

        return results

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
