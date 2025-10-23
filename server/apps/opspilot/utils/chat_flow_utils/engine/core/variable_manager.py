"""
变量管理器
"""
from typing import Any, Dict

from jinja2 import Environment, StrictUndefined


class VariableManager:
    """变量管理器"""

    def __init__(self):
        self._variables: Dict[str, Any] = {}
        # 创建 Jinja2 环境，使用 StrictUndefined 在变量不存在时抛出异常
        self._jinja_env = Environment(undefined=StrictUndefined)

    def set_variable(self, name: str, value: Any):
        """设置变量（直接存储值）"""
        self._variables[name] = value

    def get_variable(self, name: str) -> Any:
        """获取变量值"""
        return self._variables.get(name)

    def has_variable(self, name: str) -> bool:
        """检查变量是否存在"""
        return self.get_variable(name) is not None

    def get_all_variables(self) -> Dict[str, Any]:
        """获取所有变量"""
        return self._variables.copy()

    def resolve_template(self, template: str) -> str:
        """使用 Jinja2 解析模板字符串，将 {{variable_name}} 替换为实际变量值"""
        if not isinstance(template, str):
            return template

        try:
            # 创建 Jinja2 模板
            jinja_template = self._jinja_env.from_string(template)
            # 渲染模板
            return jinja_template.render(self._variables)
        except Exception:
            # 如果模板渲染失败，返回原始模板
            return template

    def resolve_template_dict(self, data: Dict[str, Any]) -> Dict[str, Any]:
        """递归解析字典中的所有模板变量"""
        result = {}
        for key, value in data.items():
            if isinstance(value, str):
                result[key] = self.resolve_template(value)
            elif isinstance(value, dict):
                result[key] = self.resolve_template_dict(value)
            elif isinstance(value, list):
                result[key] = [self.resolve_template(item) if isinstance(item, str) else item for item in value]
            else:
                result[key] = value
        return result
