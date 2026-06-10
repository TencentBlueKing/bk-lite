import uuid

import requests
from django.core.cache import cache

from apps.cmdb.constants.infra import InfraConstants
from apps.core.exceptions.base_app_exception import BaseAppException
from apps.core.logger import cmdb_logger as logger
from apps.core.utils.webhook_tls import get_webhook_tls_verify
from apps.rpc.node_mgmt import NodeMgmt


CACHE_KEY_PREFIX = "cmdb_infra_install_token:"


class InfraService:
    """CMDB 基础设施配置服务 - 代理调用外部 infra API（与 monitor.InfraService 对齐，独立实现）"""

    @staticmethod
    def generate_install_token(cluster_name: str, cloud_region_id: str) -> str:
        token = str(uuid.uuid4())
        cache_key = f"{CACHE_KEY_PREFIX}{token}"

        token_data = {
            "cluster_name": cluster_name,
            "cloud_region_id": cloud_region_id,
            "usage_count": 0,
            "max_usage": InfraConstants.TOKEN_MAX_USAGE,
        }

        cache.set(cache_key, token_data, timeout=InfraConstants.TOKEN_EXPIRE_TIME)

        logger.info(
            f"生成 CMDB infra 安装令牌成功: token={token[:8]}***, "
            f"cluster={cluster_name}, region={cloud_region_id}, "
            f"有效期={InfraConstants.TOKEN_EXPIRE_TIME}秒, "
            f"最大使用次数={InfraConstants.TOKEN_MAX_USAGE}"
        )

        return token

    @staticmethod
    def validate_and_get_token_data(token: str) -> dict:
        if not token:
            logger.warning("Token 验证失败: token 为空")
            raise BaseAppException("Token is required")

        cache_key = f"{CACHE_KEY_PREFIX}{token}"
        data = cache.get(cache_key)

        if not data:
            logger.warning(
                f"Token 验证失败: token={token[:8]}*** 在缓存中不存在或已过期"
            )
            raise BaseAppException("Invalid or expired token")

        usage_count = data.get("usage_count", 0)
        max_usage = data.get("max_usage", InfraConstants.TOKEN_MAX_USAGE)

        if usage_count >= max_usage:
            cache.delete(cache_key)
            logger.warning(
                f"Token 已达到最大使用次数: token={token[:8]}***, "
                f"usage={usage_count}/{max_usage}, cluster={data.get('cluster_name')}"
            )
            raise BaseAppException(f"Token has exceeded maximum usage limit ({max_usage} times)")

        data["usage_count"] = usage_count + 1
        cache.set(cache_key, data, timeout=InfraConstants.TOKEN_EXPIRE_TIME)

        logger.info(
            f"Token 验证成功: token={token[:8]}***, "
            f"cluster={data['cluster_name']}, region={data['cloud_region_id']}, "
            f"使用次数={data['usage_count']}/{max_usage}"
        )

        return {
            "cluster_name": data["cluster_name"],
            "cloud_region_id": data["cloud_region_id"],
            "remaining_usage": max_usage - data["usage_count"],
        }

    @staticmethod
    def render_config_from_cloud_region(cluster_name: str, cloud_region_id: str, config_type: str = "resource") -> str:
        """
        从云区域环境变量获取参数后，调用外部 webhook API 渲染 YAML。
        CMDB 默认走 type=resource 语义。
        """
        node_mgmt_rpc = NodeMgmt()
        env_vars = node_mgmt_rpc.get_cloud_region_envconfig(cloud_region_id)

        nats_username = env_vars.get('NATS_USERNAME')
        nats_password = env_vars.get('NATS_PASSWORD')
        nats_servers = env_vars.get('NATS_SERVERS')
        nats_tls_ca = env_vars.get('NATS_TLS_CA')
        webhook_server_url = env_vars.get('WEBHOOK_SERVER_URL')

        missing_vars = []
        if not nats_username:
            missing_vars.append('NATS_USERNAME')
        if not nats_password:
            missing_vars.append('NATS_PASSWORD')
        if not nats_servers:
            missing_vars.append('NATS_SERVERS')
        if not webhook_server_url:
            missing_vars.append('WEBHOOK_SERVER_URL')

        if missing_vars:
            raise BaseAppException(
                f"Missing required environment variables in cloud region {cloud_region_id}: {', '.join(missing_vars)}"
            )

        params = {
            "nats_username": nats_username,
            "nats_password": nats_password,
            "cluster_name": cluster_name,
            "type": config_type,
            "nats_url": nats_servers,
            "nats_ca": nats_tls_ca,
        }

        return InfraService.render_config_from_api(params, webhook_server_url)

    @staticmethod
    def render_config_from_api(params: dict, base_url: str = None) -> str:
        api_url = f"{base_url.rstrip('/')}/infra/kubernetes" if base_url else None

        if not api_url:
            raise BaseAppException("Webhook API URL is required")

        try:
            response = requests.post(
                api_url,
                json=params,
                headers={'Content-Type': 'application/json'},
                timeout=InfraConstants.REQUEST_TIMEOUT,
                verify=get_webhook_tls_verify(),
            )

            if response.status_code != 200:
                raise BaseAppException(
                    f"Infra API returned status {response.status_code}: {response.text}"
                )

            response_data = response.json()
            yaml_content = response_data.get('yaml')

            if not yaml_content:
                raise BaseAppException("Invalid response from infra API: missing 'yaml' field")

            return yaml_content

        except requests.Timeout as e:
            raise BaseAppException(f"Infra API request timeout: {str(e)}")
        except requests.RequestException as e:
            raise BaseAppException(f"Infra API request failed: {str(e)}")
        except ValueError as e:
            raise BaseAppException(f"Failed to parse response from infra API: {str(e)}")
        except BaseAppException:
            raise
        except Exception as e:
            logger.error(
                "Unexpected error occurred while rendering infra config",
                exc_info=True,
            )
            raise BaseAppException(f"Failed to render config: {str(e)}")
