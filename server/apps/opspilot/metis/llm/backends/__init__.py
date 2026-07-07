"""DeepAgents 自定义存储后端（backends）。

提供将 deepagents 文件系统抽象映射到 BK-Lite 既有基础设施（如 MinIO 对象存储）
的适配器实现。
"""

from apps.opspilot.metis.llm.backends.minio_backend import MinIOBackend

__all__ = ["MinIOBackend"]
