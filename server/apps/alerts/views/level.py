# -- coding: utf-8 --
from apps.alerts.filters import LevelModelFilter
from apps.alerts.models.models import Level
from apps.alerts.serializers import LevelModelSerializer
from config.drf.pagination import CustomPageNumberPagination
from config.drf.viewsets import ModelViewSet


class LevelModelViewSet(ModelViewSet):
    """
    告警等级视图集
    """
    # TODO 创建的时候动态增加level_id 锁表
    queryset = Level.objects.all()
    serializer_class = LevelModelSerializer
    filterset_class = LevelModelFilter
    ordering_fields = ["level_id"]
    ordering = ["level_id"]
    pagination_class = CustomPageNumberPagination
