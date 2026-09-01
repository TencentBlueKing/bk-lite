"""采集运行时枚举：与业务编排代码分离，便于复用与测试。"""

from __future__ import annotations

from enum import Enum


class SubmissionStatus(str, Enum):
    ACCEPTED = "accepted"
    DUPLICATE_ACTIVE = "duplicate_active"
    BUSY = "busy"


class RunStatus(str, Enum):
    RUNNING = "running"
    COMPLETED = "completed"
    COMPLETED_WITH_ERRORS = "completed_with_errors"
    FAILED = "failed"
    ABANDONED = "abandoned"


class LeaseAcquireStatus(str, Enum):
    ACQUIRED = "acquired"
    DUPLICATE_ACTIVE = "duplicate_active"


class PreflightStatus(str, Enum):
    REACHABLE = "reachable"
    UNREACHABLE = "unreachable"
    UNKNOWN = "unknown"


class FailureStage(str, Enum):
    """单目标失败的稳定归因；error_code 只表达具体原因。"""

    OUTBOUND_POLICY = "outbound_policy"
    IP_PRECHECK = "ip_precheck"
    ACCESS_PROBE = "access_probe"
    CREDENTIAL = "credential"
    COLLECTION = "collection"
    FRAMEWORK = "framework"


class AccessProbeStatus(str, Enum):
    READY = "ready"
    # 插件未声明廉价检查；运行时跳过 AccessProbe，以 collect 作为 CredentialAttempt
    NOT_SUPPORTED = "not_supported"
    AUTH_FAILED = "auth_failed"
    CAPABILITY_DENIED = "capability_denied"
    NO_RESPONSE = "no_response"
    TARGET_UNREACHABLE = "target_unreachable"
    SERVICE_UNAVAILABLE = "service_unavailable"
    TLS_VALIDATION_FAILED = "tls_validation_failed"
    PROTOCOL_MISMATCH = "protocol_mismatch"
    RATE_LIMITED = "rate_limited"
    MISCONFIGURED = "misconfigured"


class CollectOutcomeStatus(str, Enum):
    SUCCESS = "success"
    AUTH_FAILED = "auth_failed"
    RETRY_CREDENTIAL = "retry_credential"
    UNREACHABLE = "unreachable"
    FAILED = "failed"
    DEFERRED = "deferred"
