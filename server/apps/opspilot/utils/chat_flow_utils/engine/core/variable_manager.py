"""
变量管理器 - 支持安全模板渲染

安全说明：
- 使用 safe_render 替代原生 Jinja2 Environment，防止 SSTI 攻击
- 仅支持简单变量插值 {{ var }} 和属性访问 {{ var.prop }}
- 禁止控制语句、过滤器、函数调用等危险操作
"""

import threading
from typing import Any, Dict, List

from apps.core.utils.safe_template import TemplateSecurityError, safe_render


class VariableManager:
    """流程变量管理器

    负责管理工作流执行过程中的所有变量，支持：
    - 变量的存储和获取
    - 安全的模板变量渲染（防止 SSTI 攻击）
    - 递归解析嵌套结构中的模板
    """

    def __init__(self):
        """初始化变量管理器"""
        self._variables: Dict[str, Any] = {}
        # 可重入锁：并行分支（ThreadPoolExecutor）共享同一个 VariableManager，
        # 多线程并发读写 _variables 会相互覆盖（如 last_message / memory_context）。
        # 使用 RLock 守护所有读写操作，保证字典级原子性，且允许同一线程嵌套调用
        # （如 resolve_template_dict -> _resolve_value -> resolve_template）。
        self._lock = threading.RLock()

    def set_variable(self, name: str, value: Any) -> None:
        """设置变量

        Args:
            name: 变量名
            value: 变量值
        """
        with self._lock:
            self._variables[name] = value

    def get_variable(self, name: str, default: Any = None) -> Any:
        """获取变量值

        Args:
            name: 变量名
            default: 默认值

        Returns:
            变量值，不存在则返回默认值
        """
        with self._lock:
            return self._variables.get(name, default)

    def delete_variable(self, name: str) -> None:
        """删除变量

        Args:
            name: 变量名
        """
        with self._lock:
            self._variables.pop(name, None)

    def get_all_variables(self) -> Dict[str, Any]:
        """获取所有变量的副本

        Returns:
            变量字典的副本
        """
        with self._lock:
            return self._variables.copy()

    def resolve_template(self, template: str) -> str:
        """使用安全模板渲染解析模板字符串

        将 {{variable_name}} 替换为实际变量值。
        使用 safe_render 防止 SSTI 攻击。

        Args:
            template: 模板字符串

        Returns:
            渲染后的字符串，失败时返回原始模板

        Raises:
            TemplateSecurityError: 模板包含危险模式时抛出
        """
        if not isinstance(template, str):
            return template

        # 在锁内快照变量，渲染在锁外进行，缩短锁持有时间并避免渲染期间阻塞其他分支
        with self._lock:
            variables = dict(self._variables)

        try:
            return safe_render(template, variables)
        except TemplateSecurityError:
            # 安全错误向上抛出，不静默处理
            raise
        except Exception:
            # 其他渲染失败时返回原始模板
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
