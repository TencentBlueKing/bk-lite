"""搜索工具模块

这个模块包含了所有搜索相关的工具函数：
- duckduckgo: DuckDuckGo搜索工具
"""

# 导入所有工具函数，保持向后兼容性
from neco.llm.tools.search.duckduckgo import (
    duckduckgo_search,
)

__all__ = [
    # 搜索工具
    'duckduckgo_search',
]
