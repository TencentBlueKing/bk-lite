"""采集运行时共享契约：DTO 与 Protocol。

枚举见 collection_enums；常量见 collection_constants。
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from typing import Any, Mapping, Protocol

from core.collection.enums import (
    AccessProbeStatus,
    CollectOutcomeStatus,
    PreflightStatus,
)
from core.collection.runtime import CollectionRequest, RunLease

# 兼容：历史调用方从 contracts 导入枚举
__all__ = [
    "AccessProbe",
    "AccessProbeResult",
    "AccessProbeStatus",
    "CollectOutcome",
    "CollectOutcomeStatus",
    "CollectionPlugin",
    "PreflightProbe",
    "PreflightResult",
    "PreflightStatus",
    "ResultPublisher",
    "RunSummary",
    "TargetCollectionContext",
    "TargetCollectionResult",
    "TargetExecutorSettings",
    "build_collection_result_id",
]


@dataclass(frozen=True)
class PreflightResult:
    status: PreflightStatus
    error_code: str = ""
    detail: str = ""


@dataclass(frozen=True)
class AccessProbeResult:
    status: AccessProbeStatus
    error_code: str = ""
    detail: str = ""
    evidence: Mapping[str, Any] | None = None


@dataclass(frozen=True)
class CollectOutcome:
    status: CollectOutcomeStatus
    value: Any = None
    error_code: str = ""
    detail: str = ""


@dataclass(frozen=True)
class TargetCollectionContext:
    task_id: str
    plugin_ref: str
    fence: int
    params: Mapping[str, Any]
    owner_id: str = ""


@dataclass(frozen=True)
class TargetCollectionResult:
    target: str
    status: str
    attempts: int
    credential_id: str = ""
    error_code: str = ""
    value: Any = None


@dataclass(frozen=True)
class RunSummary:
    total: int
    succeeded: int
    failed: int
    unreachable: int
    deferred: int
    skipped: int


@dataclass(frozen=True)
class TargetExecutorSettings:
    # 0 = 不限制；默认与环境变量 DEFAULT 对齐，运行时由 ApplicationSettings.from_env 注入
    max_active_targets: int = 2000
    target_task_window: int = 2000
    connect_timeout_seconds: float = 5.0
    plugin_timeout_seconds: float = 60.0
    publish_guard_seconds: float = 30.0
    # 0 = 不限制；默认 3 = 连续 protocol_no_response 最多尝试次数
    max_no_response_attempts: int = 3
    publish_max_attempts: int = 2

    def __post_init__(self) -> None:
        if self.max_active_targets < 0:
            raise ValueError(
                "max_active_targets must be >= 0 (0 means unlimited)"
            )
        if self.target_task_window < 0:
            raise ValueError(
                "target_task_window must be >= 0 (0 means unlimited)"
            )
        if self.connect_timeout_seconds <= 0:
            raise ValueError("connect_timeout_seconds must be greater than zero")
        if self.plugin_timeout_seconds <= 0:
            raise ValueError("plugin_timeout_seconds must be greater than zero")
        if self.publish_guard_seconds <= 0:
            raise ValueError("publish_guard_seconds must be greater than zero")
        if self.max_no_response_attempts < 0:
            raise ValueError("max_no_response_attempts must be >= 0")
        if self.publish_max_attempts <= 0:
            raise ValueError("publish_max_attempts must be greater than zero")


class PreflightProbe(Protocol):
    async def check(
        self,
        target: str,
        request: CollectionRequest,
        *,
        timeout_seconds: float,
    ) -> PreflightResult: ...


class CollectionPlugin(Protocol):
    async def probe(
        self,
        target: str,
        credential: Mapping[str, Any],
        context: TargetCollectionContext,
        *,
        timeout_seconds: float,
    ) -> AccessProbeResult: ...

    async def collect(
        self,
        target: str,
        credential: Mapping[str, Any],
        context: TargetCollectionContext,
    ) -> CollectOutcome: ...


class AccessProbe(Protocol):
    async def probe(
        self,
        target: str,
        credential: Mapping[str, Any],
        context: TargetCollectionContext,
        *,
        timeout_seconds: float,
    ) -> AccessProbeResult: ...


class ResultPublisher(Protocol):
    async def publish(
        self,
        request: CollectionRequest,
        result: TargetCollectionResult,
        lease: RunLease,
    ) -> None: ...


def build_collection_result_id(
    *,
    task_id: str,
    plugin_ref: str,
    target: str,
    fence: int,
) -> str:
    """单目标结果幂等 ID：task_id + plugin_ref + target + fence。"""
    identity = "\0".join((task_id, plugin_ref, target, str(fence)))
    return hashlib.sha256(identity.encode("utf-8")).hexdigest()
