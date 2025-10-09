from config.drf.viewsets import ModelViewSet
from apps.mlops.filters.classification_train_data import ClassificationTrainDataFilter
from drf_yasg.utils import swagger_auto_schema
from rest_framework import viewsets

from apps.core.logger import opspilot_logger as logger
from apps.core.decorators.api_permission import HasPermission
from apps.mlops.models.classification_train_data import ClassificationTrainData
from apps.mlops.serializers.classification_train_data import ClassificationTrainDataSerializer
from config.drf.pagination import CustomPageNumberPagination


class ClassificationTrainDataViewSet(ModelViewSet):
    queryset = ClassificationTrainData.objects.all()
    serializer_class = ClassificationTrainDataSerializer
    pagination_class = CustomPageNumberPagination
    filterset_class = ClassificationTrainDataFilter
    ordering = ("-id",)
    permission_key = "dataset.classification_train_data"

    @HasPermission("classification_train_data-View")
    def list(self, request, *args, **kwargs):
        return super().list(request, *args, **kwargs)

    @HasPermission("classification_train_data-View")
    def retrieve(self, request, *args, **kwargs):
        return super().retrieve(request, *args, **kwargs)

    @HasPermission("classification_train_data-Delete")
    def destroy(self, request, *args, **kwargs):
        return super().destroy(request, *args, **kwargs)

    @HasPermission("classification_train_data-Add")
    def create(self, request, *args, **kwargs):
        return super().create(request, *args, **kwargs)

    @HasPermission("classification_train_data-Edit")
    def update(self, request, *args, **kwargs):
        return super().update(request, *args, **kwargs)