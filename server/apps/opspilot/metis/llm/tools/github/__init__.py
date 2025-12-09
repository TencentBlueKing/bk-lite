"""GitHub工具模块

这个模块包含了所有GitHub相关的工具函数，按功能分类到不同的子模块中：
- commits: Commits查询工具
"""

# 工具集构造参数元数据
# 注意：GitHub 工具的 token 是作为工具参数传入的，不是构造参数
# 这里暂不定义构造参数
from apps.opspilot.metis.llm.tools.github.commits import get_github_commits, get_github_commits_with_pagination
CONSTRUCTOR_PARAMS = []

# 导入所有工具函数，保持向后兼容性

__all__ = [
    # Commits查询工具
    "get_github_commits",
    "get_github_commits_with_pagination",
]
