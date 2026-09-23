from __future__ import annotations

from rest_framework import status
from rest_framework.response import Response

from apps.rum.services.control import ControlError


def actor_from_request(request) -> str:
    user = getattr(request, "user", None)
    if user is None or not getattr(user, "is_authenticated", False):
        return "anonymous"
    username = getattr(user, "username", None) or getattr(user, "email", None)
    return str(username or user.pk or "anonymous")


def control_error_response(exc: ControlError) -> Response:
    mapping = {
        "invalid_argument": status.HTTP_400_BAD_REQUEST,
        "not_found": status.HTTP_404_NOT_FOUND,
        "forbidden": status.HTTP_403_FORBIDDEN,
        "revision_conflict": status.HTTP_409_CONFLICT,
        "idempotency_conflict": status.HTTP_409_CONFLICT,
        "org_conflict": status.HTTP_409_CONFLICT,
        "unavailable": status.HTTP_503_SERVICE_UNAVAILABLE,
        "internal_error": status.HTTP_502_BAD_GATEWAY,
    }
    http_status = mapping.get(exc.code, status.HTTP_502_BAD_GATEWAY)
    return Response(
        {"code": exc.code, "message": exc.message},
        status=http_status,
    )


def with_revision(response: Response, revision: int) -> Response:
    if revision > 0:
        response["X-RUM-Revision"] = str(revision)
    return response
