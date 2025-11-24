"""日期时间工具模块

这个模块包含了所有日期时间相关的工具函数：
- current_time: 获取当前时间工具
"""

# 导入所有工具函数，保持向后兼容性
from neco.llm.tools.date.current_time import (
    get_current_time,
)

__all__ = [
    # 时间查询工具
    'get_current_time',
]
