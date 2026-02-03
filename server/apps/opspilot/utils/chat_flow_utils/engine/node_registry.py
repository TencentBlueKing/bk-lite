"""
节点注册器 - 支持动态节点创建和管理
"""
from typing import Any, Callable, Dict, Optional, Type

from ..nodes.action.action import HttpActionNode, NotifyNode
from ..nodes.agent.agent import AgentNode
from ..nodes.basic.entry_exit import EntryNode, ExitNode
from ..nodes.condition.branch import BranchNode
from ..nodes.converter.text_to_pdf import TextToPdfNode
from ..nodes.function.function import FunctionNode
from ..nodes.intent.intent_classifier import IntentClassifierNode
from .core.base_executor import BaseNodeExecutor


class NodeRegistry:
    """节点注册器 - 管理所有节点类型的注册和创建"""

    def __init__(self):
        self._node_classes: Dict[str, Type[BaseNodeExecutor]] = {}
        self._node_factories: Dict[str, Callable] = {}

        # 注册内置节点
        self._register_builtin_nodes()

    def _register_builtin_nodes(self):
        """注册内置节点类型"""
        # 基础节点
        self.register_node_class("restful", EntryNode)
        self.register_node_class("enterprise_wechat", EntryNode)
        self.register_node_class("dingtalk", EntryNode)
        self.register_node_class("wechat_official", EntryNode)
        self.register_node_class("openai", EntryNode)
        self.register_node_class("agui", EntryNode)  # AGUI入口节点
        self.register_node_class("embedded_chat", EntryNode)  # embedded_chat入口节点
        self.register_node_class("mobile", EntryNode)  # mobile入口节点
        self.register_node_class("web_chat", EntryNode)  # web_chat入口节点
        self.register_node_class("exit", ExitNode)
        self.register_node_class("celery", EntryNode)

        # 智能体节点
        self.register_node_class("agents", AgentNode)

        # 动作节点
        self.register_node_class("http", HttpActionNode)
        self.register_node_class("notification", NotifyNode)

        # 函数节点
        self.register_node_class("function", FunctionNode)

        # 转换节点
        self.register_node_class("text_to_pdf", TextToPdfNode)

        # 意图分类节点
        self.register_node_class("intent_classification", IntentClassifierNode)  # 别名

        # 向后兼容的别名
        self.register_node_class("start", EntryNode)
        self.register_node_class("end", ExitNode)
        self.register_node_class("condition", BranchNode)

    def register_node_class(self, node_type: str, node_class: Type[BaseNodeExecutor]):
        """注册节点类

        Args:
            node_type: 节点类型标识符
            node_class: 节点类，必须继承自BaseNodeExecutor
        """
        if not issubclass(node_class, BaseNodeExecutor):
            raise ValueError(f"节点类 {node_class.__name__} 必须继承自 BaseNodeExecutor")

        self._node_classes[node_type] = node_class

    def get_executor(self, node_type: str) -> Optional[Type[BaseNodeExecutor]]:
        """获取节点执行器类

        Args:
            node_type: 节点类型

        Returns:
            节点执行器类，如果不存在返回None
        """
        return self._node_classes.get(node_type)

    def get_supported_types(self) -> list:
        """获取所有支持的节点类型

        Returns:
            支持的节点类型列表
        """
        types = list(self._node_classes.keys()) + list(self._node_factories.keys())
        return list(set(types))  # 去重

    def get_node_info(self, node_type: str) -> Optional[Dict[str, Any]]:
        """获取节点信息

        Args:
            node_type: 节点类型

        Returns:
            节点信息字典，包含类名、模块等信息
        """
        if node_type in self._node_classes:
            node_class = self._node_classes[node_type]
            return {"type": "class", "class_name": node_class.__name__, "module": node_class.__module__, "doc": node_class.__doc__}

        if node_type in self._node_factories:
            factory = self._node_factories[node_type]
            return {
                "type": "factory",
                "function_name": factory.__name__ if hasattr(factory, "__name__") else str(factory),
                "module": factory.__module__ if hasattr(factory, "__module__") else "unknown",
                "doc": factory.__doc__ if hasattr(factory, "__doc__") else None,
            }

        return None


# 全局节点注册器实例
node_registry = NodeRegistry()
