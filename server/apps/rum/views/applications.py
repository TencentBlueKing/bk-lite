from __future__ import annotations

from rest_framework import status, viewsets
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.core.decorators.api_permission import HasPermission
from apps.rum.services.applications import ApplicationsService
from apps.rum.services.control import ControlError, get_control_plane
from apps.rum.services.validation import ValidationError
from apps.rum.views.http import actor_from_request, control_error_response, with_revision


def _service() -> ApplicationsService:
    return ApplicationsService(get_control_plane())


class RumApplicationViewSet(viewsets.ViewSet):
    lookup_value_regex = r"[^/]+"

    @HasPermission("applications-View")
    def list(self, request):
        try:
            return Response(_service().list_applications(actor_from_request(request)))
        except ControlError as exc:
            return control_error_response(exc)

    @HasPermission("applications-Operate")
    def create(self, request):
        try:
            revision, data = _service().create_application(actor_from_request(request), request.data)
            return with_revision(Response(data), revision)
        except ValidationError as exc:
            return Response({"code": "invalid_argument", "message": str(exc)}, status=status.HTTP_400_BAD_REQUEST)
        except ControlError as exc:
            return control_error_response(exc)

    @HasPermission("applications-View")
    def retrieve(self, request, pk=None):
        try:
            return Response(_service().get_application(actor_from_request(request), pk))
        except ValidationError as exc:
            return Response({"code": "invalid_argument", "message": str(exc)}, status=status.HTTP_400_BAD_REQUEST)
        except ControlError as exc:
            return control_error_response(exc)

    @HasPermission("applications-Operate")
    def update(self, request, pk=None):
        try:
            revision, data = _service().update_application(actor_from_request(request), pk, request.data)
            return with_revision(Response(data), revision)
        except ValidationError as exc:
            return Response({"code": "invalid_argument", "message": str(exc)}, status=status.HTTP_400_BAD_REQUEST)
        except ControlError as exc:
            return control_error_response(exc)

    @action(methods=["post"], detail=True, url_path="keys")
    @HasPermission("applications-Operate")
    def keys(self, request, pk=None):
        try:
            revision, data = _service().reissue_key(actor_from_request(request), pk)
            return with_revision(Response(data), revision)
        except ValidationError as exc:
            return Response({"code": "invalid_argument", "message": str(exc)}, status=status.HTTP_400_BAD_REQUEST)
        except ControlError as exc:
            return control_error_response(exc)

    @action(methods=["post"], detail=True, url_path="disable")
    @HasPermission("applications-Operate")
    def disable(self, request, pk=None):
        try:
            revision, data = _service().disable_application(actor_from_request(request), pk)
            return with_revision(Response(data), revision)
        except ValidationError as exc:
            return Response({"code": "invalid_argument", "message": str(exc)}, status=status.HTTP_400_BAD_REQUEST)
        except ControlError as exc:
            return control_error_response(exc)

    @action(methods=["get"], detail=True, url_path="status")
    @HasPermission("applications-View")
    def status_check(self, request, pk=None):
        try:
            return Response(_service().status(actor_from_request(request), pk))
        except ValidationError as exc:
            return Response({"code": "invalid_argument", "message": str(exc)}, status=status.HTTP_400_BAD_REQUEST)
        except ControlError as exc:
            return control_error_response(exc)

    @action(methods=["get"], detail=True, url_path="overview")
    @HasPermission("applications-View")
    def overview(self, request, pk=None):
        try:
            return Response(_service().overview(actor_from_request(request), pk, request.query_params.get("range")))
        except ValidationError as exc:
            return Response({"code": "invalid_argument", "message": str(exc)}, status=status.HTTP_400_BAD_REQUEST)
        except ControlError as exc:
            return control_error_response(exc)


class RumMetaView(APIView):
    @HasPermission("applications-View")
    def get(self, request):
        return Response(_service().meta())


class RumHealthView(APIView):
    @HasPermission("applications-View")
    def get(self, request):
        return Response(_service().health(actor_from_request(request)))


class RumSnippetsView(APIView):
    @HasPermission("applications-View")
    def post(self, request):
        try:
            return Response(_service().snippets(request.data))
        except ValidationError as exc:
            return Response({"code": "invalid_argument", "message": str(exc)}, status=status.HTTP_400_BAD_REQUEST)


class RumAnalyticsApplicationsView(APIView):
    @HasPermission("applications-View")
    def get(self, request):
        try:
            return Response(_service().analytics_catalog(actor_from_request(request), request.query_params.get("range")))
        except ValidationError as exc:
            return Response({"code": "invalid_argument", "message": str(exc)}, status=status.HTTP_400_BAD_REQUEST)
        except ControlError as exc:
            return control_error_response(exc)
