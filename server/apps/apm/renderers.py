from rest_framework import status
from rest_framework.renderers import JSONRenderer

from config.drf.renderers import CustomRenderer


class ApmRenderer(CustomRenderer):
    """保留 APM 显式错误码，同时维持项目统一的响应外壳。"""

    def render(self, data, accepted_media_type=None, renderer_context=None):
        response = renderer_context.get("response") if renderer_context else None
        if (
            response
            and not status.is_success(response.status_code)
            and isinstance(data, dict)
            and data.get("code")
        ):
            ret = {
                "result": False,
                "code": str(data["code"]),
                "message": self._format_validation_message(detail=data.get("detail", "") or data),
                "data": data.get("data"),
            }
            return JSONRenderer.render(self, ret, accepted_media_type, renderer_context)
        return super().render(data, accepted_media_type, renderer_context)
