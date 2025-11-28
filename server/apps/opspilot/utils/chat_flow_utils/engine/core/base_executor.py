"""
基础节点执行器 - 所有节点的抽象基类
"""
from typing import Any, Dict, List

from .variable_manager import VariableManager


class BaseNodeExecutor:
    """节点执行器基类

    所有自定义节点必须继承此类并实现 execute 方法。
    可选实现 sse_execute 方法以支持流式输出。
    """

    def __init__(self, variable_manager: VariableManager):
        """初始化节点执行器

        Args:
            variable_manager: 变量管理器实例
        """
        self.variable_manager = variable_manager

    def sse_execute(self, node_id: str, node_config: Dict[str, Any], input_data: Dict[str, Any]):
        """流式执行节点（可选实现）

        Args:
            node_id: 节点ID
            node_config: 节点配置
            input_data: 输入数据

        Yields:
            流式数据块

        Raises:
            NotImplementedError: 子类未实现此方法
        """
        raise NotImplementedError(f"节点 {node_id} 不支持流式执行")

    def execute(self, node_id: str, node_config: Dict[str, Any], input_data: Dict[str, Any]) -> Any:
        """执行节点（必须实现）

        Args:
            node_id: 节点ID
            node_config: 节点配置
            input_data: 输入数据

        Returns:
            执行结果

        Raises:
            NotImplementedError: 子类未实现此方法
        """
        raise NotImplementedError(f"节点 {node_id} 必须实现 execute 方法")

    def resolve_node_params(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """解析节点参数中的模板变量

        Args:
            params: 节点参数字典

        Returns:
            解析后的参数字典
        """
        return self.variable_manager.resolve_template_dict(params)

    def validate_params(self, params: Dict[str, Any]) -> List[str]:
        """验证节点参数（可选实现）

        Args:
            params: 节点参数

        Returns:
            错误列表，空列表表示验证通过
        """
        return []
