import hashlib
import json
import uuid
from datetime import timedelta
from urllib.parse import urljoin

from cryptography.fernet import InvalidToken
from django.conf import settings
from django.core.cache import cache
from django.utils import timezone

from apps.alerts.models.install_token import K8sInstallToken
from apps.core.exceptions.base_app_exception import BaseAppException
from apps.core.mixinx import EncryptMixin


class K8sInstallService:
    TOKEN_EXPIRE_TIME = 60 * 30
    TOKEN_MAX_USAGE = 5
    TOKEN_CLAIM_RETRIES = TOKEN_MAX_USAGE + 1
    TOKEN_CACHE_PREFIX = "alerts_k8s_install_token"

    @classmethod
    def _build_cache_key(cls, token: str) -> str:
        return f"{cls.TOKEN_CACHE_PREFIX}:{token}"

    @staticmethod
    def _hash_token(token: str) -> str:
        return hashlib.sha256(token.encode("utf-8")).hexdigest()

    @staticmethod
    def _encrypt_payload(payload: dict) -> str:
        if not settings.SECRET_KEY:
            raise ValueError("SECRET_KEY must be configured before issuing K8s install tokens")
        serialized = json.dumps(payload, ensure_ascii=False, separators=(",", ":"), sort_keys=True)
        return EncryptMixin.get_cipher_suite().encrypt(serialized.encode("utf-8")).decode("utf-8")

    @staticmethod
    def _decrypt_payload(encrypted_payload: str) -> dict:
        if not settings.SECRET_KEY:
            raise BaseAppException("Invalid or expired token")
        try:
            serialized = EncryptMixin.get_cipher_suite().decrypt(encrypted_payload.encode("utf-8"))
            payload = json.loads(serialized.decode("utf-8"))
        except (InvalidToken, UnicodeDecodeError, json.JSONDecodeError) as error:
            raise BaseAppException("Invalid or expired token") from error
        if not isinstance(payload, dict):
            raise BaseAppException("Invalid or expired token")
        return payload

    @classmethod
    def _create_token_record(cls, token: str, payload: dict) -> K8sInstallToken:
        now = timezone.now()
        return K8sInstallToken.objects.create(
            token_hash=cls._hash_token(token),
            encrypted_payload=cls._encrypt_payload(payload),
            usage_count=0,
            max_usage=cls.TOKEN_MAX_USAGE,
            expires_at=now + timedelta(seconds=cls.TOKEN_EXPIRE_TIME),
        )

    @classmethod
    def _consume_legacy_cache_usage(cls, token: str) -> tuple[dict, int, int] | None:
        cache_key = cls._build_cache_key(token)
        data = cache.get(cache_key)
        if not data:
            return None

        usage_count = data.get("usage_count", 0)
        max_usage = data.get("max_usage", cls.TOKEN_MAX_USAGE)
        payload = {key: value for key, value in data.items() if key not in {"usage_count", "max_usage"}}
        usage_cache_key = f"{cache_key}:usage_count"
        cache.add(usage_cache_key, usage_count, timeout=cls.TOKEN_EXPIRE_TIME)
        try:
            claimed_usage = cache.incr(usage_cache_key)
        except ValueError as error:
            raise BaseAppException("Invalid or expired token") from error

        if claimed_usage > max_usage:
            # 保留耗尽计数到原 payload 自然过期。若删除计数键，已经读取到旧
            # payload 的并发请求可以重新 add 计数器并再次获得额度。
            raise BaseAppException(f"Token has exceeded maximum usage limit ({max_usage} times)")
        return payload, claimed_usage, max_usage

    @classmethod
    def _consume_token_usage(cls, token: str) -> tuple[dict, int, int]:
        token_hash = cls._hash_token(token)
        fields = ("encrypted_payload", "usage_count", "max_usage", "expires_at")

        for lookup_attempt in range(cls.TOKEN_CLAIM_RETRIES):
            token_data = K8sInstallToken.objects.filter(token_hash=token_hash).values(*fields).first()
            if not token_data:
                if lookup_attempt == 0:
                    legacy_result = cls._consume_legacy_cache_usage(token)
                    if legacy_result:
                        return legacy_result
                raise BaseAppException("Invalid or expired token")

            now = timezone.now()
            if token_data["expires_at"] <= now:
                K8sInstallToken.objects.filter(token_hash=token_hash, expires_at__lte=now).delete()
                raise BaseAppException("Invalid or expired token")

            usage_count = token_data["usage_count"]
            max_usage = token_data["max_usage"]
            if usage_count >= max_usage:
                raise BaseAppException(f"Token has exceeded maximum usage limit ({max_usage} times)")

            # 先验证载荷可解密，再领取额度。密钥配置错误或轮换窗口中的旧密文
            # 不应消耗合法令牌的有限次数。
            payload = cls._decrypt_payload(token_data["encrypted_payload"])

            updated = K8sInstallToken.objects.filter(
                token_hash=token_hash,
                usage_count=usage_count,
                expires_at__gt=timezone.now(),
            ).claim_usage()
            if updated:
                return payload, usage_count + 1, max_usage

        raise BaseAppException("Invalid or expired token")

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
        if settings.K8S_INSTALL_TOKEN_DB_ENABLED:
            K8sInstallToken.objects.filter(expires_at__lte=timezone.now()).delete()
            cls._create_token_record(token, payload)
        else:
            # 第一阶段部署默认保持旧签发形态；所有 worker 都升级到能双读后，
            # 再开启数据库签发。回滚时先关闭开关，等待最长 30 分钟，再回退代码。
            cache.set(
                cls._build_cache_key(token),
                {**payload, "usage_count": 0, "max_usage": cls.TOKEN_MAX_USAGE},
                timeout=cls.TOKEN_EXPIRE_TIME,
            )
        return token

    @classmethod
    def validate_and_get_token_data(cls, token: str) -> dict:
        if not token:
            raise BaseAppException("Token is required")

        data, usage_count, max_usage = cls._consume_token_usage(token)
        return {
            "server_url": data["server_url"],
            "cluster_name": data["cluster_name"],
            "push_source_id": data["push_source_id"],
            "source_id": data["source_id"],
            "receiver_url": data["receiver_url"],
            "secret": data["secret"],
            "remaining_usage": max_usage - usage_count,
        }

    @staticmethod
    def build_install_command(server_url: str, token: str) -> str:
        return (
            "curl -sSLk -X POST -H 'Content-Type: application/json' "
            f"{server_url}/api/v1/alerts/open_api/k8s/render/ "
            f'-d \'{{"token":"{token}"}}\' | kubectl apply -f -'
        )
