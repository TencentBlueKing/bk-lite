"""腾讯云监控接入：按账号密钥动态查询可用地域。"""

from __future__ import annotations

from apps.core.exceptions.base_app_exception import ValidationAppException
from apps.core.logger import monitor_logger as logger
from apps.rpc.node_mgmt import NodeMgmt
from apps.rpc.stargazer import Stargazer


def _normalize_qcloud_regions(regions: list) -> list[dict]:
    normalized = []
    for region in regions or []:
        if not isinstance(region, dict):
            continue
        resource_id = region.get("resource_id") or region.get("Region") or region.get("RegionName") or ""
        resource_name = region.get("resource_name") or region.get("RegionName") or region.get("Region") or resource_id
        resource_id = str(resource_id or "").strip()
        if not resource_id:
            continue
        # DescribeRegions 可能带 RegionState；仅保留可用区，避免选后无数据。
        state = str(region.get("RegionState") or region.get("region_state") or "").strip().upper()
        if state and state != "AVAILABLE":
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


def _resolve_stargazer_cloud_name(cloud_region_id=None) -> str:
    """解析 Stargazer NATS 命名空间用的云区域名（{name}_stargazer）。"""
    cloud_list = NodeMgmt().cloud_region_list() or []
    if cloud_region_id not in (None, ""):
        for item in cloud_list:
            if not isinstance(item, dict):
                continue
            if str(item.get("id")) == str(cloud_region_id):
                name = str(item.get("name") or "").strip()
                if name:
                    return name
                break
        raise ValidationAppException("cloud_region_id 不存在")

    for item in cloud_list:
        if not isinstance(item, dict):
            continue
        if item.get("id") == 1:
            name = str(item.get("name") or "").strip()
            if name:
                return name
    for item in cloud_list:
        if not isinstance(item, dict):
            continue
        name = str(item.get("name") or "").strip()
        if name.lower() == "default":
            return name
    if cloud_list and isinstance(cloud_list[0], dict):
        name = str(cloud_list[0].get("name") or "").strip()
        if name:
            return name
    return "default"


class QCloudRegionService:
    @classmethod
    def list_regions(
        cls,
        *,
        username: str,
        password: str,
        cloud_region_id=None,
    ) -> list[dict]:
        secret_id = str(username or "").strip()
        secret_key = str(password or "").strip()
        if not secret_id or not secret_key:
            raise ValidationAppException("SecretId 与 SecretKey 均必填")

        cloud_name = _resolve_stargazer_cloud_name(cloud_region_id)
        instance_id = f"{cloud_name}_stargazer"
        credential = {
            "model_id": "qcloud",
            "secret_id": secret_id,
            "secret_key": secret_key,
        }

        try:
            result = Stargazer(instance_id=instance_id).list_regions(credential)
        except Exception as exc:
            logger.error(
                "event=qcloud_list_regions_rpc_failed failed_stage=stargazer_list_regions " "cloud_name=%s error_type=%s",
                cloud_name,
                type(exc).__name__,
                exc_info=True,
            )
            raise ValidationAppException("获取腾讯云地域失败，请检查 Stargazer 是否就绪") from exc

        if not isinstance(result, dict):
            raise ValidationAppException("获取腾讯云地域失败")

        if result.get("success") is False:
            message = result.get("error") or result.get("message") or "获取腾讯云地域失败"
            raise ValidationAppException(str(message))

        regions_payload = result.get("regions") or {}
        if not isinstance(regions_payload, dict):
            # 兼容偶发直接返回 region 列表
            if isinstance(regions_payload, list):
                return _normalize_qcloud_regions(regions_payload)
            raise ValidationAppException("获取腾讯云地域失败")

        if regions_payload.get("success") is False:
            message = regions_payload.get("message") or result.get("error") or "获取腾讯云地域失败"
            raise ValidationAppException(str(message))

        raw_regions = regions_payload.get("result")
        if raw_regions is None and isinstance(result.get("result"), list):
            raw_regions = result.get("result")
        return _normalize_qcloud_regions(raw_regions or [])
