from datetime import timedelta
import json
import re
import uuid

import requests
from django.core.cache import cache
from django.db import transaction
from django.utils import timezone

from apps.core.exceptions.base_app_exception import BaseAppException
from apps.core.utils.webhook_tls import get_webhook_tls_verify
from apps.log.models import CollectInstance, CollectInstanceOrganization, CollectType
from apps.log.services.search import SearchService
from apps.rpc.node_mgmt import NodeMgmt


class K8sLogCollectService:
    TOKEN_EXPIRE_TIME = 60 * 30
    TOKEN_MAX_USAGE = 5
    REQUEST_TIMEOUT = 30
    TOKEN_CACHE_PREFIX = "log_k8s_install_token"
    USAGE_COUNT_CACHE_SUFFIX = "usage_count"
    RUNTIME_PROFILES = {"standard", "docker", "custom"}
    PATH_UNSAFE_PATTERN = re.compile(r"[\r\n']")

    @classmethod
    def _build_cache_key(cls, token: str) -> str:
        return f"{cls.TOKEN_CACHE_PREFIX}:{token}"

    @classmethod
    def _consume_token_usage(cls, cache_key: str, data: dict, max_usage: int) -> int:
        usage_cache_key = f"{cache_key}:{cls.USAGE_COUNT_CACHE_SUFFIX}"
        cache.add(usage_cache_key, data.get("usage_count", 0), timeout=cls.TOKEN_EXPIRE_TIME)
        try:
            usage_count = cache.incr(usage_cache_key)
        except ValueError as exc:
            raise BaseAppException("Invalid or expired token") from exc

        if usage_count > max_usage:
            # 保留独立计数键作为 tombstone，防止已读到旧 payload 的并发请求重建计数。
            cache.delete(cache_key)
            raise BaseAppException(f"Token has exceeded maximum usage limit ({max_usage} times)")

        return usage_count

    @classmethod
    def validate_cluster_name(cls, cluster_name: str):
        if not cluster_name:
            raise BaseAppException("集群名称不能为空")

    @classmethod
    def validate_host_path(cls, path: str, field_name: str):
        if not path:
            raise BaseAppException(f"{field_name} 不能为空")
        if not isinstance(path, str):
            raise BaseAppException(f"{field_name} 格式不正确")

        normalized_path = path.strip()
        if not normalized_path.startswith("/"):
            raise BaseAppException(f"{field_name} 必须为绝对路径")
        if cls.PATH_UNSAFE_PATTERN.search(normalized_path):
            raise BaseAppException(f"{field_name} 包含非法字符")
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
            raise BaseAppException("日志运行环境配置不正确")

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
    def generate_install_token(cls, cluster_name: str, cloud_region_id: str) -> str:
        token = str(uuid.uuid4())
        cache.set(
            cls._build_cache_key(token),
            {
                "cluster_name": cluster_name,
                "cloud_region_id": str(cloud_region_id),
                "config_type": "log",
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

        max_usage = data.get("max_usage", cls.TOKEN_MAX_USAGE)
        usage_count = cls._consume_token_usage(cache_key, data, max_usage)
        return {
            "cluster_name": data["cluster_name"],
            "cloud_region_id": data["cloud_region_id"],
            "config_type": data.get("config_type", "log"),
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
        runtime_profile: str | None = None,
        host_log_path: str | None = None,
        docker_container_log_path: str | None = None,
    ) -> str:
        instance = CollectInstance.objects.filter(id=instance_id, collect_type__name="kubernetes").first()
        if not instance:
            raise BaseAppException("Kubernetes 日志接入实例不存在")

        env_vars = cls.get_cloud_region_envconfig(cloud_region_id)
        server_url = env_vars.get("NODE_SERVER_URL")
        token = cls.generate_install_token(instance.id, str(cloud_region_id))
        render_options = cls.normalize_render_options(
            runtime_profile,
            host_log_path,
            docker_container_log_path,
        )
        api_url = f"{server_url.rstrip('/')}/api/v1/log/open_api/k8s/render/"
        payload = json.dumps(
            {
                "token": token,
                **render_options,
            },
            ensure_ascii=False,
        )
        return f"curl -sSLk -X POST -H 'Content-Type: application/json' {api_url} -d '{payload}' | kubectl apply -f -"

    @classmethod
    def render_config_from_cloud_region(
        cls,
        cluster_name: str,
        cloud_region_id: str,
        runtime_profile: str | None = None,
        host_log_path: str | None = None,
        docker_container_log_path: str | None = None,
    ) -> str:
        env_vars = cls.get_cloud_region_envconfig(cloud_region_id)
        webhook_server_url = env_vars.get("WEBHOOK_SERVER_URL")
        api_url = f"{webhook_server_url.rstrip('/')}/infra/kubernetes"
        render_options = cls.normalize_render_options(
            runtime_profile,
            host_log_path,
            docker_container_log_path,
        )

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
        instance = CollectInstance.objects.filter(id=instance_id, collect_type__name="kubernetes").first()
        if not instance:
            raise BaseAppException("Kubernetes 日志接入实例不存在")

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
