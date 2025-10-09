from rest_framework import viewsets
from rest_framework.decorators import action

from apps.core.utils.web_utils import WebUtils

from apps.monitor.services.metrics import Metrics as MetricsService


class MetricsInstanceVieSet(viewsets.ViewSet):

    @action(methods=['get'], detail=False, url_path='query')
    def get_metrics(self, request):
        data = MetricsService.get_metrics(request.GET.get('query'))
        return WebUtils.response_success(data)

    @action(methods=['get'], detail=False, url_path='query_range')
    def get_metrics_range(self, request):
        data = MetricsService.get_metrics_range(
            request.GET.get('query'),
            request.GET.get('start'),
            request.GET.get('end'),
            request.GET.get('step'),
        )
        return WebUtils.response_success(data)
