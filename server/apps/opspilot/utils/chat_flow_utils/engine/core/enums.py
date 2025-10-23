"""
引擎核心枚举定义
"""
from enum import Enum


class NodeStatus(Enum):
    """节点状态枚举"""

    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    SKIPPED = "skipped"
