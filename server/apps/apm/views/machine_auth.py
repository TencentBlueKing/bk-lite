from django.db import DatabaseError
from django.http import HttpResponse
from rest_framework import status

from apps.apm.services import DjangoIngestSourceService
from apps.core.utils.open_base import OpenAPIViewSet


class ApmMachineAuthViewSet(OpenAPIViewSet):
    """供边缘代理 auth_request 调用的 APM 机器认证接口。"""

    authentication_classes = []
    service = DjangoIngestSourceService()

    @staticmethod
    def _bearer_credential(request) -> str | None:
        header = request.META.get("HTTP_AUTHORIZATION", "").strip()
        if not header.lower().startswith("bearer "):
            return None
        credential = header[7:].strip()
        return credential or None

    def list(self, request):
        credential = self._bearer_credential(request)
        if credential is None:
            return HttpResponse(status=status.HTTP_401_UNAUTHORIZED)
        try:
            source = self.service.validate_credential(credential)
        except DatabaseError:
            return HttpResponse(status=status.HTTP_503_SERVICE_UNAVAILABLE)
        if source is None:
            return HttpResponse(status=status.HTTP_401_UNAUTHORIZED)

        response = HttpResponse(status=status.HTTP_204_NO_CONTENT)
        response["X-BK-Ingest-Source-Id"] = str(source.id)
        response["Cache-Control"] = "private, max-age=10"
        return response
