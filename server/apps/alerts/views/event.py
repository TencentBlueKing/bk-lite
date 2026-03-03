# -- coding: utf-8 --
from apps.alerts.filters import EventModelFilter
from apps.alerts.models.models import Event
from apps.alerts.serializers import EventModelSerializer
from apps.core.decorators.api_permission import HasPermission
from config.drf.pagination import CustomPageNumberPagination
from config.drf.viewsets import ModelViewSet


class EventModelViewSet(ModelViewSet):
    """
    事件视图集
    """
    queryset = Event.objects.all()
    serializer_class = EventModelSerializer
    ordering_fields = ["received_at"]
    ordering = ["-received_at"]
    filterset_class = EventModelFilter
    pagination_class = CustomPageNumberPagination

    @HasPermission("Integration-View,Alarms-View")
    def list(self, request, *args, **kwargs):
        return super().list(request, *args, **kwargs)
