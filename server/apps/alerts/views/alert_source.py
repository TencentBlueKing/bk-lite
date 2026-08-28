# -- coding: utf-8 --
import hashlib
import subprocess
import tempfile
from datetime import timedelta
from pathlib import Path

from django.utils import timezone
from django.utils.translation import get_language
from rest_framework import status
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.viewsets import ReadOnlyModelViewSet

from apps.alerts.common.source_adapter.base import INTEGRATION_SECRET_PLACEHOLDER, AlertSourceAdapterFactory
from apps.alerts.filters import AlertSourceModelFilter
from apps.alerts.models.alert_source import AlertSource
from apps.alerts.models.models import Event
from apps.alerts.serializers import (
    AlertSourceDetailSerializer,
    AlertSourceOptionSerializer,
    AlertSourceOverviewSerializer,
    K8sRenderRequestSerializer,
    TeamSecretRequestSerializer,
)
from apps.alerts.serializers.alert_source import build_public_alert_source_config
from apps.alerts.service.alert_source_credential import AlertSourceCredentialService
from apps.alerts.service.k8s_install import K8sInstallService
from apps.core.decorators.api_permission import HasPermission
from apps.core.exceptions.base_app_exception import BaseAppException
from apps.core.utils.team_utils import get_current_team
from apps.core.utils.web_utils import WebUtils
from apps.rpc.node_mgmt import NodeMgmt
from config.drf.pagination import CustomPageNumberPagination

K8S_SOURCE_ID = "k8s"
ALERT_SOURCE_OPTION_PERMISSIONS = (
    "Integration-View,Alarms-View,alert_assign-View,shield_strategy-View," "alert_enrichment-View,correlation_rules-View,action_rules-View"
)
K8S_IMAGE_REFERENCE = "ghcr.io/resmoio/kubernetes-event-exporter:latest"
K8S_SUPPORT_DIR = Path(__file__).resolve().parents[1] / "support-files" / "kubernetes-event-exporter"
K8S_DOWNLOAD_FILES = {
    "deploy_yaml": {
        "key": "deploy_yaml",
        "file_name": "bk-lite-k8s-event-exporter.deploy.yaml",
        "display_name": "Deployment YAML",
    },
    "image_tar": {
        "key": "image_tar",
        "file_name": "kubernetes-event-exporter.tar",
        "display_name": "Offline Image Package",
    },
}


def _get_valid_current_team(request):
    current_team = get_current_team(request)
    if current_team in (None, ""):
        raise BaseAppException("缺少 current_team 参数")

    try:
        return int(current_team)
    except (TypeError, ValueError):
        raise BaseAppException("current_team 参数非法")


