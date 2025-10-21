"""
节点注册器 - 支持动态节点创建和管理
"""
import importlib
from typing import Any, Callable, Dict, Optional, Type

from apps.core.logger import opspilot_logger as logger

from ..nodes.action.action import HttpActionNode, NotifyNode
from ..nodes.agent.agent import AgentNode
from ..nodes.basic.entry_exit import EntryNode, ExitNode
from ..nodes.condition.branch import BranchNode
from ..nodes.function.function import FunctionNode
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
        self.register_node_class("openai", EntryNode)
        self.register_node_class("exit", ExitNode)
        self.register_node_class("celery", EntryNode)

        # 智能体节点
        self.register_node_class("agents", AgentNode)

        # 动作节点
        self.register_node_class("http", HttpActionNode)
        self.register_node_class("notification", NotifyNode)

        # 函数节点
        self.register_node_class("function", FunctionNode)

        # 向后兼容的别名
        self.register_node_class("start", EntryNode)
        self.register_node_class("end", ExitNode)
        self.register_node_class("condition", BranchNode)

        logger.info("内置节点类型注册完成")

    def register_node_class(self, node_type: str, node_class: Type[BaseNodeExecutor]):
        """注册节点类

        Args:
            node_type: 节点类型标识符
            node_class: 节点类，必须继承自BaseNodeExecutor
        """
        if not issubclass(node_class, BaseNodeExecutor):
            raise ValueError(f"节点类 {node_class.__name__} 必须继承自 BaseNodeExecutor")

        self._node_classes[node_type] = node_class
        logger.info(f"注册节点类: {node_type} -> {node_class.__name__}")

    def register_node_factory(self, node_type: str, factory: Callable):
        """注册节点工厂函数

        Args:
            node_type: 节点类型标识符
            factory: 工厂函数，接受variable_manager参数，返回BaseNodeExecutor实例
        """
        self._node_factories[node_type] = factory
        logger.info(f"注册节点工厂: {node_type}")

    def create_node(self, node_type: str, variable_manager=None) -> Optional[BaseNodeExecutor]:
        """创建节点实例

        Args:
            node_type: 节点类型
            variable_manager: 变量管理器

        Returns:
            节点实例，如果类型不支持则返回None
        """
        # 优先使用工厂函数
        if node_type in self._node_factories:
            factory = self._node_factories[node_type]
            return factory(variable_manager)

        # 使用节点类
        if node_type in self._node_classes:
            node_class = self._node_classes[node_type]
            return node_class(variable_manager)

        logger.warning(f"未找到节点类型: {node_type}")
        return None

    def get_executor(self, node_type: str) -> Optional[Type[BaseNodeExecutor]]:
        """获取节点执行器类

        Args:
            node_type: 节点类型

        Returns:
            节点执行器类，如果不存在返回None
        """
        return self._node_classes.get(node_type)

    def is_supported(self, node_type: str) -> bool:
        """检查是否支持指定的节点类型

        Args:
            node_type: 节点类型

        Returns:
            是否支持
        """
        return node_type in self._node_classes or node_type in self._node_factories

    def get_supported_types(self) -> list:
        """获取所有支持的节点类型

        Returns:
            支持的节点类型列表
        """
        types = list(self._node_classes.keys()) + list(self._node_factories.keys())
        return list(set(types))  # 去重

    def unregister_node_type(self, node_type: str):
        """注销节点类型

        Args:
            node_type: 节点类型
        """
        removed = False
        if node_type in self._node_classes:
            del self._node_classes[node_type]
            removed = True

        if node_type in self._node_factories:
            del self._node_factories[node_type]
            removed = True

        if removed:
            logger.info(f"注销节点类型: {node_type}")
        else:
            logger.warning(f"尝试注销不存在的节点类型: {node_type}")

    def load_node_from_module(self, node_type: str, module_path: str, class_name: str):
        """从模块动态加载节点类

        Args:
            node_type: 节点类型标识符
            module_path: 模块路径，如 'myapp.nodes.custom_node'
            class_name: 类名
        """
        try:
            module = importlib.import_module(module_path)
            node_class = getattr(module, class_name)
            self.register_node_class(node_type, node_class)
            logger.info(f"从模块 {module_path} 加载节点类 {class_name} 成功")
        except (ImportError, AttributeError) as e:
            logger.error(f"从模块 {module_path} 加载节点类 {class_name} 失败: {str(e)}")
            raise

    def load_nodes_from_config(self, config: Dict[str, Dict[str, str]]):
        """从配置批量加载节点类

        Args:
            config: 配置字典，格式为:
                {
                    "node_type": {
                        "module": "module.path",
                        "class": "ClassName"
                    }
                }
        """
        for node_type, node_config in config.items():
            try:
                module_path = node_config["module"]
                class_name = node_config["class"]
                self.load_node_from_module(node_type, module_path, class_name)
            except Exception as e:
                logger.error(f"加载节点类型 {node_type} 失败: {str(e)}")

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

    def list_all_nodes(self) -> Dict[str, Dict[str, Any]]:
        """列出所有注册的节点

        Returns:
            所有节点的信息字典
        """
        all_nodes = {}
        for node_type in self.get_supported_types():
            all_nodes[node_type] = self.get_node_info(node_type)
        return all_nodes


# 全局节点注册器实例
node_registry = NodeRegistry()
