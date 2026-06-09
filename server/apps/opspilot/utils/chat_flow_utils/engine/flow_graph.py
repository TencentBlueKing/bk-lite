"""
流程图 / 拓扑 / 路由 协作器 (FlowGraphMixin)

F026: 从 ChatFlowEngine 这个超大“上帝类”中拆出与流程图结构、拓扑校验、
节点查找、agents 节点 BFS 定位、意图路由以及边路由决策相关的纯结构逻辑。

这些方法不依赖任何需要在测试中被 patch 的模块级 ORM 名称
（WorkFlowTaskResult / WorkFlowTaskNodeResult / WorkFlowConversationHistory），
因此可以安全地拆分为 mixin，由 ChatFlowEngine 继承后绑定到同一个 self，
对外行为与导入路径完全不变（ChatFlowEngine 仍是公开门面）。

F031: 路由决策方法（_should_follow_edge / _get_next_nodes）改为通过
NodeResult 兼容读取节点结果，保持路由判定逻辑与历史完全一致。
"""
from collections import deque
from graphlib import TopologicalSorter
from typing import Any, Dict, List, Optional

from apps.core.logger import opspilot_logger as logger

from .core.node_result import NodeResult


class FlowGraphMixin:
    """流程图结构与路由决策协作器。

    依赖宿主类提供的属性：nodes / edges / _node_map / start_node_id。
    """

    # ---- 解析与拓扑 ----
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

    # ---- agents 节点定位 / 意图路由 ----
    def _find_agent_node_via_bfs(self, start_node):
        """使用BFS查找从起始节点可达的第一个agents节点

        注意：如果路径中包含意图分类节点（intent_classification），此方法只会找到
        意图分类节点并将其加入前置节点列表。实际的目标agents节点需要在执行完意图分类
        节点后，根据intent_result动态确定。
        """
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

                node_type = next_node.get("type", "")

                # 如果遇到意图分类节点，将其加入前置节点并停止搜索
                # 目标agents节点需要在执行完意图分类后动态确定
                if node_type == "intent_classification":
                    path_nodes.append(next_node)
                    logger.info(f"[SSE-Engine] BFS发现意图分类节点: {next_node_id}，需要动态路由")
                    # 返回 None 作为目标节点，表示需要动态路由
                    return None, path_nodes

                if node_type == "agents":
                    return next_node, path_nodes

                path_nodes.append(next_node)
                queue.append(next_node_id)

        logger.error(f"[SSE-Engine] 起始节点是 {start_node.get('type')}，但未找到后续的 agents 节点")
        return None, []

    def _find_agent_by_intent(self, intent_node_id: str, intent_result: str) -> Optional[Dict[str, Any]]:
        """根据意图分类结果，查找匹配的目标 agents 节点

        通过遍历 edges，找到 source 为意图分类节点且 sourceHandle 匹配意图结果的边，
        然后返回该边指向的目标节点。

        Args:
            intent_node_id: 意图分类节点的ID
            intent_result: 意图分类结果（如 "alarm_helper"）

        Returns:
            匹配的目标节点配置，如果未找到返回 None
        """
        for edge in self.edges:
            if edge.get("source") == intent_node_id and edge.get("sourceHandle") == intent_result:
                target_id = edge.get("target")
                target_node = self._get_node_by_id(target_id)
                if target_node:
                    logger.info(f"[SSE-Engine] 意图路由匹配成功: intent={intent_result!r} -> target_node={target_id} (type={target_node.get('type')})")
                    return target_node

        # 未找到匹配的边，记录可用的 sourceHandle 供调试
        available_handles = [edge.get("sourceHandle") for edge in self.edges if edge.get("source") == intent_node_id and edge.get("sourceHandle")]
        logger.warning(f"[SSE-Engine] 意图路由未找到匹配: intent={intent_result!r}, available_handles={available_handles}")
        return None

    # ---- 边路由决策 ----
    def _get_next_nodes(self, node_id: str, node_result: Dict[str, Any]) -> List[str]:
        """获取后续节点

        Args:
            node_id: 当前节点ID
            node_result: 节点执行结果（历史 dict 形态，引擎内部契约，永不流式输出）

        Returns:
            后续节点ID列表
        """
        next_nodes = []

        # 提取意图结果用于日志（通过 NodeResult 兼容读取内部契约）
        result = NodeResult.from_dict(node_result)
        intent_result = result.output.get("intent_result") if isinstance(result.output, dict) else None
        if intent_result:
            logger.info(f"[路由决策] 节点 {node_id} 的意图结果: {intent_result!r}")

        for edge in self.edges:
            if edge.get("source") != node_id:
                continue
            source_handle = edge.get("sourceHandle", "")
            target = edge.get("target")
            should_follow = self._should_follow_edge(edge, node_result)

            # 记录每条边的匹配情况
            if intent_result:
                logger.debug(f"[路由决策] 边 {edge.get('id')}: sourceHandle={source_handle!r}, target={target}, 匹配={should_follow}")

            if not should_follow:
                continue
            if target:
                next_nodes.append(target)

        # 记录最终选择的节点
        if next_nodes:
            target_nodes_info = []
            for target_id in next_nodes:
                target_node = self._get_node_by_id(target_id)
                if target_node:
                    node_name = target_node.get("data", {}).get("config", {}).get("agentName", "")
                    node_type = target_node.get("type", "")
                    target_nodes_info.append(f"{target_id}(type={node_type}, name={node_name})")
                else:
                    target_nodes_info.append(target_id)
            logger.info(f"[路由决策] 节点 {node_id} -> 下一个节点: {target_nodes_info}")
        else:
            logger.info(f"[路由决策] 节点 {node_id} 没有后续节点")

        return next_nodes

    def _should_follow_edge(self, edge: Dict[str, Any], node_result: Dict[str, Any]) -> bool:
        """判断是否应该沿着这条边执行

        Args:
            edge: 边定义
            node_result: 节点执行结果（历史 dict 形态，引擎内部契约）

        Returns:
            是否应该执行
        """
        source_handle = edge.get("sourceHandle", "")

        # 通过 NodeResult 兼容读取内部契约中的 output（即历史 dict 的 "data" 键）
        result = NodeResult.from_dict(node_result)
        output = result.output if isinstance(result.output, dict) else {}

        # 检查是否是意图分类节点的路由边（通过sourceHandle匹配意图结果）
        intent_result = output.get("intent_result")
        if intent_result:
            # 这是意图分类节点，检查边的sourceHandle是否匹配意图结果
            if source_handle and source_handle == intent_result:
                return True
            elif source_handle:
                return False
            else:
                # 没有sourceHandle的边，默认不跟随（意图节点必须有明确的sourceHandle）
                return False

        # 检查是否是分支/条件节点的条件边。
        # 通过源节点类型判断，而不是依赖 sourceHandle 字符串是否为 "true"/"false"，
        # 否则一个字面命名为 "true"/"false" 的意图标签会被误判为条件边。
        source_node = self._get_node_by_id(edge.get("source"))
        source_node_type = source_node.get("type", "") if source_node else ""
        if source_node_type in ["condition", "branch"] and source_handle.lower() in ["true", "false"]:
            condition_result = output.get("condition_result")
            if condition_result is None:
                logger.warning(f"分支边缺少条件结果，edge: {edge.get('id', 'unknown')}")
                return False
            return (source_handle.lower() == "true") == bool(condition_result)

        # 默认跟随边（对于非分支、非意图节点的普通边）
        return True
