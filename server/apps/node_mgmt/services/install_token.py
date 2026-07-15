import uuid
from django.core.cache import cache
from apps.core.exceptions.base_app_exception import BaseAppException
from apps.node_mgmt.constants.installer import InstallerConstants


class InstallTokenService:
    """节点安装令牌服务 - 管理限时安装令牌"""

    USAGE_COUNT_CACHE_SUFFIX = "usage_count"

    @classmethod
    def _consume_token_usage(
        cls,
        cache_key: str,
        data: dict,
        max_usage: int,
        timeout: int,
        invalid_message: str,
        exceeded_message: str,
    ) -> int:
        """Atomically consume one use without extending the token lifetime."""
        usage_cache_key = f"{cache_key}:{cls.USAGE_COUNT_CACHE_SUFFIX}"

        # ``add`` is atomic on supported cache backends. Seeding from the
        # payload keeps tokens issued before the separate counter compatible.
        cache.add(usage_cache_key, data.get("usage_count", 0), timeout=timeout)
        try:
            usage_count = cache.incr(usage_cache_key)
        except ValueError:
            raise BaseAppException(invalid_message)

        if usage_count > max_usage:
            # Keep the exhausted counter as a tombstone until its TTL ends.
            # A request that already read ``data`` must not be able to recreate
            # the counter from the stale payload after this token is deleted.
            cache.delete(cache_key)
            raise BaseAppException(exceeded_message)

        return usage_count

    @staticmethod
    def generate_install_token(
        node_id: str,
        ip: str,
        user: str,
        os: str,
        package_id: str,
        cloud_region_id: str,
        organizations: list,
        node_name: str,
        cpu_architecture: str = "",
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
        cache_key = f"{InstallerConstants.INSTALL_TOKEN_CACHE_PREFIX}:{token}"

        # 在 cache 中存储令牌及其关联的参数和使用次数
        cache.set(
            cache_key,
            {
                "node_id": node_id,
                "ip": ip,
                "user": user,
                "os": os,
                "package_id": package_id,
                "cloud_region_id": cloud_region_id,
                "organizations": organizations,
                "node_name": node_name,
                "cpu_architecture": cpu_architecture,
                "usage_count": 0,
                "max_usage": InstallerConstants.INSTALL_TOKEN_MAX_USAGE,
            },
            timeout=InstallerConstants.INSTALL_TOKEN_EXPIRE_TIME,
        )

        return token

    @staticmethod
    def validate_and_get_token_data(token: str) -> dict:
        """
        验证令牌并获取关联的参数（带次数限制）

        :param token: 限时令牌
        :return: 包含节点安装所需参数的字典
        :raises BaseAppException: 令牌无效、已过期或超过使用次数
        """
        cache_key = f"{InstallerConstants.INSTALL_TOKEN_CACHE_PREFIX}:{token}"
        data = cache.get(cache_key)

        if not data:
            raise BaseAppException("Invalid or expired token")

        max_usage = data.get("max_usage", InstallerConstants.INSTALL_TOKEN_MAX_USAGE)
        usage_count = InstallTokenService._consume_token_usage(
            cache_key=cache_key,
            data=data,
            max_usage=max_usage,
            timeout=InstallerConstants.INSTALL_TOKEN_EXPIRE_TIME,
            invalid_message="Invalid or expired token",
            exceeded_message=f"Token has exceeded maximum usage limit ({max_usage} times)",
        )

        return {
            "node_id": data["node_id"],
            "ip": data["ip"],
            "user": data["user"],
            "os": data["os"],
            "package_id": data["package_id"],
            "cloud_region_id": data["cloud_region_id"],
            "organizations": data["organizations"],
            "node_name": data["node_name"],
            "cpu_architecture": data.get("cpu_architecture", ""),
            "remaining_usage": max_usage - usage_count,
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
        cache_key = f"{InstallerConstants.DOWNLOAD_TOKEN_CACHE_PREFIX}:{token}"

        # 在 cache 中存储令牌及其关联的参数和使用次数
        cache.set(
            cache_key,
            {
                "package_id": package_id,
                "node_id": node_id,
                "usage_count": 0,
                "max_usage": InstallerConstants.DOWNLOAD_TOKEN_MAX_USAGE,
            },
            timeout=InstallerConstants.DOWNLOAD_TOKEN_EXPIRE_TIME,
        )

        return token

    @staticmethod
    def validate_and_get_download_token_data(token: str) -> dict:
        """
        验证下载令牌并获取关联的参数（带次数限制）

        :param token: 限时下载令牌
        :return: 包含 package_id 和 node_id 的字典
        :raises BaseAppException: 令牌无效、已过期或超过使用次数
        """
        cache_key = f"{InstallerConstants.DOWNLOAD_TOKEN_CACHE_PREFIX}:{token}"
        data = cache.get(cache_key)

        if not data:
            raise BaseAppException("Invalid or expired download token")

        max_usage = data.get("max_usage", InstallerConstants.DOWNLOAD_TOKEN_MAX_USAGE)
        usage_count = InstallTokenService._consume_token_usage(
            cache_key=cache_key,
            data=data,
            max_usage=max_usage,
            timeout=InstallerConstants.DOWNLOAD_TOKEN_EXPIRE_TIME,
            invalid_message="Invalid or expired download token",
            exceeded_message=f"Download token has exceeded maximum usage limit ({max_usage} times)",
        )

        return {
            "package_id": data["package_id"],
            "node_id": data["node_id"],
            "remaining_usage": max_usage - usage_count,
        }
