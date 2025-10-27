from operator import index
from config.drf.viewsets import ModelViewSet
from apps.mlops.filters.anomaly_detection import *
from rest_framework import viewsets
from config.components.mlflow import MLFLOW_TRACKER_URL
from apps.core.logger import opspilot_logger as logger
from apps.core.decorators.api_permission import HasPermission
from apps.mlops.models.anomaly_detection import *
from apps.mlops.serializers.anomaly_detection import *
from config.drf.pagination import CustomPageNumberPagination
from rest_framework.response import Response
import mlflow
from rest_framework import status
from django.http import Http404
import pandas as pd
import numpy as np
from rest_framework.decorators import action
from neco.mlops.anomaly_detection.random_forest_detector import RandomForestAnomalyDetector
from apps.mlops.tasks.anomaly_detection_train_task import start_anomaly_detection_train


class AnomalyDetectionDatasetViewSet(ModelViewSet):
    queryset = AnomalyDetectionDataset.objects.all()
    serializer_class = AnomalyDetectionDatasetSerializer
    pagination_class = CustomPageNumberPagination
    filterset_class = AnomalyDetectionDatasetFilter
    ordering = ("-id",)
    permission_key = "dataset.anomaly_detection_dataset"

    @HasPermission("anomaly_detection_datasets-View")
    def list(self, request, *args, **kwargs):
        return super().list(request, *args, **kwargs)

    @HasPermission("anomaly_detection_datasets-View")
    def retrieve(self, request, *args, **kwargs):
        return super().retrieve(request, *args, **kwargs)

    @HasPermission("anomaly_detection_datasets-Delete")
    def destroy(self, request, *args, **kwargs):
        return super().destroy(request, *args, **kwargs)

    @HasPermission("anomaly_detection_datasets-Add")
    def create(self, request, *args, **kwargs):
        return super().create(request, *args, **kwargs)

    @HasPermission("anomaly_detection_datasets-Edit")
    def update(self, request, *args, **kwargs):
        return super().update(request, *args, **kwargs)


class AnomalyDetectionTrainJobViewSet(ModelViewSet):
    queryset = AnomalyDetectionTrainJob.objects.all()
    serializer_class = AnomalyDetectionTrainJobSerializer
    filterset_class = AnomalyDetectionTrainJobFilter
    pagination_class = CustomPageNumberPagination
    permission_key = "dataset.anomaly_detection_train_job"

    @action(detail=True, methods=['post'], url_path='train')
    @HasPermission("train_tasks-Train")
    def train(self, request, pk=None):
        try:
            train_job = self.get_object()
            start_anomaly_detection_train.delay(train_job.id)

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
            experiment_name = f"AnomalyDetection_{train_job.id}_{train_job.name}"

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

            return Response(
                {
                    'train_job_name': train_job.name,
                    'data': run_datas
                }
            )
        except Exception as e:

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

    @HasPermission("train_tasks-View")
    def list(self, request, *args, **kwargs):
        return super().list(request, *args, **kwargs)

    @HasPermission("train_tasks-Add,anomaly_detection_datasets_detail-File View,anomaly_detection_datasets-View")
    def create(self, request, *args, **kwargs):
        return super().create(request, *args, **kwargs)
    
    @action(detail=True, methods=['get'], url_path='get_file')
    @HasPermission("train_tasks-View,anomaly_detection_datasets_detail-File View,anomaly_detection_datasets-View")
    def get_file(self, request, *args, **kwargs):
        try:
            train_job = self.get_object()
            train_obj = train_job.train_data_id
            val_obj = train_job.val_data_id
            test_obj = train_job.test_data_id

            def mergePoints(data_obj, filename):
                train_data = list(data_obj.train_data) if hasattr(data_obj, 'train_data') else []
                anomlay_indices = (
                    data_obj.metadata.get('anomaly_point', [])
                    if hasattr(data_obj, 'metadata') and isinstance(data_obj.metadata, dict)
                    else []
                )

                columns = ['timestamp', 'value']

                if anomlay_indices and isinstance(anomlay_indices, list):
                    for idx, item in enumerate(train_data):
                        item['label'] = 1 if idx in anomlay_indices else 0
                    columns.append('label')

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

    @HasPermission("train_tasks-Delete")
    def destroy(self, request, *args, **kwargs):
        return super().destroy(request, *args, **kwargs)

    @HasPermission("train_tasks-Edit")
    def update(self, request, *args, **kwargs):
        return super().update(request, *args, **kwargs)

    @HasPermission("train_tasks-View")
    def retrieve(self, request, *args, **kwargs):
        return super().retrieve(request, *args, **kwargs)


