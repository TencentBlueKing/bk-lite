import hashlib
import re
import uuid
from datetime import timedelta

import requests
from django.db import transaction
from django.utils import timezone

from apps.core.exceptions.base_app_exception import BaseAppException, ValidationAppException
from apps.core.utils.k8s_image_registry import build_kubectl_install_command, normalize_k8s_image_registry_prefix
from apps.core.utils.webhook_tls import get_webhook_tls_verify
from apps.log.models import CollectInstance, CollectInstanceOrganization, CollectType, K8sCollectSetting, K8sInstallToken
from apps.log.services.search import SearchService
from apps.rpc.node_mgmt import NodeMgmt


class K8sLogCollectService:
    TOKEN_EXPIRE_TIME = 60 * 30
    TOKEN_MAX_USAGE = 5
    TOKEN_CLAIM_RETRIES = TOKEN_MAX_USAGE + 1
    REQUEST_TIMEOUT = 30
    RUNTIME_PROFILES = {"standard", "docker", "custom"}
    PATH_UNSAFE_PATTERN = re.compile(r"[\r\n']")
    PATTERN_WHITELIST = re.compile(r"^[a-z0-9.*?-]+$")
    MAX_PATTERNS_PER_DIMENSION = 50
    MAX_INCLUDE_PATTERNS = 200
    SETTING_MISSING_MESSAGE = "接入配置未知，请先保存采集配置"

    @staticmethod
    def _hash_token(token: str) -> str:
        return hashlib.sha256(token.encode("utf-8")).hexdigest()

    @classmethod
    def _consume_token_usage(cls, token: str) -> tuple[dict, int]:
        """用数据库 CAS 原子领取一次额度，权威记录缺失时失败关闭。"""
        token_hash = cls._hash_token(token)
        fields = (
            "cluster_name",
            "cloud_region_id",
            "config_type",
            "image_registry_prefix",
            "usage_count",
            "max_usage",
            "expires_at",
        )

        # 每次 CAS 冲突都意味着另一个 worker 已推进计数；最多五次额度，因此
        # TOKEN_MAX_USAGE + 1 次读取足以观察成功或耗尽状态。
        for _ in range(cls.TOKEN_CLAIM_RETRIES):
            token_data = K8sInstallToken.objects.filter(token_hash=token_hash).values(*fields).first()
            if not token_data:
                raise BaseAppException("Invalid or expired token")

            now = timezone.now()
            if token_data["expires_at"] <= now:
                K8sInstallToken.objects.filter(
                    token_hash=token_hash,
                    expires_at__lte=now,
                ).delete()
                raise BaseAppException("Invalid or expired token")

            usage_count = token_data["usage_count"]
            max_usage = token_data["max_usage"]
            if usage_count >= max_usage:
                raise BaseAppException(f"Token has exceeded maximum usage limit ({max_usage} times)")

            updated = K8sInstallToken.objects.filter(
                token_hash=token_hash,
                usage_count=usage_count,
                expires_at__gt=timezone.now(),
            ).claim_usage()
            if updated:
                return token_data, usage_count + 1

        raise BaseAppException("Invalid or expired token")

    @classmethod
    def validate_cluster_name(cls, cluster_name: str):
        if not cluster_name:
            raise ValidationAppException("集群名称不能为空")

    @classmethod
    def validate_host_path(cls, path: str, field_name: str):
        if not path:
            raise ValidationAppException(f"{field_name} 不能为空")
        if not isinstance(path, str):
            raise ValidationAppException(f"{field_name} 格式不正确")

        normalized_path = path.strip()
        if not normalized_path.startswith("/"):
            raise ValidationAppException(f"{field_name} 必须为绝对路径")
        if cls.PATH_UNSAFE_PATTERN.search(normalized_path):
            raise ValidationAppException(f"{field_name} 包含非法字符")
        return normalized_path

    @classmethod
    def normalize_render_options(
        cls,
        runtime_profile: str | None = None,
        host_log_path: str | None = None,
        docker_container_log_path: str | None = None,
    ) -> dict:
        normalized_profile = (runtime_profile or "standard").strip().lower()
        if normalized_profile not in cls.RUNTIME_PROFILES:
            raise ValidationAppException("日志运行环境配置不正确")

        normalized_host_log_path = None
        normalized_docker_container_log_path = None
        if normalized_profile == "custom":
            normalized_host_log_path = cls.validate_host_path(host_log_path, "节点 Pod 日志根目录")
            if docker_container_log_path:
                normalized_docker_container_log_path = cls.validate_host_path(
                    docker_container_log_path,
                    "Docker 容器日志目录",
                )

        return {
            "runtime_profile": normalized_profile,
            "host_log_path": normalized_host_log_path,
            "docker_container_log_path": normalized_docker_container_log_path,
        }

    @classmethod
    def validate_patterns(cls, raw_value, field_name: str) -> list[str]:
        if raw_value in (None, ""):
            items = []
        elif isinstance(raw_value, str):
            items = raw_value.splitlines()
        elif isinstance(raw_value, list):
            items = raw_value
        else:
            raise ValidationAppException(f"{field_name} 格式不正确")

        normalized = []
        seen = set()
        for item in items:
            if item is None:
                continue
            if not isinstance(item, str):
                raise ValidationAppException(f"{field_name} 格式不正确")
            value = item.strip()
            if not value or value in seen:
                continue
            if "_" in value:
                raise ValidationAppException(f"{field_name} 不能包含下划线，Kubernetes 名称不含 '_'")
            if "**" in value:
                raise ValidationAppException(f"{field_name} 不支持 '**'，请使用 '*' 匹配任意长度")
            if any(ch.isupper() for ch in value):
                raise ValidationAppException(f"{field_name} 不能包含大写字母")
            if not cls.PATTERN_WHITELIST.fullmatch(value):
                raise ValidationAppException(f"{field_name} 仅允许小写字母、数字、'-'、'.'、'*'、'?'")
            seen.add(value)
            normalized.append(value)

        if len(normalized) > cls.MAX_PATTERNS_PER_DIMENSION:
            raise ValidationAppException(f"{field_name} 最多 {cls.MAX_PATTERNS_PER_DIMENSION} 项，请改用更宽的通配")
        return normalized

    @classmethod
    def build_include_patterns(cls, namespace_patterns: list[str], pod_patterns: list[str]) -> list[str]:
        if not namespace_patterns and not pod_patterns:
            return []

        namespace_globs = namespace_patterns or ["*"]
        pod_globs = pod_patterns or ["*"]
        patterns = [f"/var/log/pods/{namespace}_{pod}_*/**" for namespace in namespace_globs for pod in pod_globs]
        if len(patterns) > cls.MAX_INCLUDE_PATTERNS:
            raise ValidationAppException(f"采集范围展开后超过 {cls.MAX_INCLUDE_PATTERNS} 条，请改用更宽的通配")
        return patterns

    @staticmethod
    def get_k8s_instance(instance_id: str) -> CollectInstance:
        instance = CollectInstance.objects.filter(id=instance_id, collect_type__name="kubernetes").first()
        if not instance:
            raise BaseAppException("Kubernetes 日志接入实例不存在")
        return instance

    @classmethod
    def serialize_setting(cls, instance: CollectInstance, setting: K8sCollectSetting | None) -> dict:
        if setting is None:
            return {"instance_id": instance.id, "unknown": True}
        return {
            "instance_id": instance.id,
            "unknown": False,
            "runtime_profile": setting.runtime_profile,
            "host_log_path": setting.host_log_path or None,
            "docker_container_log_path": setting.docker_container_log_path or None,
            "namespace_patterns": setting.namespace_patterns or [],
            "pod_patterns": setting.pod_patterns or [],
        }

    @classmethod
    def get_setting(cls, instance_id: str) -> dict:
        instance = cls.get_k8s_instance(instance_id)
        setting = K8sCollectSetting.objects.filter(collect_instance_id=instance.id).first()
        return cls.serialize_setting(instance, setting)

    @classmethod
    def save_setting(cls, instance_id: str, data: dict) -> dict:
        instance = cls.get_k8s_instance(instance_id)
        render_options = cls.normalize_render_options(
            data.get("runtime_profile"),
            data.get("host_log_path"),
            data.get("docker_container_log_path"),
        )
        namespace_patterns = cls.validate_patterns(data.get("namespace_patterns"), "采集 Namespace")
        pod_patterns = cls.validate_patterns(data.get("pod_patterns"), "采集 Pod")
        cls.build_include_patterns(namespace_patterns, pod_patterns)

        with transaction.atomic():
            setting, _created = K8sCollectSetting.objects.update_or_create(
                collect_instance_id=instance.id,
                defaults={
                    "runtime_profile": render_options["runtime_profile"],
                    "host_log_path": render_options["host_log_path"] or "",
                    "docker_container_log_path": render_options["docker_container_log_path"] or "",
                    "namespace_patterns": namespace_patterns,
                    "pod_patterns": pod_patterns,
                },
            )
        return cls.serialize_setting(instance, setting)

    @classmethod
    def load_setting_render_options(cls, instance_id: str) -> dict:
        instance = cls.get_k8s_instance(instance_id)
        setting = K8sCollectSetting.objects.filter(collect_instance_id=instance.id).first()
        if setting is None:
            raise ValidationAppException(cls.SETTING_MISSING_MESSAGE)
        render_options = cls.normalize_render_options(
            setting.runtime_profile,
            setting.host_log_path or None,
            setting.docker_container_log_path or None,
        )
        namespace_patterns = cls.validate_patterns(setting.namespace_patterns, "采集 Namespace")
        pod_patterns = cls.validate_patterns(setting.pod_patterns, "采集 Pod")
        render_options["namespace_patterns"] = namespace_patterns
        render_options["pod_patterns"] = pod_patterns
        return render_options

    @staticmethod
    def get_collect_type(collect_type_id):
        collect_type = CollectType.objects.filter(id=collect_type_id).first()
        if not collect_type:
            raise BaseAppException("采集类型不存在")
        if collect_type.name != "kubernetes":
            raise BaseAppException("当前采集类型不是 Kubernetes")
        return collect_type

    @classmethod
    def create_k8s_collect_instance(cls, data: dict):
        organizations = data.get("organizations") or []
        collect_type_id = data.get("collect_type_id")
        name = (data.get("name") or "").strip()
        instance_id = (data.get("id") or name).strip()

        cls.get_collect_type(collect_type_id)
        cls.validate_cluster_name(name)
        cls.validate_cluster_name(instance_id)

        if CollectInstance.objects.filter(collect_type_id=collect_type_id, name=name).exists():
            raise BaseAppException("当前集群名称已存在")
        if CollectInstance.objects.filter(id=instance_id).exists():
            raise BaseAppException("当前实例 ID 已存在")

        with transaction.atomic():
            instance = CollectInstance.objects.create(
                id=instance_id,
                name=name,
                collect_type_id=collect_type_id,
                node_id=None,
            )

            assos = [
                CollectInstanceOrganization(
                    collect_instance_id=instance.id,
                    organization=organization,
                )
                for organization in organizations
            ]
            if assos:
                CollectInstanceOrganization.objects.bulk_create(assos, ignore_conflicts=True)

        return {"instance_id": instance.id}

    @classmethod
    def generate_install_token(
        cls,
        cluster_name: str,
        cloud_region_id: str,
        image_registry_prefix: str | None = None,
    ) -> str:
        image_registry_prefix = normalize_k8s_image_registry_prefix(image_registry_prefix)
        token = str(uuid.uuid4())
        now = timezone.now()
        K8sInstallToken.objects.filter(expires_at__lte=now).delete()
        K8sInstallToken.objects.create(
            token_hash=cls._hash_token(token),
            cluster_name=cluster_name,
            cloud_region_id=str(cloud_region_id),
            config_type="log",
            image_registry_prefix=image_registry_prefix,
            usage_count=0,
            max_usage=cls.TOKEN_MAX_USAGE,
            expires_at=now + timedelta(seconds=cls.TOKEN_EXPIRE_TIME),
        )
        return token

    @classmethod
    def validate_and_get_token_data(cls, token: str) -> dict:
        if not token:
            raise BaseAppException("Token is required")

        data, usage_count = cls._consume_token_usage(token)
        max_usage = data["max_usage"]
        return {
            "cluster_name": data["cluster_name"],
            "cloud_region_id": data["cloud_region_id"],
            "config_type": data["config_type"],
            "image_registry_prefix": normalize_k8s_image_registry_prefix(data.get("image_registry_prefix")),
            "remaining_usage": max_usage - usage_count,
        }

    @staticmethod
    def get_cloud_region_envconfig(cloud_region_id: str) -> dict:
        env_vars = NodeMgmt().get_cloud_region_envconfig(cloud_region_id)
        missing_vars = []
        for field in [
            "NODE_SERVER_URL",
            "WEBHOOK_SERVER_URL",
            "NATS_USERNAME",
            "NATS_PASSWORD",
            "NATS_SERVERS",
        ]:
            if not env_vars.get(field):
                missing_vars.append(field)

        if missing_vars:
            raise BaseAppException(f"Missing required environment variables in cloud region {cloud_region_id}: {', '.join(missing_vars)}")

        return env_vars

    @classmethod
    def generate_install_command(
        cls,
        instance_id: str,
        cloud_region_id: str,
        image_registry_prefix: str | None = None,
    ) -> str:
        instance = cls.get_k8s_instance(instance_id)
        cls.load_setting_render_options(instance.id)

        env_vars = cls.get_cloud_region_envconfig(cloud_region_id)
        server_url = env_vars.get("NODE_SERVER_URL")
        token = cls.generate_install_token(instance.id, str(cloud_region_id), image_registry_prefix)
        api_url = f"{server_url.rstrip('/')}/api/v1/log/open_api/k8s/render/"
        return build_kubectl_install_command(api_url, token)

    @classmethod
    def render_config_from_cloud_region(
        cls,
        cluster_name: str,
        cloud_region_id: str,
        image_registry_prefix: str | None = None,
    ) -> str:
        render_options = cls.load_setting_render_options(cluster_name)
        env_vars = cls.get_cloud_region_envconfig(cloud_region_id)
        webhook_server_url = env_vars.get("WEBHOOK_SERVER_URL")
        api_url = f"{webhook_server_url.rstrip('/')}/infra/kubernetes"

        try:
            response = requests.post(
                api_url,
                json={
                    "cluster_name": cluster_name,
                    "type": "log",
                    "nats_url": env_vars.get("NATS_SERVERS"),
                    "nats_username": env_vars.get("NATS_USERNAME"),
                    "nats_password": env_vars.get("NATS_PASSWORD"),
                    "nats_ca": env_vars.get("NATS_TLS_CA"),
                    "image_registry_prefix": normalize_k8s_image_registry_prefix(image_registry_prefix),
                    **render_options,
                },
                headers={"Content-Type": "application/json"},
                timeout=cls.REQUEST_TIMEOUT,
                verify=get_webhook_tls_verify(),
            )
            if response.status_code != 200:
                raise BaseAppException(f"Infra API returned status {response.status_code}: {response.text}")

            response_data = response.json()
            yaml_content = response_data.get("yaml")
            if not yaml_content:
                raise BaseAppException("Invalid response from infra API: missing 'yaml' field")
            return yaml_content
        except requests.Timeout as error:
            raise BaseAppException(f"Infra API request timeout: {error}")
        except requests.RequestException as error:
            raise BaseAppException(f"Infra API request failed: {error}")
        except ValueError as error:
            raise BaseAppException(f"Failed to parse response from infra API: {error}")

    @staticmethod
    def check_collect_status(instance_id: str) -> bool:
        instance = K8sLogCollectService.get_k8s_instance(instance_id)

        end_time = timezone.now()
        start_time = end_time - timedelta(minutes=10)
        query = f'collect_type:"kubernetes" AND instance_id:"{instance.id}"'
        data = SearchService.search_logs(
            query,
            start_time.isoformat(timespec="seconds"),
            end_time.isoformat(timespec="seconds"),
            1,
        )
        return bool(data)
