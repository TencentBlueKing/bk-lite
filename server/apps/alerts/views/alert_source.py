# -- coding: utf-8 --
from apps.alerts.filters import AlertSourceModelFilter
from apps.alerts.models.alert_source import AlertSource
from apps.alerts.serializers import AlertSourceModelSerializer
from config.drf.pagination import CustomPageNumberPagination
from config.drf.viewsets import ModelViewSet


class AlertSourceModelViewSet(ModelViewSet):
    """
    告警源
    """
    queryset = AlertSource.objects.all()
    serializer_class = AlertSourceModelSerializer
    ordering_fields = ["id"]
    ordering = ["id"]
    filterset_class = AlertSourceModelFilter
    pagination_class = CustomPageNumberPagination
