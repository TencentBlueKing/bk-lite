# -- coding: utf-8 --
from apps.alerts.filters import EventModelFilter
from apps.alerts.constants import PERMISSION_EVENT
from apps.alerts.models.models import Event
from apps.alerts.serializers import EventModelSerializer
from apps.core.decorators.api_permission import HasPermission
from apps.core.utils.viewset_utils import AuthViewSet
from config.drf.pagination import CustomPageNumberPagination


class EventModelViewSet(AuthViewSet):
    """
    事件视图集
    """

    queryset = Event.objects.select_related("source")
    serializer_class = EventModelSerializer
    ordering_fields = ["received_at"]
    ordering = ["-received_at"]
    filterset_class = EventModelFilter
    pagination_class = CustomPageNumberPagination
    ORGANIZATION_FIELD = "team"
    permission_key = PERMISSION_EVENT

    def get_queryset(self):
        return Event.objects.select_related("source")

    @HasPermission("Integration-View,Alarms-View")
    def list(self, request, *args, **kwargs):
        return super().list(request, *args, **kwargs)

    @HasPermission("Integration-View,Alarms-View")
    def retrieve(self, request, *args, **kwargs):
        return super().retrieve(request, *args, **kwargs)

    @HasPermission("Integration-Edit")
    def create(self, request, *args, **kwargs):
        return super().create(request, *args, **kwargs)

    @HasPermission("Integration-Edit")
    def update(self, request, *args, **kwargs):
        return super().update(request, *args, **kwargs)

    @HasPermission("Integration-Edit")
    def partial_update(self, request, *args, **kwargs):
        return super().partial_update(request, *args, **kwargs)

    @HasPermission("Integration-Edit")
    def destroy(self, request, *args, **kwargs):
        return super().destroy(request, *args, **kwargs)
