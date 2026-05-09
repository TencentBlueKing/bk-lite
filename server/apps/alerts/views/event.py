# -- coding: utf-8 --
from apps.alerts.filters import EventModelFilter
from apps.alerts.models.models import Event
from apps.alerts.serializers import EventModelSerializer
from apps.alerts.utils.permission_scope import filter_event_queryset_for_request
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

    def get_queryset(self):
        request = getattr(self, "request", None)
        if request is None:
            return Event.objects.all()
        return filter_event_queryset_for_request(Event.objects.all(), request)

    @HasPermission("Integration-View,Alarms-View")
    def list(self, request, *args, **kwargs):
        return super().list(request, *args, **kwargs)

    @HasPermission("Integration-View,Alarms-View")
    def retrieve(self, request, *args, **kwargs):
        return super().retrieve(request, *args, **kwargs)
