"""
流程执行工厂类
"""

from typing import Any, Dict, Optional

from apps.opspilot.models import BotWorkFlow

from .engine import ChatFlowEngine


class FlowExecutionFactory:
    """流程执行工厂"""

    @staticmethod
    def create_flow_engine(
        workflow: BotWorkFlow,
        start_node_id: str = None,
        config: Optional[Dict[str, Any]] = None,
        entry_type: str = None,
        execution_id: str = None,
    ) -> ChatFlowEngine:
        """创建流程引擎

        Args:
            workflow: 工作流实例
            start_node_id: 起始节点 ID
            config: 配置项
            entry_type: 入口类型（如 openai、agui 等）
        """
        engine = ChatFlowEngine(workflow, start_node_id, entry_type=entry_type, execution_id=execution_id)

        if config:
            # 应用配置
            engine.max_parallel_nodes = config.get("max_parallel_nodes", 5)
            engine.max_retry_count = config.get("max_retry_count", 3)
            engine.execution_timeout = config.get("execution_timeout", 300)

        return engine


# 为了向后兼容，创建一些工厂函数
def create_chat_flow_engine(
    workflow: BotWorkFlow,
    start_node_id: str = None,
    config: Optional[Dict[str, Any]] = None,
    entry_type: str = None,
    execution_id: str = None,
) -> ChatFlowEngine:
    """创建聊天流程引擎

    Args:
        workflow: 工作流实例
        start_node_id: 起始节点 ID
        config: 配置项
        entry_type: 入口类型（如 openai、agui 等）
    """
    return FlowExecutionFactory.create_flow_engine(workflow, start_node_id, config, entry_type, execution_id)
