from config.drf.viewsets import ModelViewSet
from apps.mlops.filters.classification_dataset import ClassificationDatasetFilter
from drf_yasg.utils import swagger_auto_schema
from rest_framework import viewsets

from apps.core.logger import opspilot_logger as logger
from apps.core.decorators.api_permission import HasPermission
from apps.mlops.models.classification_dataset import ClassificationDataset
from apps.mlops.serializers.classification_dataset import ClassificationDatasetSerializer
from config.drf.pagination import CustomPageNumberPagination


class ClassificationDatasetViewSet(ModelViewSet):
    queryset = ClassificationDataset.objects.all()
    serializer_class = ClassificationDatasetSerializer
    pagination_class = CustomPageNumberPagination
    filterset_class = ClassificationDatasetFilter
    ordering = ("-id",)
    permission_key = "dataset.classification_dataset"

    @HasPermission("classification_datasets-View")
    def list(self, request, *args, **kwargs):
        return super().list(request, *args, **kwargs)

    @HasPermission("classification_datasets-View")
    def retrieve(self, request, *args, **kwargs):
        return super().retrieve(request, *args, **kwargs)

    @HasPermission("classification_datasets-Delete")
    def destroy(self, request, *args, **kwargs):
        return super().destroy(request, *args, **kwargs)

    @HasPermission("classification_datasets-Add")
    def create(self, request, *args, **kwargs):
        return super().create(request, *args, **kwargs)

    @HasPermission("classification_datasets-Edit")
    def update(self, request, *args, **kwargs):
        return super().update(request, *args, **kwargs)