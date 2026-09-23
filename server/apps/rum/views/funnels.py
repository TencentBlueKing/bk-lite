from __future__ import annotations

from rest_framework import status, viewsets
from rest_framework.decorators import action
from rest_framework.response import Response

from apps.core.decorators.api_permission import HasPermission
from apps.rum.services.control import ControlError
from apps.rum.services.funnels import FunnelsService
from apps.rum.services.validation import ValidationError
from apps.rum.views.http import actor_from_request, control_error_response


def _service() -> FunnelsService:
    return FunnelsService()


class RumFunnelViewSet(viewsets.ViewSet):
    lookup_value_regex = r"[^/]+"

    @HasPermission("funnels-View")
    def list(self, request):
        return Response(_service().list_funnels())

    @HasPermission("funnels-Operate")
    def create(self, request):
        try:
            return Response(_service().create_funnel(actor_from_request(request), request.data))
        except ValidationError as exc:
            return Response({"code": "invalid_argument", "message": str(exc)}, status=status.HTTP_400_BAD_REQUEST)
        except ControlError as exc:
            return control_error_response(exc)

    @HasPermission("funnels-Operate")
    def update(self, request, pk=None):
        try:
            return Response(_service().update_funnel(actor_from_request(request), pk, request.data))
        except ValidationError as exc:
            return Response({"code": "invalid_argument", "message": str(exc)}, status=status.HTTP_400_BAD_REQUEST)
        except ControlError as exc:
            return control_error_response(exc)

    @HasPermission("funnels-Operate")
    def destroy(self, request, pk=None):
        try:
            _service().delete_funnel(pk)
            return Response(status=status.HTTP_204_NO_CONTENT)
        except ControlError as exc:
            return control_error_response(exc)

    @action(methods=["get"], detail=True, url_path="reach")
    @HasPermission("funnels-View")
    def reach(self, request, pk=None):
        try:
            return Response(_service().funnel_reach(actor_from_request(request), pk, request.query_params))
        except ValidationError as exc:
            return Response({"code": "invalid_argument", "message": str(exc)}, status=status.HTTP_400_BAD_REQUEST)
        except ControlError as exc:
            return control_error_response(exc)
