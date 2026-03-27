from rest_framework.decorators import action

from apps.core.utils.open_base import OpenAPIViewSet
from apps.core.utils.web_utils import WebUtils
from apps.monitor.services.push_api import PushAPIService
from apps.monitor.tasks.push_api import publish_push_api_metrics


class PushAPIViewSet(OpenAPIViewSet):
    @action(methods=["post"], detail=False, url_path="report")
    def report(self, request):
        result = PushAPIService.authenticate_and_prepare_enqueue(request.data)
        publish_push_api_metrics.delay(request.data, result["token_team"])

        return WebUtils.response_success(
            {
                "accepted": True,
                "status": "queued",
                "request_id": result["request_id"],
                "template_id": result["template_id"],
            }
        )
