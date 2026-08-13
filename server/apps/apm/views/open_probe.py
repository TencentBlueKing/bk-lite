from django.http import JsonResponse, StreamingHttpResponse
from rest_framework.decorators import action

from apps.apm.services.probe_artifacts import ProbeArtifactNotFound, open_probe_artifact_stream
from apps.core.logger import apm_logger as logger
from apps.core.utils.open_base import OpenAPIViewSet


class ApmOpenProbeViewSet(OpenAPIViewSet):
    """APM 探针制品免登录下载。

    接入脚本在目标主机（无平台登录态）上执行，参照节点管理 open_api 的
    安装器下载方式提供系统内下载地址；只允许下载白名单内的公开探针制品，
    不接受任意对象 key。
    """

    @action(detail=False, methods=["get"], url_path=r"probe/download/(?P<artifact_name>[A-Za-z0-9._-]{1,128})")
    def download_probe_artifact(self, request, artifact_name=None):
        try:
            stream, filename = open_probe_artifact_stream(artifact_name)
        except ProbeArtifactNotFound:
            return JsonResponse(
                {"code": "probe_artifact_not_found", "detail": "探针文件不存在，请先在服务端初始化探针制品。"},
                status=404,
            )
        except Exception as exc:
            logger.warning("APM probe artifact download failed: %s", type(exc).__name__)
            return JsonResponse(
                {"code": "probe_artifact_unavailable", "detail": "探针文件暂时不可用，请稍后重试。"},
                status=503,
            )
        response = StreamingHttpResponse(stream, content_type="application/octet-stream")
        response["Content-Disposition"] = f'attachment; filename="{filename}"'
        return response
