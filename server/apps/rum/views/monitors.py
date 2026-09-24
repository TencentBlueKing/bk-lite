from __future__ import annotations

from rest_framework import status, viewsets
from rest_framework.response import Response

from apps.core.decorators.api_permission import HasPermission
from apps.rum.services.control import ControlError
from apps.rum.services.monitors import MonitorsService
from apps.rum.services.validation import ValidationError
from apps.rum.views.http import actor_from_request, control_error_response


def _service() -> MonitorsService:
    return MonitorsService()


class RumMonitorViewSet(viewsets.ViewSet):
    lookup_value_regex = r"[^/]+"

    @HasPermission("monitors-View")
    def list(self, request):
        return Response(_service().list_monitors())

    @HasPermission("monitors-Operate")
    def create(self, request):
        try:
            return Response(_service().create_monitor(actor_from_request(request), request.data))
        except ValidationError as exc:
            return Response({"code": "invalid_argument", "message": str(exc)}, status=status.HTTP_400_BAD_REQUEST)
        except ControlError as exc:
            return control_error_response(exc)

    @HasPermission("monitors-Operate")
    def update(self, request, pk=None):
        try:
            return Response(_service().update_monitor(actor_from_request(request), pk, request.data))
        except ValidationError as exc:
            return Response({"code": "invalid_argument", "message": str(exc)}, status=status.HTTP_400_BAD_REQUEST)
        except ControlError as exc:
            return control_error_response(exc)

    @HasPermission("monitors-Operate")
    def destroy(self, request, pk=None):
        try:
            _service().delete_monitor(pk)
            return Response(status=status.HTTP_204_NO_CONTENT)
        except ControlError as exc:
            return control_error_response(exc)


class RumAlertEventViewSet(viewsets.ViewSet):
    lookup_value_regex = r"[^/]+"

    @HasPermission("alert_events-View")
    def list(self, request):
        return Response(_service().list_alert_events(request.query_params))

    @HasPermission("alert_events-View")
    def retrieve(self, request, pk=None):
        try:
            return Response(_service().get_alert_event(pk))
        except ControlError as exc:
            return control_error_response(exc)
