# -- coding: utf-8 --
from apps.alerts.filters import OperatorLogModelFilter
from apps.alerts.models.operator_log import OperatorLog
from apps.alerts.serializers import OperatorLogModelSerializer
from apps.alerts.utils.permission_scope import filter_operator_log_queryset_for_request
from apps.core.decorators.api_permission import HasPermission
from config.drf.pagination import CustomPageNumberPagination
from config.drf.viewsets import ModelViewSet


class SystemLogModelViewSet(ModelViewSet):
    """
    系统日志视图集
    """
    queryset = OperatorLog.objects.all()
    serializer_class = OperatorLogModelSerializer
    filterset_class = OperatorLogModelFilter
    ordering_fields = ["created_at"]
    ordering = ["-created_at"]
    pagination_class = CustomPageNumberPagination

    def get_queryset(self):
        request = getattr(self, "request", None)
        if request is None:
            return OperatorLog.objects.all()
        return filter_operator_log_queryset_for_request(OperatorLog.objects.all(), request)

    @HasPermission("operation_log-View")
    def list(self, request, *args, **kwargs):
        return super().list(request, *args, **kwargs)

    @HasPermission("operation_log-View")
    def retrieve(self, request, *args, **kwargs):
        return super().retrieve(request, *args, **kwargs)
