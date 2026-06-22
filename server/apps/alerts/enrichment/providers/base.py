from abc import ABC, abstractmethod
from typing import Dict, List


class EnrichmentProvider(ABC):
    """丰富数据源黑盒接口。引擎不感知任何源专有语义。"""

    provider_type: str = ""

    @abstractmethod
    def fetch_batch(self, keys: List, config: Dict) -> Dict:
        """输入归一化后的 BindingKey 列表，返回 {key: list[record]}（或 {key: record}）。"""
        raise NotImplementedError


_REGISTRY: Dict[str, EnrichmentProvider] = {}


def register_provider(cls):
    """类装饰器：实例化并按 provider_type 注册（单例）。"""
    if not cls.provider_type:
        raise ValueError(f"{cls.__name__} 缺少 provider_type")
    _REGISTRY[cls.provider_type] = cls()
    return cls


def get_provider(provider_type: str) -> EnrichmentProvider:
    if provider_type not in _REGISTRY:
        raise KeyError(f"未注册的 provider_type: {provider_type}")
    return _REGISTRY[provider_type]
