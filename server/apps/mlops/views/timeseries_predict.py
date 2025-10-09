from config.drf.viewsets import ModelViewSet
from apps.mlops.filters.timeseries_predict import *
from rest_framework import viewsets

from apps.core.logger import opspilot_logger as logger
from apps.core.decorators.api_permission import HasPermission
from apps.mlops.models.timeseries_predict import *
from apps.mlops.serializers.timeseries_predict import *
from config.drf.pagination import CustomPageNumberPagination


class TimeSeriesPredictDatasetViewSet(ModelViewSet):
    queryset = TimeSeriesPredictDataset.objects.all()
    serializer_class = TimeSeriesPredictDatasetSerializer
    pagination_class = CustomPageNumberPagination
    filterset_class = TimeSeriesPredictDatasetFilter
    ordering = ("-id",)
    permission_key = "dataset.timeseries_predict_dataset"

    @HasPermission("timeseries_predict_datasets-View")
    def list(self, request, *args, **kwargs):
        return super().list(request, *args, **kwargs)

    @HasPermission("timeseries_predict_datasets-View")
    def retrieve(self, request, *args, **kwargs):
        return super().retrieve(request, *args, **kwargs)

    @HasPermission("timeseries_predict_datasets-Delete")
    def destroy(self, request, *args, **kwargs):
        return super().destroy(request, *args, **kwargs)

    @HasPermission("timeseries_predict_datasets-Add")
    def create(self, request, *args, **kwargs):
        return super().create(request, *args, **kwargs)

    @HasPermission("timeseries_predict_datasets-Edit")
    def update(self, request, *args, **kwargs):
        return super().update(request, *args, **kwargs)


class TimeSeriesPredictTrainJobViewSet(ModelViewSet):
    queryset = TimeSeriesPredictTrainJob.objects.all()
    serializer_class = TimeSeriesPredictTrainJobSerializer
    pagination_class = CustomPageNumberPagination
    filterset_class = TimeSeriesPredictTrainJobFilter
    ordering = ("-id",)
    permission_key = "dataset.timeseries_predict_train_job"

    @HasPermission("timeseries_predict_train_jobs-View")
    def list(self, request, *args, **kwargs):
        return super().list(request, *args, **kwargs)

    @HasPermission("timeseries_predict_train_jobs-View")
    def retrieve(self, request, *args, **kwargs):
        return super().retrieve(request, *args, **kwargs)

    @HasPermission("timeseries_predict_train_jobs-Delete")
    def destroy(self, request, *args, **kwargs):
        return super().destroy(request, *args, **kwargs)

    @HasPermission("timeseries_predict_train_jobs-Add")
    def create(self, request, *args, **kwargs):
        return super().create(request, *args, **kwargs)

    @HasPermission("timeseries_predict_train_jobs-Edit")
    def update(self, request, *args, **kwargs):
        return super().update(request, *args, **kwargs)


class TimeSeriesPredictTrainHistoryViewSet(ModelViewSet):
    queryset = TimeSeriesPredictTrainHistory.objects.all()
    serializer_class = TimeSeriesPredictTrainHistorySerializer
    pagination_class = CustomPageNumberPagination
    filterset_class = TimeSeriesPredictTrainHistoryFilter
    ordering = ("-id",)
    permission_key = "dataset.timeseries_predict_train_history"

    @HasPermission("timeseries_predict_train_history-View")
    def list(self, request, *args, **kwargs):
        return super().list(request, *args, **kwargs)

    @HasPermission("timeseries_predict_train_history-View")
    def retrieve(self, request, *args, **kwargs):
        return super().retrieve(request, *args, **kwargs)

    @HasPermission("timeseries_predict_train_history-Delete")
    def destroy(self, request, *args, **kwargs):
        return super().destroy(request, *args, **kwargs)

    @HasPermission("timeseries_predict_train_history-Add")
    def create(self, request, *args, **kwargs):
        return super().create(request, *args, **kwargs)

    @HasPermission("timeseries_predict_train_history-Edit")
    def update(self, request, *args, **kwargs):
        return super().update(request, *args, **kwargs)


class TimeSeriesPredictTrainDataViewSet(ModelViewSet):
    queryset = TimeSeriesPredictTrainData.objects.all()
    serializer_class = TimeSeriesPredictTrainDataSerializer
    pagination_class = CustomPageNumberPagination
    filterset_class = TimeSeriesPredictTrainDataFilter
    ordering = ("-id",)
    permission_key = "dataset.timeseries_predict_train_data"

    @HasPermission("timeseries_predict_train_data-View")
    def list(self, request, *args, **kwargs):
        return super().list(request, *args, **kwargs)

    @HasPermission("timeseries_predict_train_data-View")
    def retrieve(self, request, *args, **kwargs):
        return super().retrieve(request, *args, **kwargs)

    @HasPermission("timeseries_predict_train_data-Delete")
    def destroy(self, request, *args, **kwargs):
        return super().destroy(request, *args, **kwargs)

    @HasPermission("timeseries_predict_train_data-Add")
    def create(self, request, *args, **kwargs):
        return super().create(request, *args, **kwargs)

    @HasPermission("timeseries_predict_train_data-Edit")
    def update(self, request, *args, **kwargs):
        return super().update(request, *args, **kwargs)


class TimeSeriesPredictServingViewSet(ModelViewSet):
    queryset = TimeSeriesPredictServing.objects.all()
    serializer_class = TimeSeriesPredictServingSerializer
    pagination_class = CustomPageNumberPagination
    filterset_class = TimeSeriesPredictServingFilter
    ordering = ("-id",)
    permission_key = "dataset.timeseries_predict_serving"

    @HasPermission("timeseries_predict_servings-View")
    def list(self, request, *args, **kwargs):
        return super().list(request, *args, **kwargs)

    @HasPermission("timeseries_predict_servings-View")
    def retrieve(self, request, *args, **kwargs):
        return super().retrieve(request, *args, **kwargs)

    @HasPermission("timeseries_predict_servings-Delete")
    def destroy(self, request, *args, **kwargs):
        return super().destroy(request, *args, **kwargs)

    @HasPermission("timeseries_predict_servings-Add")
    def create(self, request, *args, **kwargs):
        return super().create(request, *args, **kwargs)

    @HasPermission("timeseries_predict_servings-Edit")
    def update(self, request, *args, **kwargs):
        return super().update(request, *args, **kwargs)
