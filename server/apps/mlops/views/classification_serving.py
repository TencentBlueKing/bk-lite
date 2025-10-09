from config.drf.viewsets import ModelViewSet
from apps.mlops.filters.classification_serving import ClassificationServingFilter
from drf_yasg.utils import swagger_auto_schema
from rest_framework import viewsets

from apps.core.logger import opspilot_logger as logger
from apps.core.decorators.api_permission import HasPermission
from apps.mlops.models.classification_serving import ClassificationServing
from apps.mlops.serializers.classification_serving import ClassificationServingSerializer
from config.drf.pagination import CustomPageNumberPagination


class ClassificationServingViewSet(ModelViewSet):
    queryset = ClassificationServing.objects.all()
    serializer_class = ClassificationServingSerializer
    pagination_class = CustomPageNumberPagination
    filterset_class = ClassificationServingFilter
    ordering = ("-id",)
    permission_key = "dataset.classification_serving"

    @HasPermission("classification_servings-View")
    def list(self, request, *args, **kwargs):
        return super().list(request, *args, **kwargs)

    @HasPermission("classification_servings-View")
    def retrieve(self, request, *args, **kwargs):
        return super().retrieve(request, *args, **kwargs)

    @HasPermission("classification_servings-Delete")
    def destroy(self, request, *args, **kwargs):
        return super().destroy(request, *args, **kwargs)

    @HasPermission("classification_servings-Add")
    def create(self, request, *args, **kwargs):
        return super().create(request, *args, **kwargs)

    @HasPermission("classification_servings-Edit")
    def update(self, request, *args, **kwargs):
        return super().update(request, *args, **kwargs)