class AnomalyDetectionTrainDataViewSet(ModelViewSet):
    """异常检测训练数据视图集"""

    queryset = AnomalyDetectionTrainData.objects.all()
    serializer_class = AnomalyDetectionTrainDataSerializer
    filterset_class = AnomalyDetectionTrainDataFilter
    pagination_class = CustomPageNumberPagination
    permission_key = "dataset.anomaly_detection_train_data"

    @HasPermission("anomaly_detection_datasets_detail-File View")
    def list(self, request, *args, **kwargs):
        return super().list(request, *args, **kwargs)

    @HasPermission("anomaly_detection_datasets_detail-File Upload")
    def create(self, request, *args, **kwargs):
        return super().create(request, *args, **kwargs)

    @HasPermission("anomaly_detection_datasets_detail-File Delete")
    def destroy(self, request, *args, **kwargs):
        return super().destroy(request, *args, **kwargs)

    @HasPermission("anomaly_detection_datasets_detail-File Edit")
    def update(self, request, *args, **kwargs):
        return super().update(request, *args, **kwargs)

    @HasPermission("anomaly_detection_datasets_detail-File View")
    def retrieve(self, request, *args, **kwargs):
        return super().retrieve(request, *args, **kwargs)


class AnomalyDetectionServingViewSet(ModelViewSet):
    queryset = AnomalyDetectionServing.objects.all()
    serializer_class = AnomalyDetectionServingSerializer
    filterset_class = AnomalyDetectionServingFilter
    pagination_class = CustomPageNumberPagination
    permission_key = "serving.anomaly_detection_serving"

    @HasPermission("model_release-View")
    def list(self, request, *args, **kwargs):
        return super().list(request, *args, **kwargs)

    @HasPermission("model_release-Add,train_tasks-View")
    def create(self, request, *args, **kwargs):
        return super().create(request, *args, **kwargs)

    @HasPermission("model_release-Delete")
    def destroy(self, request, *args, **kwargs):
        return super().destroy(request, *args, **kwargs)

    @HasPermission("model_release-Update")
    def update(self, request, *args, **kwargs):
        return super().update(request, *args, **kwargs)

    @HasPermission("model_release-View")
    def retrieve(self, request, *args, **kwargs):
        return super().retrieve(request, *args, **kwargs)

    @HasPermission("model_release-View")
    @action(detail=False, methods=['post'], url_path='predict')
    def predict(self, request, pk=None):
        """
        异常检测推理接口

        通过AnomalyDetectionServing的id获取模型配置，接收JSON数据进行异常检测推理
        """
        try:
            # 获取并验证请求数据
            data = request.data
            serving_id = data.get('serving_id')
            time_series_data = data.get('data')
            mlflow.set_tracking_uri(MLFLOW_TRACKER_URL)

            # 验证必需参数
            if not serving_id:
                return Response(
                    {'error': 'serving_id参数是必需的'},
                    status=status.HTTP_400_BAD_REQUEST
                )

            if not time_series_data:
                return Response(
                    {'error': 'data参数是必需的'},
                    status=status.HTTP_400_BAD_REQUEST
                )

            # 获取异常检测服务配置
            try:
                serving = AnomalyDetectionServing.objects.select_related(
                    'anomaly_detection_train_job').get(id=serving_id)
            except AnomalyDetectionServing.DoesNotExist:
                return Response(
                    {'error': f'异常检测服务不存在: {serving_id}'},
                    status=status.HTTP_404_NOT_FOUND
                )

            # 检查服务状态是否启用
            if serving.status != 'active':
                return Response(
                    {'error': f'异常检测服务未启用，当前状态: {serving.status}'},
                    status=status.HTTP_400_BAD_REQUEST
                )

            # 检查关联的训练任务状态
            train_job = serving.anomaly_detection_train_job
            if train_job.status != 'completed':
                return Response(
                    {'error': f'关联的训练任务未完成，当前状态: {train_job.status}'},
                    status=status.HTTP_400_BAD_REQUEST
                )

            # 从服务配置和训练任务获取模型信息
            # model_name = f"{train_job.algorithm}_{train_job.id}"  # 基于训练任务ID生成模型名称
            model_name = f"AnomalyDetection_{train_job.algorithm}_{train_job.id}" 
            model_version = serving.model_version
            anomaly_threshold = serving.anomaly_threshold
            algorithm = train_job.algorithm

            # 将数据转换为DataFrame
            df = pd.DataFrame(time_series_data)

            # 确保DataFrame有timestamp列，以便后续能够正确映射回原始数据
            if 'timestamp' not in df.columns and len(time_series_data) > 0:
                # 如果没有timestamp列，添加索引作为timestamp
                df['timestamp'] = [item.get('timestamp', f'index_{i}') for i, item in enumerate(time_series_data)]
            # 根据算法类型选择对应的检测器
            if algorithm == 'RandomForest':
                detector = RandomForestAnomalyDetector()
            else:
                return Response(
                    {'error': f'不支持的算法类型: {algorithm}'},
                    status=status.HTTP_400_BAD_REQUEST
                )

            # 执行异常检测推理
            # 使用改进的预测方法，避免频率重采样导致的数据扩展问题
            try:
                # 首先尝试使用不重采样的方法
                model = detector._load_model_with_cache(model_name, model_version)
                result_df = detector._predict_without_resampling(df, model)
                logger.info(f"使用无重采样方法成功，结果长度: {len(result_df)}")
            except Exception as e:
                logger.warning(f"无重采样方法失败: {str(e)}，回退到标准方法")
                # 回退到原始方法
                result_df = detector.predict(df, model_name, model_version)

            # 添加调试信息
            logger.info(f"异常检测推理调试信息:")
            logger.info(f"  - 原始数据长度: {len(time_series_data)}")
            logger.info(f"  - 输入DataFrame形状: {df.shape}")
            logger.info(f"  - 结果DataFrame形状: {result_df.shape}")
            logger.info(f"  - 结果DataFrame列: {result_df.columns.tolist()}")

            # 确保result_df的长度不超过原始数据长度，并处理长度不匹配的情况
            if len(result_df) != len(time_series_data):
                logger.warning(f"结果长度 ({len(result_df)}) != 原始长度 ({len(time_series_data)})")

                if len(result_df) > len(time_series_data):
                    # 如果结果比原始数据长，截断到原始长度
                    logger.info("截断结果到原始数据长度")
                    result_df = result_df.head(len(time_series_data))
                elif len(result_df) < len(time_series_data):
                    # 如果结果比原始数据短，可能是由于dropna()造成的
                    # 为了保持数据对齐，我们需要重新索引
                    logger.warning("结果数据少于原始数据，可能由于数据清理造成")
                    # 这种情况下我们需要特殊处理索引对应关系
                    # 在后续的predictions构造中会处理这个问题

            # 根据阈值判断异常点
            result_df['is_anomaly'] = (result_df['anomaly_probability'] >= anomaly_threshold).astype(int)

            # 构造返回结果
            predictions = []

            # 处理结果长度与原始数据长度不匹配的情况
            min_length = min(len(result_df), len(time_series_data))
            logger.info(f"将使用最小长度进行数据对齐: {min_length}")

            for idx in range(min_length):
                # 获取结果数据
                if idx < len(result_df):
                    # 通过iloc获取第idx行，避免索引问题
                    row = result_df.iloc[idx]
                    value = float(row['value'])
                    anomaly_probability = float(row['anomaly_probability'])
                    is_anomaly = int(row['is_anomaly'])
                else:
                    # 如果result_df不够长，使用默认值
                    logger.warning(f"result_df索引{idx}不存在，使用默认值")
                    value = 0.0
                    anomaly_probability = 0.0
                    is_anomaly = 0

                # 获取原始数据的timestamp
                if idx < len(time_series_data):
                    original_data = time_series_data[idx]
                    timestamp = original_data.get('timestamp', f'index_{idx}')
                else:
                    # 如果原始数据不够长，生成默认timestamp
                    timestamp = f"index_{idx}"
                    logger.warning(f"原始数据索引{idx}不存在，使用默认timestamp")

                predictions.append({
                    'timestamp': timestamp,
                    'value': value,
                    'anomaly_probability': anomaly_probability,
                    'is_anomaly': is_anomaly
                })

            # 如果原始数据比结果数据长，为剩余的数据点添加默认预测
            if len(time_series_data) > len(result_df):
                logger.warning(f"原始数据比结果数据长，为剩余的{len(time_series_data) - len(result_df)}个数据点添加默认预测")
                for idx in range(len(result_df), len(time_series_data)):
                    original_data = time_series_data[idx]
                    predictions.append({
                        'timestamp': original_data.get('timestamp', f'index_{idx}'),
                        'value': float(original_data.get('value', 0.0)),
                        'anomaly_probability': 0.0,  # 默认概率
                        'is_anomaly': 0  # 默认非异常
                    })

            return Response({
                'success': True,
                'serving_id': serving_id,
                'serving_name': serving.name,
                'train_job_id': train_job.id,
                'train_job_name': train_job.name,
                'algorithm': algorithm,
                'model_name': model_name,
                'model_version': model_version,
                'anomaly_threshold': anomaly_threshold,
                'total_points': len(predictions),
                'anomaly_count': sum(p['is_anomaly'] for p in predictions),
                'predictions': predictions
            }, status=status.HTTP_200_OK)

        except IndexError as e:
            return Response(
                {'error': f'数据索引错误: {str(e)}，请检查输入数据格式和模型兼容性'},
                status=status.HTTP_400_BAD_REQUEST
            )
        except Exception as e:
            return Response(
                {'error': f'推理失败: {str(e)}'},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )
