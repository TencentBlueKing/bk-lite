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
from django.http import Http404, FileResponse
import pandas as pd
import numpy as np
from rest_framework.decorators import action
from apps.mlops.utils.webhook_client import WebhookClient, WebhookError, WebhookConnectionError, WebhookTimeoutError
import os
import tempfile
import shutil


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
        """
        启动训练任务
        """
        try:
            train_job = self.get_object()
            
            # 检查任务状态
            if train_job.status == 'running':
                return Response(
                    {'error': '训练任务已在运行中'},
                    status=status.HTTP_400_BAD_REQUEST
                )
            
            # 获取环境变量
            bucket = os.getenv("MINIO_PUBLIC_BUCKETS", "munchkin-public")
            minio_endpoint = os.getenv("MLFLOW_S3_ENDPOINT_URL", "")
            mlflow_tracking_uri = os.getenv("MLFLOW_TRACKER_URL", "")
            minio_access_key = os.getenv("MINIO_ACCESS_KEY", "")
            minio_secret_key = os.getenv("MINIO_SECRET_KEY", "")

            if not minio_endpoint:
                return Response(
                    {'error': 'MinIO 访问端点未配置'},
                    status=status.HTTP_500_INTERNAL_SERVER_ERROR
                )
            
            if not mlflow_tracking_uri:
                return Response(
                    {'error': 'MLflow 访问端点未配置'},
                    status=status.HTTP_500_INTERNAL_SERVER_ERROR
                ) 
            
            if not minio_access_key or not minio_secret_key:
                return Response(
                    {'error': 'MinIO 访问凭证未配置'},
                    status=status.HTTP_500_INTERNAL_SERVER_ERROR
                )
            
            # 检查必要字段
            if not train_job.dataset_version or not train_job.dataset_version.dataset_file:
                return Response(
                    {'error': '数据集文件不存在'},
                    status=status.HTTP_400_BAD_REQUEST
                )
            
            if not train_job.config_url:
                return Response(
                    {'error': '训练配置文件不存在'},
                    status=status.HTTP_400_BAD_REQUEST
                )
            
            # 构建训练任务标识
            job_id = f"AnomalyDetection_{train_job.algorithm}_{train_job.id}"
            
            logger.info(f"启动训练任务: {job_id}")
            logger.info(f"  Dataset: {train_job.dataset_version.dataset_file.name}")
            logger.info(f"  Config: {train_job.config_url.name}")
            
            # 调用 WebhookClient 启动训练
            WebhookClient.train(
                job_id=job_id,
                bucket=bucket,
                dataset=train_job.dataset_version.dataset_file.name,
                config=train_job.config_url.name,
                minio_endpoint=minio_endpoint,
                mlflow_tracking_uri=mlflow_tracking_uri,
                minio_access_key=minio_access_key,
                minio_secret_key=minio_secret_key
            )
            
            # 更新任务状态
            train_job.status = 'running'
            train_job.save(update_fields=['status'])
            
            logger.info(f"训练任务已启动: {job_id}")
            
            return Response({
                'message': '训练任务已启动',
                'job_id': job_id,
                'train_job_id': train_job.id
            })
            
        except WebhookTimeoutError as e:
            return Response(
                {'error': str(e)},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )
        except WebhookConnectionError as e:
            return Response(
                {'error': str(e)},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )
        except WebhookError as e:
            logger.error(f"启动训练任务失败: {e}")
            return Response(
                {'error': str(e)},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )
        except Exception as e:
            logger.error(f"启动训练任务失败: {str(e)}", exc_info=True)
            return Response(
                {'error': f'启动训练任务失败: {str(e)}'},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )
    
    @action(detail=True, methods=['post'], url_path='stop')
    @HasPermission("train_tasks-Stop")
    def stop(self, request, *args, **kwargs):
        """
        停止训练任务
        """
        try:
            train_job = self.get_object()
            
            # 检查任务状态
            if train_job.status != 'running':
                return Response(
                    {'error': '训练任务未在运行中'},
                    status=status.HTTP_400_BAD_REQUEST
                )
            
            # 构建训练任务标识
            job_id = f"AnomalyDetection_{train_job.algorithm}_{train_job.id}"
            
            logger.info(f"停止训练任务: {job_id}")
            
            # 调用 WebhookClient 停止任务（默认删除容器）
            result = WebhookClient.stop(job_id)
            
            # 更新任务状态
            train_job.status = 'pending'
            train_job.save(update_fields=['status'])
            
            logger.info(f"训练任务已停止: {job_id}")
            
            return Response({
                'message': '训练任务已停止',
                'job_id': job_id,
                'train_job_id': train_job.id,
                'webhook_response': result
            })
            
        except WebhookTimeoutError as e:
            return Response(
                {'error': str(e)},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )
        except WebhookConnectionError as e:
            return Response(
                {'error': str(e)},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )
        except WebhookError as e:
            logger.error(f"停止训练任务失败: {e}")
            return Response(
                {'error': str(e)},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )
        except Exception as e:
            logger.error(f"停止训练任务失败: {str(e)}", exc_info=True)
            return Response(
                {'error': f'停止训练任务失败: {str(e)}'},
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
                return Response({
                    'train_job_id': train_job.id,
                    'train_job_name': train_job.name,
                    'algorithm': train_job.algorithm,
                    'job_status': train_job.status,
                    'message': '未找到对应的MLflow实验',
                    'data': []
                })

            experiment = experiments[0]

            # 查找该实验中的运行
            runs = mlflow.search_runs(
                experiment_ids=[experiment.experiment_id],
                order_by=["start_time DESC"],
            )

            if runs.empty:
                return Response({
                    'train_job_id': train_job.id,
                    'train_job_name': train_job.name,
                    'algorithm': train_job.algorithm,
                    'job_status': train_job.status,
                    'message': '未找到训练运行记录',
                    'data': []
                })

            # 每次运行信息的耗时和名称
            run_datas = []
            latest_run_status = None  # 记录最新一次运行的状态
            
            for idx, row in runs.iterrows():
                # 处理时间计算，避免产生NaN或Infinity
                try:
                    start_time = row["start_time"]
                    end_time = row["end_time"]

                    # 计算耗时
                    if pd.notna(start_time):
                        if pd.notna(end_time):
                            # 已完成：使用实际结束时间
                            duration_seconds = (end_time - start_time).total_seconds()
                        else:
                            # 运行中：使用当前时间计算已运行时长
                            current_time = pd.Timestamp.now(tz=start_time.tz)
                            duration_seconds = (current_time - start_time).total_seconds()
                        duration_minutes = duration_seconds / 60
                    else:
                        duration_minutes = 0

                    # 获取run_name，处理可能的缺失值
                    run_name = row.get("tags.mlflow.runName", "")
                    if pd.isna(run_name):
                        run_name = ""
                    
                    # 获取状态
                    run_status = row.get("status", "UNKNOWN")
                    
                    # 记录第一条（最新）的运行状态
                    if idx == 0:
                        latest_run_status = run_status

                    run_data = {
                        "run_id": str(row["run_id"]),
                        "run_name": str(run_name),
                        "status": str(run_status),  # RUNNING/FINISHED/FAILED/KILLED
                        "start_time": start_time.isoformat() if pd.notna(start_time) else None,
                        "end_time": end_time.isoformat() if pd.notna(end_time) else None,
                        "duration_minutes": float(duration_minutes) if np.isfinite(duration_minutes) else 0
                    }
                    run_datas.append(run_data)

                except Exception as e:
                    logger.warning(f"解析 run 数据失败: {e}")
                    continue
            
            # 同步最新运行状态到 TrainJob（避免状态不一致）
            if latest_run_status and train_job.status == 'running':
                status_map = {
                    'FINISHED': 'completed',
                    'FAILED': 'failed',
                    'KILLED': 'failed',
                }
                new_status = status_map.get(latest_run_status)
                
                if new_status:
                    train_job.status = new_status
                    train_job.save(update_fields=['status'])
                    logger.info(f"自动同步 TrainJob {train_job.id} 状态: running -> {new_status} (基于 MLflow: {latest_run_status})")

            return Response({
                'train_job_id': train_job.id,
                'train_job_name': train_job.name,
                'algorithm': train_job.algorithm,
                'job_status': train_job.status,  # 返回当前 TrainJob 状态
                'total_runs': len(run_datas),
                'data': run_datas
            })
        except Exception as e:
            logger.error(f"获取训练记录列表失败: {str(e)}", exc_info=True)
            return Response(
                {'error': f'获取训练记录失败: {str(e)}'},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
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
    @HasPermission("train_tasks-View")
    def get_metric_data(self, request, run_id: str, metric_name: str):
        """
        获取指定 run 的指定指标的历史数据
        """
        try:
            # 跟踪Mlflow的uri
            mlflow.set_tracking_uri(MLFLOW_TRACKER_URL)

            # 创建客户端
            client = mlflow.tracking.MlflowClient()

            # 获取指标历史数据
            history = client.get_metric_history(run_id, metric_name)
            
            if not history:
                return Response({
                    "run_id": run_id,
                    "metric_name": metric_name,
                    "total_points": 0,
                    "metric_history": []
                })
            
            # 检查是否所有 step 都相同（通常是 0，表示未设置 step）
            all_steps = [m.step for m in history]
            unique_steps = set(all_steps)
            
            # 如果所有 step 都相同，说明记录时未指定 step，使用 timestamp 排序
            if len(unique_steps) == 1:
                logger.info(f"指标 {metric_name} 未使用 step，按 timestamp 排序（共 {len(history)} 条）")
                metric_history = [
                    {
                        "step": idx,  # 使用序号代替 step
                        "value": m.value,
                        "timestamp": m.timestamp
                    }
                    for idx, m in enumerate(sorted(history, key=lambda x: x.timestamp))
                ]
            else:
                # 正常场景：使用 step 去重，相同 step 保留最新的值
                metric_dict = {}
                for metric in history:
                    step = metric.step
                    # 如果 step 已存在，根据 timestamp 保留最新的
                    if step in metric_dict:
                        if metric.timestamp > metric_dict[step]['timestamp']:
                            metric_dict[step] = {
                                'step': step,
                                'value': metric.value,
                                'timestamp': metric.timestamp
                            }
                    else:
                        metric_dict[step] = {
                            'step': step,
                            'value': metric.value,
                            'timestamp': metric.timestamp
                        }
                
                # 按 step 排序
                metric_history = sorted(metric_dict.values(), key=lambda x: x['step'])
            
            # 移除 timestamp（仅用于排序/去重）
            metric_history_clean = [
                {
                    "step": item['step'],
                    "value": item['value']
                }
                for item in metric_history
            ]
            
            logger.info(f"返回 {len(metric_history_clean)} 条指标数据，step 范围: {metric_history_clean[0]['step'] if metric_history_clean else 'N/A'} - {metric_history_clean[-1]['step'] if metric_history_clean else 'N/A'}")

            return Response({
                "run_id": run_id,
                "metric_name": metric_name,
                "total_points": len(metric_history_clean),
                "metric_history": metric_history_clean
            })
            
        except Exception as e:
            logger.error(f"获取指标历史数据失败: {str(e)}", exc_info=True)
            return Response(
                {'error': f'获取指标历史数据失败: {str(e)}'},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )
    
    @action(detail=False, methods=['get'], url_path='run_params/(?P<run_id>.+?)')
    @HasPermission("train_tasks-View")
    def get_run_params(self, request, run_id: str):
        """
        获取指定 run 的配置参数（用于查看历史训练的配置）
        """
        try:
            # 设置 MLflow 跟踪 URI
            mlflow.set_tracking_uri(MLFLOW_TRACKER_URL)
            
            # 创建 MLflow 客户端
            client = mlflow.tracking.MlflowClient()
            
            # 获取 run 信息
            run = client.get_run(run_id)
            
            # 获取所有参数
            params = run.data.params
            
            # 获取 run_name 和状态
            run_name = run.data.tags.get('mlflow.runName', '')
            run_status = run.info.status
            start_time = run.info.start_time
            end_time = run.info.end_time
            
            return Response({
                'run_id': run_id,
                'run_name': run_name,
                'status': run_status,
                'start_time': pd.Timestamp(start_time, unit='ms').isoformat() if start_time else None,
                'end_time': pd.Timestamp(end_time, unit='ms').isoformat() if end_time else None,
                'params': params
            })
            
        except Exception as e:
            logger.error(f"获取运行参数失败: {str(e)}", exc_info=True)
            return Response(
                {'error': f'获取运行参数失败: {str(e)}'},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )
    
    @action(detail=False, methods=['get'], url_path='download_model/(?P<run_id>[^/]+)')
    @HasPermission("train_tasks-View")
    def download_model(self, request, run_id: str):
        """
        从 MLflow 下载模型并直接返回 ZIP 文件
        
        简化版本：直接从 MLflow 拉取 artifact → 打包 → 浏览器下载
        """
        from io import BytesIO
        
        try:
            # 1. 设置 MLflow
            mlflow.set_tracking_uri(MLFLOW_TRACKER_URL)
            mlflow_client = mlflow.tracking.MlflowClient()
            
            # 2. 验证 run 是否存在
            try:
                run = mlflow_client.get_run(run_id)
            except Exception as e:
                logger.error(f"Run 不存在: {run_id} - {e}")
                return Response(
                    {'error': f'Run 不存在: {run_id}'},
                    status=status.HTTP_404_NOT_FOUND
                )
            
            # 3. 检查模型 artifacts 是否存在
            try:
                artifacts = mlflow_client.list_artifacts(run_id, path="model")
                if not artifacts:
                    return Response(
                        {'error': '该 Run 未保存模型，无法下载'},
                        status=status.HTTP_404_NOT_FOUND
                    )
            except Exception as e:
                logger.error(f"获取模型 artifacts 失败: {e}")
                return Response(
                    {'error': f'获取模型 artifacts 失败: {str(e)}'},
                    status=status.HTTP_500_INTERNAL_SERVER_ERROR
                )
            
            # 4. 生成文件名
            run_name = run.data.tags.get('mlflow.runName', 'unknown')
            algorithm = run.data.params.get('algorithm', 'unknown')
            
            # 尝试从 Model Registry 获取模型名称和版本
            model_name = None
            model_version = None
            try:
                model_versions = mlflow_client.search_model_versions(f"run_id='{run_id}'")
                if model_versions:
                    model_name = model_versions[0].name
                    model_version = model_versions[0].version
            except Exception as e:
                logger.warning(f"未找到注册模型信息: {e}")
            
            # 构建文件名
            if model_name and model_version:
                filename = f"{model_name}_v{model_version}.zip"
            else:
                filename = f"{algorithm}_{run_name}_{run_id[:8]}.zip"
            
            logger.info(f"开始下载模型: run_id={run_id}, filename={filename}")
            
            # 5. 下载模型并打包
            with tempfile.TemporaryDirectory() as tmpdir:
                try:
                    # 从 MLflow 下载 model artifact
                    logger.info(f"从 MLflow 下载模型 artifacts...")
                    local_path = mlflow.artifacts.download_artifacts(
                        run_id=run_id,
                        artifact_path="model",
                        dst_path=tmpdir
                    )
                    logger.info(f"模型下载完成: {local_path}")
                    
                    # 打包成 ZIP
                    logger.info(f"开始打包模型...")
                    zip_base = os.path.join(tmpdir, run_id)
                    shutil.make_archive(
                        zip_base,
                        'zip',
                        local_path
                    )
                    zip_path = f"{zip_base}.zip"
                    
                    # 获取文件大小
                    file_size = os.path.getsize(zip_path)
                    logger.info(f"模型打包完成: {zip_path}, 大小: {round(file_size / 1024 / 1024, 2)} MB")
                    
                    # 6. 读取文件到内存（避免 Windows 文件句柄占用问题）
                    logger.info(f"读取文件到内存...")
                    with open(zip_path, 'rb') as f:
                        file_data = f.read()
                    
                    logger.info(f"文件已读取到内存，大小: {len(file_data)} 字节")
                    
                    # 7. 使用 BytesIO 包装，文件句柄已关闭，临时目录可以正常清理
                    file_obj = BytesIO(file_data)
                    
                    response = FileResponse(
                        file_obj,
                        content_type='application/zip',
                        as_attachment=True,
                        filename=filename
                    )
                    
                    logger.info(f"模型下载请求完成: {filename}")
                    return response
                    
                except Exception as e:
                    logger.error(f"模型下载或打包失败: {e}", exc_info=True)
                    return Response(
                        {'error': f'模型处理失败: {str(e)}'},
                        status=status.HTTP_500_INTERNAL_SERVER_ERROR
                    )
            
        except Exception as e:
            logger.error(f"下载模型失败: {str(e)}", exc_info=True)
            return Response(
                {'error': f'下载模型失败: {str(e)}'},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
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


class AnomalyDetectionDatasetReleaseViewSet(ModelViewSet):
    """异常检测数据集发布版本视图集"""
    queryset = AnomalyDetectionDatasetRelease.objects.all()
    serializer_class = AnomalyDetectionDatasetReleaseSerializer
    filterset_class = AnomalyDetectionDatasetReleaseFilter
    pagination_class = CustomPageNumberPagination
    permission_key = "dataset.anomaly_detection_dataset_release"

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
    
    @action(detail=True, methods=['get'], url_path='download')
    @HasPermission("anomaly_detection_datasets-View")
    def download(self, request, *args, **kwargs):
        """
        下载数据集版本的 ZIP 文件
        """
        try:
            release = self.get_object()
            
            if not release.dataset_file or not release.dataset_file.name:
                return Response(
                    {'error': '数据集文件不存在'},
                    status=status.HTTP_404_NOT_FOUND
                )
            
            # 获取文件
            file = release.dataset_file.open('rb')
            filename = f"{release.dataset.name}_{release.version}.zip"
            
            response = FileResponse(file, content_type='application/zip')
            response['Content-Disposition'] = f'attachment; filename="{filename}"'
            
            logger.info(f"下载数据集版本: {release.id} - {filename}")
            
            return response
            
        except Exception as e:
            logger.error(f"下载数据集失败: {str(e)}", exc_info=True)
            return Response(
                {'error': f'下载失败: {str(e)}'},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )
    
    @action(detail=True, methods=['post'], url_path='archive')
    @HasPermission("anomaly_detection_datasets-Edit")
    def archive(self, request, *args, **kwargs):
        """
        归档数据集版本(将状态改为 archived)
        """
        try:
            release = self.get_object()
            
            if release.status == 'archived':
                return Response(
                    {'error': '数据集版本已处于归档状态'},
                    status=status.HTTP_400_BAD_REQUEST
                )
            
            release.status = 'archived'
            release.description = f"[已归档] {release.description or ''}"
            release.save(update_fields=['status', 'description'])
            
            logger.info(f"归档数据集版本: {release.id}")
            
            return Response({
                'message': '归档成功',
                'release_id': release.id
            })
            
        except Exception as e:
            logger.error(f"归档失败: {str(e)}", exc_info=True)
            return Response(
                {'error': f'归档失败: {str(e)}'},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )
    
    @action(detail=True, methods=['post'], url_path='unarchive')
    @HasPermission("anomaly_detection_datasets-Edit")
    def unarchive(self, request, *args, **kwargs):
        """
        恢复已归档的数据集版本(将状态改为 published)
        """
        try:
            release = self.get_object()
            
            if release.status != 'archived':
                return Response(
                    {'error': '只能恢复已归档的数据集版本'},
                    status=status.HTTP_400_BAD_REQUEST
                )
            
            # 移除归档标记
            original_description = release.description or ''
            if original_description.startswith('[已归档] '):
                release.description = original_description.replace('[已归档] ', '', 1)
            
            release.status = 'published'
            release.save(update_fields=['status', 'description'])
            
            logger.info(f"恢复数据集版本: {release.id} - {release.dataset.name} {release.version}")
            
            return Response({
                'message': '恢复成功',
                'release_id': release.id,
                'status': release.status
            })
            
        except Exception as e:
            logger.error(f"恢复失败: {str(e)}", exc_info=True)
            return Response(
                {'error': f'恢复失败: {str(e)}'},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )


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
                detector = None
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
