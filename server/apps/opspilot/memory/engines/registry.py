"""Memory Engine Registry - Central registry for memory engines."""

import logging
from typing import Dict, List, Type

from apps.opspilot.memory.engines.base import BaseMemoryEngine

logger = logging.getLogger(__name__)


def check_sdk_availability() -> Dict[str, bool]:
    """检查各引擎 SDK 是否可用

    Returns:
        dict: {"mem0": bool, "zep": bool, "httpx": bool}
    """
    availability = {}

    # 检查 mem0
    try:
        import mem0  # noqa

        availability["mem0"] = True
    except ImportError:
        availability["mem0"] = False

    # 检查 zep-cloud
    try:
        import zep_cloud  # noqa

        availability["zep"] = True
    except ImportError:
        availability["zep"] = False

    # 检查 httpx
    try:
        import httpx  # noqa

        availability["httpx"] = True
    except ImportError:
        availability["httpx"] = False

    return availability


class MemoryEngineRegistry:
    """记忆引擎注册表

    管理所有已注册的记忆引擎，提供引擎获取、列表、Schema 查询功能。
    """

    _engines: Dict[str, Type[BaseMemoryEngine]] = {}

    @classmethod
    def register(cls, engine_type: str, engine_class: Type[BaseMemoryEngine]) -> None:
        """注册引擎

        Args:
            engine_type: 引擎类型标识 (如 "local", "mem0")
            engine_class: 引擎类
        """
        cls._engines[engine_type] = engine_class
        logger.info(f"Registered memory engine: {engine_type}")

    @classmethod
    def get_engine(cls, memory_space_id: int) -> BaseMemoryEngine:
        """获取引擎实例

        Args:
            memory_space_id: 记忆空间 ID

        Returns:
            BaseMemoryEngine: 引擎实例

        Raises:
            ValueError: 引擎类型未注册
            MemorySpace.DoesNotExist: 记忆空间不存在
        """
        from apps.opspilot.models import MemorySpace

        memory_space = MemorySpace.objects.get(id=memory_space_id)
        engine_type = memory_space.storage_type

        if engine_type not in cls._engines:
            raise ValueError(f"Unknown memory engine type: {engine_type}")

        engine_class = cls._engines[engine_type]
        return engine_class(memory_space_id)

    @classmethod
    def list_engines(cls) -> List[Dict[str, str]]:
        """列出所有已注册的引擎

        Returns:
            list: 引擎信息列表
        """
        result = []
        for engine_type, engine_class in cls._engines.items():
            try:
                info = engine_class.get_engine_info()
                result.append(info)
            except Exception as e:
                logger.error(f"Failed to get engine info for {engine_type}: {e}")
        return result

    @classmethod
    def get_schema(cls, engine_type: str) -> Dict:
        """获取引擎配置 Schema

        Args:
            engine_type: 引擎类型

        Returns:
            dict: 包含引擎信息和字段定义

        Raises:
            ValueError: 引擎类型未注册
        """
        if engine_type not in cls._engines:
            raise ValueError(f"Unknown memory engine type: {engine_type}")

        engine_class = cls._engines[engine_type]
        info = engine_class.get_engine_info()
        fields = engine_class.get_config_schema()

        return {
            "type": info.get("type", engine_type),
            "name": info.get("name", engine_type),
            "description": info.get("description", ""),
            "fields": fields,
        }

    @classmethod
    def is_registered(cls, engine_type: str) -> bool:
        """检查引擎是否已注册"""
        return engine_type in cls._engines

    @classmethod
    def get_engine_class(cls, engine_type: str) -> Type[BaseMemoryEngine]:
        """获取引擎类"""
        if engine_type not in cls._engines:
            raise ValueError(f"Unknown memory engine type: {engine_type}")
        return cls._engines[engine_type]
