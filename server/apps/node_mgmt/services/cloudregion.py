import requests
import re

from apps.core.exceptions.base_app_exception import BaseAppException
from apps.core.logger import node_logger as logger
from apps.core.utils.crypto.aes_crypto import AESCryptor
from apps.node_mgmt.models import SidecarEnv
from apps.node_mgmt.models.cloud_region import CloudRegion
from apps.node_mgmt.constants.cloudregion_service import CloudRegionServiceConstants
from apps.node_mgmt.constants.database import CloudRegionConstants
from apps.node_mgmt.constants.node import NodeConstants


class RegionService:

    @staticmethod
    def get_cloud_region_envconfig(cloud_region_id):
        """获取云区域环境变量"""
        objs = SidecarEnv.objects.filter(cloud_region_id=cloud_region_id)
        variables = {}
        for obj in objs:
            if obj.type == "secret":
                # 如果是密文，解密后使用
                aes_obj = AESCryptor()
                value = aes_obj.decode(obj.value)
                variables[obj.key] = value
            else:
                # 如果是普通变量，直接使用
                variables[obj.key] = obj.value
        return variables

    @staticmethod
    def get_deploy_script(data: dict):
        """获取云区域服务部署脚本
        
        data:
            cloud_region_id: 云区域ID（必须是整数）

        Returns:
            str: 部署脚本内容
            
        Raises:
            BaseAppException: 当参数无效、云区域不存在或webhook调用失败时
        """
        # 参数类型验证
        try:
            cloud_region_id = int(data["cloud_region_id"])
        except (TypeError, ValueError):
            raise BaseAppException("Invalid cloud_region_id: must be an integer")
        
        # 验证云区域是否存在
        cloud_region = CloudRegion.objects.filter(id=cloud_region_id).first()
        if not cloud_region:
            logger.warning(f"Cloud region not found: {cloud_region_id}")
            raise BaseAppException("Cloud region not found")

        # 从 SidecarEnv 获取 webhook URL
        webhook_url = None
        objs = SidecarEnv.objects.filter(cloud_region=cloud_region_id)
        for obj in objs:
            if obj.key == "WEBHOOK_SERVER_URL":
                webhook_url = obj.value
                break

        if not webhook_url:
            logger.error(f"Missing WEBHOOK_SERVER_URL for cloud region {cloud_region_id}")
            raise BaseAppException("Webhook configuration missing")

        # 构造 webhook API URL
        webhook_api_url = f"{webhook_url.rstrip('/')}/infra/cloud_region"

        # 准备请求参数
        webhook_params = {
            "cloud_region_id": cloud_region_id,
            "cloud_region_name": cloud_region.name,
        }

        try:
            # 调用 webhook API 获取部署脚本
            response = requests.post(
                webhook_api_url,
                json=webhook_params,
                headers={'Content-Type': 'application/json'},
                timeout=CloudRegionServiceConstants.WEBHOOK_REQUEST_TIMEOUT,
                verify=False  # 跳过 SSL 证书验证（内网环境）
            )

            # 检查响应状态
            if response.status_code != 200:
                logger.error(f"Webhook API error: status={response.status_code}, region={cloud_region_id}")
                raise BaseAppException("Failed to generate deploy script")

            # 解析 webhook 返回的响应
            try:
                webhook_response = response.json()
                deploy_script = webhook_response.get("deploy_script") or webhook_response.get("commands")
            except ValueError:
                # 如果解析 JSON 失败，则认为返回的是纯文本脚本（向后兼容）
                deploy_script = response.text

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
        ipv6_match = re.search(r'\[([^\]]+)\]', value)
        if ipv6_match:
            return f"[{ipv6_match.group(1)}]"
        
        # 匹配普通 IP 或域名
        match = re.search(r'(?:https?://)?([^:/]+)', value)
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
                is_pre=True  # 只复制预置变量作为模板
            )
            
            if not default_env_vars.exists():
                logger.warning(f"No environment variables found in default cloud region")
                return 0
            
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
                
                new_env_vars.append(SidecarEnv(
                    key=env_var.key,
                    value=new_value,
                    type=env_var.type,
                    description=env_var.description,
                    cloud_region_id=cloud_region_id,
                    is_pre=False  # 新云区域的变量不是预置变量，可以修改
                ))
            
            # 使用 bulk_create 批量创建，ignore_conflicts=True 避免重复创建
            created_count = len(SidecarEnv.objects.bulk_create(new_env_vars, ignore_conflicts=True))
            
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
            # 获取默认云区域的地址（从 NODE_SERVER_URL 中提取）
            default_env_var = SidecarEnv.objects.filter(
                cloud_region_id=CloudRegionConstants.DEFAULT_CLOUD_REGION_ID,
                key=NodeConstants.SERVER_URL_KEY,
                is_pre=True
            ).first()

            if not default_env_var:
                logger.warning(f"Could not find NODE_SERVER_URL in default cloud region")
                return 0

            default_address = RegionService._extract_default_address(default_env_var.value)
            if not default_address:
                logger.warning(f"Could not extract default address from NODE_SERVER_URL")
                return 0

            # 确定旧地址和新地址
            # 如果没有旧代理地址，说明之前使用的是默认地址
            old_address = old_proxy_address if old_proxy_address else default_address
            new_address = new_proxy_address if new_proxy_address else default_address

            if old_address == new_address:
                logger.info(f"Proxy address not changed for cloud region {cloud_region_id}, skip update")
                return 0

            # 获取需要更新的环境变量
            env_vars_to_update = SidecarEnv.objects.filter(
                cloud_region_id=cloud_region_id,
                key__in=NodeConstants.PROXY_ADDRESS_REPLACE_KEYS
            )

            if not env_vars_to_update.exists():
                logger.warning(f"No environment variables to update for cloud region {cloud_region_id}")
                return 0

            # 批量更新环境变量
            updated_count = 0
            for env_var in env_vars_to_update:
                old_value = env_var.value
                new_value = RegionService._replace_address(old_value, old_address, new_address)

                if old_value != new_value:
                    env_var.value = new_value
                    env_var.save(update_fields=['value'])
                    updated_count += 1
                    logger.info(f"Updated {env_var.key} for cloud region {cloud_region_id}: {old_value} -> {new_value}")

            logger.info(f"Updated {updated_count} environment variables for cloud region {cloud_region_id}")
            return updated_count

        except Exception as e:
            logger.exception(f"Failed to update environment variables for cloud region {cloud_region_id}")
            # 不抛出异常，避免影响云区域更新流程
            return 0

