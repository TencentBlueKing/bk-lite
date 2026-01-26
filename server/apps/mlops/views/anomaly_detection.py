from config.drf.viewsets import ModelViewSet
from apps.mlops.filters.anomaly_detection import *
from apps.core.logger import mlops_logger as logger
from apps.core.decorators.api_permission import HasPermission
from apps.mlops.models.anomaly_detection import *
from apps.mlops.serializers.anomaly_detection import *
from config.drf.pagination import CustomPageNumberPagination
from rest_framework.response import Response
from rest_framework import status
from django.http import FileResponse
import pandas as pd
import numpy as np
from rest_framework.decorators import action
from apps.mlops.utils.webhook_client import (
    WebhookClient,
    WebhookError,
    WebhookConnectionError,
    WebhookTimeoutError,
)
from apps.mlops.utils import mlflow_service
import os
import requests


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
    queryset = AnomalyDetectionTrainJob.objects.select_related(
        "dataset_version", "dataset_version__dataset"
    ).all()
    serializer_class = AnomalyDetectionTrainJobSerializer
    filterset_class = AnomalyDetectionTrainJobFilter
    pagination_class = CustomPageNumberPagination
    ordering = ("-id",)
    permission_key = "dataset.anomaly_detection_train_job"

    MLFLOW_PREFIX = "AnomalyDetection"  # MLflow 命名前缀

    @action(detail=True, methods=["post"], url_path="train")
    @HasPermission("train_tasks-Train")
    def train(self, request, pk=None):
        """
        启动训练任务
        """
        try:
            train_job = self.get_object()

            # 检查任务状态
            if train_job.status == "running":
                return Response(
                    {"error": "训练任务已在运行中"}, status=status.HTTP_400_BAD_REQUEST
                )

            # 获取环境变量
            bucket = os.getenv("MINIO_PUBLIC_BUCKETS", "munchkin-public")
            minio_endpoint = os.getenv("MLFLOW_S3_ENDPOINT_URL", "")
            mlflow_tracking_uri = os.getenv("MLFLOW_TRACKER_URL", "")
            minio_access_key = os.getenv("MINIO_ACCESS_KEY", "")
            minio_secret_key = os.getenv("MINIO_SECRET_KEY", "")

            if not minio_endpoint:
                logger.error("MinIO endpoint not configured")
                return Response(
                    {"error": "系统配置错误，请联系管理员"},
                    status=status.HTTP_500_INTERNAL_SERVER_ERROR,
                )

            if not mlflow_tracking_uri:
                logger.error("MLflow tracking URI not configured")
                return Response(
                    {"error": "系统配置错误，请联系管理员"},
                    status=status.HTTP_500_INTERNAL_SERVER_ERROR,
                )

            if not minio_access_key or not minio_secret_key:
                logger.error("MinIO credentials not configured")
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
                minio_secret_key=minio_secret_key,
                train_image="classify-anomaly:latest",
            )

            # 更新任务状态
            train_job.status = "running"
            train_job.save(update_fields=["status"])

            logger.info(f"训练任务已启动: {job_id}")

            return Response(
                {
                    "message": "训练任务已启动",
                    "job_id": job_id,
                    "train_job_id": train_job.id,
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
    @HasPermission("train_tasks-Stop")
    def stop(self, request, *args, **kwargs):
        """
        停止训练任务
        """
        try:
            train_job = self.get_object()

            # 检查任务状态
            if train_job.status != "running":
                return Response(
                    {"error": "训练任务未在运行中"}, status=status.HTTP_400_BAD_REQUEST
                )

            # 构建训练任务标识
            job_id = mlflow_service.build_job_id(
                prefix=self.MLFLOW_PREFIX,
                algorithm=train_job.algorithm,
                train_job_id=train_job.id,
            )

            logger.info(f"停止训练任务: {job_id}")

            # 调用 WebhookClient 停止任务（默认删除容器）
            result = WebhookClient.stop(job_id)

            # 更新任务状态
            train_job.status = "pending"
            train_job.save(update_fields=["status"])

            logger.info(f"训练任务已停止: {job_id}")

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

    @action(detail=True, methods=["get"], url_path="runs_data_list")
    @HasPermission("train_tasks-View")
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
                        "status": str(run_status),  # RUNNING/FINISHED/FAILED/KILLED
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

            # 同步最新运行状态到 TrainJob（避免状态不一致）
            if latest_run_status and train_job.status == "running":
                status_map = {
                    "FINISHED": "completed",
                    "FAILED": "failed",
                    "KILLED": "failed",
                }
                new_status = status_map.get(latest_run_status)

                if new_status:
                    train_job.status = new_status
                    train_job.save(update_fields=["status"])
                    logger.info(
                        f"自动同步 TrainJob {train_job.id} 状态: running -> {new_status} (基于 MLflow: {latest_run_status})"
                    )

            return Response(
                {
                    "train_job_id": train_job.id,
                    "train_job_name": train_job.name,
                    "algorithm": train_job.algorithm,
                    "job_status": train_job.status,  # 返回当前 TrainJob 状态
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
    @HasPermission("train_tasks-View")
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
    @HasPermission("train_tasks-View")
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

            logger.info(f"返回 {len(metric_data)} 条指标数据")

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
    @HasPermission("train_tasks-View")
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

    @action(detail=True, methods=["get"], url_path="model_versions")
    @HasPermission("train_tasks-View")
    def get_model_versions(self, request, pk=None):
        """
        获取训练任务对应模型的所有版本列表
        """
        try:
            train_job = self.get_object()

            # 构造模型名称
            model_name = mlflow_service.build_model_name(
                prefix=self.MLFLOW_PREFIX,
                algorithm=train_job.algorithm,
                train_job_id=train_job.id,
            )

            # 查询模型版本
            version_data = mlflow_service.get_model_versions(model_name)

            if not version_data:
                logger.info(f"模型未找到版本: {model_name}")
                return Response({"model_name": model_name, "versions": [], "total": 0})

            logger.info(
                f"获取模型版本列表成功: {model_name}, 共 {len(version_data)} 个版本"
            )

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
    @HasPermission("train_tasks-View")
    def download_model(self, request, run_id: str):
        """
        从 MLflow 下载模型并直接返回 ZIP 文件

        简化版本：直接从 MLflow 拉取 artifact → 打包 → 浏览器下载
        """
        from io import BytesIO

        try:
            # 获取 run 信息（用于文件命名）
            run = mlflow_service.get_run_info(run_id)
            run_name = run.data.tags.get("mlflow.runName", run_id)

            # 下载并打包模型
            zip_buffer = mlflow_service.download_model_artifact(run_id)

            # 构建文件名
            filename = f"AnomalyDetection_{run_name}_{run_id[:8]}.zip"

            # 返回文件
            response = FileResponse(
                zip_buffer,
                content_type="application/zip",
                as_attachment=True,
                filename=filename,
            )

            logger.info(f"模型下载请求完成: {filename}")
            return response

        except Exception as e:
            logger.error(f"下载模型失败: {str(e)}", exc_info=True)
            return Response(
                {"error": f"下载模型失败: {str(e)}"},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )

    @HasPermission("train_tasks-View")
    def list(self, request, *args, **kwargs):
        return super().list(request, *args, **kwargs)

    @HasPermission(
        "train_tasks-Add,anomaly_detection_datasets_detail-File View,anomaly_detection_datasets-View"
    )
    def create(self, request, *args, **kwargs):
        return super().create(request, *args, **kwargs)

    @action(detail=True, methods=["get"], url_path="get_file")
    @HasPermission(
        "train_tasks-View,anomaly_detection_datasets_detail-File View,anomaly_detection_datasets-View"
    )
    def get_file(self, request, *args, **kwargs):
        try:
            train_job = self.get_object()
            train_obj = train_job.train_data_id
            val_obj = train_job.val_data_id
            test_obj = train_job.test_data_id

            def mergePoints(data_obj, filename):
                train_data = (
                    list(data_obj.train_data) if hasattr(data_obj, "train_data") else []
                )
                anomlay_indices = (
                    data_obj.metadata.get("anomaly_point", [])
                    if hasattr(data_obj, "metadata")
                    and isinstance(data_obj.metadata, dict)
                    else []
                )

                columns = ["timestamp", "value"]

                if anomlay_indices and isinstance(anomlay_indices, list):
                    for idx, item in enumerate(train_data):
                        item["label"] = 1 if idx in anomlay_indices else 0
                    columns.append("label")

                return {"data": train_data, "columns": columns, "filename": filename}

            return Response(
                [
                    mergePoints(train_obj, "train_file.csv"),
                    mergePoints(val_obj, "val_file.csv"),
                    mergePoints(test_obj, "test_file.csv"),
                    {
                        "data": train_job.hyperopt_config,
                        "columns": [],
                        "filename": "hyperopt_config.json",
                    },
                ]
            )

        except Exception as e:
            logger.error(
                f"获取训练文件失败 - TrainJobID: {kwargs.get('pk')} - {str(e)}"
            )
            return Response(
                {"error": f"获取文件信息失败: {str(e)}"},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
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

    queryset = AnomalyDetectionTrainData.objects.select_related("dataset").all()
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

    queryset = AnomalyDetectionDatasetRelease.objects.select_related("dataset").all()
    serializer_class = AnomalyDetectionDatasetReleaseSerializer
    filterset_class = AnomalyDetectionDatasetReleaseFilter
    pagination_class = CustomPageNumberPagination
    permission_key = "dataset.anomaly_detection_dataset_release"

    @HasPermission("anomaly_detection_dataset_releases-View")
    def list(self, request, *args, **kwargs):
        return super().list(request, *args, **kwargs)

    @HasPermission("anomaly_detection_dataset_releases-View")
    def retrieve(self, request, *args, **kwargs):
        return super().retrieve(request, *args, **kwargs)

    @HasPermission("anomaly_detection_dataset_releases-Delete")
    def destroy(self, request, *args, **kwargs):
        return super().destroy(request, *args, **kwargs)

    @HasPermission("anomaly_detection_dataset_releases-Add")
    def create(self, request, *args, **kwargs):
        return super().create(request, *args, **kwargs)

    @HasPermission("anomaly_detection_dataset_releases-Edit")
    def update(self, request, *args, **kwargs):
        return super().update(request, *args, **kwargs)

    @action(detail=True, methods=["get"], url_path="download")
    @HasPermission("anomaly_detection_dataset_releases-View")
    def download(self, request, *args, **kwargs):
        """
        下载数据集版本的 ZIP 文件
        """
        try:
            release = self.get_object()

            if not release.dataset_file or not release.dataset_file.name:
                return Response(
                    {"error": "数据集文件不存在"}, status=status.HTTP_404_NOT_FOUND
                )

            # 获取文件
            file = release.dataset_file.open("rb")
            filename = f"{release.dataset.name}_{release.version}.zip"

            response = FileResponse(file, content_type="application/zip")
            response["Content-Disposition"] = f'attachment; filename="{filename}"'

            logger.info(f"下载数据集版本: {release.id} - {filename}")

            return response

        except Exception as e:
            logger.error(f"下载数据集失败: {str(e)}", exc_info=True)
            return Response(
                {"error": f"下载失败: {str(e)}"},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )

    @action(detail=True, methods=["post"], url_path="archive")
    @HasPermission("anomaly_detection_datasets-Edit")
    def archive(self, request, *args, **kwargs):
        """
        归档数据集版本(将状态改为 archived)
        """
        try:
            release = self.get_object()

            if release.status == "archived":
                return Response(
                    {"error": "数据集版本已处于归档状态"},
                    status=status.HTTP_400_BAD_REQUEST,
                )

            release.status = "archived"
            release.description = f"[已归档] {release.description or ''}"
            release.save(update_fields=["status", "description"])

            logger.info(f"归档数据集版本: {release.id}")

            return Response({"message": "归档成功", "release_id": release.id})

        except Exception as e:
            logger.error(f"归档失败: {str(e)}", exc_info=True)
            return Response(
                {"error": f"归档失败: {str(e)}"},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )

    @action(detail=True, methods=["post"], url_path="unarchive")
    @HasPermission("anomaly_detection_datasets-Edit")
    def unarchive(self, request, *args, **kwargs):
        """
        恢复已归档的数据集版本(将状态改为 published)
        """
        try:
            release = self.get_object()

            if release.status != "archived":
                return Response(
                    {"error": "只能恢复已归档的数据集版本"},
                    status=status.HTTP_400_BAD_REQUEST,
                )

            # 移除归档标记
            original_description = release.description or ""
            if original_description.startswith("[已归档] "):
                release.description = original_description.replace("[已归档] ", "", 1)

            release.status = "published"
            release.save(update_fields=["status", "description"])

            logger.info(
                f"恢复数据集版本: {release.id} - {release.dataset.name} {release.version}"
            )

            return Response(
                {
                    "message": "恢复成功",
                    "release_id": release.id,
                    "status": release.status,
                }
            )

        except Exception as e:
            logger.error(f"恢复失败: {str(e)}", exc_info=True)
            return Response(
                {"error": f"恢复失败: {str(e)}"},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )


class AnomalyDetectionServingViewSet(ModelViewSet):
    queryset = AnomalyDetectionServing.objects.select_related(
        "train_job", "train_job__dataset_version", "train_job__dataset_version__dataset"
    ).all()
    serializer_class = AnomalyDetectionServingSerializer
    filterset_class = AnomalyDetectionServingFilter
    pagination_class = CustomPageNumberPagination
    permission_key = "serving.anomaly_detection_serving"

    MLFLOW_PREFIX = "AnomalyDetection"  # MLflow 命名前缀

    @HasPermission("model_release-View")
    def list(self, request, *args, **kwargs):
        """列表查询，实时同步容器状态"""
        response = super().list(request, *args, **kwargs)

        if isinstance(response.data, dict):
            servings = response.data.get("items", [])
        else:
            servings = response.data

        if not servings:
            return response

        serving_ids = [f"AnomalyDetection_Serving_{s['id']}" for s in servings]

        try:
            # 批量查询
            result = WebhookClient.get_status(serving_ids)
            status_map = {s.get("id"): s for s in result}

            updates = []
            for serving_data in servings:
                serving_id = f"AnomalyDetection_Serving_{serving_data['id']}"
                container_info = status_map.get(serving_id)

                if container_info:
                    # 直接使用 webhookd 响应
                    serving_data["container_info"] = container_info

                    # 同步到数据库
                    serving_obj = AnomalyDetectionServing.objects.get(
                        id=serving_data["id"]
                    )
                    serving_obj.container_info = container_info
                    updates.append(serving_obj)
                else:
                    # webhookd 没返回这个容器的状态（不应该发生）
                    serving_data["container_info"] = {
                        "status": "error",
                        "state": "unknown",
                        "message": "webhookd 未返回此容器状态",
                    }

            if updates:
                AnomalyDetectionServing.objects.bulk_update(updates, ["container_info"])

        except WebhookError as e:
            logger.error(f"查询容器状态失败: {e}")
            # 降级：使用数据库中的旧值，添加错误标记
            for serving_data in servings:
                old_info = serving_data.get("container_info") or {}
                serving_data["container_info"] = {
                    **old_info,
                    "status": "error",
                    "_query_failed": True,
                    "_error": str(e),
                }

        return response

    @HasPermission("model_release-View")
    def retrieve(self, request, *args, **kwargs):
        """详情查询，实时同步容器状态"""
        response = super().retrieve(request, *args, **kwargs)

        serving_id = f"AnomalyDetection_Serving_{response.data['id']}"

        try:
            result = WebhookClient.get_status([serving_id])
            container_info = result[0] if result else None

            if container_info:
                # 直接使用 webhookd 响应
                response.data["container_info"] = container_info

                # 更新数据库
                AnomalyDetectionServing.objects.filter(id=response.data["id"]).update(
                    container_info=container_info
                )
            else:
                # webhookd 没返回状态
                response.data["container_info"] = {
                    "status": "error",
                    "state": "unknown",
                    "message": "webhookd 未返回容器状态",
                }

        except WebhookError as e:
            logger.error(f"查询容器状态失败: {e}")
            # 降级：使用数据库中的旧值，添加错误标记
            old_info = response.data.get("container_info") or {}
            response.data["container_info"] = {
                **old_info,
                "status": "error",
                "_query_failed": True,
                "_error": str(e),
            }

        return response

    @HasPermission("model_release-Delete")
    def destroy(self, request, *args, **kwargs):
        return super().destroy(request, *args, **kwargs)

    @HasPermission("model_release-Add,train_tasks-View")
    def create(self, request, *args, **kwargs):
        """
        创建 serving 服务并自动启动容器
        """
        # 创建 serving 记录（初始状态为 inactive）
        response = super().create(request, *args, **kwargs)
        serving_id = response.data["id"]

        try:
            # 获取创建的 serving 对象
            serving = AnomalyDetectionServing.objects.get(id=serving_id)

            # 获取环境变量
            mlflow_tracking_uri = os.getenv("MLFLOW_TRACKER_URL", "")
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
            container_id = f"AnomalyDetection_Serving_{serving.id}"

            logger.info(
                f"自动启动 serving 服务: {container_id}, Model URI: {model_uri}, Port: {serving.port or 'auto'}"
            )

            try:
                # 调用 WebhookClient 启动服务
                result = WebhookClient.serve(
                    container_id,
                    mlflow_tracking_uri,
                    model_uri,
                    port=serving.port,
                    train_image="classify-anomaly:latest",
                )

                # 启动成功，仅更新容器信息
                serving.container_info = result
                serving.save(update_fields=["container_info"])

                logger.info(
                    f"Serving 服务已自动启动: {container_id}, Port: {result.get('port')}"
                )

                # 更新返回数据（status 由用户控制，不修改）
                response.data["container_info"] = result
                response.data["message"] = "服务已创建并启动"

            except WebhookError as e:
                error_msg = str(e)
                logger.error(f"自动启动 serving 失败: {error_msg}")

                # 处理容器已存在的情况（同步容器状态）
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

                        # 仅更新容器信息，不修改 status
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
                    # 其他错误
                    serving.container_info = {"status": "error", "message": error_msg}
                    serving.save(update_fields=["container_info"])
                    response.data["container_info"] = serving.container_info
                    response.data["message"] = f"服务已创建但启动失败: {error_msg}"

        except Exception as e:
            logger.error(f"自动启动 serving 异常: {str(e)}", exc_info=True)
            # 确保至少有基本的错误信息
            response.data["message"] = f"服务已创建但启动异常: {str(e)}"

        return response

    @HasPermission("model_release-Update")
    def update(self, request, *args, **kwargs):
        """
        更新 serving 配置，自动检测并重启容器

        基于实际容器运行状态决策：
        - 容器 running + 配置变更 → 自动重启
        - 容器非 running → 仅更新数据库，用户自行决定是否启动
        """
        instance = self.get_object()

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

        container_id = f"AnomalyDetection_Serving_{instance.id}"

        # 获取容器实际状态（更新前）
        container_state = instance.container_info.get("state")
        container_port = instance.container_info.get("port")

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
                logger.info(f"配置变更需要重启，删除旧容器: {container_id}")
                WebhookClient.remove(container_id)
                logger.info(f"旧容器已删除: {container_id}")
            except WebhookError as e:
                logger.warning(f"删除旧容器失败（可能已不存在）: {e}")
                # 继续执行，尝试启动新容器

            try:
                # 获取环境变量
                mlflow_tracking_uri = os.getenv("MLFLOW_TRACKER_URL", "")
                if not mlflow_tracking_uri:
                    raise ValueError("环境变量 MLFLOW_TRACKER_URL 未配置")

                # 解析新的 model_uri
                model_uri = self._resolve_model_uri(instance)

                logger.info(
                    f"使用新配置启动容器: {container_id}, Model URI: {model_uri}, Port: {instance.port or 'auto'}"
                )

                # 启动新容器
                result = WebhookClient.serve(
                    container_id,
                    mlflow_tracking_uri,
                    model_uri,
                    port=instance.port,
                    train_image="classify-anomaly:latest",
                )

                # 更新容器信息（status 由用户控制，不修改）
                instance.container_info = result
                instance.save(update_fields=["container_info"])

                logger.info(f"新容器已启动: {container_id}, Port: {result.get('port')}")

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
    @HasPermission("model_release-Start")
    def start(self, request, *args, **kwargs):
        """
        启动 serving 服务
        """
        try:
            serving = self.get_object()

            # 获取环境变量
            mlflow_tracking_uri = os.getenv("MLFLOW_TRACKER_URL", "")
            if not mlflow_tracking_uri:
                return Response(
                    {"error": "环境变量 MLFLOW_TRACKER_URL 未配置"},
                    status=status.HTTP_500_INTERNAL_SERVER_ERROR,
                )

            # 解析 model_uri
            try:
                model_uri = self._resolve_model_uri(serving)
            except ValueError as e:
                return Response({"error": str(e)}, status=status.HTTP_400_BAD_REQUEST)

            # 构建 serving ID
            serving_id = f"AnomalyDetection_Serving_{serving.id}"

            logger.info(
                f"启动 serving 服务: {serving_id}, Model URI: {model_uri}, Port: {serving.port or 'auto'}"
            )

            try:
                # 调用 WebhookClient 启动服务
                result = WebhookClient.serve(
                    serving_id,
                    mlflow_tracking_uri,
                    model_uri,
                    port=serving.port,
                    train_image="classify-anomaly:latest",
                )

                # 正常启动成功，仅更新容器信息
                serving.container_info = result
                serving.save(update_fields=["container_info"])

                logger.info(
                    f"Serving 服务已启动: {serving_id}, Port: {result.get('port')}"
                )

                return Response(
                    {
                        "message": "服务已启动",
                        "serving_id": serving_id,
                        "container_info": result,
                    }
                )

            except WebhookError as e:
                error_msg = str(e)

                # 处理容器已存在的情况
                if e.code == "CONTAINER_ALREADY_EXISTS":
                    logger.warning(f"检测到容器已存在，同步容器信息: {serving_id}")
                    try:
                        # 查询当前容器状态
                        result = WebhookClient.get_status([serving_id])
                        container_info = (
                            result[0]
                            if result
                            else {
                                "status": "error",
                                "id": serving_id,
                                "message": "无法查询容器状态",
                            }
                        )

                        # 仅更新容器信息，不修改 status
                        serving.container_info = container_info
                        serving.save(update_fields=["container_info"])

                        logger.info(f"容器信息已同步: {container_info.get('state')}")

                        return Response(
                            {
                                "message": "检测到容器已存在，已同步容器信息",
                                "container_info": container_info,
                                "warning": "容器已存在",
                            }
                        )
                    except WebhookError as sync_error:
                        logger.error(f"同步容器状态失败: {sync_error}")
                        return Response(
                            {"error": f"容器已存在但同步状态失败: {sync_error}"},
                            status=status.HTTP_500_INTERNAL_SERVER_ERROR,
                        )
                else:
                    # 其他错误直接返回
                    logger.error(f"启动 serving 失败: {error_msg}")
                    return Response(
                        {"error": error_msg},
                        status=status.HTTP_500_INTERNAL_SERVER_ERROR,
                    )

        except WebhookTimeoutError as e:
            return Response(
                {"error": str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )
        except WebhookConnectionError as e:
            return Response(
                {"error": str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )
        except Exception as e:
            logger.error(f"启动 serving 服务失败: {str(e)}", exc_info=True)
            return Response(
                {"error": f"启动服务失败: {str(e)}"},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )

    @action(detail=True, methods=["post"], url_path="stop")
    @HasPermission("model_release-Stop")
    def stop(self, request, *args, **kwargs):
        """
        停止 serving 服务（停止并删除容器）
        """
        try:
            serving = self.get_object()

            # 构建 serving ID
            serving_id = f"AnomalyDetection_Serving_{serving.id}"

            logger.info(f"停止 serving 服务: {serving_id}")

            # 调用 WebhookClient 停止服务（默认删除容器）
            result = WebhookClient.stop(serving_id)

            logger.info(f"Serving 服务已停止: {serving_id}")

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
            logger.error(f"停止 serving 服务失败: {str(e)}", exc_info=True)
            return Response(
                {"error": f"停止服务失败: {str(e)}"},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )

    @action(detail=True, methods=["post"], url_path="remove")
    @HasPermission("model_release-Remove")
    def remove(self, request, *args, **kwargs):
        """
        删除 serving 容器（可处理运行中的容器）
        """
        try:
            serving = self.get_object()

            # 构建 serving ID
            serving_id = f"AnomalyDetection_Serving_{serving.id}"

            logger.info(f"删除 serving 容器: {serving_id}")

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

            logger.info(f"Serving 容器已删除: {serving_id}")

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
            logger.error(f"删除 serving 容器失败: {str(e)}", exc_info=True)
            return Response(
                {"error": f"删除容器失败: {str(e)}"},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )

    @action(detail=True, methods=["post"], url_path="predict")
    @HasPermission("model_release-Predict")
    def predict(self, request, *args, **kwargs):
        """
        调用 serving 服务进行异常检测

        URL: POST /api/v1/mlops/anomaly_detection_servings/{pk}/predict/

        请求参数:
            url: 预测服务主机地址（如 http://192.168.1.100，不含端口）
            data: 历史时间序列数据数组 [{"timestamp": "...", "value": ...}, ...]

        返回格式:
            预测服务的响应（通常为 {"success": true, "data": [...], "metadata": {...}, "error": null}）
        """
        try:
            serving = self.get_object()

            # 获取参数
            url = request.data.get("url")
            data = request.data.get("data")

            # 参数校验
            if not url:
                return Response(
                    {"error": "url 参数不能为空"}, status=status.HTTP_400_BAD_REQUEST
                )

            if not data:
                return Response(
                    {"error": "data 参数不能为空"}, status=status.HTTP_400_BAD_REQUEST
                )

            if not isinstance(data, list):
                return Response(
                    {"error": "data 必须是数组格式"}, status=status.HTTP_400_BAD_REQUEST
                )

            # 获取实际运行端口
            port = serving.container_info.get("port")
            if not port:
                return Response(
                    {"error": "服务端口未配置，请确认服务已启动"},
                    status=status.HTTP_400_BAD_REQUEST,
                )

            # 构建预测服务 URL
            # url: http://192.168.1.100 + port: 38291 -> http://192.168.1.100:38291/predict
            predict_url = f"{url.rstrip('/')}:{port}/predict"

            # 构建请求体
            payload = {"data": data}

            logger.info(
                f"调用预测服务: serving_id={serving.id}, url={predict_url}, data_size={len(data)}"
            )

            # 发起 HTTP POST 请求
            response = requests.post(
                predict_url,
                json=payload,
                timeout=60,
                headers={"Content-Type": "application/json"},
            )

            # 处理响应
            if response.status_code == 200:
                result = response.json()

                # 检查业务层面的 success 状态
                if result.get("success") is False:
                    # 预测服务返回失败
                    error_info = result.get("error") or {}
                    error_code = error_info.get("code", "UNKNOWN")
                    error_message = error_info.get("message", "预测失败")

                    logger.error(
                        f"预测服务返回失败: serving_id={serving.id}, code={error_code}, message={error_message}"
                    )
                    return Response(
                        {
                            "error": error_message,
                            "error_code": error_code,
                            "details": error_info.get("details"),
                        },
                        status=status.HTTP_400_BAD_REQUEST,
                    )

                # 预测成功
                predictions = result.get("data") or []
                prediction_size = (
                    len(predictions) if isinstance(predictions, (list, tuple)) else 0
                )
                logger.info(
                    f"预测成功: serving_id={serving.id}, prediction_size={prediction_size}"
                )
                return Response(result)
            else:
                error_msg = f"预测服务返回错误: HTTP {response.status_code}"
                try:
                    error_detail = response.json()
                    error_msg = f"{error_msg} - {error_detail}"
                except Exception:
                    error_msg = f"{error_msg} - {response.text[:200]}"

                logger.error(f"预测失败: {error_msg}")
                return Response(
                    {"error": error_msg}, status=status.HTTP_500_INTERNAL_SERVER_ERROR
                )

        except requests.exceptions.Timeout:
            error_msg = f"预测请求超时（超过 60 秒）"
            logger.error(f"预测超时: serving_id={serving.id}, url={predict_url}")
            return Response(
                {"error": error_msg}, status=status.HTTP_504_GATEWAY_TIMEOUT
            )
        except requests.exceptions.ConnectionError as e:
            error_msg = f"无法连接预测服务: {str(e)}"
            logger.error(
                f"预测连接失败: serving_id={serving.id}, url={predict_url}, error={e}"
            )
            return Response(
                {"error": error_msg}, status=status.HTTP_503_SERVICE_UNAVAILABLE
            )
        except requests.exceptions.RequestException as e:
            error_msg = f"预测请求异常: {str(e)}"
            logger.error(
                f"预测请求异常: serving_id={serving.id}, error={e}", exc_info=True
            )
            return Response(
                {"error": error_msg}, status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )
        except Exception as e:
            logger.error(
                f"预测失败: serving_id={serving.id}, error={str(e)}", exc_info=True
            )
            return Response(
                {"error": f"预测失败: {str(e)}"},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )

    def _resolve_model_uri(self, serving):
        """
        解析 MLflow Model URI

        Args:
            serving: AnomalyDetectionServing 实例

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
