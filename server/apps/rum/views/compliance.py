from __future__ import annotations

from rest_framework import status, viewsets
from rest_framework.response import Response

from apps.core.decorators.api_permission import HasPermission
from apps.rum.services.compliance import ComplianceService
from apps.rum.services.control import ControlError
from apps.rum.services.validation import ValidationError
from apps.rum.views.http import actor_from_request, control_error_response, with_revision


def _service() -> ComplianceService:
    return ComplianceService()


class RumComplianceViewSet(viewsets.ViewSet):
    @HasPermission("compliance-View")
    def list(self, request):
        try:
            return Response(_service().list_jobs(request.query_params, actor=actor_from_request(request)))
        except ValidationError as exc:
            return Response({"code": "invalid_argument", "message": str(exc)}, status=status.HTTP_400_BAD_REQUEST)
        except ControlError as exc:
            return control_error_response(exc)

    @HasPermission("compliance-Operate")
    def create(self, request):
        try:
            revision, data = _service().erase(actor_from_request(request), request.data)
            return with_revision(Response(data), revision)
        except ValidationError as exc:
            return Response({"code": "invalid_argument", "message": str(exc)}, status=status.HTTP_400_BAD_REQUEST)
        except ControlError as exc:
            return control_error_response(exc)
