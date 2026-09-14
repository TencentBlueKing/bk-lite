"""阿里云监控接入：按账号密钥动态查询可用地域。"""

from __future__ import annotations

from apps.core.exceptions.base_app_exception import ValidationAppException
from apps.core.logger import monitor_logger as logger
from apps.monitor.services.qcloud_regions import (
    _normalize_collect_config_ids,
    _resolve_stargazer_cloud_name,
    maybe_decrypt_posted_cloud_secret,
    resolve_stored_cloud_credentials,
)
from apps.rpc.stargazer import Stargazer

_ALIYUN_AUTH_FAILED = "AccessKey 无效或权限不足，请检查 AccessKey ID / AccessKey Secret"


def _public_aliyun_region_error(message) -> str:
    """阿里云地域拉取失败时的用户可见文案，禁止泄漏腾讯云 SDK 异常原文。"""
    text = str(message or "").strip()
    lowered = text.lower()
    if (
        "TencentCloudSDKException" in text
        or "SecretIdNotFound" in text
        or "SecretId不存在" in text
        or "invalidaccesskey" in lowered
        or "signaturedoesnotmatch" in lowered
        or "authfailure" in lowered
        or "forbidden.ram" in lowered
        or "specified access key is not found" in lowered
    ):
        return _ALIYUN_AUTH_FAILED
    if not text:
        return "获取阿里云地域失败"
    if "SDKException" in text or "requestId" in text:
        return "获取阿里云地域失败，请检查 AccessKey 是否正确且具备 ECS DescribeRegions 权限"
    return text


def _normalize_aliyun_regions(regions: list) -> list[dict]:
    normalized = []
    for region in regions or []:
        if not isinstance(region, dict):
            continue
        resource_id = region.get("resource_id") or region.get("RegionId") or region.get("Region") or ""
        resource_name = region.get("resource_name") or region.get("LocalName") or resource_id
        resource_id = str(resource_id or "").strip()
        if not resource_id:
            continue
        state = str(region.get("status") or region.get("RegionStatus") or region.get("RegionState") or "").strip().lower()
        if state and state not in ("available", "avail"):
            continue
        normalized.append(
            {
                "label": str(resource_name or resource_id),
                "value": resource_id,
                "resource_id": resource_id,
                "resource_name": str(resource_name or resource_id),
            }
        )
    return normalized


class AliyunRegionService:
    @classmethod
    def list_regions(
        cls,
        *,
        username: str = "",
        password: str = "",
        cloud_region_id=None,
        collect_config_id=None,
        actor_context=None,
    ) -> list[dict]:
        config_ids = _normalize_collect_config_ids(collect_config_id)
        if config_ids:
            username, password = resolve_stored_cloud_credentials(config_ids, actor_context)
        access_key = str(username or "").strip()
        access_secret = maybe_decrypt_posted_cloud_secret(password)
        if not access_key or not access_secret:
            raise ValidationAppException("AccessKey ID 与 AccessKey Secret 均必填")

        cloud_name = _resolve_stargazer_cloud_name(cloud_region_id)
        instance_id = f"{cloud_name}_stargazer"
        credential = {
            "model_id": "aliyun",
            "secret_id": access_key,
            "secret_key": access_secret,
        }

        try:
            result = Stargazer(instance_id=instance_id).list_regions(credential)
        except Exception as exc:
            logger.error(
                "event=aliyun_list_regions_rpc_failed failed_stage=stargazer_list_regions " "cloud_name=%s error_type=%s",
                cloud_name,
                type(exc).__name__,
                exc_info=True,
            )
            raise ValidationAppException("获取阿里云地域失败，请检查 Stargazer 是否就绪") from exc

        if not isinstance(result, dict):
            raise ValidationAppException("获取阿里云地域失败")

        if result.get("success") is False:
            raise ValidationAppException(_public_aliyun_region_error(result.get("error") or result.get("message")))

        regions_payload = result.get("regions") or {}
        if not isinstance(regions_payload, dict):
            if isinstance(regions_payload, list):
                return _normalize_aliyun_regions(regions_payload)
            raise ValidationAppException("获取阿里云地域失败")

        if regions_payload.get("success") is False:
            raise ValidationAppException(_public_aliyun_region_error(regions_payload.get("message") or result.get("error")))

        raw_regions = regions_payload.get("result")
        if raw_regions is None and isinstance(result.get("result"), list):
            raw_regions = result.get("result")
        return _normalize_aliyun_regions(raw_regions or [])
