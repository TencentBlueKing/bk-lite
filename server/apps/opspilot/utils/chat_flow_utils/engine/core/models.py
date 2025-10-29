"""
引擎核心数据模型
"""
from dataclasses import dataclass, field
from typing import Any, Dict, Optional

from .enums import NodeStatus


@dataclass
class NodeExecutionContext:
    """节点执行上下文"""

    node_id: str
    flow_id: Optional[str] = None
    status: NodeStatus = NodeStatus.PENDING
    input_data: Dict[str, Any] = field(default_factory=dict)
    output_data: Dict[str, Any] = field(default_factory=dict)
    error_message: Optional[str] = None
    start_time: Optional[float] = None
    end_time: Optional[float] = None
