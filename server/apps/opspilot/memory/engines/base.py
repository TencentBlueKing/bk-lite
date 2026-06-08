"""Base Memory Engine - Abstract base class for all memory engines."""

import logging
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


@dataclass
class MemoryEntity:
    """记忆实体，标识记忆的所有者"""

    user_id: Optional[str] = None  # 用户 ID（用于个人记忆）
    organization_id: Optional[int] = None  # 组织 ID（用于团队记忆）

    def to_dict(self) -> Dict[str, Any]:
        """转换为字典"""
        result = {}
        if self.user_id:
            result["user_id"] = self.user_id
        if self.organization_id:
            result["organization_id"] = self.organization_id
        return result


@dataclass
class MemoryReadResult:
    """记忆读取结果"""

    context: str = ""  # 合并后的上下文字符串
    raw_memories: List[Dict[str, Any]] = field(default_factory=list)  # 原始记忆列表
    source: str = ""  # 来源引擎类型


@dataclass
class MemoryWriteResult:
    """记忆写入结果"""

    success: bool = False
    memory_id: Optional[str] = None
    event_id: Optional[str] = None  # Mem0 异步事件 ID
    message: str = ""


class BaseMemoryEngine(ABC):
    """记忆引擎基类

    所有记忆引擎必须继承此类并实现抽象方法。
    """

    def __init__(self, memory_space_id: int):
        """初始化引擎

        Args:
            memory_space_id: 记忆空间 ID，引擎内部查询配置
        """
        self.memory_space_id = memory_space_id
        self._memory_space = None
        self._config = None

    @property
    def memory_space(self):
        """延迟加载记忆空间对象"""
        if self._memory_space is None:
            from apps.opspilot.models import MemorySpace

            self._memory_space = MemorySpace.objects.get(id=self.memory_space_id)
        return self._memory_space

    @property
    def config(self) -> dict:
        """获取解密后的配置"""
        if self._config is None:
            self._config = self.memory_space.get_decrypted_config()
        return self._config

    @abstractmethod
    def read(
        self,
        entity: MemoryEntity,
        query: Optional[str] = None,
        top_k: int = 5,
    ) -> MemoryReadResult:
        """读取记忆

        Args:
            entity: 记忆实体（用户或组织）
            query: 查询字符串（用于语义搜索）
            top_k: 返回的最大记忆数量

        Returns:
            MemoryReadResult: 读取结果
        """
        pass

    @abstractmethod
    def write(
        self,
        entity: MemoryEntity,
        content: str,
        title: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None,
        model_id: Optional[int] = None,
    ) -> MemoryWriteResult:
        """写入记忆

        Args:
            entity: 记忆实体（用户或组织）
            content: 记忆内容
            title: 记忆标题
            metadata: 额外元数据
            model_id: 可选的模型 ID，用于覆盖记忆空间的默认模型

        Returns:
            MemoryWriteResult: 写入结果
        """
        pass

    @abstractmethod
    def delete(
        self,
        entity: MemoryEntity,
        memory_id: Optional[str] = None,
    ) -> bool:
        """删除记忆

        Args:
            entity: 记忆实体（用户或组织）
            memory_id: 记忆 ID（如为 None 则删除该实体的所有记忆）

        Returns:
            bool: 是否删除成功
        """
        pass

    def test_connection(self) -> Dict[str, Any]:
        """测试连接

        Returns:
            dict: {"success": bool, "message": str}
        """
        return {"success": True, "message": "连接测试未实现"}

    @classmethod
    @abstractmethod
    def get_engine_info(cls) -> Dict[str, str]:
        """获取引擎信息

        Returns:
            dict: {"type": str, "name": str, "description": str}
        """
        pass

    @classmethod
    @abstractmethod
    def get_config_schema(cls) -> List[Dict[str, Any]]:
        """获取配置参数定义

        Returns:
            list: 字段定义列表，每项包含:
                - name: 字段名
                - label: 显示标签
                - type: 字段类型 (text/password/number/select/json)
                - required: 是否必填
                - encrypted: 是否加密存储
                - default: 默认值
                - options: select 类型的选项列表
        """
        pass
