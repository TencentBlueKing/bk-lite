import json
import shlex
import uuid

import requests
from django.core.cache import cache
from django.db import transaction

from apps.core.exceptions.base_app_exception import BaseAppException, ValidationAppException
from apps.core.utils.webhook_tls import get_webhook_tls_verify
from apps.monitor.constants.k3s_onboarding import (
    CLUSTER_OBJECT_NAME,
    REQUEST_TIMEOUT,
    TOKEN_EXPIRE_TIME,
    TOKEN_MAX_USAGE,
    TOKEN_PREFIX,
    WEBHOOK_PATH,
)
from apps.monitor.models import (
    MonitorInstance,
    MonitorInstanceOrganization,
    MonitorObject,
)
from apps.monitor.services.monitor_object import MonitorObjectService
from apps.monitor.services.node_mgmt import InstanceConfigService
from apps.monitor.utils.dimension import parse_instance_id
from apps.monitor.utils.victoriametrics_api import VictoriaMetricsAPI
from apps.rpc.node_mgmt import NodeMgmt


class K3SOnboardingService:
    """独立编排 K3S 监控实例、有限期清单和上报验证。"""

    SIGNALS = {
        "cluster": (
            "kube_node_info",
            "prometheus_remote_write_kube_node_info",
        ),
        "container": (
            "container_cpu_usage_seconds_total",
            "prometheus_remote_write_container_cpu_usage_seconds_total",
        ),
        "node": ("system_load1", "system_load1"),
    }

    @staticmethod
    def _get_cluster_object(monitor_object_id):
        monitor_object = MonitorObject.objects.filter(id=monitor_object_id).first()
        if not monitor_object or monitor_object.name != CLUSTER_OBJECT_NAME:
            raise ValidationAppException(
                f"monitor_object_id must reference {CLUSTER_OBJECT_NAME}"
            )
        return monitor_object

    @staticmethod
    def _get_cluster_instance(instance_id):
        instance = (
            MonitorInstance.objects.select_related("monitor_object")
            .filter(id=instance_id, is_deleted=False, is_active=True)
            .first()
        )
        if not instance or instance.monitor_object.name != CLUSTER_OBJECT_NAME:
            raise ValidationAppException(
                f"instance_id must reference an active {CLUSTER_OBJECT_NAME}"
            )
        return instance

    @classmethod
    @transaction.atomic
    def create_instance(
        cls,
        *,
        monitor_object_id,
        instance_id,
        name,
        organizations,
    ):
        monitor_object = cls._get_cluster_object(monitor_object_id)
        MonitorObjectService.validate_new_instance_name_unique(
            monitor_object.id,
            name,
        )
        stored_id = str((str(instance_id),))
        instance = MonitorInstance.objects.create(
            id=stored_id,
            name=name,
            monitor_object=monitor_object,
            auto=False,
        )
        MonitorInstanceOrganization.objects.bulk_create(
            [
                MonitorInstanceOrganization(
                    monitor_instance=instance,
                    organization=organization,
                )
                for organization in organizations
            ],
            ignore_conflicts=True,
        )
        InstanceConfigService.create_default_rule(
            monitor_object.id,
            instance.id,
            organizations,
        )
        return {"instance_id": instance.id}

    @staticmethod
    def _payload_key(token):
        return f"{token}:payload"

    @staticmethod
    def _usage_key(token):
        return f"{token}:usage"

    @classmethod
    def issue_render_token(cls, *, instance, cloud_region_id):
        logical_instance_id = parse_instance_id(instance.id)[0]
        organizations = list(
            instance.monitorinstanceorganization_set.values_list(
                "organization",
                flat=True,
            )
        )
        token = f"{TOKEN_PREFIX}:{uuid.uuid4()}"
        payload = {
            "instance_id": logical_instance_id,
            "instance_pk": instance.id,
            "cloud_region_id": cloud_region_id,
            "organizations": organizations,
        }
        cache.set(
            cls._payload_key(token),
            payload,
            timeout=TOKEN_EXPIRE_TIME,
        )
        cache.add(
            cls._usage_key(token),
            0,
            timeout=TOKEN_EXPIRE_TIME,
        )
        return token

    @classmethod
    def _consume_render_token(cls, token):
        if not token or not token.startswith(f"{TOKEN_PREFIX}:"):
            raise BaseAppException("K3S render token is required")

        payload_key = cls._payload_key(token)
        usage_key = cls._usage_key(token)
        payload = cache.get(payload_key)
        if not payload:
            raise BaseAppException("Invalid or expired K3S render token")

        try:
            usage = cache.incr(usage_key)
        except ValueError as exc:
            raise BaseAppException("Invalid or expired K3S render token") from exc

        if usage > TOKEN_MAX_USAGE:
            cache.delete_many([payload_key, usage_key])
            raise BaseAppException(
                f"K3S render token has exceeded maximum usage limit ({TOKEN_MAX_USAGE} times)"
            )

        cls._get_cluster_instance(payload["instance_pk"])
        return payload, TOKEN_MAX_USAGE - usage

    @classmethod
    def generate_install_commands(cls, *, instance_id, cloud_region_id):
        instance = cls._get_cluster_instance(instance_id)
        env = NodeMgmt().get_cloud_region_envconfig(cloud_region_id)
        server_url = env.get("NODE_SERVER_URL")
        if not server_url:
            raise BaseAppException(
                f"Missing NODE_SERVER_URL in cloud region {cloud_region_id}"
            )

        endpoint = (
            f"{server_url.rstrip('/')}"
            "/api/v1/monitor/open_api/k3s_onboarding/render/"
        )

        def build_command(token, kubectl_command):
            body = shlex.quote(json.dumps({"token": token}, separators=(",", ":")))
            return (
                "curl -sSLk --fail "
                f"-X POST -H 'Content-Type: application/json' {shlex.quote(endpoint)} "
                f"-d {body} | {kubectl_command}"
            )

        install_token = cls.issue_render_token(
            instance=instance,
            cloud_region_id=cloud_region_id,
        )
        uninstall_token = cls.issue_render_token(
            instance=instance,
            cloud_region_id=cloud_region_id,
        )
        return {
            "install_command": build_command(
                install_token,
                "kubectl apply -f -",
            ),
            "uninstall_command": build_command(
                uninstall_token,
                "kubectl delete --ignore-not-found=true -f -",
            ),
            "expires_in": TOKEN_EXPIRE_TIME,
        }

    @classmethod
    def render_manifest(cls, token):
        payload, remaining_usage = cls._consume_render_token(token)
        cloud_region_id = payload["cloud_region_id"]
        env = NodeMgmt().get_cloud_region_envconfig(cloud_region_id)
        required = {
            "NATS_USERNAME": "nats_username",
            "NATS_PASSWORD": "nats_password",
            "NATS_SERVERS": "nats_url",
            "NATS_TLS_CA": "nats_ca",
            "WEBHOOK_SERVER_URL": None,
        }
        missing = [name for name in required if not env.get(name)]
        if missing:
            raise BaseAppException(
                f"Missing required environment variables in cloud region {cloud_region_id}: "
                f"{', '.join(missing)}"
            )

        request_payload = {
            target: env[source]
            for source, target in required.items()
            if target is not None
        }
        request_payload["cluster_name"] = payload["instance_id"]
        url = f"{env['WEBHOOK_SERVER_URL'].rstrip('/')}{WEBHOOK_PATH}"

        try:
            response = requests.post(
                url,
                json=request_payload,
                headers={"Content-Type": "application/json"},
                timeout=REQUEST_TIMEOUT,
                verify=get_webhook_tls_verify(),
            )
            if response.status_code != 200:
                raise BaseAppException(
                    f"K3S renderer returned status {response.status_code}"
                )
            rendered = response.json()
        except requests.Timeout as exc:
            raise BaseAppException("K3S renderer request timed out") from exc
        except requests.RequestException as exc:
            raise BaseAppException("K3S renderer request failed") from exc
        except ValueError as exc:
            raise BaseAppException("K3S renderer returned invalid JSON") from exc

        yaml_content = rendered.get("yaml")
        if not yaml_content:
            raise BaseAppException("K3S renderer response is missing yaml")
        return {
            "yaml": yaml_content,
            "remaining_usage": remaining_usage,
        }

    @classmethod
    def verify_reporting(cls, instance_id):
        instance = cls._get_cluster_instance(instance_id)
        logical_instance_id = parse_instance_id(instance.id)[0]
        signals = {}
        api = VictoriaMetricsAPI()

        for signal, (metric, measurement) in cls.SIGNALS.items():
            query = (
                f"{measurement}"
                f'{{instance_type="k3s",instance_id={json.dumps(logical_instance_id)}}}'
            )
            try:
                response = api.query(query)
                result = response.get("data", {}).get("result", [])
                status = "success" if result else "pending"
            except Exception:
                status = "error"
            signals[signal] = {"status": status, "metric": metric}

        statuses = {signal["status"] for signal in signals.values()}
        if statuses == {"success"}:
            status = "success"
        elif statuses == {"pending"}:
            status = "pending"
        elif statuses == {"error"}:
            status = "error"
        else:
            status = "partial"
        return {"status": status, "signals": signals}
