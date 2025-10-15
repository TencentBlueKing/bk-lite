from config.drf.viewsets import ModelViewSet
from rest_framework import viewsets
from rest_framework.decorators import action
from rest_framework import status
from rest_framework.response import Response

from apps.core.logger import opspilot_logger as logger
from apps.core.decorators.api_permission import HasPermission
from apps.mlops.models.classification import *
from apps.mlops.serializers.classification import *
from apps.mlops.filters.classification import *
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
    

    @action(detail=True, methods=['get'], url_path='get_file')
    @HasPermission("classification_train_jobs-View,classification_train_data-View,classification_datasets-View")
    def get_file(self, request, *args, **kwargs):
        try:
            train_job = self.get_object()
            train_obj = train_job.train_data_id
            val_obj = train_job.val_data_id
            test_obj = train_job.test_data_id

            def mergePoints(data_obj, filename):
                train_data = list(data_obj.train_data) if hasattr(data_obj, 'train_data') else []

                columns = (
                    data_obj.metadata.get('headers', [])
                    if hasattr(data_obj, 'metadata') and isinstance(data_obj.metadata, dict)
                    else []
                )

                return {
                    "data": train_data,
                    "columns": columns,
                    "filename": filename
                }

            return Response(
                [
                    mergePoints(train_obj, 'train_file.csv'),
                    mergePoints(val_obj, 'val_file.csv'),
                    mergePoints(test_obj, 'test_file.csv'),
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