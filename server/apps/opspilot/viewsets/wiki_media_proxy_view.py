"""Wiki 解析图片同源代理：HMAC 校验后从 MinIO 流式输出。"""

from __future__ import annotations

from django.http import FileResponse, HttpResponse, JsonResponse
from rest_framework.permissions import AllowAny
from rest_framework.views import APIView

from apps.opspilot.services.wiki.parsed_media_service import open_media_bytes, verify_media_proxy_request


class WikiParsedMediaProxyView(APIView):
    """GET /wiki_mgmt/media/?locator=&exp=&sig=

    供 <img src> 使用：无需 Bearer，靠短时 HMAC。经前端 /api/proxy 同源访问。
    """

    authentication_classes = []
    permission_classes = [AllowAny]

    def get(self, request):
        locator = request.GET.get("locator") or ""
        exp = request.GET.get("exp")
        sig = request.GET.get("sig")
        if not verify_media_proxy_request(locator, exp, sig):
            return JsonResponse({"result": False, "message": "invalid media token"}, status=403)
        try:
            fp, content_type = open_media_bytes(locator)
        except Exception:
            return HttpResponse(status=404)
        response = FileResponse(fp, content_type=content_type)
        response["Cache-Control"] = "private, max-age=3600"
        return response
