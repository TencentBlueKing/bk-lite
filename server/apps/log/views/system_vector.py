from django.http import HttpResponse
from rest_framework.decorators import action

from apps.core.utils.open_base import OpenAPIViewSet
from apps.log.services.log_extractor.auth import authenticate_system_vector_token
from apps.log.services.log_extractor.publication import get_published_snapshot


class SystemVectorConfigViewSet(OpenAPIViewSet):
    @action(methods=("get",), detail=False, url_path="config")
    def config(self, request):
        if not authenticate_system_vector_token(request.headers.get("Authorization")):
            response = HttpResponse(status=401)
            response["WWW-Authenticate"] = "Bearer"
            response["Cache-Control"] = "no-store"
            return response
        snapshot = get_published_snapshot()
        if not snapshot:
            response = HttpResponse(status=503)
            response["Cache-Control"] = "no-store"
            return response
        response = HttpResponse(snapshot.content.encode("utf-8"), content_type="application/yaml; charset=utf-8")
        response["X-Config-Checksum"] = snapshot.checksum
        response["X-Config-Generation"] = str(snapshot.generation)
        response["Cache-Control"] = "no-store"
        return response
