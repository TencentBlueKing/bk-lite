"""
基础入口和出口节点
"""
from typing import Any, Dict

from apps.core.logger import opspilot_logger as logger
from apps.opspilot.utils.chat_flow_utils.engine.core.base_executor import BaseNodeExecutor


class EntryNode(BaseNodeExecutor):
    """入口节点"""

    def execute(self, node_id: str, node_config: Dict[str, Any], input_data: Dict[str, Any]) -> Dict[str, Any]:
        params = node_config["data"].get("config", {})
        input_key = params.get("inputParams", "last_message")
        output_key = params.get("outputParams", "last_message")
        message = input_data.get(input_key, "开始执行流程")
        logger.info(f"入口节点 {node_id}: {message}")
        return {output_key: message}


class ExitNode(BaseNodeExecutor):
    """出口节点"""

    def execute(self, node_id: str, node_config: Dict[str, Any], input_data: Dict[str, Any]) -> Dict[str, Any]:
        params = node_config["data"].get("config", {})
        input_key = params.get("inputParams", "last_message")
        output_key = params.get("outputParams", "last_message")
        message = input_data.get(input_key, "流程执行完成")
        logger.info(f"出口节点 {node_id}: {message}")
        return {output_key: message}


# 向后兼容的别名
StartNode = EntryNode
EndNode = ExitNode
