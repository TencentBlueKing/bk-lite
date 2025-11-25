"""
OpsPilot 应用信号注册

在应用启动时自动导入所有信号处理器
"""
# 导入所有信号处理器以确保它们被注册
from . import knowledge_signals  # noqa: F401
