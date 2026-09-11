from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Dict, List, Set


@dataclass(frozen=True)
class FetchBatchResult:
    """Provider 批量查询结果，同时区分真实未命中和查询失败。"""

    records: Dict
    failed_keys: Set = field(default_factory=set)
    budget_exhausted_keys: Set = field(default_factory=set)


class EnrichmentProvider(ABC):
    """丰富数据源黑盒接口。引擎不感知任何源专有语义。"""

    provider_type: str = ""

    @abstractmethod
    def fetch_batch(self, keys: List, config: Dict) -> Dict | FetchBatchResult:
        """返回记录；需区分失败时返回 FetchBatchResult，避免把故障写成负缓存。"""
        raise NotImplementedError


_REGISTRY: Dict[str, EnrichmentProvider] = {}


def register_provider(cls):
    """类装饰器：实例化并按 provider_type 注册（单例）。"""
    if not cls.provider_type:
        raise ValueError(f"{cls.__name__} 缺少 provider_type")
    _REGISTRY[cls.provider_type] = cls()
    return cls


def get_provider(provider_type: str) -> EnrichmentProvider:
    if provider_type == "cmdb" and provider_type not in _REGISTRY:
        # 在首次运行时加载内置源；不能依赖其他模块碰巧导入装饰器完成注册。
        from apps.alerts.enrichment.providers.cmdb import CMDBProvider

        if provider_type not in _REGISTRY:
            register_provider(CMDBProvider)
    if provider_type not in _REGISTRY:
        raise KeyError(f"未注册的 provider_type: {provider_type}")
    return _REGISTRY[provider_type]
