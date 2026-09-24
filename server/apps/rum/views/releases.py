from __future__ import annotations

from rest_framework import status, viewsets
from rest_framework.decorators import action
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.throttling import SimpleRateThrottle
from rest_framework.views import APIView

from apps.core.decorators.api_permission import HasPermission
from apps.rum.services.control import ControlError
from apps.rum.services.releases import ReleasesService
from apps.rum.services.validation import ValidationError
from apps.rum.views.http import actor_from_request, control_error_response


def _service() -> ReleasesService:
    return ReleasesService()


class RumReleaseViewSet(viewsets.ViewSet):
    lookup_value_regex = r"[^/]+"

    @HasPermission("releases-View")
    def list(self, request):
        try:
            return Response(_service().list_releases(actor_from_request(request), request.query_params))
        except ValidationError as exc:
            return Response({"code": "invalid_argument", "message": str(exc)}, status=status.HTTP_400_BAD_REQUEST)
        except ControlError as exc:
            return control_error_response(exc)

    @action(methods=["put"], detail=False, url_path=r"baselines/(?P<application>[^/.]+)")
    @HasPermission("releases-Operate")
    def put_baseline(self, request, application=None):
        try:
            return Response(_service().put_baseline(actor_from_request(request), application, request.data))
        except ValidationError as exc:
            return Response({"code": "invalid_argument", "message": str(exc)}, status=status.HTTP_400_BAD_REQUEST)
        except ControlError as exc:
            return control_error_response(exc)


_MAX_UPLOAD_READ = (8 << 20) + 1


class RumSourcemapView(APIView):
    @HasPermission("releases-View")
    def get(self, request):
        try:
            return Response(_service().list_sourcemaps(actor_from_request(request), request.query_params))
        except ValidationError as exc:
            return Response({"code": "invalid_argument", "message": str(exc)}, status=status.HTTP_400_BAD_REQUEST)
        except ControlError as exc:
            return control_error_response(exc)

    @HasPermission("releases-Operate")
    def post(self, request):
        upload = request.FILES.get("file")
        if upload is None:
            return Response(
                {"code": "invalid_argument", "message": "file is required"},
                status=status.HTTP_400_BAD_REQUEST,
            )
        raw = upload.read(_MAX_UPLOAD_READ)
        form = {
            "application": request.data.get("application"),
            "release": request.data.get("release"),
            "asset": request.data.get("asset"),
        }
        try:
            return Response(_service().upload_sourcemap(actor_from_request(request), form, raw))
        except ValidationError as exc:
            return Response({"code": "invalid_argument", "message": str(exc)}, status=status.HTTP_400_BAD_REQUEST)
        except ControlError as exc:
            return control_error_response(exc)


class RumSourcemapCredentialRotateView(APIView):
    @HasPermission("releases-Operate")
    def post(self, request, application=None):
        try:
            return Response(_service().rotate_credential(actor_from_request(request), application))
        except ValidationError as exc:
            return Response({"code": "invalid_argument", "message": str(exc)}, status=status.HTTP_400_BAD_REQUEST)
        except ControlError as exc:
            return control_error_response(exc)


class RumSourcemapIngestThrottle(SimpleRateThrottle):
    """CI ingest is token-authenticated only; throttle by source IP."""

    scope = "rum_sourcemap_ingest"

    def get_cache_key(self, request, view):
        return self.cache_format % {"scope": self.scope, "ident": self.get_ident(request)}


class RumSourcemapIngestView(APIView):
    authentication_classes = []
    permission_classes = [AllowAny]
    throttle_classes = [RumSourcemapIngestThrottle]

    def post(self, request):
        raw = request.body or b""
        if len(raw) > _MAX_UPLOAD_READ:
            return Response(
                {"code": "invalid_argument", "message": "sourcemap exceeds upload size limit"},
                status=status.HTTP_400_BAD_REQUEST,
            )
        try:
            return Response(
                _service().ingest_sourcemap(
                    request.META.get("HTTP_AUTHORIZATION", ""),
                    request.query_params,
                    raw,
                )
            )
        except ValidationError as exc:
            return Response({"code": "invalid_argument", "message": str(exc)}, status=status.HTTP_400_BAD_REQUEST)
        except ControlError as exc:
            return control_error_response(exc)
