"""腾讯云监控接入：按账号密钥动态查询可用地域。"""

from __future__ import annotations

import re

from apps.core.exceptions.base_app_exception import ValidationAppException
from apps.core.logger import monitor_logger as logger
from apps.core.utils.crypto.aes_crypto import AESCryptor
from apps.rpc.node_mgmt import NodeMgmt
from apps.rpc.stargazer import Stargazer

_STORED_CREDENTIALS_MISSING_TEMPLATE = (
    "event=cloud_region_stored_credentials_missing failed_stage=load_collect_config " "config_id=%s error_type=missing_child"
)
_ENV_PASSWORD_PLAIN_FALLBACK_TEMPLATE = "event=cloud_region_env_password_plain_fallback failed_stage=decrypt_env_password " "error_type=%s"


_AES_BLOB_RE = re.compile(r"^[A-Za-z0-9_-]{40,}$")


def maybe_decrypt_posted_cloud_secret(raw) -> str:
    """编辑回填的 SecretKey 是 AES 密文；明文密钥原样返回。"""
    text = str(raw or "").strip()
    if not text:
        return ""
    if not _AES_BLOB_RE.fullmatch(text):
        return text
    decoded = AESCryptor().try_decode(text)
    return decoded if decoded else text


def _normalize_collect_config_ids(value) -> list[str]:
    if value in (None, ""):
        return []
    if isinstance(value, (list, tuple, set)):
        return [str(item).strip() for item in value if item not in (None, "") and str(item).strip()]
    text = str(value).strip()
    return [text] if text else []


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


def _extract_child_username(child: dict) -> str:
    content = child.get("content")
    if not isinstance(content, dict):
        return ""
    config = content.get("config")
    if not isinstance(config, dict):
        return ""
    headers = config.get("http_headers")
    if not isinstance(headers, dict):
        return ""
    return str(headers.get("username") or "").strip()


def _extract_child_password(child: dict) -> str:
    env_config = child.get("env_config")
    if not isinstance(env_config, dict):
        return ""
    aes_obj = AESCryptor()
    for key, value in env_config.items():
        if "password" not in str(key).lower() or not value:
            continue
        raw = str(value)
        try:
            return aes_obj.decode(raw)
        except Exception as exc:
            logger.debug(
                _ENV_PASSWORD_PLAIN_FALLBACK_TEMPLATE,
                type(exc).__name__,
            )
            return raw
    return ""


def resolve_stored_cloud_credentials(collect_config_id, actor_context=None) -> tuple[str, str]:
    """从已授权的采集子配置解密云账号密钥；不信任前端回填的密文。"""
    from apps.monitor.services.node_mgmt import InstanceConfigService

    ids = _normalize_collect_config_ids(collect_config_id)
    if not ids:
        raise ValidationAppException("配置不存在或无权限")

    payload = InstanceConfigService.get_config_content(ids, actor_context)
    child = payload.get("child") if isinstance(payload, dict) else None
    if not isinstance(child, dict):
        logger.warning(
            _STORED_CREDENTIALS_MISSING_TEMPLATE,
            ",".join(ids)[:64],
        )
        raise ValidationAppException("配置不存在或无权限")

    username = _extract_child_username(child)
    password = _extract_child_password(child)
    if not username or not password:
        raise ValidationAppException("配置中缺少云账号密钥")
    return username, password


class QCloudRegionService:
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
        secret_id = str(username or "").strip()
        secret_key = maybe_decrypt_posted_cloud_secret(password)
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
