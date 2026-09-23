from __future__ import annotations

from django.http import HttpResponse
from rest_framework import status, viewsets
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.core.decorators.api_permission import HasPermission
from apps.rum.services.control import ControlError
from apps.rum.services.sessions import SessionsService
from apps.rum.services.validation import ValidationError
from apps.rum.views.http import actor_from_request, control_error_response


def _service() -> SessionsService:
    return SessionsService()


class RumSessionViewSet(viewsets.ViewSet):
    lookup_value_regex = r"[^/]+"

    @HasPermission("sessions-View")
    def list(self, request):
        try:
            return Response(_service().list_sessions(actor_from_request(request), request.query_params))
        except ValidationError as exc:
            return Response({"code": "invalid_argument", "message": str(exc)}, status=status.HTTP_400_BAD_REQUEST)
        except ControlError as exc:
            return control_error_response(exc)

    @HasPermission("sessions-View")
    def retrieve(self, request, pk=None):
        try:
            return Response(_service().get_session(actor_from_request(request), pk, request.query_params))
        except ValidationError as exc:
            return Response({"code": "invalid_argument", "message": str(exc)}, status=status.HTTP_400_BAD_REQUEST)
        except ControlError as exc:
            return control_error_response(exc)

    @action(methods=["get"], detail=False, url_path="trend")
    @HasPermission("sessions-View")
    def trend(self, request):
        try:
            return Response(_service().session_trend(actor_from_request(request), request.query_params))
        except ValidationError as exc:
            return Response({"code": "invalid_argument", "message": str(exc)}, status=status.HTTP_400_BAD_REQUEST)
        except ControlError as exc:
            return control_error_response(exc)


class RumReplayManifestView(APIView):
    @HasPermission("sessions-View")
    def get(self, request):
        try:
            return Response(_service().replay_manifest(actor_from_request(request), request.query_params))
        except ValidationError as exc:
            return Response({"code": "invalid_argument", "message": str(exc)}, status=status.HTTP_400_BAD_REQUEST)
        except ControlError as exc:
            return control_error_response(exc)
        except RuntimeError as exc:
            return Response(
                {"code": "replay_signing_unavailable", "message": str(exc)},
                status=status.HTTP_503_SERVICE_UNAVAILABLE,
            )


class RumReplayGrantView(APIView):
    @HasPermission("sessions-View")
    def post(self, request):
        try:
            return Response(_service().replay_grant(actor_from_request(request), request.data))
        except ValidationError as exc:
            return Response({"code": "invalid_argument", "message": str(exc)}, status=status.HTTP_400_BAD_REQUEST)
        except ControlError as exc:
            return control_error_response(exc)
        except RuntimeError as exc:
            return Response(
                {"code": "replay_signing_unavailable", "message": str(exc)},
                status=status.HTTP_503_SERVICE_UNAVAILABLE,
            )


class RumReplaySegmentView(APIView):
    @HasPermission("sessions-View")
    def get(self, request, token: str):
        try:
            claims = _service().replay_segment_claims(token)
        except ControlError as exc:
            return control_error_response(exc)
        from apps.rum.services.replay import get_replay_index

        index = get_replay_index()
        blob = getattr(index, "segment_blob", lambda _key: None)(claims.get("objectKey") or "")
        if blob:
            response = HttpResponse(blob, content_type="application/octet-stream")
            response["Content-Length"] = str(len(blob))
            return response
        # Object store lands with T14/T28 wiring; keep contract explicit.
        return Response(
            {
                "code": "replay_storage_unavailable",
                "message": "Replay object storage is not configured on the RUM BFF",
            },
            status=status.HTTP_503_SERVICE_UNAVAILABLE,
        )
