from typing import Any

from nanoid import generate
from pydantic import BaseModel, Field

from apps.core.logger import system_mgmt_logger as logger

from .registry import get_capability_adapter_registry, get_provider_registry


# 平台内部错误（应用/manifest 配置错、provider 实现 bug）
# → 触发排查平台代码 / manifest / 配置
_PLATFORM_INTERNAL_CODES = frozenset(
    {
        "provider.invalid_config",
        "provider.invalid_response",
        "provider.not_implemented",
        "provider.operation_not_implemented",
        "provider.unavailable",
    }
)

# 外部 API 错误（远端拒绝、超时、网络问题）
# → 触发排查外部服务状态 / 凭证 / 网络
_EXTERNAL_API_CODES = frozenset(
    {
        "provider.auth_failed",
        "provider.permission_denied",
        "provider.bot_not_enabled",
        "provider.permission_unverified",
        "provider.request_failed",
        "provider.timeout",
    }
)


def _classify_test_connection_failure_tag(error_codes: list[str]) -> str:
    """根据 error codes 把 test_connection 失败分类为 platform/internal 或 external/api。

    返回 tag 用于日志前缀，让运维一眼看出根因方向（平台代码 vs 外部服务）。
    多个 code 时按优先级：platform/internal > external/api > unknown。
    """
    code_set = set(error_codes or [])
    if code_set & _PLATFORM_INTERNAL_CODES:
        return "platform/internal"
    if code_set & _EXTERNAL_API_CODES:
        return "external/api"
    return "unknown"


class CapabilityExecutionError(BaseModel):
    code: str = Field(description="平台统一错误码")
    message: str = Field(description="错误摘要")
    retryable: bool = Field(default=False, description="是否可直接重试")
    field: str = Field(default="", description="关联字段")
    detail: str = Field(default="", description="安全的排查详情")
    external_code: str = Field(default="", description="第三方错误码")
    external_request_id: str = Field(default="", description="第三方请求 ID")


class CapabilityExecutionResult(BaseModel):
    success: bool = Field(description="是否整体成功")
    summary: str = Field(description="结果摘要")
    request_id: str = Field(default_factory=lambda: generate(size=12), description="平台请求 ID")
    partial_success: bool = Field(default=False, description="是否部分成功")
    retryable: bool = Field(default=False, description="是否可直接重试")
    payload: dict[str, Any] = Field(default_factory=dict, description="能力结果负载")
    errors: list[CapabilityExecutionError] = Field(default_factory=list, description="错误列表")

    @classmethod
    def success_result(cls, summary: str, payload: dict[str, Any] | None = None):
        return cls(success=True, summary=summary, payload=payload or {})

    @classmethod
    def failed_result(
        cls,
        summary: str,
        *,
        code: str,
        retryable: bool = False,
        field: str = "",
        detail: str = "",
        external_code: str = "",
        external_request_id: str = "",
        payload: dict[str, Any] | None = None,
    ):
        return cls(
            success=False,
            summary=summary,
            retryable=retryable,
            payload=payload or {},
            errors=[
                CapabilityExecutionError(
                    code=code,
                    message=summary,
                    retryable=retryable,
                    field=field,
                    detail=detail,
                    external_code=external_code,
                    external_request_id=external_request_id,
                )
            ],
        )

    @classmethod
    def not_implemented(cls, capability_key: str, operation: str):
        return cls.failed_result(
            f"Capability '{capability_key}' does not implement operation '{operation}'",
            code="provider.operation_not_implemented",
        )

    def to_dict(self) -> dict[str, Any]:
        return self.model_dump()