class AlertSourceModelViewSet(ReadOnlyModelViewSet):
    """
    告警源
    """

    queryset = AlertSource.objects.all()
    serializer_class = AlertSourceOverviewSerializer
    ordering_fields = ["id"]
    ordering = ["id"]
    filterset_class = AlertSourceModelFilter
    pagination_class = CustomPageNumberPagination

    def get_serializer_class(self):
        if self.action == "options":
            return AlertSourceOptionSerializer
        if self.action == "retrieve":
            return AlertSourceDetailSerializer
        return AlertSourceOverviewSerializer

    @HasPermission("Integration-View")
    def list(self, request, *args, **kwargs):
        return super().list(request, *args, **kwargs)

    @HasPermission("Integration-Detail")
    def retrieve(self, request, *args, **kwargs):
        return super().retrieve(request, *args, **kwargs)

    @HasPermission(ALERT_SOURCE_OPTION_PERMISSIONS)
    @action(detail=False, methods=["get"], url_path="options")
    def options(self, request):
        return super().list(request)

    @HasPermission("Integration-Detail")
    @action(detail=True, methods=["get"], url_path="integration-guide")
    def integration_guide(self, request, pk=None):
        alert_source = self.get_object()
        adapter_class = AlertSourceAdapterFactory.get_adapter(alert_source)
        adapter = adapter_class(alert_source=alert_source)
        base_url = request.build_absolute_uri("/").rstrip("/")
        language = getattr(request, "LANGUAGE_CODE", None) or get_language() or "zh-hans"
        return Response(
            adapter.get_integration_guide(
                base_url,
                language=language,
                credential=INTEGRATION_SECRET_PLACEHOLDER,
            )
        )

    @HasPermission("Integration-Detail")
    @action(detail=True, methods=["post"], url_path="integration-material")
    def integration_material(self, request, pk=None):
        request_serializer = TeamSecretRequestSerializer(data=request.data)
        request_serializer.is_valid(raise_exception=True)
        source = self.get_object()
        credential = AlertSourceCredentialService.deployment_credential(
            request.user,
            source,
            request_serializer.validated_data["team_id"],
        )
        adapter_class = AlertSourceAdapterFactory.get_adapter(source)
        adapter = adapter_class(alert_source=source)
        base_url = request.build_absolute_uri("/").rstrip("/")
        language = getattr(request, "LANGUAGE_CODE", None) or get_language() or "zh-hans"
        return Response(adapter.get_integration_guide(base_url, language=language, credential=credential))

    @staticmethod
    def _get_k8s_source():
        return AlertSource.objects.filter(source_id=K8S_SOURCE_ID).first()

    @staticmethod
    def _build_k8s_deploy_yaml(
        receiver_url: str,
        secret: str,
        cluster_name: str,
        push_source_id: str,
        insecure_skip_verify: bool = False,
    ):
        secret_template = (K8S_SUPPORT_DIR / "secret.yaml.template").read_text(encoding="utf-8").strip()
        exporter_template = (K8S_SUPPORT_DIR / "bk-lite-k8s-event-exporter.yaml").read_text(encoding="utf-8").strip()
        secret_template = secret_template.replace("your-k8s-cluster", cluster_name)
        secret_template = secret_template.replace("http://bk-lite-server:8001/api/v1/alerts/api/receiver_data/", receiver_url)
        secret_template = secret_template.replace("your-alert-source-secret", secret)
        secret_template = secret_template.replace("BK_LITE_PUSH_SOURCE_ID: k8s", f"BK_LITE_PUSH_SOURCE_ID: {push_source_id}")
        # 把基于 secret 的 hash 注入 Deployment template 的 annotation，
        # 让 secret 变更后 kubectl apply 触发滚动重启（envFrom 注入的环境变量在 Pod 启动时一次性固化）。
        secret_hash = hashlib.sha256((secret or "").encode("utf-8")).hexdigest()[:16]
        exporter_template = exporter_template.replace("PLACEHOLDER_SECRET_HASH", secret_hash)
        # 自签证书场景：在 webhook receiver 的 endpoint 后插入 tls.insecureSkipVerify=true。
        # 缩进必须对齐 ConfigMap 内嵌 config.yaml 的层级（endpoint 10 空格 → tls 10 空格 → insecureSkipVerify 12 空格）。
        if insecure_skip_verify:
            exporter_template = exporter_template.replace(
                'endpoint: "${BK_LITE_RECEIVER_URL}"',
                'endpoint: "${BK_LITE_RECEIVER_URL}"\n          tls:\n            insecureSkipVerify: true',
            )
        guide_header = "\n".join(
            [
                "# BK-Lite K8s Event Exporter Deployment Template",
                "# This file is already rendered from BK-Lite K8s integration settings.",
                f"# Cluster Name: {cluster_name}",
                f"# Push Source ID: {push_source_id}",
                "",
            ]
        )
        # exporter_template 先出（含 Namespace 声明），再出 secret_template，
        # 否则 kubectl apply 时 Secret 可能撞上 Namespace 还未生效的窗口。
        return f"{guide_header}{exporter_template}\n---\n{secret_template}\n"

    @staticmethod
    def _build_k8s_image_tar_file():
        temp_file = tempfile.NamedTemporaryFile(prefix="k8s-event-exporter-", suffix=".tar")
        try:
            subprocess.run(
                ["docker", "save", "-o", temp_file.name, K8S_IMAGE_REFERENCE],
                check=True,
                capture_output=True,
                text=True,
            )
            temp_file.seek(0)
        except subprocess.CalledProcessError as error:
            temp_file.close()
            raise RuntimeError(error.stderr or error.stdout or "Failed to export image") from error
        except BaseException:
            temp_file.close()
            raise
        return temp_file

    @classmethod
    def _build_k8s_render_payload(cls, request, source: AlertSource):
        request_serializer = K8sRenderRequestSerializer(data=request.data)
        request_serializer.is_valid(raise_exception=True)
        data = request_serializer.validated_data
        team_secret = AlertSourceCredentialService.deployment_credential(
            request.user,
            source,
            data["team_id"],
        )
        payload = K8sInstallService.build_render_payload(
            source_id=source.source_id,
            source_secret=team_secret,
            receiver_path=source.config.get("url", ""),
            server_url=data["server_url"],
            cluster_name=data["cluster_name"],
            push_source_id=data.get("push_source_id"),
        )
        payload["insecure_skip_verify"] = data["insecure_skip_verify"]
        return payload

    @HasPermission("Integration-Detail")
    @action(methods=["get"], detail=False, url_path="k8s_meta")
    def k8s_meta(self, request):
        source = self._get_k8s_source()
        if not source:
            return WebUtils.response_error(
                error_message="K8s alert source not found",
                status_code=status.HTTP_404_NOT_FOUND,
            )

        public_config = build_public_alert_source_config(source)
        data = {
            "source_id": source.source_id,
            "name": source.name,
            "description": source.description,
            "receiver_url": public_config.get("url", ""),
            "method": public_config.get("method", "POST"),
            "headers": public_config.get("headers", {}),
            "push_source_id_default": "k8s",
            "push_source_id_configurable": True,
            "image_reference": K8S_IMAGE_REFERENCE,
            "download_files": list(K8S_DOWNLOAD_FILES.values()),
            "notes": [
                "下载渲染后的部署 YAML 后，可以直接配合离线镜像包完成部署。",
                "BK_LITE_SOURCE_ID 固定为 k8s，BK_LITE_PUSH_SOURCE_ID 默认 k8s，但支持按集群或链路自定义。",
                "该方案面向告警场景，默认只转发 Warning 类型 Kubernetes Event。",
            ],
        }
        return WebUtils.response_success(data)

    @HasPermission("Integration-Detail")
    @action(methods=["post"], detail=False, url_path="snmp_trap_nodes")
    def snmp_trap_nodes(self, request):
        current_team = _get_valid_current_team(request)
        organization_ids = [] if request.user.is_superuser else [i["id"] for i in getattr(request.user, "group_list", [])]
        query_data = {
            "cloud_region_id": request.data.get("cloud_region_id"),
            "organization_ids": organization_ids,
            "name": request.data.get("name"),
            "ip": request.data.get("ip"),
            "os": request.data.get("os"),
            "page": request.data.get("page", 1),
            "page_size": request.data.get("page_size", 10),
            "is_active": request.data.get("is_active"),
            "is_manual": request.data.get("is_manual"),
            "is_container": request.data.get("is_container"),
            "permission_data": {
                "username": request.user.username,
                "domain": request.user.domain,
                "current_team": current_team,
            },
        }
        data = NodeMgmt().node_list(query_data)
        if not isinstance(data, dict):
            data = {}
        return WebUtils.response_success(
            {
                "count": data.get("count", 0),
                "nodes": data.get("nodes", []),
            }
        )

    @HasPermission("Integration-Detail")
    @action(methods=["post"], detail=False, url_path="k8s_render")
    def k8s_render(self, request):
        source = self._get_k8s_source()
        if not source:
            return WebUtils.response_error(
                error_message="K8s alert source not found",
                status_code=status.HTTP_404_NOT_FOUND,
            )

        payload = self._build_k8s_render_payload(request, source)
        yaml_content = self._build_k8s_deploy_yaml(
            receiver_url=payload["receiver_url"],
            secret=payload["secret"],
            cluster_name=payload["cluster_name"],
            push_source_id=payload["push_source_id"],
            insecure_skip_verify=payload.get("insecure_skip_verify", False),
        )
        return WebUtils.response_file(yaml_content.encode("utf-8"), K8S_DOWNLOAD_FILES["deploy_yaml"]["file_name"])

    @HasPermission("Integration-Detail")
    @action(methods=["post"], detail=False, url_path="k8s_install_command")
    def k8s_install_command(self, request):
        source = self._get_k8s_source()
        if not source:
            return WebUtils.response_error(
                error_message="K8s alert source not found",
                status_code=status.HTTP_404_NOT_FOUND,
            )

        payload = self._build_k8s_render_payload(request, source)
        token = K8sInstallService.generate_install_token(payload)
        command = K8sInstallService.build_install_command(payload["server_url"], token)
        return WebUtils.response_success({"command": command, "token": token})

    @HasPermission("Integration-Detail")
    @action(methods=["post"], detail=False, url_path="k8s_download/(?P<file_key>[^/.]+)")
    def k8s_download(self, request, file_key):
        file_meta = K8S_DOWNLOAD_FILES.get(file_key)
        if not file_meta:
            return WebUtils.response_error(
                error_message="Unsupported download file",
                status_code=status.HTTP_404_NOT_FOUND,
            )
        if file_key == "image_tar":
            try:
                return WebUtils.response_file(self._build_k8s_image_tar_file(), file_meta["file_name"])
            except RuntimeError as error:
                return WebUtils.response_error(error_message=str(error), status_code=status.HTTP_500_INTERNAL_SERVER_ERROR)
        source = self._get_k8s_source()
        if not source:
            return WebUtils.response_error(
                error_message="K8s alert source not found",
                status_code=status.HTTP_404_NOT_FOUND,
            )
        payload = self._build_k8s_render_payload(request, source)
        yaml_content = self._build_k8s_deploy_yaml(
            receiver_url=payload["receiver_url"],
            secret=payload["secret"],
            cluster_name=payload["cluster_name"],
            push_source_id=payload["push_source_id"],
            insecure_skip_verify=payload.get("insecure_skip_verify", False),
        )
        return WebUtils.response_file(yaml_content.encode("utf-8"), file_meta["file_name"])

    @HasPermission("Integration-Detail")
    @action(methods=["get"], detail=True, url_path="team_secrets")
    def list_team_secrets(self, request, pk=None):
        source = self.get_object()
        return WebUtils.response_success(AlertSourceCredentialService.list_metadata(request.user, source))

    @HasPermission("Integration-Detail")
    @action(methods=["post"], detail=True, url_path="team_secrets/reveal")
    def reveal_team_secret(self, request, pk=None):
        request_serializer = TeamSecretRequestSerializer(data=request.data)
        request_serializer.is_valid(raise_exception=True)
        source = self.get_object()
        result = AlertSourceCredentialService.reveal(
            request.user,
            source,
            request_serializer.validated_data["team_id"],
        )
        return WebUtils.response_success(result)

    @HasPermission("Integration-Detail")
    @action(methods=["post"], detail=True, url_path="team_secrets/add")
    def add_team_secret(self, request, pk=None):
        source = self.get_object()
        request_serializer = TeamSecretRequestSerializer(data=request.data)
        request_serializer.is_valid(raise_exception=True)
        result = AlertSourceCredentialService.add(
            request.user,
            source.pk,
            request_serializer.validated_data["team_id"],
        )
        return WebUtils.response_success(result)

    @HasPermission("Integration-Detail")
    @action(methods=["post"], detail=True, url_path="team_secrets/regenerate")
    def regenerate_team_secret(self, request, pk=None):
        source = self.get_object()
        request_serializer = TeamSecretRequestSerializer(data=request.data)
        request_serializer.is_valid(raise_exception=True)
        result = AlertSourceCredentialService.regenerate(
            request.user,
            source.pk,
            request_serializer.validated_data["team_id"],
        )
        return WebUtils.response_success(result)

    @HasPermission("Integration-Detail")
    @action(methods=["post"], detail=True, url_path="team_secrets/remove")
    def remove_team_secret(self, request, pk=None):
        source = self.get_object()
        request_serializer = TeamSecretRequestSerializer(data=request.data)
        request_serializer.is_valid(raise_exception=True)
        result = AlertSourceCredentialService.remove(
            request.user,
            source.pk,
            request_serializer.validated_data["team_id"],
        )
        return WebUtils.response_success(result)

    @HasPermission("Integration-View")
    @action(methods=["get"], detail=False, url_path="daily_event_stats")
    def daily_event_stats(self, request):
        """Return today's and yesterday's total event counts across all sources."""
        now = timezone.localtime(timezone.now())
        today_start = now.replace(hour=0, minute=0, second=0, microsecond=0)
        yesterday_start = today_start - timedelta(days=1)

        today_count = Event.objects.filter(received_at__gte=today_start).count()
        yesterday_count = Event.objects.filter(
            received_at__gte=yesterday_start,
            received_at__lt=today_start,
        ).count()

        return WebUtils.response_success(
            {
                "today_count": today_count,
                "yesterday_count": yesterday_count,
            }
        )
