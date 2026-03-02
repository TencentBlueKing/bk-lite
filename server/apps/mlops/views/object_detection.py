from config.drf.viewsets import ModelViewSet

from apps.mlops.constants import TrainJobStatus, DatasetReleaseStatus, MLflowRunStatus
from apps.core.logger import mlops_logger as logger
from apps.mlops.models.object_detection import *
from apps.mlops.serializers.object_detection import *
from apps.mlops.filters.object_detection import *
from config.drf.pagination import CustomPageNumberPagination
from apps.core.decorators.api_permission import HasPermission
from rest_framework import status
from rest_framework.response import Response
from rest_framework.decorators import action
from django.db import transaction
from django.http import FileResponse
from apps.mlops.utils import mlflow_service
from apps.mlops.utils.validators import validate_serving_status_change
from apps.mlops.utils.webhook_client import (
    WebhookClient,
    WebhookError,
    WebhookConnectionError,
    WebhookTimeoutError,
)
from apps.mlops.services import (
    get_image_by_prefix,
    get_mlflow_train_config,
    get_mlflow_tracking_uri,
    ConfigurationError,
)
import os
import pandas as pd
import numpy as np
import requests
from apps.mlops.models import AlgorithmConfig
from apps.mlops.serializers.algorithm_config import (
    AlgorithmConfigSerializer,
    AlgorithmConfigListSerializer,
)
from apps.mlops.filters.algorithm_config import AlgorithmConfigFilter


class ObjectDetectionDatasetViewSet(ModelViewSet):
    """目标检测数据集视图集"""

    queryset = ObjectDetectionDataset.objects.all()
    serializer_class = ObjectDetectionDatasetSerializer
    filterset_class = ObjectDetectionDatasetFilter
    pagination_class = CustomPageNumberPagination
    ordering = ("-id",)
    permission_key = "dataset.object_detection_dataset"

    @HasPermission("object_detection-View")
    def list(self, request, *args, **kwargs):
        return super().list(request, *args, **kwargs)

    @HasPermission("object_detection-View")
    def retrieve(self, request, *args, **kwargs):
        return super().retrieve(request, *args, **kwargs)

    @HasPermission("object_detection-Delete")
    def destroy(self, request, *args, **kwargs):
        return super().destroy(request, *args, **kwargs)

    @HasPermission("object_detection-Add")
    def create(self, request, *args, **kwargs):
        return super().create(request, *args, **kwargs)

    @HasPermission("object_detection-Edit")
    def update(self, request, *args, **kwargs):
        return super().update(request, *args, **kwargs)


class ObjectDetectionTrainDataViewSet(ModelViewSet):
    """目标检测训练数据视图集（重构：支持ZIP文件上传）"""

    queryset = ObjectDetectionTrainData.objects.select_related("dataset").all()
    serializer_class = ObjectDetectionTrainDataSerializer
    pagination_class = CustomPageNumberPagination
    filterset_class = ObjectDetectionTrainDataFilter
    ordering = ("-id",)
    permission_key = "dataset.object_detection_train_data"

    @HasPermission("object_detection-View")
    def list(self, request, *args, **kwargs):
        return super().list(request, *args, **kwargs)

    @HasPermission("object_detection-View")
    def retrieve(self, request, *args, **kwargs):
        return super().retrieve(request, *args, **kwargs)

    @HasPermission("object_detection-Delete")
    def destroy(self, request, *args, **kwargs):
        """
        删除训练数据实例，自动删除关联的 MinIO ZIP 文件
        """
        try:
            # train_data FileField 会在模型的 save() 方法中自动清理
            # 删除实例（模型会自动清理文件）
            super().destroy(request, *args, **kwargs)
            return Response(status=status.HTTP_204_NO_CONTENT)

        except Exception as e:
            logger.error(f"删除训练数据失败: {str(e)}", exc_info=True)
            return Response(
                {"error": f"删除失败: {str(e)}"},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )

    @HasPermission("object_detection-Add")
    def create(self, request, *args, **kwargs):
        """
        创建训练数据：上传 ZIP 压缩包 + metadata
        """
        return super().create(request, *args, **kwargs)

    @HasPermission("object_detection-Edit")
    def update(self, request, *args, **kwargs):
        """
        更新训练数据：可替换 ZIP 文件或更新 metadata
        """
        return super().update(request, *args, **kwargs)

    @action(detail=True, methods=["get"], url_path="download")
    @HasPermission("object_detection-View")
    def download(self, request, pk=None):
        """下载训练数据 ZIP 文件"""
        try:
            instance = self.get_object()

            if not instance.train_data:
                return Response(
                    {"error": "训练数据文件不存在"}, status=status.HTTP_404_NOT_FOUND
                )

            file = instance.train_data.open("rb")
            filename = f"{instance.name}_{instance.id}.zip"

            response = FileResponse(file, content_type="application/zip")
            response["Content-Disposition"] = f'attachment; filename="{filename}"'
            response["Content-Length"] = instance.train_data.size

            return response

        except Exception as e:
            logger.error(f"下载训练数据失败: {str(e)}", exc_info=True)
            return Response(
                {"error": f"下载失败: {str(e)}"},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )


