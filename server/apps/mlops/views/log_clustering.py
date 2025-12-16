from config.drf.viewsets import ModelViewSet
from apps.mlops.filters.log_clustering import *
from rest_framework import viewsets
from rest_framework.decorators import action
from rest_framework import status
from rest_framework.response import Response

from apps.core.logger import opspilot_logger as logger
from apps.core.decorators.api_permission import HasPermission
from apps.mlops.models.log_clustering import *
from apps.mlops.serializers.log_clustering import *
from config.drf.pagination import CustomPageNumberPagination


class LogClusteringDatasetViewSet(ModelViewSet):
    queryset = LogClusteringDataset.objects.all()
    serializer_class = LogClusteringDatasetSerializer
    pagination_class = CustomPageNumberPagination
    filterset_class = LogClusteringDatasetFilter
    ordering = ("-id",)
    permission_key = "dataset.log_clustering_dataset"

    @HasPermission("log_clustering_datasets-View")
    def list(self, request, *args, **kwargs):
        return super().list(request, *args, **kwargs)

    @HasPermission("log_clustering_datasets-View")
    def retrieve(self, request, *args, **kwargs):
        return super().retrieve(request, *args, **kwargs)

    @HasPermission("log_clustering_datasets-Delete")
    def destroy(self, request, *args, **kwargs):
        return super().destroy(request, *args, **kwargs)

    @HasPermission("log_clustering_datasets-Add")
    def create(self, request, *args, **kwargs):
        return super().create(request, *args, **kwargs)

    @HasPermission("log_clustering_datasets-Edit")
    def update(self, request, *args, **kwargs):
        return super().update(request, *args, **kwargs)


class LogClusteringTrainJobViewSet(ModelViewSet):
    queryset = LogClusteringTrainJob.objects.all()
    serializer_class = LogClusteringTrainJobSerializer
    pagination_class = CustomPageNumberPagination
    filterset_class = LogClusteringTrainJobFilter
    ordering = ("-id",)
    permission_key = "dataset.log_clustering_train_job"

    @HasPermission("log_clustering_train_jobs-View")
    def list(self, request, *args, **kwargs):
        return super().list(request, *args, **kwargs)

    @HasPermission("log_clustering_train_jobs-View")
    def retrieve(self, request, *args, **kwargs):
        return super().retrieve(request, *args, **kwargs)

    @HasPermission("log_clustering_train_jobs-Delete")
    def destroy(self, request, *args, **kwargs):
        return super().destroy(request, *args, **kwargs)

    @HasPermission("log_clustering_train_jobs-Add")
    def create(self, request, *args, **kwargs):
        return super().create(request, *args, **kwargs)

    @HasPermission("log_clustering_train_jobs-Edit")
    def update(self, request, *args, **kwargs):
        return super().update(request, *args, **kwargs)
    
    @action(detail=True, methods=['get'], url_path='get_file')
    @HasPermission("log_clustering_train_jobs-View,log_clustering_train_data-View,log_clustering_datasets-View")
    def get_file(self, request, *args, **kwargs):
        try:
            train_job = self.get_object()
            train_obj = train_job.train_data_id
            val_obj = train_job.val_data_id
            test_obj = train_job.test_data_id

            def mergePoints(data_obj, filename):
                train_data = list(data_obj.train_data) if hasattr(data_obj, 'train_data') else []

                return {
                    "data": train_data,
                    "columns": [],
                    "filename": filename
                }

            return Response(
                [
                    mergePoints(train_obj, 'train_file.txt'),
                    mergePoints(val_obj, 'val_file.txt'),
                    mergePoints(test_obj, 'test_file.txt'),
                    {
                        "data": train_job.hyperopt_config,
                        "columns": [],
                        "filename": "hyperopt_config.json"
                    }
                ]
            )
        
        except Exception as e:
            logger.error(f"获取训练文件失败 - TrainJobID: {kwargs.get('pk')} - {str(e)}")
            return Response(
                {'error': f'获取文件信息失败: {str(e)}'},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )


class LogClusteringTrainHistoryViewSet(ModelViewSet):
    queryset = LogClusteringTrainHistory.objects.all()
    serializer_class = LogClusteringTrainHistorySerializer
    pagination_class = CustomPageNumberPagination
    filterset_class = LogClusteringTrainHistoryFilter
    ordering = ("-id",)
    permission_key = "dataset.log_clustering_train_history"

    @HasPermission("log_clustering_train_history-View")
    def list(self, request, *args, **kwargs):
        return super().list(request, *args, **kwargs)

    @HasPermission("log_clustering_train_history-View")
    def retrieve(self, request, *args, **kwargs):
        return super().retrieve(request, *args, **kwargs)

    @HasPermission("log_clustering_train_history-Delete")
    def destroy(self, request, *args, **kwargs):
        return super().destroy(request, *args, **kwargs)

    @HasPermission("log_clustering_train_history-Add")
    def create(self, request, *args, **kwargs):
        return super().create(request, *args, **kwargs)

    @HasPermission("log_clustering_train_history-Edit")
    def update(self, request, *args, **kwargs):
        return super().update(request, *args, **kwargs)


class LogClusteringTrainDataViewSet(ModelViewSet):
    queryset = LogClusteringTrainData.objects.all()
    serializer_class = LogClusteringTrainDataSerializer
    pagination_class = CustomPageNumberPagination
    filterset_class = LogClusteringTrainDataFilter
    ordering = ("-id",)
    permission_key = "dataset.log_clustering_train_data"

    @HasPermission("log_clustering_train_data-View")
    def list(self, request, *args, **kwargs):
        return super().list(request, *args, **kwargs)

    @HasPermission("log_clustering_train_data-View")
    def retrieve(self, request, *args, **kwargs):
        return super().retrieve(request, *args, **kwargs)

    @HasPermission("log_clustering_train_data-Delete")
    def destroy(self, request, *args, **kwargs):
        return super().destroy(request, *args, **kwargs)

    @HasPermission("log_clustering_train_data-Add")
    def create(self, request, *args, **kwargs):
        return super().create(request, *args, **kwargs)

    @HasPermission("log_clustering_train_data-Edit")
    def update(self, request, *args, **kwargs):
        return super().update(request, *args, **kwargs)


class LogClusteringServingViewSet(ModelViewSet):
    queryset = LogClusteringServing.objects.all()
    serializer_class = LogClusteringServingSerializer
    pagination_class = CustomPageNumberPagination
    filterset_class = LogClusteringServingFilter
    ordering = ("-id",)
    permission_key = "dataset.log_clustering_serving"

    @HasPermission("log_clustering_servings-View")
    def list(self, request, *args, **kwargs):
        return super().list(request, *args, **kwargs)

    @HasPermission("log_clustering_servings-View")
    def retrieve(self, request, *args, **kwargs):
        return super().retrieve(request, *args, **kwargs)

    @HasPermission("log_clustering_servings-Delete")
    def destroy(self, request, *args, **kwargs):
        return super().destroy(request, *args, **kwargs)

    @HasPermission("log_clustering_servings-Add")
    def create(self, request, *args, **kwargs):
        return super().create(request, *args, **kwargs)

    @HasPermission("log_clustering_servings-Edit")
    def update(self, request, *args, **kwargs):
        return super().update(request, *args, **kwargs)
