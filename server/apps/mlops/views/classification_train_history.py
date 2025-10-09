from config.drf.viewsets import ModelViewSet
from apps.mlops.filters.classification_train_history import ClassificationTrainHistoryFilter
from drf_yasg.utils import swagger_auto_schema
from rest_framework import viewsets

from apps.core.logger import opspilot_logger as logger
from apps.core.decorators.api_permission import HasPermission
from apps.mlops.models.classification_train_history import ClassificationTrainHistory
from apps.mlops.serializers.classification_train_history import ClassificationTrainHistorySerializer
from config.drf.pagination import CustomPageNumberPagination


class ClassificationTrainHistoryViewSet(ModelViewSet):
    queryset = ClassificationTrainHistory.objects.all()
    serializer_class = ClassificationTrainHistorySerializer
    pagination_class = CustomPageNumberPagination
    filterset_class = ClassificationTrainHistoryFilter
    ordering = ("-id",)
    permission_key = "dataset.classification_train_history"

    @HasPermission("classification_train_history-View")
    def list(self, request, *args, **kwargs):
        return super().list(request, *args, **kwargs)

    @HasPermission("classification_train_history-View")
    def retrieve(self, request, *args, **kwargs):
        return super().retrieve(request, *args, **kwargs)

    @HasPermission("classification_train_history-Delete")
    def destroy(self, request, *args, **kwargs):
        return super().destroy(request, *args, **kwargs)

    @HasPermission("classification_train_history-Add")
    def create(self, request, *args, **kwargs):
        return super().create(request, *args, **kwargs)

    @HasPermission("classification_train_history-Edit")
    def update(self, request, *args, **kwargs):
        return super().update(request, *args, **kwargs)