"""
变量管理器 - 支持Jinja2模板渲染
"""
from typing import Any, Dict, List

from jinja2 import Environment, StrictUndefined


class VariableManager:
    """流程变量管理器

    负责管理工作流执行过程中的所有变量，支持：
    - 变量的存储和获取
    - Jinja2模板变量渲染
    - 递归解析嵌套结构中的模板
    """

    def __init__(self):
        """初始化变量管理器"""
        self._variables: Dict[str, Any] = {}
        # 创建Jinja2环境，使用StrictUndefined在变量不存在时抛出异常
        self._jinja_env = Environment(undefined=StrictUndefined)

    def set_variable(self, name: str, value: Any) -> None:
        """设置变量

        Args:
            name: 变量名
            value: 变量值
        """
        self._variables[name] = value

    def get_variable(self, name: str, default: Any = None) -> Any:
        """获取变量值

        Args:
            name: 变量名
            default: 默认值

        Returns:
            变量值，不存在则返回默认值
        """
        return self._variables.get(name, default)

    def has_variable(self, name: str) -> bool:
        """检查变量是否存在

        Args:
            name: 变量名

        Returns:
            变量是否存在
        """
        return name in self._variables

    def delete_variable(self, name: str) -> None:
        """删除变量

        Args:
            name: 变量名
        """
        self._variables.pop(name, None)

    def clear_variables(self) -> None:
        """清空所有变量"""
        self._variables.clear()

    def get_all_variables(self) -> Dict[str, Any]:
        """获取所有变量的副本

        Returns:
            变量字典的副本
        """
        return self._variables.copy()

    def resolve_template(self, template: str) -> str:
        """使用Jinja2解析模板字符串

        将 {{variable_name}} 替换为实际变量值。

        Args:
            template: 模板字符串

        Returns:
            渲染后的字符串，失败时返回原始模板
        """
        if not isinstance(template, str):
            return template

        try:
            jinja_template = self._jinja_env.from_string(template)
            return jinja_template.render(self._variables)
        except Exception:
            # 模板渲染失败时返回原始模板
            return template

    def resolve_template_dict(self, data: Dict[str, Any]) -> Dict[str, Any]:
        """递归解析字典中的所有模板变量

        Args:
            data: 包含模板的字典

        Returns:
            解析后的字典
        """
        result = {}
        for key, value in data.items():
            result[key] = self._resolve_value(value)
        return result

    def resolve_template_list(self, data: List[Any]) -> List[Any]:
        """递归解析列表中的所有模板变量

        Args:
            data: 包含模板的列表

        Returns:
            解析后的列表
        """
        return [self._resolve_value(item) for item in data]

    def _resolve_value(self, value: Any) -> Any:
        """解析单个值（递归处理）

        Args:
            value: 待解析的值

        Returns:
            解析后的值
        """
        if isinstance(value, str):
            return self.resolve_template(value)
        elif isinstance(value, dict):
            return self.resolve_template_dict(value)
        elif isinstance(value, list):
            return self.resolve_template_list(value)
        else:
            return value
