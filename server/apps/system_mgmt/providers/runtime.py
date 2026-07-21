from typing import Any

from nanoid import generate
from pydantic import BaseModel, Field

from apps.core.logger import logger

from .registry import get_capability_adapter_registry, get_provider_registry


# 平台内部错误（应用/manifest 配置错、provider 实现 bug）
# → 触发排查平台代码 / manifest / 配置
_PLATFORM_INTERNAL_CODES = frozenset(
    {
        "provider.invalid_config",
        "provider.invalid_response",
        "provider.not_implemented",
        "provider.operation_not_implemented",
    }
)

# 外部 API 错误（远端拒绝、超时、网络问题）
# → 触发排查外部服务状态 / 凭证 / 网络
_EXTERNAL_API_CODES = frozenset(
    {
        "provider.auth_failed",
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
        manifest = self.get_provider_manifest(instance.provider_key)
        runtime_config = instance.get_runtime_config()
        capability_results: dict[str, dict[str, Any]] = {}
        capability_status: dict[str, str] = {}
        failure_details: list[dict[str, Any]] = []
        failure_codes: list[str] = []
        all_success = True
        capabilities = manifest.capabilities
        if capability_key:
            capability = manifest.get_capability(capability_key)
            if capability is None:
                raise ValueError(f"Provider '{manifest.key}' does not declare capability '{capability_key}'")
            capabilities = [capability]

        for capability in capabilities:
            result = self.execute(
                provider_key=manifest.key,
                capability_key=capability.key,
                operation="test_connection",
                config=runtime_config,
            )
            capability_results[capability.key] = result.to_dict()
            capability_status[capability.key] = "ready" if result.success else "verification_failed"
            all_success = all_success and result.success
            if not result.success:
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

        summary = f"Provider '{manifest.key}' connection test succeeded" if all_success else f"Provider '{manifest.key}' connection test failed"
        logger.info(
            f"Integration instance test connection completed, "
            f"instance_id={getattr(instance, 'id', None)}, "
            f"instance_name={getattr(instance, 'name', None)!r}, "
            f"provider_key={manifest.key}, success={all_success}, "
            f"capability_status={capability_status}"
        )
        return CapabilityExecutionResult(
            success=all_success,
            summary=summary,
            partial_success=not all_success and any(item["success"] for item in capability_results.values()),
            retryable=not all_success,
            payload={
                "provider_key": manifest.key,
                "instance_status": "ready" if all_success else "verification_failed",
                "capability_status": capability_status,
                "capability_results": capability_results,
            },
        )
