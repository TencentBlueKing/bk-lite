"""
OpsPilot 应用信号注册

在应用启动时自动导入所有信号处理器
"""
# 导入所有信号处理器以确保它们被注册
# （旧知识库相关信号已随旧功能移除）
from apps.opspilot.signals import wiki_material_signal  # noqa: F401,E402  资料删除清理 MinIO 文件
