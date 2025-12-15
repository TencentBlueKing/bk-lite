import uuid

import requests
from django.core.cache import cache

from apps.core.exceptions.base_app_exception import BaseAppException
from apps.monitor.constants.infra import InfraConstants
from apps.rpc.node_mgmt import NodeMgmt


class InfraService:
    """基础设施配置服务 - 代理调用外部 infra API"""

    @staticmethod
    def generate_install_token(cluster_name: str, cloud_region_id: str) -> str:
        """
        生成安装令牌（5分钟有效，最多使用5次）

        :param cluster_name: 集群名称
        :param cloud_region_id: 云区域 ID
        :return: 限时令牌
        """
        # 生成限时令牌
        token = str(uuid.uuid4())
        cache_key = f"infra_install_token:{token}"

        # 在 cache 中存储令牌及其关联的参数和使用次数，5分钟过期
        cache.set(cache_key, {
            "cluster_name": cluster_name,
            "cloud_region_id": cloud_region_id,
            "usage_count": 0,
            "max_usage": InfraConstants.TOKEN_MAX_USAGE,
        }, timeout=InfraConstants.TOKEN_EXPIRE_TIME)

        return token

    @staticmethod
    def validate_and_get_token_data(token: str) -> dict:
        """
        验证令牌并获取关联的参数（带次数限制）

        :param token: 限时令牌
        :return: 包含 cluster_name 和 cloud_region_id 的字典
        :raises BaseAppException: 令牌无效、已过期或超过使用次数
        """
        cache_key = f"infra_install_token:{token}"
        data = cache.get(cache_key)

        if not data:
            raise BaseAppException("Invalid or expired token")

        # 检查使用次数
        usage_count = data.get("usage_count", 0)
        max_usage = data.get("max_usage", InfraConstants.TOKEN_MAX_USAGE)

        if usage_count >= max_usage:
            # 超过最大使用次数，删除令牌
            cache.delete(cache_key)
            raise BaseAppException(f"Token has exceeded maximum usage limit ({max_usage} times)")

        # 增加使用次数
        data["usage_count"] = usage_count + 1

        # 更新 cache，使用默认过期时间（简化处理，不保留原 TTL）
        cache.set(cache_key, data, timeout=InfraConstants.TOKEN_EXPIRE_TIME)

        return {
            "cluster_name": data["cluster_name"],
            "cloud_region_id": data["cloud_region_id"],
            "remaining_usage": max_usage - data["usage_count"],
        }

    @staticmethod
    def render_config_from_cloud_region(cluster_name: str, cloud_region_id: str, config_type: str = "metric") -> str:
        """
        从云区域环境变量获取参数后，调用外部 API 渲染配置

        :param cluster_name: 集群名称
        :param cloud_region_id: 云区域 ID
        :param config_type: 配置类型，默认 metric
        :return: 渲染后的 YAML 字符串
        :raises BaseAppException: 参数缺失或 API 调用失败时抛出异常
        """
        # 通过 RPC 调用获取云区域环境变量
        node_mgmt_rpc = NodeMgmt()
        env_vars = node_mgmt_rpc.get_cloud_region_envconfig(cloud_region_id)

        # 提取必需的环境变量
        nats_username = env_vars.get('NATS_USERNAME')
        nats_password = env_vars.get('NATS_PASSWORD')
        nats_servers = env_vars.get('NATS_SERVERS')
        nats_tls_ca = env_vars.get('NATS_TLS_CA')
        webhook_server_url = env_vars.get('WEBHOOK_SERVER_URL')

        # 验证必需的环境变量
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

        # 构造请求参数
        params = {
            "nats_username": nats_username,
            "nats_password": nats_password,
            "cluster_name": cluster_name,
            "type": config_type,
            "nats_url": nats_servers,
            "nats_ca": nats_tls_ca,
        }

        # 调用外部 webhook API
        return InfraService.render_config_from_api(params, webhook_server_url)

    @staticmethod
    def render_config_from_api(params: dict, base_url: str = None) -> str:
        """
        调用外部 webhook API 渲染基础设施配置 YAML

        :param params: 请求参数字典
        :param base_url: webhook 服务基础地址
        :return: 渲染后的 YAML 字符串
        :raises BaseAppException: API 调用失败时抛出异常
        """
        # 从 WEBHOOK_SERVER_URL 构造 infra API 地址
        # 例如: http://10.10.41.149:8080 -> http://10.10.41.149:8080/infra/render
        api_url = f"{base_url.rstrip('/')}/infra/render" if base_url else None

        if not api_url:
            raise BaseAppException("Webhook API URL is required")

        try:
            # 使用 requests 调用外部 API
            response = requests.post(
                api_url,
                json=params,
                headers={'Content-Type': 'application/json'},
                timeout=InfraConstants.REQUEST_TIMEOUT,
                verify=False  # 跳过 SSL 证书验证
            )

            # 检查响应状态
            if response.status_code != 200:
                raise BaseAppException(
                    f"Infra API returned status {response.status_code}: {response.text}"
                )

            # 解析响应（假设返回的是 {"yaml": "..."} 格式）
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
        except Exception as e:
            import traceback
            error_detail = traceback.format_exc()
            raise BaseAppException(f"Failed to render config: {str(e)} | Detail: {error_detail}")
