from config.drf.viewsets import ModelViewSet
from apps.mlops.filters.classification_train_job import ClassificationTrainJobFilter
from drf_yasg.utils import swagger_auto_schema
from rest_framework import viewsets

from apps.core.logger import opspilot_logger as logger
from apps.core.decorators.api_permission import HasPermission
from apps.mlops.models.classification_train_job import ClassificationTrainJob
from apps.mlops.serializers.classification_train_job import ClassificationTrainJobSerializer
from config.drf.pagination import CustomPageNumberPagination


class ClassificationTrainJobViewSet(ModelViewSet):
    queryset = ClassificationTrainJob.objects.all()
    serializer_class = ClassificationTrainJobSerializer
    pagination_class = CustomPageNumberPagination
    filterset_class = ClassificationTrainJobFilter
    ordering = ("-id",)
    permission_key = "dataset.classification_train_job"

    @HasPermission("classification_train_jobs-View")
    def list(self, request, *args, **kwargs):
        return super().list(request, *args, **kwargs)

    @HasPermission("classification_train_jobs-View")
    def retrieve(self, request, *args, **kwargs):
        return super().retrieve(request, *args, **kwargs)

    @HasPermission("classification_train_jobs-Delete")
    def destroy(self, request, *args, **kwargs):
        return super().destroy(request, *args, **kwargs)

    @HasPermission("classification_train_jobs-Add")
    def create(self, request, *args, **kwargs):
        return super().create(request, *args, **kwargs)

    @HasPermission("classification_train_jobs-Edit")
    def update(self, request, *args, **kwargs):
        return super().update(request, *args, **kwargs)