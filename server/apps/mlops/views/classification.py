from unittest import result
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
from apps.mlops.tasks.classification_train_task import start_classification_train
from neco.mlops.classification.random_forest_classifier import RandomForestClassifier
import mlflow
import pandas as pd
import numpy as np
from config.components.mlflow import MLFLOW_TRACKER_URL




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
    
    @HasPermission("classification_servings-View")
    @action(detail=False, methods=['post'], url_path='predict')
    def predirect(self, request):
        try:
            # 获取并验证请求数据
            data = request.data
            serving_id = data.get("serving_id")
            time_series = data.get("data")

            # 参数验证
            if not serving_id:
                return Response(
                    {'error': 'serving_id参数是必需的'},
                    status=status.HTTP_400_BAD_REQUEST
                )
            
            if not time_series:
                return Response(
                    {'error': 'data参数是必需的'},
                    status.HTTP_400_BAD_REQUEST
                )
            
            # 获取分类服务配置
            try:
                serving = ClassificationServing.objects.select_related(
                    'classification_train_job'
                ).get(id = serving_id)
            except ClassificationServing.DoesNotExist:
                return Response(
                    {'error': f'分类任务服务不存在: {serving_id}'},
                    status=status.HTTP_404_NOT_FOUND
                )
            
            # 检查服务是否启用
            if serving.status != 'active':
                 return Response(
                     {'error': f'分类任务服务未启用，当前状态: {serving.status}'},
                     status=status.HTTP_400_BAD_REQUEST
                 )
            
            # 检查服务关联任务状态
            train_job = serving.classification_train_job
            if(train_job.status != 'completed'):
                return Response(
                    {'error': f'关联的训练任务未完成，当前状态: {train_job.status}'},
                    status=status.HTTP_400_BAD_REQUEST
                )
            
            # 从服务配置中获取模型信息
            model_name = f"Classification_{train_job.algorithm}_{train_job.id}"
            model_version = serving.model_version
            algorithm = train_job.algorithm

            mlflow.set_tracking_uri(MLFLOW_TRACKER_URL)
            # 将数据转为DataFrame
            df = pd.DataFrame(time_series)
            # 根据算法类型选择对应的检测器
            if algorithm == 'RandomForest':
                detector = RandomForestClassifier()
            else:
                return Response(
                    {'error': f'不支持的算法类型: {algorithm}'},
                    status=status.HTTP_400_BAD_REQUEST
                )
            result_df = detector.predict(df,model_name,model_version)
            
            return Response({
                'success': True,
                'serving_id': serving_id,
                'serving_name': serving.name,
                'train_job_id': train_job.id,
                'train_job_name': train_job.name,
                'algorithm': algorithm,
                'model_name': model_name,
                'model_version': model_version,
                'data': time_series,
                'predictions': result_df
            }, status=status.HTTP_200_OK)

        except Exception as e:
            return Response(
                {'error': f'推理失败: {str(e)}'},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )
    
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
        
    @action(detail=True, methods=['post'], url_path='train')
    @HasPermission("train_tasks-Train")
    def train(self, request, pk=None):
        try:
            train_job = self.get_object()
            start_classification_train.delay(train_job.id)

            return Response(
                status=status.HTTP_200_OK
            )

        except ValueError as e:
            return Response(
                {'error': str(e)},
                status=status.HTTP_400_BAD_REQUEST
            )
        except Exception as e:
            return Response(
                {'error': f'训练启动失败: {str(e)}'},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )
        
    @action(detail=True, methods=['get'], url_path='runs_data_list')
    @HasPermission("train_tasks-View")
    def get_run_data_list(self, request, pk=None):
        try:
            # 获取训练任务
            train_job = self.get_object()

            # 设置mlflow跟踪
            mlflow.set_tracking_uri(MLFLOW_TRACKER_URL)

            # 构造实验名称（与训练时保持一致）
            experiment_name = f"Classification_{train_job.id}_{train_job.name}"

            # 查找实验
            experiments = mlflow.search_experiments(filter_string=f"name = '{experiment_name}'")
            if not experiments:
                return Response(
                    {'error': '未找到对应的MLflow实验'},
                    status=status.HTTP_404_NOT_FOUND
                )

            experiment = experiments[0]

            # 查找该实验中的运行
            runs = mlflow.search_runs(
                experiment_ids=[experiment.experiment_id],
                order_by=["start_time DESC"],
            )

            if runs.empty:
                return Response(
                    {'error': '未找到训练运行记录'},
                    status=status.HTTP_404_NOT_FOUND
                )

            # 每次运行信息的耗时和名称
            run_datas = []
            for _, row in runs.iterrows():
                # 处理时间计算，避免产生NaN或Infinity
                try:
                    start_time = row["start_time"]
                    end_time = row["end_time"]

                    # 检查时间是否有效
                    if pd.isna(start_time) or pd.isna(end_time):
                        duration_minutes = 0
                    else:
                        duration = end_time - start_time
                        # 检查duration是否为有效值
                        if pd.isna(duration):
                            duration_minutes = 0
                        else:
                            duration_seconds = duration.total_seconds()
                            # 检查是否为有效数值
                            if np.isfinite(duration_seconds):
                                duration_minutes = duration_seconds / 60
                            else:
                                duration_minutes = 0

                    # 获取run_name，处理可能的缺失值
                    run_name = row.get("tags.mlflow.runName", "")
                    if pd.isna(run_name):
                        run_name = ""

                except Exception:
                    # 如果计算出错，使用默认值
                    duration_minutes = 0
                    run_name = ""

                run_data = {
                    "run_id": str(row["run_id"]),  # 确保是字符串
                    "create_time": row["start_time"].isoformat() if not pd.isna(row["start_time"]) else None,
                    "duration": float(duration_minutes) if np.isfinite(duration_minutes) else 0,
                    "run_name": str(run_name)
                }
                run_datas.append(run_data)
            
            logger.info(len(run_datas))

            return Response(
                {
                    'train_job_name': train_job.name,
                    'data': run_datas
                }
            )
        except Exception as e:
            logger.info(e)
            return Response(
                {
                    'train_job_name': train_job.name,
                    'data': [],
                }
            )

    @action(detail=False, methods=['get'], url_path='runs_metrics_list/(?P<run_id>.+?)')
    @HasPermission("train_tasks-View")
    def get_runs_metrics_list(self, request, run_id: str):
        try:
            # 设置MLflow跟踪URI
            mlflow.set_tracking_uri(MLFLOW_TRACKER_URL)

            # 创建MLflow客户端
            client = mlflow.tracking.MlflowClient()

            # 定义需要获取历史的指标
            important_metrics = [metric for metric in client.get_run(run_id).data.metrics.keys()
                                 if not str(metric).startswith("system")]

            return Response({
                'metrics': important_metrics
            })

        except Exception as e:
            return Response(
                {'error': f'获取指标列表失败: {str(e)}'},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )

    @action(detail=False, methods=['get'], url_path='runs_metrics_history/(?P<run_id>.+?)/(?P<metric_name>.+?)')
    def get_metric_data(self, request, run_id: str, metric_name: str):
        # 跟踪Mlflow的uri
        mlflow.set_tracking_uri(MLFLOW_TRACKER_URL)

        # 创建客户端
        client = mlflow.tracking.MlflowClient()

        # 获取指标历史数据
        history = client.get_metric_history(run_id, metric_name)

        # 创建data字典
        metric_history = [
            {
                "step": metric.step,
                "value": metric.value
            }
            for metric in history
        ]

        return Response(
            {
                "metric_name": metric_name,
                "metric_history": metric_history
            }
        )