class ObjectDetectionDatasetReleaseViewSet(ModelViewSet):
    """目标检测数据集发布版本视图集"""

    queryset = ObjectDetectionDatasetRelease.objects.select_related("dataset").all()
    serializer_class = ObjectDetectionDatasetReleaseSerializer
    pagination_class = CustomPageNumberPagination
    filterset_class = ObjectDetectionDatasetReleaseFilter
    ordering = ("-created_at",)
    permission_key = "dataset.object_detection_dataset_release"

    @HasPermission("object_detection-View")
    def list(self, request, *args, **kwargs):
        return super().list(request, *args, **kwargs)

    @HasPermission("object_detection-View")
    def retrieve(self, request, *args, **kwargs):
        return super().retrieve(request, *args, **kwargs)

    @HasPermission("object_detection-Delete")
    def destroy(self, request, *args, **kwargs):
        return super().destroy(request, *args, **kwargs)

    @HasPermission("object_detection-Add")
    def create(self, request, *args, **kwargs):
        return super().create(request, *args, **kwargs)

    @HasPermission("object_detection-Edit")
    def update(self, request, *args, **kwargs):
        return super().update(request, *args, **kwargs)

    @action(detail=True, methods=["get"], url_path="download")
    @HasPermission("object_detection-View")
    def download(self, request, *args, **kwargs):
        """下载数据集发布版本的压缩包"""
        try:
            instance = self.get_object()

            if not instance.dataset_file:
                return Response(
                    {"error": "数据集文件不存在"}, status=status.HTTP_404_NOT_FOUND
                )

            file = instance.dataset_file.open("rb")
            filename = f"{instance.dataset.name}_{instance.version}.zip"

            response = FileResponse(file, content_type="application/zip")
            response["Content-Disposition"] = f'attachment; filename="{filename}"'

            return response

        except Exception as e:
            logger.error(f"下载数据集失败: {str(e)}", exc_info=True)
            return Response(
                {"error": f"下载失败: {str(e)}"},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )

    @action(detail=True, methods=["post"], url_path="archive")
    @HasPermission("object_detection-Edit")
    def archive(self, request, pk=None):
        """归档数据集版本"""
        try:
            instance = self.get_object()

            if instance.status == DatasetReleaseStatus.ARCHIVED:
                return Response(
                    {"error": "数据集版本已经是归档状态"},
                    status=status.HTTP_400_BAD_REQUEST,
                )

            instance.status = DatasetReleaseStatus.ARCHIVED
            instance.save(update_fields=["status"])

            serializer = self.get_serializer(instance)
            return Response(serializer.data)

        except Exception as e:
            logger.error(f"归档数据集版本失败: {str(e)}", exc_info=True)
            return Response(
                {"error": f"归档失败: {str(e)}"},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )

    @action(detail=True, methods=["post"], url_path="unarchive")
    @HasPermission("object_detection-Edit")
    def unarchive(self, request, pk=None):
        """恢复归档的数据集版本"""
        try:
            instance = self.get_object()

            if instance.status != DatasetReleaseStatus.ARCHIVED:
                return Response(
                    {"error": "只能恢复归档状态的数据集版本"},
                    status=status.HTTP_400_BAD_REQUEST,
                )

            instance.status = DatasetReleaseStatus.PUBLISHED
            instance.save(update_fields=["status"])

            serializer = self.get_serializer(instance)
            return Response(serializer.data)

        except Exception as e:
            logger.error(f"恢复数据集版本失败: {str(e)}", exc_info=True)
            return Response(
                {"error": f"恢复失败: {str(e)}"},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )


class ObjectDetectionTrainJobViewSet(ModelViewSet):
    """目标检测训练任务视图集"""

    queryset = ObjectDetectionTrainJob.objects.select_related(
        "dataset_version", "dataset_version__dataset"
    ).all()
    serializer_class = ObjectDetectionTrainJobSerializer
    pagination_class = CustomPageNumberPagination
    filterset_class = ObjectDetectionTrainJobFilter
    ordering = ("-created_at",)
    permission_key = "train_tasks.object_detection_train_job"

    # MLflow 前缀
    MLFLOW_PREFIX = "ObjectDetection"

    @HasPermission("object_detection-View")
    def list(self, request, *args, **kwargs):
        return super().list(request, *args, **kwargs)

    @HasPermission("object_detection-View")
    def retrieve(self, request, *args, **kwargs):
        return super().retrieve(request, *args, **kwargs)

    @HasPermission("object_detection-Delete")
    def destroy(self, request, *args, **kwargs):
        return super().destroy(request, *args, **kwargs)

    @HasPermission("object_detection-Add")
    def create(self, request, *args, **kwargs):
        return super().create(request, *args, **kwargs)

    @HasPermission("object_detection-Edit")
    def update(self, request, *args, **kwargs):
        return super().update(request, *args, **kwargs)

    @action(detail=True, methods=["post"], url_path="train")
    @HasPermission("object_detection-Train")
    def train(self, request, pk=None):
        """
        启动目标检测训练任务
        """
        try:
            train_job = self.get_object()

            # 检查任务状态
            if train_job.status == TrainJobStatus.RUNNING:
                return Response(
                    {"error": "训练任务已在运行中"}, status=status.HTTP_400_BAD_REQUEST
                )

            # 获取训练配置
            try:
                config = get_mlflow_train_config()
            except ConfigurationError as e:
                logger.error(str(e))
                return Response(
                    {"error": "系统配置错误，请联系管理员"},
                    status=status.HTTP_500_INTERNAL_SERVER_ERROR,
                )

            # 检查必要字段
            if (
                not train_job.dataset_version
                or not train_job.dataset_version.dataset_file
            ):
                return Response(
                    {"error": "数据集文件不存在"}, status=status.HTTP_400_BAD_REQUEST
                )

            if not train_job.config_url:
                return Response(
                    {"error": "训练配置文件不存在"}, status=status.HTTP_400_BAD_REQUEST
                )

            # 构建训练任务标识
            job_id = mlflow_service.build_job_id(
                prefix=self.MLFLOW_PREFIX,
                algorithm=train_job.algorithm,
                train_job_id=train_job.id,
            )

            # 从 hyperopt_config 中提取 device 参数
            device = None
            if train_job.hyperopt_config:
                hyperparams = train_job.hyperopt_config.get("hyperparams", {})
                device = hyperparams.get("device")

            # 动态获取训练镜像
            train_image = get_image_by_prefix(self.MLFLOW_PREFIX, train_job.algorithm)

            # 调用 WebhookClient 启动训练
            WebhookClient.train(
                job_id=job_id,
                bucket=config.bucket,
                dataset=train_job.dataset_version.dataset_file.name,
                config=train_job.config_url.name,
                minio_endpoint=config.minio_endpoint,
                mlflow_tracking_uri=config.mlflow_tracking_uri,
                minio_access_key=config.minio_access_key,
                minio_secret_key=config.minio_secret_key,
                train_image=train_image,
                device=device,
            )

            # 更新任务状态
            train_job.status = TrainJobStatus.RUNNING
            train_job.save(update_fields=["status"])

            return Response(
                {
                    "message": "训练任务已启动",
                    "job_id": job_id,
                    "train_job_id": train_job.id,
                    "algorithm": train_job.algorithm,
                }
            )

        except WebhookTimeoutError as e:
            return Response(
                {"error": str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )
        except WebhookConnectionError as e:
            return Response(
                {"error": str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )
        except WebhookError as e:
            logger.error(f"启动训练任务失败: {e}")
            return Response(
                {"error": str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )
        except Exception as e:
            logger.error(f"启动训练任务失败: {str(e)}", exc_info=True)
            return Response(
                {"error": f"启动训练任务失败: {str(e)}"},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )

    @action(detail=True, methods=["post"], url_path="stop")
    @HasPermission("object_detection-Stop")
    def stop(self, request, *args, **kwargs):
        """
        停止目标检测训练任务
        """
        try:
            train_job = self.get_object()

            # 检查任务状态
            if train_job.status != TrainJobStatus.RUNNING:
                return Response(
                    {"error": "训练任务未在运行中"}, status=status.HTTP_400_BAD_REQUEST
                )

            # 构建训练任务标识
            job_id = mlflow_service.build_job_id(
                prefix=self.MLFLOW_PREFIX,
                algorithm=train_job.algorithm,
                train_job_id=train_job.id,
            )

            # 调用 WebhookClient 停止任务（默认删除容器）
            result = WebhookClient.stop(job_id)

            # 更新任务状态
            train_job.status = TrainJobStatus.PENDING
            train_job.save(update_fields=["status"])

            return Response(
                {
                    "message": "训练任务已停止",
                    "job_id": job_id,
                    "train_job_id": train_job.id,
                    "webhook_response": result,
                }
            )

        except WebhookTimeoutError as e:
            return Response(
                {"error": str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )
        except WebhookConnectionError as e:
            return Response(
                {"error": str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )
        except WebhookError as e:
            logger.error(f"停止训练任务失败: {e}")
            return Response(
                {"error": str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )
        except Exception as e:
            logger.error(f"停止训练任务失败: {str(e)}", exc_info=True)
            return Response(
                {"error": f"停止训练任务失败: {str(e)}"},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )

    @action(detail=True, methods=["get"], url_path="model_versions")
    @HasPermission("object_detection-View")
    def get_model_versions(self, request, pk=None):
        """
        获取训练任务对应模型的所有版本列表（从MLflow）
        """
        try:
            train_job = self.get_object()

            # 构造模型名称：ObjectDetection_YOLOv11n_123
            model_name = mlflow_service.build_model_name(
                prefix=self.MLFLOW_PREFIX,
                algorithm=train_job.algorithm,
                train_job_id=train_job.id,
            )

            # 查询模型版本
            version_data = mlflow_service.get_model_versions(model_name)

            if not version_data:
                logger.warning(f"模型未找到版本: {model_name}")
                return Response({"model_name": model_name, "versions": [], "total": 0})


            return Response(
                {
                    "model_name": model_name,
                    "total": len(version_data),
                    "versions": version_data,
                }
            )

        except Exception as e:
            logger.error(f"获取模型版本列表失败: {str(e)}", exc_info=True)
            return Response(
                {"error": f"获取模型版本列表失败: {str(e)}"},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )

    @action(detail=False, methods=["get"], url_path="download_model/(?P<run_id>[^/]+)")
    @HasPermission("object_detection-View")
    def download_model(self, request, run_id: str):
        """
        从 MLflow 下载模型并直接返回 ZIP 文件

        Args:
            run_id: MLflow run ID
        """
        try:
            logger.info(f"开始下载模型: run_id={run_id}")

            # 下载模型并打包为 ZIP
            zip_buffer = mlflow_service.download_model_artifact(
                run_id=run_id, artifact_path="model"
            )

            # 构造文件名
            filename = f"model_{run_id}.zip"

            # 返回文件响应
            from django.http import HttpResponse

            response = HttpResponse(
                zip_buffer.getvalue(), content_type="application/zip"
            )
            response["Content-Disposition"] = f'attachment; filename="{filename}"'
            response["Content-Length"] = len(zip_buffer.getvalue())

            logger.info(
                f"模型下载成功: run_id={run_id}, size={len(zip_buffer.getvalue())} bytes"
            )
            return response

        except Exception as e:
            logger.error(f"下载模型失败: {str(e)}", exc_info=True)
            return Response(
                {"error": f"下载模型失败: {str(e)}"},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )

    @action(detail=True, methods=["get"], url_path="runs_data_list")
    @HasPermission("object_detection-View")
    def get_run_data_list(self, request, pk=None):
        try:
            # 获取训练任务
            train_job = self.get_object()

            # 构造实验名称（与训练时保持一致）
            experiment_name = mlflow_service.build_experiment_name(
                prefix=self.MLFLOW_PREFIX,
                algorithm=train_job.algorithm,
                train_job_id=train_job.id,
            )

            # 查找实验
            experiment = mlflow_service.get_experiment_by_name(experiment_name)
            if not experiment:
                return Response(
                    {
                        "train_job_id": train_job.id,
                        "train_job_name": train_job.name,
                        "algorithm": train_job.algorithm,
                        "job_status": train_job.status,
                        "message": "未找到对应的MLflow实验",
                        "data": [],
                    }
                )

            # 查找该实验中的运行
            runs = mlflow_service.get_experiment_runs(experiment.experiment_id)

            if runs.empty:
                return Response(
                    {
                        "train_job_id": train_job.id,
                        "train_job_name": train_job.name,
                        "algorithm": train_job.algorithm,
                        "job_status": train_job.status,
                        "message": "未找到训练运行记录",
                        "data": [],
                    }
                )

            # 每次运行信息的耗时和名称
            run_datas = []
            latest_run_status = None

            for idx, row in runs.iterrows():
                # 处理时间计算，避免产生NaN或Infinity
                try:
                    start_time = row["start_time"]
                    end_time = row["end_time"]

                    # 计算耗时
                    if pd.notna(start_time):
                        if pd.notna(end_time):
                            duration_seconds = (end_time - start_time).total_seconds()
                        else:
                            current_time = pd.Timestamp.now(tz=start_time.tz)
                            duration_seconds = (
                                current_time - start_time
                            ).total_seconds()
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
                        "status": str(run_status),
                        "start_time": start_time.isoformat()
                        if pd.notna(start_time)
                        else None,
                        "end_time": end_time.isoformat()
                        if pd.notna(end_time)
                        else None,
                        "duration_minutes": float(duration_minutes)
                        if np.isfinite(duration_minutes)
                        else 0,
                    }
                    run_datas.append(run_data)

                except Exception as e:
                    logger.warning(f"解析 run 数据失败: {e}")
                    continue

            # 同步最新运行状态到 TrainJob
            if latest_run_status and train_job.status == TrainJobStatus.RUNNING:
                new_status = MLflowRunStatus.TO_TRAIN_JOB_STATUS.get(latest_run_status)

                if new_status:
                    train_job.status = new_status
                    train_job.save(update_fields=["status"])

            return Response(
                {
                    "train_job_id": train_job.id,
                    "train_job_name": train_job.name,
                    "algorithm": train_job.algorithm,
                    "job_status": train_job.status,
                    "total_runs": len(run_datas),
                    "data": run_datas,
                }
            )
        except Exception as e:
            logger.error(f"获取训练记录列表失败: {str(e)}", exc_info=True)
            return Response(
                {"error": f"获取训练记录失败: {str(e)}"},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )

    @action(detail=False, methods=["get"], url_path="runs_metrics_list/(?P<run_id>.+?)")
    @HasPermission("object_detection-View")
    def get_runs_metrics_list(self, request, run_id: str):
        try:
            # 获取运行的指标列表（过滤系统指标）
            model_metrics = mlflow_service.get_run_metrics(
                run_id=run_id, filter_system=True
            )

            return Response({"run_id": run_id, "metrics": model_metrics})

        except Exception as e:
            return Response(
                {"error": f"获取指标列表失败: {str(e)}"},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )

    @action(
        detail=False,
        methods=["get"],
        url_path="runs_metrics_history/(?P<run_id>.+?)/(?P<metric_name>.+?)",
    )
    @HasPermission("object_detection-View")
    def get_metric_data(self, request, run_id: str, metric_name: str):
        """
        获取指定 run 的指定指标的历史数据
        """
        try:
            # 获取指标历史数据（自动处理排序）
            metric_data = mlflow_service.get_metric_history(run_id, metric_name)

            if not metric_data:
                return Response(
                    {
                        "run_id": run_id,
                        "metric_name": metric_name,
                        "total_points": 0,
                        "metric_history": [],
                    }
                )

            return Response(
                {
                    "run_id": run_id,
                    "metric_name": metric_name,
                    "total_points": len(metric_data),
                    "metric_history": metric_data,
                }
            )

        except Exception as e:
            logger.error(f"获取指标历史数据失败: {str(e)}", exc_info=True)
            return Response(
                {"error": f"获取指标历史数据失败: {str(e)}"},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )

    @action(detail=False, methods=["get"], url_path="run_params/(?P<run_id>.+?)")
    @HasPermission("object_detection-View")
    def get_run_params(self, request, run_id: str):
        """
        获取指定 run 的配置参数（用于查看历史训练的配置）
        """
        try:
            # 获取运行信息和参数
            run = mlflow_service.get_run_info(run_id)
            params = mlflow_service.get_run_params(run_id)

            # 提取运行元信息
            run_name = run.data.tags.get("mlflow.runName", run_id)
            run_status = run.info.status
            start_time = run.info.start_time
            end_time = run.info.end_time

            return Response(
                {
                    "run_id": run_id,
                    "run_name": run_name,
                    "status": run_status,
                    "start_time": pd.Timestamp(start_time, unit="ms").isoformat()
                    if start_time
                    else None,
                    "end_time": pd.Timestamp(end_time, unit="ms").isoformat()
                    if end_time
                    else None,
                    "params": params,
                }
            )

        except Exception as e:
            logger.error(f"获取运行参数失败: {str(e)}", exc_info=True)
            return Response(
                {"error": f"获取运行参数失败: {str(e)}"},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )


class ObjectDetectionServingViewSet(ModelViewSet):
    """目标检测服务视图集"""

    queryset = ObjectDetectionServing.objects.select_related(
        "train_job", "train_job__dataset_version", "train_job__dataset_version__dataset"
    ).all()
    serializer_class = ObjectDetectionServingSerializer
    pagination_class = CustomPageNumberPagination
    filterset_class = ObjectDetectionServingFilter
    ordering = ("-created_at",)
    permission_key = "serving.object_detection_serving"

    # MLflow 前缀
    MLFLOW_PREFIX = "ObjectDetection"

    @HasPermission("object_detection-View")
    def list(self, request, *args, **kwargs):
        """列表查询，实时同步容器状态"""
        response = super().list(request, *args, **kwargs)

        if isinstance(response.data, dict):
            servings = response.data.get("items", [])
        else:
            servings = response.data

        if not servings:
            return response

        serving_ids = [f"ObjectDetection_Serving_{s['id']}" for s in servings]

        try:
            # 批量查询容器状态
            result = WebhookClient.get_status(serving_ids)
            status_map = {s.get("id"): s for s in result}

            # 批量获取所有需要更新的对象（避免N+1查询）
            serving_id_list = [s["id"] for s in servings]
            serving_objs = ObjectDetectionServing.objects.filter(id__in=serving_id_list)
            serving_obj_map = {obj.id: obj for obj in serving_objs}

            updates = []
            for serving_data in servings:
                serving_id = f"ObjectDetection_Serving_{serving_data['id']}"
                container_info = status_map.get(serving_id)

                if container_info:
                    serving_data["container_info"] = container_info

                    # 同步到数据库：从缓存字典获取对象，无额外查询
                    serving_obj = serving_obj_map.get(serving_data["id"])
                    if serving_obj:
                        serving_obj.container_info = container_info
                        updates.append(serving_obj)
                else:
                    serving_data["container_info"] = {
                        "status": "error",
                        "state": "unknown",
                        "message": "webhookd 未返回此容器状态",
                    }

            if updates:
                ObjectDetectionServing.objects.bulk_update(updates, ["container_info"])

        except WebhookError as e:
            logger.error(f"查询容器状态失败: {e}")
            # 降级：使用数据库中的旧值
            for serving_data in servings:
                old_info = serving_data.get("container_info") or {}
                serving_data["container_info"] = {
                    **old_info,
                    "status": "error",
                    "_query_failed": True,
                    "_error": str(e),
                }

        return response

    @HasPermission("object_detection-View")
    def retrieve(self, request, *args, **kwargs):
        return super().retrieve(request, *args, **kwargs)

    @HasPermission("object_detection-Delete")
    def destroy(self, request, *args, **kwargs):
        return super().destroy(request, *args, **kwargs)

    @HasPermission("object_detection-Add")
    def create(self, request, *args, **kwargs):
        """创建 serving 服务并自动启动容器"""
        response = super().create(request, *args, **kwargs)
        serving_id = response.data["id"]

        try:
            serving = ObjectDetectionServing.objects.get(id=serving_id)

            # 获取 MLflow tracking URI
            mlflow_tracking_uri = get_mlflow_tracking_uri()
            if not mlflow_tracking_uri:
                logger.error("环境变量 MLFLOW_TRACKER_URL 未配置")
                serving.container_info = {
                    "status": "error",
                    "message": "环境变量 MLFLOW_TRACKER_URL 未配置",
                }
                serving.save(update_fields=["container_info"])
                response.data["container_info"] = serving.container_info
                response.data["message"] = "服务已创建但启动失败：环境变量未配置"
                return response

            # 解析 model_uri
            try:
                model_uri = self._resolve_model_uri(serving)
            except ValueError as e:
                logger.error(f"解析 model URI 失败: {e}")
                serving.container_info = {
                    "status": "error",
                    "message": f"解析模型 URI 失败: {str(e)}",
                }
                serving.save(update_fields=["container_info"])
                response.data["container_info"] = serving.container_info
                response.data["message"] = f"服务已创建但启动失败：{str(e)}"
                return response

            # 构建 serving ID
            container_id = f"ObjectDetection_Serving_{serving.id}"

            # 从关联训练任务的 hyperopt_config 中提取 device 参数
            device = None
            if serving.train_job and serving.train_job.hyperopt_config:
                hyperparams = serving.train_job.hyperopt_config.get("hyperparams", {})
                device = hyperparams.get("device")

            try:
                # 动态获取服务镜像
                train_image = get_image_by_prefix(
                    self.MLFLOW_PREFIX, serving.train_job.algorithm
                )

                # 调用 WebhookClient 启动服务
                result = WebhookClient.serve(
                    container_id,
                    mlflow_tracking_uri,
                    model_uri,
                    port=serving.port,
                    train_image=train_image,
                    device=device,
                )

                serving.container_info = result
                serving.save(update_fields=["container_info"])

                response.data["container_info"] = result
                response.data["message"] = "服务已创建并启动"

            except WebhookError as e:
                error_msg = str(e)
                logger.error(f"自动启动 serving 失败: {error_msg}")

                # 处理容器已存在的情况
                if e.code == "CONTAINER_ALREADY_EXISTS":
                    try:
                        result = WebhookClient.get_status([container_id])
                        container_info = (
                            result[0]
                            if result
                            else {
                                "status": "error",
                                "id": container_id,
                                "message": "无法查询容器状态",
                            }
                        )

                        serving.container_info = container_info
                        serving.save(update_fields=["container_info"])

                        response.data["container_info"] = container_info
                        response.data["message"] = (
                            "服务已创建，检测到容器已存在并同步容器状态"
                        )
                        response.data["warning"] = "容器已存在，已同步容器信息"
                    except WebhookError:
                        serving.container_info = {
                            "status": "error",
                            "message": f"容器已存在但同步状态失败: {error_msg}",
                        }
                        serving.save(update_fields=["container_info"])
                        response.data["container_info"] = serving.container_info
                        response.data["message"] = "服务已创建但启动失败"
                else:
                    serving.container_info = {"status": "error", "message": error_msg}
                    serving.save(update_fields=["container_info"])
                    response.data["container_info"] = serving.container_info
                    response.data["message"] = f"服务已创建但启动失败: {error_msg}"

        except Exception as e:
            logger.error(f"自动启动 serving 异常: {str(e)}", exc_info=True)
            response.data["message"] = f"服务已创建但启动异常: {str(e)}"

        return response

    @HasPermission("object_detection-Edit")
    def update(self, request, *args, **kwargs):
        """
        更新 serving 配置，自动检测并重启容器

        基于实际容器运行状态决策：
        - 容器 running + 配置变更 → 自动重启
        - 容器非 running → 仅更新数据库，用户自行决定是否启动
        """
        instance = self.get_object()

        # 兜底校验：容器未运行时不允许设置 status=active
        new_status = request.data.get("status")
        if error_response := validate_serving_status_change(instance, new_status):
            return error_response

        # 保存旧值用于判断变更
        old_port = instance.port
        old_model_version = instance.model_version
        old_train_job_id = instance.train_job.id

        # 检测是否更新了影响容器的字段（基于请求数据与旧值对比）
        model_version_changed = "model_version" in request.data and str(
            request.data["model_version"]
        ) != str(old_model_version)
        train_job_changed = (
            "train_job" in request.data
            and int(request.data["train_job"]) != old_train_job_id
        )
        port_changed = "port" in request.data and request.data.get("port") != old_port

        container_id = f"ObjectDetection_Serving_{instance.id}"

        # 获取容器实际状态（更新前），防御性处理 container_info 为空的情况
        container_info = instance.container_info or {}
        container_state = container_info.get("state")
        container_port = container_info.get("port")

        # 更新数据库
        response = super().update(request, *args, **kwargs)
        instance.refresh_from_db()

        # 只有容器在运行时才考虑重启
        if container_state != "running":
            return response

        # 决策：是否需要重启
        need_restart = False

        # 1. model/train_job 变更，必须重启
        if model_version_changed or train_job_changed:
            need_restart = True

        # 2. 仅 port 变更，检查策略
        elif port_changed:
            new_port = instance.port
            if new_port is None and old_port is not None:
                # 有值 → None：不重启（当前端口视为自动分配，下次再应用）
                need_restart = False
            elif new_port is not None and old_port is None:
                # None → 有值：需要重启（用户明确要指定端口）
                need_restart = True
            elif new_port is not None and old_port is not None:
                # 有值 → 另一个有值：检查是否与实际端口一致
                if container_port and str(new_port) != str(container_port):
                    need_restart = True

        # 如果需要重启，先删除旧容器
        if need_restart:
            try:
                logger.warning(f"配置变更需要重启，删除旧容器: {container_id}")
                WebhookClient.remove(container_id)
            except WebhookError as e:
                logger.warning(f"删除旧容器失败（可能已不存在）: {e}")
                # 继续执行，尝试启动新容器

            try:
                # 获取环境变量
                mlflow_tracking_uri = get_mlflow_tracking_uri()
                if not mlflow_tracking_uri:
                    raise ValueError("环境变量 MLFLOW_TRACKER_URL 未配置")

                # 解析新的 model_uri
                model_uri = self._resolve_model_uri(instance)

                # 从关联训练任务的 hyperopt_config 中提取 device 参数
                device = None
                if instance.train_job and instance.train_job.hyperopt_config:
                    hyperparams = instance.train_job.hyperopt_config.get("hyperparams", {})
                    device = hyperparams.get("device")

                # 动态获取推理镜像
                train_image = get_image_by_prefix(
                    self.MLFLOW_PREFIX, instance.train_job.algorithm
                )

                # 启动新容器
                result = WebhookClient.serve(
                    container_id,
                    mlflow_tracking_uri,
                    model_uri,
                    port=instance.port,
                    train_image=train_image,
                    device=device,
                )

                # 更新容器信息（status 由用户控制，不修改）
                instance.container_info = result
                instance.save(update_fields=["container_info"])

                # 更新返回数据
                response.data["container_info"] = result
                response.data["message"] = "配置已更新并重启服务"

            except Exception as e:
                logger.error(f"自动重启失败: {str(e)}", exc_info=True)

                # 启动失败，仅更新容器信息
                instance.container_info = {
                    "status": "error",
                    "message": f"配置已更新但重启失败: {str(e)}",
                }
                instance.save(update_fields=["container_info"])

                response.data["container_info"] = instance.container_info
                response.data["message"] = f"配置已更新但重启失败: {str(e)}"
                response.data["warning"] = "请手动调用 start 接口重新启动服务"

        return response

    @action(detail=True, methods=["post"], url_path="start")
    @HasPermission("object_detection-Start")
    def start(self, request, *args, **kwargs):
        """
        启动目标检测 serving 服务
        """
        try:
            serving = self.get_object()

            # 获取 MLflow tracking URI
            mlflow_tracking_uri = get_mlflow_tracking_uri()
            if not mlflow_tracking_uri:
                logger.error("MLflow tracking URI not configured")
                return Response(
                    {"error": "系统配置错误，请联系管理员"},
                    status=status.HTTP_500_INTERNAL_SERVER_ERROR,
                )

            # 解析 model_uri
            try:
                model_uri = self._resolve_model_uri(serving)
            except ValueError as e:
                return Response({"error": str(e)}, status=status.HTTP_400_BAD_REQUEST)

            # 构建 serving ID
            serving_id = f"ObjectDetection_Serving_{serving.id}"

            # 从关联训练任务的 hyperopt_config 中提取 device 参数
            device = None
            if serving.train_job and serving.train_job.hyperopt_config:
                hyperparams = serving.train_job.hyperopt_config.get("hyperparams", {})
                device = hyperparams.get("device")

            try:
                # 动态获取服务镜像
                train_image = get_image_by_prefix(
                    self.MLFLOW_PREFIX, serving.train_job.algorithm
                )

                # 调用 WebhookClient 启动服务
                result = WebhookClient.serve(
                    serving_id,
                    mlflow_tracking_uri,
                    model_uri,
                    port=serving.port,
                    train_image=train_image,
                    device=device,
                )

                # 正常启动成功，更新容器信息以及将status设为 'active'
                serving.container_info = result
                serving.status = "active"
                serving.save(update_fields=["container_info", "status"])

                return Response(
                    {
                        "message": "服务已启动",
                        "serving_id": serving_id,
                        "container_info": result,
                    }
                )

            except WebhookError as e:
                error_msg = str(e)

                # 处理端口冲突
                if (
                    "端口已被占用" in error_msg
                    or "port is already allocated" in error_msg
                ):
                    return Response(
                        {"error": f"端口 {serving.port} 已被占用，请选择其他端口"},
                        status=status.HTTP_409_CONFLICT,
                    )

                # 处理模型不存在
                if "Model" in error_msg and "not found" in error_msg:
                    return Response(
                        {"error": f"模型 {model_uri} 不存在，请确认模型版本正确"},
                        status=status.HTTP_404_NOT_FOUND,
                    )

                raise

        except WebhookTimeoutError as e:
            return Response(
                {"error": str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )
        except WebhookConnectionError as e:
            return Response(
                {"error": str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )
        except WebhookError as e:
            logger.error(f"启动 serving 失败: {e}")
            return Response(
                {"error": str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )
        except Exception as e:
            logger.error(f"启动目标检测 serving 服务失败: {str(e)}", exc_info=True)
            return Response(
                {"error": f"启动服务失败: {str(e)}"},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )

    @action(detail=True, methods=["post"], url_path="stop")
    @HasPermission("object_detection-Stop")
    def stop(self, request, *args, **kwargs):
        """
        停止目标检测 serving 服务（停止并删除容器）
        """
        try:
            serving = self.get_object()

            # 构建 serving ID
            serving_id = f"ObjectDetection_Serving_{serving.id}"

            # 调用 WebhookClient 停止服务（默认删除容器）
            result = WebhookClient.stop(serving_id)

            # 停止容器时同时将status改为'inactive'
            serving.status = "inactive"
            serving.save(update_fields=["status"])

            return Response(
                {
                    "message": "服务已停止并删除",
                    "serving_id": serving_id,
                    "webhook_response": result,
                }
            )

        except WebhookTimeoutError as e:
            return Response(
                {"error": str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )
        except WebhookConnectionError as e:
            return Response(
                {"error": str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )
        except WebhookError as e:
            logger.error(f"停止 serving 失败: {e}")
            return Response(
                {"error": str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )
        except Exception as e:
            logger.error(f"停止目标检测 serving 服务失败: {str(e)}", exc_info=True)
            return Response(
                {"error": f"停止服务失败: {str(e)}"},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )

    @action(detail=True, methods=["post"], url_path="remove")
    @HasPermission("object_detection-Remove")
    def remove(self, request, *args, **kwargs):
        """
        删除目标检测 serving 容器（可处理运行中的容器）
        """
        try:
            serving = self.get_object()

            # 构建 serving ID
            serving_id = f"ObjectDetection_Serving_{serving.id}"

            # 调用 WebhookClient 删除容器
            result = WebhookClient.remove(serving_id)

            # 更新容器信息（status 由用户控制，不修改）
            serving.container_info = {
                "status": "success",
                "id": serving_id,
                "state": "removed",
                "message": "容器已删除",
            }
            serving.save(update_fields=["container_info"])

            return Response(
                {
                    "message": "容器已删除",
                    "serving_id": serving_id,
                    "webhook_response": result,
                }
            )

        except WebhookTimeoutError as e:
            return Response(
                {"error": str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )
        except WebhookConnectionError as e:
            return Response(
                {"error": str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )
        except WebhookError as e:
            logger.error(f"删除容器失败: {e}")
            return Response(
                {"error": str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )
        except Exception as e:
            logger.error(f"删除目标检测 serving 容器失败: {str(e)}", exc_info=True)
            return Response(
                {"error": f"删除容器失败: {str(e)}"},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )

    @action(detail=True, methods=["post"], url_path="predict")
    @HasPermission("object_detection-Predict")
    def predict(self, request, *args, **kwargs):
        """
        调用目标检测 serving 服务进行预测

        请求参数:
            url: 预测服务主机地址
            image: base64编码的图片数据

        Returns:
            目标检测结果（边界框、类别、置信度）
        """
        serving = self.get_object()

        # 校验服务状态
        if serving.status != "active":
            return Response(
                {"error": "服务未发布，请先发布服务"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        # 验证容器信息
        if not serving.container_info or not isinstance(serving.container_info, dict):
            return Response(
                {"error": "服务未启动或容器信息不可用"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        # 获取端口
        port = serving.container_info.get("port")
        if not port:
            return Response(
                {"error": "服务端口不可用"}, status=status.HTTP_400_BAD_REQUEST
            )

        # 获取预测参数
        url = request.data.get("url")
        image_data = request.data.get("image")

        if not url:
            return Response(
                {"error": "缺少参数: url"}, status=status.HTTP_400_BAD_REQUEST
            )
        if not image_data:
            return Response(
                {"error": "缺少参数: image"}, status=status.HTTP_400_BAD_REQUEST
            )

        # 构建预测请求URL
        predict_url = f"{url}:{port}/predict"

        try:

            # 调用推理服务
            response = requests.post(
                predict_url, json={"image": image_data}, timeout=60
            )
            response.raise_for_status()

            result = response.json()

            return Response(result)

        except requests.exceptions.Timeout:
            logger.error(f"推理请求超时: {predict_url}")
            return Response(
                {"error": "推理请求超时"}, status=status.HTTP_504_GATEWAY_TIMEOUT
            )
        except requests.exceptions.ConnectionError as e:
            logger.error(f"无法连接推理服务: {predict_url}, 错误: {e}")
            return Response(
                {"error": f"无法连接推理服务: {str(e)}"},
                status=status.HTTP_503_SERVICE_UNAVAILABLE,
            )
        except requests.exceptions.HTTPError as e:
            logger.error(f"推理服务返回错误: {e}")
            return Response(
                {"error": f"推理服务错误: {str(e)}"},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )
        except Exception as e:
            logger.error(f"目标检测推理失败: {str(e)}", exc_info=True)
            return Response(
                {"error": f"推理失败: {str(e)}"},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )

    def _resolve_model_uri(self, serving):
        """
        解析 MLflow Model URI

        Args:
            serving: ObjectDetectionServing 实例

        Returns:
            str: MLflow model URI

        Raises:
            ValueError: 解析失败时抛出
        """
        train_job = serving.train_job
        model_name = mlflow_service.build_model_name(
            prefix=self.MLFLOW_PREFIX,
            algorithm=train_job.algorithm,
            train_job_id=train_job.id,
        )

        return mlflow_service.resolve_model_uri(model_name, serving.model_version)


class ObjectDetectionAlgorithmConfigViewSet(ModelViewSet):
    """目标检测算法配置视图集"""

    queryset = AlgorithmConfig.objects.filter(algorithm_type="object_detection")
    serializer_class = AlgorithmConfigSerializer
    filterset_class = AlgorithmConfigFilter
    pagination_class = CustomPageNumberPagination
    ordering = ("id",)
    permission_key = "algorithm.object_detection_algorithm_config"

    def get_serializer_class(self):
        if (
            self.action == "list"
            and not self.request.query_params.get(
                "include_form_config", "false"
            ).lower()
            == "true"
        ):
            return AlgorithmConfigListSerializer
        return AlgorithmConfigSerializer

    @HasPermission("object_detection-View")
    def list(self, request, *args, **kwargs):
        return super().list(request, *args, **kwargs)

    @HasPermission("object_detection-View")
    def retrieve(self, request, *args, **kwargs):
        return super().retrieve(request, *args, **kwargs)

    @HasPermission("object_detection-Add")
    def create(self, request, *args, **kwargs):
        request.data["algorithm_type"] = "object_detection"
        return super().create(request, *args, **kwargs)

    @HasPermission("object_detection-Edit")
    def update(self, request, *args, **kwargs):
        return super().update(request, *args, **kwargs)

    @HasPermission("object_detection-Edit")
    def partial_update(self, request, *args, **kwargs):
        instance = self.get_object()
        is_active_new = request.data.get("is_active")
        if instance.is_active and is_active_new is False:
            task_count = ObjectDetectionTrainJob.objects.filter(
                algorithm=instance.name
            ).count()
            if task_count > 0:
                return Response(
                    {
                        "error": f"无法禁用：有 {task_count} 个训练任务正在使用此算法",
                        "task_count": task_count,
                    },
                    status=status.HTTP_400_BAD_REQUEST,
                )
        return super().partial_update(request, *args, **kwargs)

    @HasPermission("object_detection-Delete")
    def destroy(self, request, *args, **kwargs):
        instance = self.get_object()
        task_count = ObjectDetectionTrainJob.objects.filter(
            algorithm=instance.name
        ).count()
        if task_count > 0:
            return Response(
                {
                    "error": f"无法删除：有 {task_count} 个训练任务正在使用此算法",
                    "task_count": task_count,
                },
                status=status.HTTP_400_BAD_REQUEST,
            )
        return super().destroy(request, *args, **kwargs)

    @action(detail=False, methods=["get"], url_path="by_type")
    @HasPermission("object_detection-View")
    def by_type(self, request):
        queryset = self.get_queryset().filter(is_active=True)
        serializer = AlgorithmConfigSerializer(queryset, many=True)
        return Response(serializer.data)

    @action(detail=False, methods=["get"], url_path="get_image")
    @HasPermission("object_detection-View")
    def get_image(self, request):
        name = request.query_params.get("name")
        if not name:
            return Response({"error": "name 参数必填"}, status=400)
        try:
            config = AlgorithmConfig.objects.get(
                algorithm_type="object_detection", name=name, is_active=True
            )
            return Response({"image": config.image})
        except AlgorithmConfig.DoesNotExist:
            return Response(
                {"error": f"未找到算法配置: object_detection/{name}"}, status=404
            )
