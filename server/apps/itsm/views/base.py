from rest_framework.response import Response
from rest_framework.views import APIView

from apps.core.decorators.api_permission import HasPermission
from apps.itsm.authentication import MiddlewareUserAuthentication


class ItsmAPIView(APIView):
    authentication_classes = [MiddlewareUserAuthentication]
    permission_classes = []

    @staticmethod
    def actor(request) -> str:
        return getattr(getattr(request, "user", None), "username", "") or "admin"

    @staticmethod
    def fail(message: str, status_code: int = 400) -> Response:
        return Response({"message": message}, status=status_code)


__all__ = ["HasPermission", "ItsmAPIView"]
