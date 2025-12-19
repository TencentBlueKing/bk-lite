import uuid
from django.core.cache import cache
from apps.core.exceptions.base_app_exception import BaseAppException


class InstallTokenService:
    """节点安装令牌服务 - 管理限时安装令牌"""

    # 令牌过期时间（秒）- 30分钟
    TOKEN_EXPIRE_TIME = 60 * 30

    # 令牌最大使用次数
    TOKEN_MAX_USAGE = 5

    # 下载令牌过期时间（秒）- 10分钟
    DOWNLOAD_TOKEN_EXPIRE_TIME = 60 * 10

    # 下载令牌最大使用次数
    DOWNLOAD_TOKEN_MAX_USAGE = 3

    @staticmethod
    def generate_install_token(
        node_id: str,
        ip: str,
        user: str,
        os: str,
        package_id: str,
        cloud_region_id: str,
        organizations: list,
        node_name: str
    ) -> str:
        """
        生成安装令牌（30分钟有效，最多使用5次）

        :param node_id: 节点ID
        :param ip: 节点IP
        :param user: 用户名
        :param os: 操作系统
        :param package_id: 安装包ID
        :param cloud_region_id: 云区域ID
        :param organizations: 组织列表
        :param node_name: 节点名称
        :return: 限时令牌
        """
        token = str(uuid.uuid4())
        cache_key = f"node_install_token:{token}"

        # 在 cache 中存储令牌及其关联的参数和使用次数
        cache.set(cache_key, {
            "node_id": node_id,
            "ip": ip,
            "user": user,
            "os": os,
            "package_id": package_id,
            "cloud_region_id": cloud_region_id,
            "organizations": organizations,
            "node_name": node_name,
            "usage_count": 0,
            "max_usage": InstallTokenService.TOKEN_MAX_USAGE,
        }, timeout=InstallTokenService.TOKEN_EXPIRE_TIME)

        return token

    @staticmethod
    def validate_and_get_token_data(token: str) -> dict:
        """
        验证令牌并获取关联的参数（带次数限制）

        :param token: 限时令牌
        :return: 包含节点安装所需参数的字典
        :raises BaseAppException: 令牌无效、已过期或超过使用次数
        """
        cache_key = f"node_install_token:{token}"
        data = cache.get(cache_key)

        if not data:
            raise BaseAppException("Invalid or expired token")

        # 检查使用次数
        usage_count = data.get("usage_count", 0)
        max_usage = data.get("max_usage", InstallTokenService.TOKEN_MAX_USAGE)

        if usage_count >= max_usage:
            # 超过最大使用次数，删除令牌
            cache.delete(cache_key)
            raise BaseAppException(f"Token has exceeded maximum usage limit ({max_usage} times)")

        # 增加使用次数
        data["usage_count"] = usage_count + 1

        # 更新 cache
        cache.set(cache_key, data, timeout=InstallTokenService.TOKEN_EXPIRE_TIME)

        return {
            "node_id": data["node_id"],
            "ip": data["ip"],
            "user": data["user"],
            "os": data["os"],
            "package_id": data["package_id"],
            "cloud_region_id": data["cloud_region_id"],
            "organizations": data["organizations"],
            "node_name": data["node_name"],
            "remaining_usage": max_usage - data["usage_count"],
        }

    @staticmethod
    def generate_download_token(package_id: str, node_id: str) -> str:
        """
        生成下载令牌（10分钟有效，最多使用3次）

        :param package_id: 安装包ID
        :param node_id: 节点ID（用于审计）
        :return: 限时下载令牌
        """
        token = str(uuid.uuid4())
        cache_key = f"package_download_token:{token}"

        # 在 cache 中存储令牌及其关联的参数和使用次数
        cache.set(cache_key, {
            "package_id": package_id,
            "node_id": node_id,
            "usage_count": 0,
            "max_usage": InstallTokenService.DOWNLOAD_TOKEN_MAX_USAGE,
        }, timeout=InstallTokenService.DOWNLOAD_TOKEN_EXPIRE_TIME)

        return token

    @staticmethod
    def validate_and_get_download_token_data(token: str) -> dict:
        """
        验证下载令牌并获取关联的参数（带次数限制）

        :param token: 限时下载令牌
        :return: 包含 package_id 和 node_id 的字典
        :raises BaseAppException: 令牌无效、已过期或超过使用次数
        """
        cache_key = f"package_download_token:{token}"
        data = cache.get(cache_key)

        if not data:
            raise BaseAppException("Invalid or expired download token")

        # 检查使用次数
        usage_count = data.get("usage_count", 0)
        max_usage = data.get("max_usage", InstallTokenService.DOWNLOAD_TOKEN_MAX_USAGE)

        if usage_count >= max_usage:
            # 超过最大使用次数，删除令牌
            cache.delete(cache_key)
            raise BaseAppException(f"Download token has exceeded maximum usage limit ({max_usage} times)")

        # 增加使用次数
        data["usage_count"] = usage_count + 1

        # 更新 cache
        cache.set(cache_key, data, timeout=InstallTokenService.DOWNLOAD_TOKEN_EXPIRE_TIME)

        return {
            "package_id": data["package_id"],
            "node_id": data["node_id"],
            "remaining_usage": max_usage - data["usage_count"],
        }
