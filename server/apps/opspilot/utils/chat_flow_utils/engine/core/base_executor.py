"""
基础节点执行器
"""
from typing import Any, Dict, List

from .variable_manager import VariableManager


class BaseNodeExecutor:
    def __init__(self, variable_manager: VariableManager):
        self.variable_manager = variable_manager

    def sse_execute(self, node_id: str, node_config: Dict[str, Any], input_data: Dict[str, Any]):
        """流式执行节点，子类可实现此方法，默认抛异常"""
        raise NotImplementedError("子类必须实现execute方法")

    def execute(self, node_id: str, node_config: Dict[str, Any], input_data: Dict[str, Any]) -> Any:
        """执行节点，子类必须实现此方法"""
        raise NotImplementedError("子类必须实现execute方法")

    def resolve_node_params(self, params: Dict[str, Any], node_id: str) -> Dict[str, Any]:
        """解析节点参数中的模板变量"""
        return self.variable_manager.resolve_template_dict(params)

    def validate_params(self, params: Dict[str, Any]) -> List[str]:
        """验证节点参数，返回错误列表"""
        return []
