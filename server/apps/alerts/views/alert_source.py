# -- coding: utf-8 --
from rest_framework.response import Response

from apps.alerts.common.source_adapter.base import AlertSourceAdapterFactory
from pathlib import Path
import subprocess
import tempfile

from rest_framework.decorators import action
from rest_framework import status

from apps.alerts.filters import AlertSourceModelFilter
from apps.alerts.models.alert_source import AlertSource
from apps.alerts.serializers import AlertSourceModelSerializer
from apps.alerts.service.k8s_install import K8sInstallService
from apps.core.decorators.api_permission import HasPermission
from apps.core.utils.web_utils import WebUtils
from config.drf.pagination import CustomPageNumberPagination
from config.drf.viewsets import ModelViewSet

K8S_SOURCE_ID = "k8s"
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


class AlertSourceModelViewSet(ModelViewSet):
    """
    告警源
    """
    queryset = AlertSource.objects.all()
    serializer_class = AlertSourceModelSerializer
    ordering_fields = ["id"]
    ordering = ["id"]
    filterset_class = AlertSourceModelFilter
    pagination_class = CustomPageNumberPagination

    @action(detail=True, methods=["get"], url_path="integration-guide")
    def integration_guide(self, request, pk=None):
        alert_source = self.get_object()
        adapter_class = AlertSourceAdapterFactory.get_adapter(alert_source)
        adapter = adapter_class(alert_source=alert_source)
        base_url = request.build_absolute_uri("/").rstrip("/")
        return Response(adapter.get_integration_guide(base_url))

    @staticmethod
    def _get_k8s_source():
        return AlertSource.objects.filter(source_id=K8S_SOURCE_ID).first()

    @staticmethod
    def _build_k8s_deploy_yaml(receiver_url: str, secret: str, cluster_name: str, push_source_id: str):
        secret_template = (K8S_SUPPORT_DIR / "secret.yaml.template").read_text(encoding="utf-8").strip()
        exporter_template = (K8S_SUPPORT_DIR / "bk-lite-k8s-event-exporter.yaml").read_text(encoding="utf-8").strip()
        secret_template = secret_template.replace("your-k8s-cluster", cluster_name)
        secret_template = secret_template.replace("http://bk-lite-server:8001/api/v1/alerts/api/receiver_data/",
                                                  receiver_url)
        secret_template = secret_template.replace("your-alert-source-secret", secret)
        secret_template = secret_template.replace("BK_LITE_PUSH_SOURCE_ID: k8s",
                                                  f"BK_LITE_PUSH_SOURCE_ID: {push_source_id}")
        guide_header = "\n".join(
            [
                "# BK-Lite K8s Event Exporter Deployment Template",
                "# This file is already rendered from BK-Lite K8s integration settings.",
                f"# Cluster Name: {cluster_name}",
                f"# Push Source ID: {push_source_id}",
                "",
            ]
        )
        return f"{guide_header}{secret_template}\n---\n{exporter_template}\n"

    @staticmethod
    def _build_k8s_image_tar_file():
        temp_file = tempfile.NamedTemporaryFile(prefix="k8s-event-exporter-", suffix=".tar", delete=False)
        temp_file.close()
        try:
            subprocess.run(
                ["docker", "save", "-o", temp_file.name, K8S_IMAGE_REFERENCE],
                check=True,
                capture_output=True,
                text=True,
            )
        except subprocess.CalledProcessError as error:
            raise RuntimeError(error.stderr or error.stdout or "Failed to export image") from error
        return open(temp_file.name, "rb")

    @classmethod
    def _build_k8s_render_payload(cls, request, source: AlertSource):
        payload = K8sInstallService.build_render_payload(
            source_id=source.source_id,
            source_secret=source.secret,
            receiver_path=source.config.get("url", ""),
            server_url=request.data.get("server_url", ""),
            cluster_name=request.data.get("cluster_name", ""),
            push_source_id=request.data.get("push_source_id"),
        )
        return payload

    @HasPermission("Integration-View")
    @action(methods=["get"], detail=False, url_path="k8s_meta")
    def k8s_meta(self, request):
        source = self._get_k8s_source()
        if not source:
            return WebUtils.response_error(
                error_message="K8s alert source not found",
                status_code=status.HTTP_404_NOT_FOUND,
            )

        data = {
            "source_id": source.source_id,
            "name": source.name,
            "description": source.description,
            "receiver_url": source.config.get("url", ""),
            "method": source.config.get("method", "POST"),
            "headers": source.config.get("headers", {}),
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

    @HasPermission("Integration-View")
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
        )
        return WebUtils.response_file(yaml_content.encode("utf-8"), K8S_DOWNLOAD_FILES["deploy_yaml"]["file_name"])

    @HasPermission("Integration-View")
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

    @HasPermission("Integration-View")
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
                return WebUtils.response_error(error_message=str(error),
                                               status_code=status.HTTP_500_INTERNAL_SERVER_ERROR)
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
        )
        return WebUtils.response_file(yaml_content.encode("utf-8"), file_meta["file_name"])
