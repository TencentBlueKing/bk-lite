from __future__ import annotations

from rest_framework import status, viewsets
from rest_framework.response import Response

from apps.core.decorators.api_permission import HasPermission
from apps.rum.services.control import ControlError
from apps.rum.services.validation import ValidationError
from apps.rum.services.views import ViewsService
from apps.rum.views.http import actor_from_request, control_error_response


def _service() -> ViewsService:
    return ViewsService()


class RumViewViewSet(viewsets.ViewSet):
    @HasPermission("views-View")
    def list(self, request):
        try:
            return Response(_service().list_views(actor_from_request(request), request.query_params))
        except ValidationError as exc:
            return Response({"code": "invalid_argument", "message": str(exc)}, status=status.HTTP_400_BAD_REQUEST)
        except ControlError as exc:
            return control_error_response(exc)


class RumSavedViewViewSet(viewsets.ViewSet):
    lookup_value_regex = r"[^/]+"

    @HasPermission("views-View")
    def list(self, request):
        return Response(_service().list_saved_views(actor_from_request(request), request.query_params.get("screen")))

    @HasPermission("views-Operate")
    def create(self, request):
        try:
            return Response(_service().create_saved_view(actor_from_request(request), request.data))
        except ValidationError as exc:
            return Response({"code": "invalid_argument", "message": str(exc)}, status=status.HTTP_400_BAD_REQUEST)

    @HasPermission("views-Operate")
    def destroy(self, request, pk=None):
        try:
            _service().delete_saved_view(actor_from_request(request), pk)
            return Response(status=status.HTTP_204_NO_CONTENT)
        except ControlError as exc:
            return control_error_response(exc)
