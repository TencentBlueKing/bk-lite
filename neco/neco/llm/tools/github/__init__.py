"""GitHub工具模块

这个模块包含了所有GitHub相关的工具函数，按功能分类到不同的子模块中：
- commits: Commits查询工具
"""

# 导入所有工具函数，保持向后兼容性
from neco.llm.tools.github.commits import (
    get_github_commits,
    get_github_commits_with_pagination,
)

__all__ = [
    # Commits查询工具
    'get_github_commits',
    'get_github_commits_with_pagination',
]