class RuntimeApplicationService:
    def __init__(self):
        self.provider_registry = get_provider_registry()
        self.adapter_registry = get_capability_adapter_registry()

    def get_provider_manifest(self, provider_key: str):
        manifest = self.provider_registry.get(provider_key)
        if manifest is None:
            raise ValueError(f"Unknown provider '{provider_key}'")
        return manifest

    def _provider_unavailable_result(self, provider_key: str, *, error_type: str):
        logger.warning(
            "event=provider_unavailable pack_key=%s failed_stage=test_connection error_type=%s",
            provider_key,
            error_type,
        )
        return CapabilityExecutionResult.failed_result(
            "Provider is unavailable",
            code="provider.unavailable",
            payload={
                "provider_key": provider_key,
                "instance_status": "verification_failed",
                "capability_status": {},
                "capability_results": {},
            },
        )

    def get_adapter_class(self, provider_key: str, capability_key: str):
        manifest = self.get_provider_manifest(provider_key)
        capability = manifest.get_capability(capability_key)
        if capability is None:
            raise ValueError(f"Provider '{provider_key}' does not declare capability '{capability_key}'")
        adapter_cls = self.adapter_registry.get(capability.adapter_key)
        if adapter_cls is None:
            raise ValueError(f"Adapter '{capability.adapter_key}' is not registered")
        return adapter_cls

    def execute(self, *, provider_key: str, capability_key: str, operation: str, config: dict[str, Any], **kwargs):
        adapter_cls = self.get_adapter_class(provider_key, capability_key)
        handler = getattr(adapter_cls, operation, None)
        if not callable(handler):
            return CapabilityExecutionResult.not_implemented(capability_key, operation)

        result = handler(config=config, provider_key=provider_key, capability_key=capability_key, **kwargs)
        if isinstance(result, CapabilityExecutionResult):
            return result
        if isinstance(result, dict):
            return CapabilityExecutionResult.model_validate(result)
        raise ValueError(f"Adapter '{adapter_cls.__name__}' returned unsupported result type '{type(result)}'")

    def test_connection(self, instance, capability_key: str | None = None):
        provider_key = getattr(instance, "provider_key", "")
        manifest = self.provider_registry.get(provider_key)
        if manifest is None:
            return self._provider_unavailable_result(provider_key, error_type="unregistered")
        runtime_config = instance.get_runtime_config()
        base_adapter_key = getattr(manifest, "base_connection_adapter_key", "")
        if not capability_key and base_adapter_key:
            adapter_cls = self.adapter_registry.get(base_adapter_key)
            if adapter_cls is None:
                return self._provider_unavailable_result(provider_key, error_type="adapter_unregistered")
            result = adapter_cls.test_connection(
                config=runtime_config,
                provider_key=manifest.key,
                capability_key="base",
            )
            if isinstance(result, dict):
                result = CapabilityExecutionResult.model_validate(result)
            if not isinstance(result, CapabilityExecutionResult):
                raise ValueError(f"Adapter '{adapter_cls.__name__}' returned unsupported result type '{type(result)}'")
            return result.model_copy(
                update={
                    "payload": {
                        "provider_key": manifest.key,
                        "instance_status": "ready" if result.success else "verification_failed",
                        "capability_status": dict(getattr(instance, "capability_status", {}) or {}),
                        "capability_results": {},
                    }
                }
            )

        capability_results: dict[str, dict[str, Any]] = {}
        capability_status: dict[str, str] = {}
        failure_details: list[dict[str, Any]] = []
        failure_codes: list[str] = []
        first_failure_result: CapabilityExecutionResult | None = None
        all_success = True
        capabilities = manifest.capabilities
        if capability_key:
            capability = manifest.get_capability(capability_key)
            if capability is None:
                return self._provider_unavailable_result(provider_key, error_type="capability_unregistered")
            capabilities = [capability]

        for capability in capabilities:
            try:
                result = self.execute(
                    provider_key=manifest.key,
                    capability_key=capability.key,
                    operation="test_connection",
                    config=runtime_config,
                )
            except ValueError:
                return self._provider_unavailable_result(provider_key, error_type="adapter_unregistered")
            capability_results[capability.key] = result.to_dict()
            capability_status[capability.key] = "ready" if result.success else "verification_failed"
            all_success = all_success and result.success
            if not result.success:
                if first_failure_result is None:
                    first_failure_result = result
                error_codes = [error.code for error in (result.errors or [])]
                failure_codes.extend(error_codes)
                error_details = [
                    {
                        "code": e.code,
                        "field": e.field,
                        "external_code": e.external_code,
                        "external_request_id": e.external_request_id,
                    }
                    for e in (result.errors or [])
                ]
                failure_details.append(
                    {
                        "capability_key": capability.key,
                        "request_id": result.request_id,
                        "codes": error_codes,
                        "errors": error_details,
                    }
                )

        if failure_details:
            tag = _classify_test_connection_failure_tag(failure_codes)
            logger.warning(
                f"[{tag}] Integration instance test connection failed, "
                f"instance_id={getattr(instance, 'id', None)}, "
                f"instance_name={getattr(instance, 'name', None)!r}, "
                f"provider_key={manifest.key}, failures={failure_details}"
            )

        summary = (
            f"Provider '{manifest.key}' connection test succeeded"
            if all_success
            else first_failure_result.summary
        )
        logger.info(
            f"Integration instance test connection completed, "
            f"instance_id={getattr(instance, 'id', None)}, "
            f"instance_name={getattr(instance, 'name', None)!r}, "
            f"provider_key={manifest.key}, success={all_success}, "
            f"capability_status={capability_status}"
        )
        failed_capabilities = [
            item for item in capability_results.values() if not item["success"]
        ]
        return CapabilityExecutionResult(
            success=all_success,
            summary=summary,
            partial_success=not all_success and any(item["success"] for item in capability_results.values()),
            retryable=bool(failed_capabilities)
            and all(item["retryable"] for item in failed_capabilities),
            errors=first_failure_result.errors if first_failure_result else [],
            payload={
                "provider_key": manifest.key,
                "instance_status": "ready" if all_success else "verification_failed",
                "capability_status": capability_status,
                "capability_results": capability_results,
            },
        )
