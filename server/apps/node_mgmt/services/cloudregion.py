import re
import os
import uuid

import requests
from django.core.cache import cache

from apps.core.exceptions.base_app_exception import BaseAppException
from apps.core.logger import node_logger as logger
from apps.core.utils.crypto.aes_crypto import AESCryptor
from apps.core.utils.webhook_tls import get_webhook_tls_verify
from apps.node_mgmt.models import SidecarEnv
from apps.node_mgmt.models.cloud_region import CloudRegion
from apps.node_mgmt.constants.cloudregion_service import CloudRegionServiceConstants
from apps.node_mgmt.constants.database import CloudRegionConstants, EnvVariableConstants
from apps.node_mgmt.constants.node import NodeConstants
from apps.node_mgmt.constants.controller import ControllerConstants
from apps.node_mgmt.services.sidecar_cache import build_sidecar_env_cache_key, invalidate_sidecar_env_cache
from apps.node_mgmt.utils.token_auth import generate_node_token


class RegionService:
    @staticmethod
    def get_region_service_instance_id(cloud_region_name: str, service_name: str) -> str:
        """返回云区域级服务的实例 ID。

        云区域环境通过 webhookd proxy 部署时，会将 ``ZONE_NAME`` 注入到
        ``NATS_INSTANCE_ID``，因此 region 级 ``nats-executor`` 的实例 ID
        固定等于 ``cloud_region.name``；``stargazer`` 则在此基础上追加
        ``_stargazer`` 后缀。

        注意：这与节点/采集器路径中使用 ``node.id`` 作为实例 ID 的语义不同，
        两者不能混用。
        """
        if service_name == CloudRegionServiceConstants.NATS_EXECUTOR_SERVICE_NAME:
            return cloud_region_name
        if service_name == CloudRegionServiceConstants.STARGAZER_SERVICE_NAME:
            return f"{cloud_region_name}_stargazer"
        raise BaseAppException(f"Unsupported cloud region service: {service_name}")

    @staticmethod
    def _decode_env_rows(env_rows, keys=None):
        variables = {}
        selected_keys = set(keys) if keys is not None else None
        aes_obj = AESCryptor()
        for env_row in env_rows:
            if selected_keys is not None and env_row["key"] not in selected_keys:
                continue

            if env_row["type"] == "secret":
                try:
                    variables[env_row["key"]] = aes_obj.decode(env_row["value"])
                except Exception as error:
                    logger.warning(
                        "Failed to decode cloud region secret env %s for cloud region cache read: %s",
                        env_row["key"],
                        error,
                    )
                    variables[env_row["key"]] = env_row["value"]
            else:
                variables[env_row["key"]] = env_row["value"]
        return variables

    @staticmethod
    def _get_cloud_region_env_rows(cloud_region_id):
        """获取云区域环境变量"""
        cache_key = build_sidecar_env_cache_key(cloud_region_id)
        cached_env_rows = cache.get(cache_key)
        if cached_env_rows is not None:
            return cached_env_rows

        env_rows = list(SidecarEnv.objects.filter(cloud_region_id=cloud_region_id).values("key", "value", "type"))
        cache.set(cache_key, env_rows, ControllerConstants.E_CACHE_TIMEOUT)
        return env_rows

    @staticmethod
    def get_cloud_region_envconfig(cloud_region_id, keys=None):
        return RegionService._decode_env_rows(RegionService._get_cloud_region_env_rows(cloud_region_id), keys=keys)

    @staticmethod
    def get_deploy_script(data: dict):
        """获取云区域代理服务部署脚本，调用 webhookd /infra/proxy 接口"""
        try:
            cloud_region_id = int(data["cloud_region_id"])
        except (TypeError, ValueError):
            raise BaseAppException("Invalid cloud_region_id: must be an integer")

        cloud_region = CloudRegion.objects.filter(id=cloud_region_id).first()
        if not cloud_region:
            logger.warning(f"Cloud region not found: {cloud_region_id}")
            raise BaseAppException("Cloud region not found")

        env_vars = RegionService._get_env_vars_dict(cloud_region_id)

        webhook_url = env_vars.get("WEBHOOK_SERVER_URL") or os.getenv("WEBHOOK_SERVER_URL")
        if not webhook_url:
            logger.error(f"Missing WEBHOOK_SERVER_URL for cloud region {cloud_region_id}")
            raise BaseAppException("Webhook configuration missing")

        server_url = env_vars.get("NODE_SERVER_URL")
        nats_url = env_vars.get("NATS_SERVERS")
        nats_username = env_vars.get("NATS_USERNAME")
        nats_password = env_vars.get(NodeConstants.NATS_PASSWORD_KEY)
        nats_monitor_username = os.getenv("NATS_ADMIN_USERNAME") or os.getenv("DEFAULT_ZONE_VAR_NATS_ADMIN_USERNAME")
        nats_monitor_password = os.getenv(NodeConstants.NATS_ADMIN_PASSWORD_KEY) or os.getenv("DEFAULT_ZONE_VAR_NATS_ADMIN_PASSWORD")

        missing_vars = []
        if not server_url:
            missing_vars.append("NODE_SERVER_URL")
        if not nats_url:
            missing_vars.append("NATS_SERVERS")
        if not nats_username:
            missing_vars.append("NATS_USERNAME")
        if not nats_password:
            missing_vars.append(NodeConstants.NATS_PASSWORD_KEY)
        if not nats_monitor_username:
            missing_vars.append("NATS_ADMIN_USERNAME")
        if not nats_monitor_password:
            missing_vars.append(NodeConstants.NATS_ADMIN_PASSWORD_KEY)
        if missing_vars:
            logger.error(
                "Missing required environment variables in cloud region %s: %s",
                cloud_region_id,
                ", ".join(missing_vars),
            )
            raise BaseAppException("Cloud region environment configuration is incomplete")

        proxy_ip = cloud_region.proxy_address
        if not proxy_ip:
            logger.error(f"Missing proxy_address for cloud region {cloud_region_id}")
            raise BaseAppException("Cloud region proxy_address not configured")

        node_id = uuid.uuid4().hex
        api_token = generate_node_token(node_id, proxy_ip, "system")
        redis_password = uuid.uuid4().hex[:12]

        region_executor_instance_id = RegionService.get_region_service_instance_id(
            cloud_region.name,
            CloudRegionServiceConstants.NATS_EXECUTOR_SERVICE_NAME,
        )

        webhook_params = {
            "node_id": node_id,
            "zone_id": str(cloud_region_id),
            "zone_name": cloud_region.name,
            "server_url": server_url,
            "nats_url": nats_url,
            "nats_username": nats_username,
            "nats_password": nats_password,
            "api_token": api_token,
            "redis_password": redis_password,
            "proxy_ip": proxy_ip,
            "nats_monitor_username": nats_monitor_username,
            "nats_monitor_password": nats_monitor_password,
            "traefik_web_port": env_vars.get("TRAEFIK_WEB_PORT", "443"),
        }

        webhook_api_url = f"{webhook_url.rstrip('/')}/infra/proxy"

        try:
            logger.info(
                "Generating deploy script for cloud region %s with region executor instance_id=%s",
                cloud_region_id,
                region_executor_instance_id,
            )
            response = requests.post(
                webhook_api_url,
                json=webhook_params,
                headers={"Content-Type": "application/json"},
                timeout=CloudRegionServiceConstants.WEBHOOK_REQUEST_TIMEOUT,
                verify=get_webhook_tls_verify(),
            )

            if response.status_code != 200:
                logger.error(f"Webhook API error: status={response.status_code}, region={cloud_region_id}, body={response.text}")
                raise BaseAppException("Failed to generate deploy script")

            webhook_response = response.json()
            if webhook_response.get("status") == "error":
                error_msg = webhook_response.get("message", "Unknown error")
                logger.error(f"Webhook returned error for region {cloud_region_id}: {error_msg}")
                raise BaseAppException(f"Webhook error: {error_msg}")

            deploy_script = webhook_response.get("install_script")
            if not deploy_script or not deploy_script.strip():
                logger.error(f"Empty deploy script returned for region {cloud_region_id}")
                raise BaseAppException("Invalid response from webhook API")

            logger.info(f"Successfully retrieved deploy script for cloud region {cloud_region_id}")
            return deploy_script

        except requests.Timeout:
            logger.error(f"Webhook API timeout for cloud region {cloud_region_id}")
            raise BaseAppException("Deploy script request timeout")
        except requests.RequestException as e:
            logger.error(f"Webhook API request failed for region {cloud_region_id}: {str(e)}")
            raise BaseAppException("Failed to connect to webhook service")
        except BaseAppException:
            raise
        except Exception as e:
            logger.exception(f"Unexpected error generating deploy script for region {cloud_region_id}")
            raise BaseAppException("Failed to generate deploy script")

    @staticmethod
    def _get_env_vars_dict(cloud_region_id: int) -> dict:
        """获取云区域环境变量并解密密文类型"""
        env_vars = {}
        aes_crypto = AESCryptor()
        for obj in SidecarEnv.objects.filter(cloud_region_id=cloud_region_id):
            if obj.type == "secret":
                env_vars[obj.key] = aes_crypto.decode(obj.value)
            else:
                env_vars[obj.key] = obj.value
        return env_vars

    @staticmethod
    def _extract_default_address(value):
        """从默认云区域的环境变量中提取 IP 地址或域名

        Args:
            value: 环境变量值，如 "https://10.10.41.149:443" 或 "10.10.41.149:4223"

        Returns:
            str: 提取的地址，如 "10.10.41.149"
        """
        # 匹配 IP 地址或域名（不包含端口）
        # 支持以下格式：
        # 1. https://10.10.41.149:443
        # 2. 10.10.41.149:4223
        # 3. https://api.example.com:443
        # 4. https://[2001:db8::1]:443 (IPv6)

        # 先尝试匹配 IPv6 格式 [xxx]
        ipv6_match = re.search(r"\[([^\]]+)\]", value)
        if ipv6_match:
            return f"[{ipv6_match.group(1)}]"

        # 匹配普通 IP 或域名
        match = re.search(r"(?:https?://)?([^:/]+)", value)
        if match:
            return match.group(1)
        return None

    @staticmethod
    def _replace_address(value, old_address, new_address):
        """在环境变量中替换地址

        Args:
            value: 原始值，如 "https://10.10.41.149:443"
            old_address: 旧地址，如 "10.10.41.149"
            new_address: 新地址，如 "local.host"

        Returns:
            str: 替换后的值，如 "https://local.host:443"
        """
        if not old_address or not new_address:
            return value
        return value.replace(old_address, new_address)

    @staticmethod
    def _sync_proxy_address_env_var(cloud_region_id: int, proxy_address: str) -> int:
        """同步云区域代理地址环境变量 PROXY_ADDRESS。"""
        normalized_proxy_address = proxy_address or ""
        env_var, created = SidecarEnv.objects.get_or_create(
            cloud_region_id=cloud_region_id,
            key=EnvVariableConstants.PROXY_ADDRESS_KEY,
            defaults={
                "value": normalized_proxy_address,
                "type": EnvVariableConstants.TYPE_NORMAL,
                "description": "云区域代理地址",
                "is_pre": False,
            },
        )

        if created:
            logger.info(f"Created PROXY_ADDRESS env var for cloud region {cloud_region_id}: {normalized_proxy_address}")
            return 1

        update_fields = []
        if env_var.value != normalized_proxy_address:
            env_var.value = normalized_proxy_address
            update_fields.append("value")
        if env_var.type != EnvVariableConstants.TYPE_NORMAL:
            env_var.type = EnvVariableConstants.TYPE_NORMAL
            update_fields.append("type")
        if env_var.is_pre:
            env_var.is_pre = False
            update_fields.append("is_pre")
        if not env_var.description:
            env_var.description = "云区域代理地址"
            update_fields.append("description")

        if update_fields:
            env_var.save(update_fields=update_fields)
            logger.info(f"Updated PROXY_ADDRESS env var for cloud region {cloud_region_id}: {normalized_proxy_address}")
            return 1

        return 0

    @staticmethod
    def _get_default_proxy_address() -> str | None:
        """从默认云区域环境变量中提取默认代理地址。"""
        default_env_var = SidecarEnv.objects.filter(
            cloud_region_id=CloudRegionConstants.DEFAULT_CLOUD_REGION_ID,
            key=NodeConstants.SERVER_URL_KEY,
            is_pre=True,
        ).first()

        if not default_env_var:
            logger.warning("Could not find NODE_SERVER_URL in default cloud region")
            return None

        default_address = RegionService._extract_default_address(default_env_var.value)
        if not default_address:
            logger.warning("Could not extract default address from NODE_SERVER_URL")
            return None

        return default_address

    @staticmethod
    def _sync_proxy_address_replace_env_vars(
        cloud_region_id: int,
        old_proxy_address: str,
        new_proxy_address: str,
        default_proxy_address: str | None = None,
    ) -> int:
        """同步需要基于代理地址做替换的环境变量。"""
        resolved_default_proxy_address = default_proxy_address or RegionService._get_default_proxy_address()
        if not resolved_default_proxy_address:
            return 0

        old_address = old_proxy_address or resolved_default_proxy_address
        new_address = new_proxy_address or resolved_default_proxy_address

        if old_address == new_address:
            logger.info(f"Proxy address not changed for cloud region {cloud_region_id}, skip replace env vars update")
            return 0

        env_vars_to_update = SidecarEnv.objects.filter(
            cloud_region_id=cloud_region_id,
            key__in=NodeConstants.PROXY_ADDRESS_REPLACE_KEYS,
        )

        if not env_vars_to_update.exists():
            logger.warning(f"No environment variables to update for cloud region {cloud_region_id}")
            return 0

        updated_count = 0
        for env_var in env_vars_to_update:
            old_value = env_var.value
            new_value = RegionService._replace_address(old_value, old_address, new_address)

            if old_value != new_value:
                env_var.value = new_value
                env_var.save(update_fields=["value"])
                updated_count += 1
                logger.info(f"Updated {env_var.key} for cloud region {cloud_region_id}: {old_value} -> {new_value}")

        return updated_count

    @staticmethod
    def sync_proxy_related_env_vars(
        cloud_region_id: int,
        old_proxy_address: str = "",
        new_proxy_address: str = "",
        default_proxy_address: str | None = None,
    ) -> int:
        """统一同步云区域代理地址相关环境变量。"""
        updated_count = RegionService._sync_proxy_address_env_var(cloud_region_id, new_proxy_address)
        updated_count += RegionService._sync_proxy_address_replace_env_vars(
            cloud_region_id=cloud_region_id,
            old_proxy_address=old_proxy_address,
            new_proxy_address=new_proxy_address,
            default_proxy_address=default_proxy_address,
        )
        logger.info(f"Synchronized {updated_count} proxy-related env vars for cloud region {cloud_region_id}")
        return updated_count

    @staticmethod
    def init_env_vars(cloud_region_id):
        """初始化云区域下的环境变量

        从默认云区域复制环境变量到新创建的云区域，并替换特殊环境变量中的地址

        Args:
            cloud_region_id: 新创建的云区域ID

        Returns:
            int: 复制的环境变量数量
        """
        try:
            # 验证云区域是否存在
            cloud_region = CloudRegion.objects.filter(id=cloud_region_id).first()
            if not cloud_region:
                logger.warning(f"Cloud region not found: {cloud_region_id}")
                return 0

            # 如果没有配置代理地址，记录警告但继续执行
            proxy_address = cloud_region.proxy_address
            if not proxy_address:
                logger.warning(f"No proxy address configured for cloud region {cloud_region_id}, using default values")

            # 获取默认云区域的所有预置环境变量
            default_env_vars = SidecarEnv.objects.filter(
                cloud_region_id=CloudRegionConstants.DEFAULT_CLOUD_REGION_ID,
                is_pre=True,  # 只复制预置变量作为模板
            )

            if not default_env_vars.exists():
                logger.warning(f"No environment variables found in default cloud region")
                return RegionService._sync_proxy_address_env_var(cloud_region_id, proxy_address)

            # 提取默认云区域的地址（从 NODE_SERVER_URL 中提取）
            default_address = None
            if proxy_address:
                for env_var in default_env_vars:
                    if env_var.key == NodeConstants.SERVER_URL_KEY:
                        default_address = RegionService._extract_default_address(env_var.value)
                        break

                if default_address:
                    logger.info(f"Extracted default address: {default_address}, will replace with: {proxy_address}")
                else:
                    logger.warning(f"Could not extract default address from NODE_SERVER_URL")

            # 批量创建环境变量
            new_env_vars = []
            for env_var in default_env_vars:
                new_value = env_var.value

                # 对特殊环境变量进行地址替换
                if proxy_address and default_address and env_var.key in NodeConstants.PROXY_ADDRESS_REPLACE_KEYS:
                    new_value = RegionService._replace_address(env_var.value, default_address, proxy_address)
                    logger.info(f"Replaced {env_var.key}: {env_var.value} -> {new_value}")

                new_env_vars.append(
                    SidecarEnv(
                        key=env_var.key,
                        value=new_value,
                        type=env_var.type,
                        description=env_var.description,
                        cloud_region_id=cloud_region_id,
                        is_pre=False,  # 新云区域的变量不是预置变量，可以修改
                    )
                )

            # 使用 bulk_create 批量创建，ignore_conflicts=True 避免重复创建
            created_count = len(SidecarEnv.objects.bulk_create(new_env_vars, ignore_conflicts=True))
            if created_count:
                invalidate_sidecar_env_cache([cloud_region_id])
            created_count += RegionService.sync_proxy_related_env_vars(
                cloud_region_id=cloud_region_id,
                old_proxy_address=proxy_address,
                new_proxy_address=proxy_address,
                default_proxy_address=default_address,
            )

            logger.info(f"Initialized {created_count} environment variables for cloud region {cloud_region_id}")
            return created_count

        except Exception as e:
            logger.exception(f"Failed to initialize environment variables for cloud region {cloud_region_id}")
            # 不抛出异常，避免影响云区域创建流程
            return 0

    @staticmethod
    def update_env_vars_on_proxy_change(cloud_region_id, old_proxy_address, new_proxy_address):
        """当云区域的 proxy_address 修改时，更新相关环境变量

        Args:
            cloud_region_id: 云区域ID
            old_proxy_address: 旧的代理地址
            new_proxy_address: 新的代理地址

        Returns:
            int: 更新的环境变量数量
        """
        try:
            return RegionService.sync_proxy_related_env_vars(
                cloud_region_id=cloud_region_id,
                old_proxy_address=old_proxy_address or "",
                new_proxy_address=new_proxy_address or "",
            )

        except Exception as e:
            logger.exception(f"Failed to update environment variables for cloud region {cloud_region_id}")
            # 不抛出异常，避免影响云区域更新流程
            return 0
