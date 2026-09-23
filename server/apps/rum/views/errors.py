from __future__ import annotations

from rest_framework import status, viewsets
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.core.decorators.api_permission import HasPermission
from apps.rum.services.control import ControlError
from apps.rum.services.errors import ErrorsService
from apps.rum.services.validation import ValidationError
from apps.rum.views.http import actor_from_request, control_error_response


def _service() -> ErrorsService:
    return ErrorsService()


class RumErrorViewSet(viewsets.ViewSet):
    lookup_value_regex = r"[^/]+"

    @HasPermission("errors-View")
    def list(self, request):
        try:
            return Response(_service().list_errors(actor_from_request(request), request.query_params))
        except ValidationError as exc:
            return Response({"code": "invalid_argument", "message": str(exc)}, status=status.HTTP_400_BAD_REQUEST)
        except ControlError as exc:
            return control_error_response(exc)

    @HasPermission("errors-View")
    def retrieve(self, request, pk=None):
        try:
            return Response(_service().error_detail(actor_from_request(request), pk, request.query_params))
        except ValidationError as exc:
            return Response({"code": "invalid_argument", "message": str(exc)}, status=status.HTTP_400_BAD_REQUEST)
        except ControlError as exc:
            return control_error_response(exc)

    @action(methods=["patch"], detail=False, url_path=r"issues/(?P<fingerprint>[^/.]+)")
    @HasPermission("errors-Operate")
    def patch_issue(self, request, fingerprint=None):
        try:
            return Response(_service().patch_issue(actor_from_request(request), fingerprint, request.data))
        except ValidationError as exc:
            return Response({"code": "invalid_argument", "message": str(exc)}, status=status.HTTP_400_BAD_REQUEST)
        except ControlError as exc:
            return control_error_response(exc)


class RumSourcemapRestoreView(APIView):
    @HasPermission("releases-View")
    def post(self, request):
        try:
            return Response(_service().restore_sourcemap(actor_from_request(request), request.data))
        except ValidationError as exc:
            return Response({"code": "invalid_argument", "message": str(exc)}, status=status.HTTP_400_BAD_REQUEST)
        except ControlError as exc:
            return control_error_response(exc)
