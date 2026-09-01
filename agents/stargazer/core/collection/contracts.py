"""采集运行时共享契约：DTO 与 Protocol。

枚举见 ``core.collection.enums``；常量见 ``core.collection.constants``。
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from enum import Enum
from typing import Any, Mapping, Protocol

from core.collection.constants import DEFAULT_MAX_ACTIVE_TARGETS, DEFAULT_TARGET_TASK_WINDOW
from core.collection.enums import AccessProbeStatus, CollectOutcomeStatus, FailureStage, PreflightStatus
from core.collection.runtime import CollectionRequest, RunLease

# 兼容：历史调用方从 contracts 导入枚举
__all__ = [
    "AccessProbe",
    "AccessProbeResult",
    "AccessProbeStatus",
    "CollectOutcome",
    "CollectOutcomeStatus",
    "CollectionPlugin",
    "CredentialFailureResult",
    "PreflightProbe",
    "PreflightResult",
    "PreflightStatus",
    "PublishOutcome",
    "PublishReceipt",
    "PublishStatus",
    "ResultPublisher",
    "ResultSink",
    "RunSummary",
    "StructuredMetricsPayload",
    "TargetCollectionContext",
    "TargetCollectionResult",
    "TargetExecutorSettings",
    "build_collection_result_id",
    "has_publishable_metrics",
]


@dataclass(frozen=True)
class PreflightResult:
    status: PreflightStatus
    error_code: str = ""
    detail: str = ""
    connect_host: str = ""
    failed_stage: FailureStage | None = None


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
class StructuredMetricsPayload:
    """统一运行时内部的结构化配置采集指标，避免中间文本往返转换。"""

    data: Mapping[str, Any]
    error: str = ""
    round_metadata: Mapping[str, Any] | None = None


def has_publishable_metrics(value: Any) -> bool:
    """判断成功结果是否包含至少一项可编码的业务指标。"""

    if isinstance(value, StructuredMetricsPayload):
        return any(bool(rows) for rows in value.data.values())
    if isinstance(value, str):
        return bool(value.strip())
    return bool(value)


@dataclass(frozen=True)
class TargetCollectionContext:
    task_id: str
    plugin_ref: str
    fence: int
    params: Mapping[str, Any]
    owner_id: str = ""
    attempt_id: str = ""


@dataclass(frozen=True)
class CredentialFailureResult:
    credential_id: str
    error_code: str


@dataclass(frozen=True)
class TargetCollectionResult:
    target: str
    status: str
    attempts: int
    credential_id: str = ""
    error_code: str = ""
    value: Any = None
    credential_failures: tuple[CredentialFailureResult, ...] = ()
    publish_timestamp_ms: int = 0
    detail: str = ""
    failed_stage: FailureStage | None = None


class PublishStatus(str, Enum):
    CONFIRMED = "confirmed"
    RETRYABLE_FAILED = "retryable_failed"
    DELIVERY_UNKNOWN = "delivery_unknown"
    EVENT_FAILED = "event_failed"
    PERMANENT_FAILED = "permanent_failed"


@dataclass(frozen=True)
class PublishOutcome:
    status: PublishStatus
    attempts: int = 1
    error_code: str = ""

    @property
    def succeeded(self) -> bool:
        return self.status == PublishStatus.CONFIRMED


@dataclass(frozen=True)
class RunSummary:
    total: int
    collection_succeeded: int
    collection_failed: int
    unreachable: int
    deferred: int
    skipped: int
    publish_succeeded: int = 0
    publish_not_applicable: int = 0
    publish_failed: int = 0
    publish_unknown: int = 0
    publish_event_failed: int = 0
    publish_permanent_failed: int = 0

    @property
    def succeeded(self) -> int:
        """兼容旧调用方。"""
        return self.collection_succeeded

    @property
    def failed(self) -> int:
        """兼容旧调用方。"""
        return self.collection_failed

    @property
    def has_errors(self) -> bool:
        return bool(
            self.collection_failed
            or self.unreachable
            or self.publish_failed
            or self.publish_unknown
            or self.publish_event_failed
            or self.publish_permanent_failed
        )


@dataclass(frozen=True)
class TargetExecutorSettings:
    # 0 = 不限制；默认与环境变量 DEFAULT 对齐，运行时由 ApplicationSettings.from_env 注入
    max_active_targets: int = DEFAULT_MAX_ACTIVE_TARGETS
    target_task_window: int = DEFAULT_TARGET_TASK_WINDOW
    connect_timeout_seconds: float = 15.0
    plugin_timeout_seconds: float = 60.0
    publish_guard_seconds: float = 30.0
    publish_queue_timeout_seconds: float = 60.0
    publish_total_timeout_seconds: float = 120.0
    # 0 = 不限制；默认 3 = 连续 protocol_no_response 最多尝试次数
    max_no_response_attempts: int = 3
    publish_max_attempts: int = 2

    def __post_init__(self) -> None:
        if self.max_active_targets < 0:
            raise ValueError("max_active_targets must be >= 0 (0 means unlimited)")
        if self.target_task_window < 0:
            raise ValueError("target_task_window must be >= 0 (0 means unlimited)")
        if self.connect_timeout_seconds <= 0:
            raise ValueError("connect_timeout_seconds must be greater than zero")
        if self.plugin_timeout_seconds <= 0:
            raise ValueError("plugin_timeout_seconds must be greater than zero")
        if self.publish_guard_seconds <= 0:
            raise ValueError("publish_guard_seconds must be greater than zero")
        if self.publish_queue_timeout_seconds <= 0:
            raise ValueError("publish_queue_timeout_seconds must be greater than zero")
        if self.publish_total_timeout_seconds <= 0:
            raise ValueError("publish_total_timeout_seconds must be greater than zero")
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
    ) -> PreflightResult:
        ...


class CollectionPlugin(Protocol):
    async def probe(
        self,
        target: str,
        credential: Mapping[str, Any],
        context: TargetCollectionContext,
        *,
        timeout_seconds: float,
    ) -> AccessProbeResult:
        ...

    async def collect(
        self,
        target: str,
        credential: Mapping[str, Any],
        context: TargetCollectionContext,
    ) -> CollectOutcome:
        ...


class AccessProbe(Protocol):
    async def probe(
        self,
        target: str,
        credential: Mapping[str, Any],
        context: TargetCollectionContext,
        *,
        timeout_seconds: float,
    ) -> AccessProbeResult:
        ...


class ResultPublisher(Protocol):
    """执行器依赖的有界发布队列 interface。"""

    async def enqueue(
        self,
        request: CollectionRequest,
        result: TargetCollectionResult,
        lease: RunLease,
    ) -> PublishReceipt:
        ...


class ResultSink(Protocol):
    """发布队列内部依赖的最终投递 interface。"""

    async def publish_batch(
        self,
        items,
    ) -> Mapping[str, BaseException | PublishOutcome | None]:
        ...


class PublishReceipt(Protocol):
    def done(self) -> bool:
        ...

    async def wait(self) -> PublishOutcome | None:
        ...

    def cancel_if_unattempted(self) -> bool:
        ...


def build_collection_result_id(
    *,
    task_id: str,
    plugin_ref: str,
    target: str,
    fence: int,
    attempt_id: str = "",
) -> str:
    """单次运行内稳定的目标结果幂等 ID。"""
    identity = "\0".join((task_id, plugin_ref, target, str(fence), str(attempt_id or "")))
    return hashlib.sha256(identity.encode("utf-8")).hexdigest()
