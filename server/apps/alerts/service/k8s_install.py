import uuid
from urllib.parse import urljoin

from django.core.cache import cache

from apps.core.exceptions.base_app_exception import BaseAppException


class K8sInstallService:
    TOKEN_EXPIRE_TIME = 60 * 30
    TOKEN_MAX_USAGE = 5
    TOKEN_CACHE_PREFIX = "alerts_k8s_install_token"

    @classmethod
    def _build_cache_key(cls, token: str) -> str:
        return f"{cls.TOKEN_CACHE_PREFIX}:{token}"

    @staticmethod
    def normalize_base_url(server_url: str) -> str:
        value = (server_url or "").strip()
        if not value:
            raise BaseAppException("服务地址不能为空")
        if not value.startswith(("http://", "https://")):
            raise BaseAppException("服务地址格式不正确，必须以 http:// 或 https:// 开头")
        return value.rstrip("/")

    @staticmethod
    def normalize_cluster_name(cluster_name: str) -> str:
        value = (cluster_name or "").strip()
        if not value:
            raise BaseAppException("集群名称不能为空")
        return value

    @staticmethod
    def normalize_push_source_id(push_source_id: str | None) -> str:
        value = (push_source_id or "k8s").strip()
        if not value:
            raise BaseAppException("推送来源不能为空")
        return value

    @classmethod
    def build_render_payload(
        cls,
        source_id: str,
        source_secret: str,
        receiver_path: str,
        server_url: str,
        cluster_name: str,
        push_source_id: str | None = None,
    ) -> dict:
        base_url = cls.normalize_base_url(server_url)
        cluster = cls.normalize_cluster_name(cluster_name)
        push_source = cls.normalize_push_source_id(push_source_id)
        return {
            "server_url": base_url,
            "cluster_name": cluster,
            "push_source_id": push_source,
            "source_id": source_id,
            "receiver_url": urljoin(f"{base_url}/", receiver_path.lstrip("/")),
            "secret": source_secret,
        }

    @classmethod
    def generate_install_token(cls, payload: dict) -> str:
        token = str(uuid.uuid4())
        cache.set(
            cls._build_cache_key(token),
            {
                **payload,
                "usage_count": 0,
                "max_usage": cls.TOKEN_MAX_USAGE,
            },
            timeout=cls.TOKEN_EXPIRE_TIME,
        )
        return token

    @classmethod
    def validate_and_get_token_data(cls, token: str) -> dict:
        if not token:
            raise BaseAppException("Token is required")

        cache_key = cls._build_cache_key(token)
        data = cache.get(cache_key)
        if not data:
            raise BaseAppException("Invalid or expired token")

        usage_count = data.get("usage_count", 0)
        max_usage = data.get("max_usage", cls.TOKEN_MAX_USAGE)
        if usage_count >= max_usage:
            cache.delete(cache_key)
            raise BaseAppException(f"Token has exceeded maximum usage limit ({max_usage} times)")

        data["usage_count"] = usage_count + 1
        cache.set(cache_key, data, timeout=cls.TOKEN_EXPIRE_TIME)
        return {
            "server_url": data["server_url"],
            "cluster_name": data["cluster_name"],
            "push_source_id": data["push_source_id"],
            "source_id": data["source_id"],
            "receiver_url": data["receiver_url"],
            "secret": data["secret"],
            "remaining_usage": max_usage - data["usage_count"],
        }

    @staticmethod
    def build_install_command(server_url: str, token: str) -> str:
        return (
            "curl -sSLk -X POST -H 'Content-Type: application/json' "
            f"{server_url}/api/v1/alerts/open_api/k8s/render/ "
            f"-d '{{\"token\":\"{token}\"}}' | kubectl apply -f -"
        )
