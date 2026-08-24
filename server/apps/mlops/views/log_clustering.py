import json
import os

import numpy as np
import pandas as pd
import requests
from django.http import FileResponse
from rest_framework import status
from rest_framework.decorators import action
from rest_framework.response import Response

from apps.core.decorators.api_permission import HasPermission
from apps.core.logger import mlops_logger as logger
from apps.mlops.constants import DatasetReleaseStatus, MLflowRunStatus, TrainJobStatus
from apps.mlops.filters.algorithm_config import AlgorithmConfigFilter
from apps.mlops.filters.log_clustering import (
    LogClusteringDatasetFilter,
    LogClusteringDatasetReleaseFilter,
    LogClusteringServingFilter,
    LogClusteringTrainDataFilter,
    LogClusteringTrainJobFilter,
)
from apps.mlops.models import AlgorithmConfig
from apps.mlops.models.log_clustering import (
    LogClusteringDataset,
    LogClusteringDatasetRelease,
    LogClusteringServing,
    LogClusteringTrainData,
    LogClusteringTrainJob,
)
from apps.mlops.predict_url_builder import build_predict_url
from apps.mlops.serializers.algorithm_config import AlgorithmConfigListSerializer, AlgorithmConfigSerializer
from apps.mlops.serializers.log_clustering import (
    LogClusteringDatasetReleaseSerializer,
    LogClusteringDatasetSerializer,
    LogClusteringServingSerializer,
    LogClusteringTrainDataSerializer,
    LogClusteringTrainJobSerializer,
)
from apps.mlops.services import ConfigurationError, get_image_by_prefix, get_mlflow_tracking_uri, get_mlflow_train_config
from apps.mlops.utils import mlflow_service
from apps.mlops.utils.group_scope import filter_queryset_by_parent_team
from apps.mlops.utils.i18n import mlops_exception_message, mlops_message
from apps.mlops.utils.webhook_client import WebhookClient, WebhookConnectionError, WebhookError, WebhookTimeoutError
from apps.mlops.views.base import BaseTrainJobViewSet, TeamModelViewSet
from config.drf.pagination import CustomPageNumberPagination
from config.drf.viewsets import ModelViewSet


class LogClusteringDatasetViewSet(TeamModelViewSet):
    queryset = LogClusteringDataset.objects.all()
    serializer_class = LogClusteringDatasetSerializer
    pagination_class = CustomPageNumberPagination
    filterset_class = LogClusteringDatasetFilter
    ordering = ("-id",)
    permission_key = "dataset.log_clustering_dataset"

    @HasPermission("log_clustering-View")
    def list(self, request, *args, **kwargs):
        return super().list(request, *args, **kwargs)

    @HasPermission("log_clustering-View")
    def retrieve(self, request, *args, **kwargs):
        return super().retrieve(request, *args, **kwargs)

    @HasPermission("log_clustering-Delete")
    def destroy(self, request, *args, **kwargs):
        return super().destroy(request, *args, **kwargs)

    @HasPermission("log_clustering-Add")
    def create(self, request, *args, **kwargs):
        return super().create(request, *args, **kwargs)

    @HasPermission("log_clustering-Edit")
    def update(self, request, *args, **kwargs):
        return super().update(request, *args, **kwargs)


class LogClusteringTrainJobViewSet(BaseTrainJobViewSet):
    queryset = LogClusteringTrainJob.objects.select_related("dataset_version", "dataset_version__dataset").all()
    serializer_class = LogClusteringTrainJobSerializer
    pagination_class = CustomPageNumberPagination
    filterset_class = LogClusteringTrainJobFilter
    ordering = ("-id",)
    permission_key = "train_job.log_clustering_train_job"

    MLFLOW_PREFIX = "LogClustering"  # MLflow 命名前缀

    @HasPermission("log_clustering-View")
    def list(self, request, *args, **kwargs):
        return super().list(request, *args, **kwargs)

    @HasPermission("log_clustering-View")
    def retrieve(self, request, *args, **kwargs):
        return super().retrieve(request, *args, **kwargs)

    @HasPermission("log_clustering-Delete")
    def destroy(self, request, *args, **kwargs):
        return self.destroy_train_job_with_runtime_cleanup(request, *args, **kwargs)

    @HasPermission("log_clustering-Add")
    def create(self, request, *args, **kwargs):
        return super().create(request, *args, **kwargs)

    @HasPermission("log_clustering-Edit")
    def update(self, request, *args, **kwargs):
        return super().update(request, *args, **kwargs)

    @action(detail=True, methods=["post"], url_path="train")
    @HasPermission("log_clustering-Train")
    def train(self, request, pk=None):
        """
        启动训练任务
        """
        train_job = None
        previous_status = None
        try:
            train_job = self.get_object()

            # 检查任务状态
            if train_job.status == TrainJobStatus.RUNNING:
                return Response({"error": mlops_message(request, "error.training_task_already_running")}, status=status.HTTP_400_BAD_REQUEST)

            # 获取训练配置
            try:
                config = get_mlflow_train_config()
            except ConfigurationError as e:
                logger.error(str(e))
                return Response(
                    {"error": mlops_message(request, "error.system_configuration_error")},
                    status=status.HTTP_500_INTERNAL_SERVER_ERROR,
                )

            # 检查必要字段
            if not train_job.dataset_version or not train_job.dataset_version.dataset_file:
                return Response({"error": mlops_message(request, "error.dataset_file_not_found")}, status=status.HTTP_400_BAD_REQUEST)

            if not train_job.config_url:
                return Response({"error": mlops_message(request, "error.training_config_file_not_found")}, status=status.HTTP_400_BAD_REQUEST)

            scope_error = self.ensure_train_job_dataset_scope(request, train_job)
            if scope_error is not None:
                return scope_error

            # 构建训练任务标识
            job_id = mlflow_service.build_job_id(
                prefix=self.MLFLOW_PREFIX,
                algorithm=train_job.algorithm,
                train_job_id=train_job.id,
            )

            # 动态获取训练镜像
            train_image = get_image_by_prefix(self.MLFLOW_PREFIX, train_job.algorithm)

            # 获取当前 run 数量（在容器启动前查询，避免读到新 run 导致 off-by-one）
            from apps.mlops.tasks.poll_train_job_status import poll_train_job_status

            expected_run_count = 0
            try:
                experiment_name = mlflow_service.build_experiment_name(
                    prefix=self.MLFLOW_PREFIX,
                    algorithm=train_job.algorithm,
                    train_job_id=train_job.id,
                )
                experiment = mlflow_service.get_experiment_by_name(experiment_name)
                current_run_count = 0
                if experiment:
                    runs = mlflow_service.get_experiment_runs(experiment.experiment_id)
                    current_run_count = len(runs) if not runs.empty else 0
                expected_run_count = current_run_count + 1
            except Exception:
                logger.warning(f"查询 MLflow run 数量失败，降级 expected_run_count=0, TrainJob ID={train_job.id}")

            previous_status = self.claim_train_job_running(train_job)
            if previous_status is None:
                return Response({"error": mlops_message(request, "error.training_task_already_running")}, status=status.HTTP_400_BAD_REQUEST)

            # 启动前清理可能残留的旧训练容器
            try:
                WebhookClient.stop(job_id)
                logger.info(f"已清理残留的旧训练容器: job_id={job_id}")
            except (WebhookError, WebhookConnectionError, WebhookTimeoutError):
                pass  # 容器不存在是正常的

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
            )

            # 启动异步轮询训练状态
            logger.info(f"触发轮询任务: TrainJob ID={train_job.id}, 预期 run 数量: {expected_run_count}")
            poll_train_job_status.delay(train_job.id, self.MLFLOW_PREFIX, expected_run_count)

            return Response(
                {
                    "message": mlops_message(request, "message.training_task_started"),
                    "job_id": job_id,
                    "train_job_id": train_job.id,
                }
            )

        except WebhookTimeoutError as e:
            if train_job and previous_status is not None:
                self.restore_train_job_status(train_job, previous_status)
            return Response({"error": mlops_exception_message(request, e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
        except WebhookConnectionError as e:
            if train_job and previous_status is not None:
                self.restore_train_job_status(train_job, previous_status)
            return Response({"error": mlops_exception_message(request, e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
        except WebhookError as e:
            if train_job and previous_status is not None:
                self.restore_train_job_status(train_job, previous_status)
            logger.error(f"启动训练任务失败: {e}")
            return Response({"error": mlops_exception_message(request, e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
        except Exception as e:
            if train_job and previous_status is not None:
                self.restore_train_job_status(train_job, previous_status)
            logger.error(f"启动训练任务失败: {str(e)}", exc_info=True)
            return Response(
                {"error": mlops_message(request, "error.training_task_start_failed", detail=mlops_exception_message(request, e))},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )

    @action(detail=True, methods=["post"], url_path="stop")
    @HasPermission("log_clustering-Stop")
    def stop(self, request, *args, **kwargs):
        """
        停止训练任务
        """
        try:
            train_job = self.get_object()

            # 检查任务状态
            if train_job.status != TrainJobStatus.RUNNING:
                return Response({"error": mlops_message(request, "error.training_task_not_running")}, status=status.HTTP_400_BAD_REQUEST)

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
                    "message": mlops_message(request, "message.training_task_stopped"),
                    "job_id": job_id,
                    "webhook_response": result,
                }
            )

        except WebhookError as e:
            logger.error(f"停止训练任务失败: {e}")
            return Response({"error": mlops_exception_message(request, e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
        except Exception as e:
            logger.error(f"停止训练任务失败: {str(e)}", exc_info=True)
            return Response(
                {"error": mlops_message(request, "error.training_task_stop_failed", detail=mlops_exception_message(request, e))},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )

    @action(detail=True, methods=["get"], url_path="runs_data_list")
    @HasPermission("log_clustering-View")
    def get_run_data_list(self, request, pk=None):
        """
        获取训练任务的所有 MLflow 运行记录
        """
        try:
            pagination = self.parse_run_list_pagination(request)
            if pagination is None:
                return Response({"error": mlops_message(request, "error.pagination_must_be_positive_integer")}, status=status.HTTP_400_BAD_REQUEST)
            page, page_size, use_pagination = pagination

            train_job = self.get_object()

            # 构造实验名称
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
                        "message": mlops_message(request, "message.mlflow_experiment_not_found"),
                        "count": 0,
                        "items": [],
                    }
                )

            # 查找该实验中的所有运行
            runs = mlflow_service.get_experiment_runs(experiment.experiment_id)

            if runs.empty:
                return Response(
                    {
                        "train_job_id": train_job.id,
                        "train_job_name": train_job.name,
                        "algorithm": train_job.algorithm,
                        "job_status": train_job.status,
                        "message": mlops_message(request, "message.training_run_not_found"),
                        "count": 0,
                        "items": [],
                    }
                )

            # 每次运行信息的耗时和名称
            run_datas = []

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
                    run_status = row.get("status", MLflowRunStatus.UNKNOWN)

                    run_data = {
                        "run_id": str(row["run_id"]),
                        "run_name": str(run_name),
                        "status": str(run_status),  # RUNNING/FINISHED/FAILED/KILLED
                        "start_time": start_time.isoformat() if pd.notna(start_time) else None,
                        "end_time": end_time.isoformat() if pd.notna(end_time) else None,
                        "duration_minutes": float(duration_minutes) if np.isfinite(duration_minutes) else 0,
                    }
                    run_datas.append(run_data)

                except Exception as e:
                    logger.warning(f"解析 run 数据失败: {e}")
                    continue

            # 标注 run 删除资格
            self.annotate_run_delete_eligibility(run_datas, train_job.status)

            # 分页处理
            total_count = len(run_datas)
            if use_pagination:
                start_idx = (page - 1) * page_size
                end_idx = start_idx + page_size
                paginated_data = run_datas[start_idx:end_idx]
            else:
                paginated_data = run_datas

            return Response(
                {
                    "train_job_id": train_job.id,
                    "train_job_name": train_job.name,
                    "algorithm": train_job.algorithm,
                    "job_status": train_job.status,
                    "count": total_count,
                    "items": paginated_data,
                }
            )
        except Exception as e:
            logger.error(f"获取训练记录列表失败: {str(e)}", exc_info=True)
            return Response(
                {"error": mlops_message(request, "error.training_records_fetch_failed", detail=str(e))},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )

    @action(detail=True, methods=["delete"], url_path="runs/(?P<run_id>[^/]+)")
    @HasPermission("log_clustering-Delete")
    def delete_run(self, request, pk=None, run_id=None):
        return super().delete_run(request, pk=pk, run_id=run_id)

    @action(detail=True, methods=["get"], url_path="runs/(?P<run_id>[^/]+)/metrics_list")
    @HasPermission("log_clustering-View")
    def get_runs_metrics_list(self, request, pk=None, run_id: str = ""):
        """
        获取指定 run 的 Model 指标列表（过滤掉 System 指标）
        """
        try:
            train_job = self.get_authorized_object_or_none()
            if train_job is None:
                return self.run_not_found_response(run_id)
            if not self.train_job_has_run(train_job, run_id):
                return self.run_not_found_response(run_id)

            # 获取运行的指标列表（过滤系统指标）
            model_metrics = mlflow_service.get_run_metrics(run_id=run_id, filter_system=True)

            return Response({"run_id": run_id, "metrics": model_metrics})

        except Exception as e:
            logger.error(f"获取指标列表失败: {str(e)}", exc_info=True)
            return Response(
                {"error": mlops_message(request, "error.metrics_list_fetch_failed", detail=str(e))},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )

    @action(
        detail=True,
        methods=["get"],
        url_path="runs/(?P<run_id>[^/]+)/metrics_history/(?P<metric_name>.+?)",
    )
    @HasPermission("log_clustering-View")
    def get_metric_data(self, request, pk=None, run_id: str = "", metric_name: str = ""):
        return super().get_metric_data(request, pk=pk, run_id=run_id, metric_name=metric_name)

    @action(detail=True, methods=["get"], url_path="runs/(?P<run_id>[^/]+)/run_params")
    @HasPermission("log_clustering-View")
    def get_run_params(self, request, pk=None, run_id: str = ""):
        return super().get_run_params(request, pk=pk, run_id=run_id)

    @action(detail=True, methods=["get"], url_path="model_versions")
    @HasPermission("log_clustering-View")
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
                {"error": mlops_message(request, "error.model_versions_fetch_failed", detail=str(e))},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )

    @action(detail=True, methods=["get"], url_path="runs/(?P<run_id>[^/]+)/download_model")
    @HasPermission("log_clustering-View")
    def download_model(self, request, pk=None, run_id: str = ""):
        """
        从 MLflow 下载模型并直接返回 ZIP 文件

        简化版本：直接从 MLflow 拉取 artifact → 打包 → 浏览器下载
        """
        try:
            train_job = self.get_authorized_object_or_none()
            if train_job is None:
                return self.run_not_found_response(run_id)
            if not self.train_job_has_run(train_job, run_id):
                return self.run_not_found_response(run_id)

            # 获取 run 信息（用于文件命名）
            run = mlflow_service.get_run_info(run_id)
            run_name = run.data.tags.get("mlflow.runName", run_id)

            # 下载并打包模型
            zip_buffer = mlflow_service.download_model_artifact(run_id)

            # 构造文件名
            safe_run_name = "".join(c if c.isalnum() or c in ("-", "_") else "_" for c in run_name)
            filename = f"mlflow_model_{safe_run_name}_{run_id[:8]}.zip"

            # 返回文件响应
            response = mlflow_service.build_model_download_response(zip_buffer, filename)

            logger.info(f"模型下载完成 [run_id: {run_id}, filename: {filename}]")
            return response

        except Exception as e:
            logger.error(f"下载模型失败: {str(e)}", exc_info=True)
            return Response(
                {"error": mlops_message(request, "error.model_download_failed", detail=str(e))},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )


class LogClusteringDatasetReleaseViewSet(ModelViewSet):
    queryset = LogClusteringDatasetRelease.objects.select_related("dataset").all()
    serializer_class = LogClusteringDatasetReleaseSerializer
    pagination_class = CustomPageNumberPagination
    filterset_class = LogClusteringDatasetReleaseFilter
    ordering = ("-id",)
    permission_key = "dataset.log_clustering_dataset_release"

    def get_queryset(self):
        return filter_queryset_by_parent_team(super().get_queryset(), self.request, "dataset__team")

    @HasPermission("log_clustering-View")
    def list(self, request, *args, **kwargs):
        return super().list(request, *args, **kwargs)

    @HasPermission("log_clustering-View")
    def retrieve(self, request, *args, **kwargs):
        return super().retrieve(request, *args, **kwargs)

    @HasPermission("log_clustering-Delete")
    def destroy(self, request, *args, **kwargs):
        return super().destroy(request, *args, **kwargs)

    @HasPermission("log_clustering-Add")
    def create(self, request, *args, **kwargs):
        return super().create(request, *args, **kwargs)

    @HasPermission("log_clustering-Edit")
    def update(self, request, *args, **kwargs):
        return super().update(request, *args, **kwargs)

    @action(detail=True, methods=["get"], url_path="download")
    @HasPermission("log_clustering-View")
    def download(self, request, *args, **kwargs):
        """
        下载数据集版本的 ZIP 文件
        """
        try:
            release = self.get_object()

            if not release.dataset_file or not release.dataset_file.name:
                return Response({"error": mlops_message(request, "error.dataset_file_not_found")}, status=status.HTTP_404_NOT_FOUND)

            # 获取文件
            file = release.dataset_file.open("rb")
            filename = f"{release.dataset.name}_{release.version}.zip"

            response = FileResponse(file, content_type="application/zip")
            response["Content-Disposition"] = f'attachment; filename="{filename}"'

            return response

        except Exception as e:
            logger.error(f"下载数据集失败: {str(e)}", exc_info=True)
            return Response(
                {"error": mlops_message(request, "error.dataset_download_failed", detail=str(e))},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )

    @action(detail=True, methods=["post"], url_path="archive")
    @HasPermission("log_clustering-Edit")
    def archive(self, request, *args, **kwargs):
        """
        归档数据集版本(将状态改为 archived)
        """
        try:
            release = self.get_object()

            if release.status == DatasetReleaseStatus.ARCHIVED:
                return Response(
                    {"error": mlops_message(request, "error.dataset_release_already_archived")},
                    status=status.HTTP_400_BAD_REQUEST,
                )

            release.status = DatasetReleaseStatus.ARCHIVED
            release.description = f"[已归档] {release.description or ''}"
            release.save(update_fields=["status", "description"])

            return Response({"message": mlops_message(request, "message.archive_success"), "release_id": release.id})

        except Exception as e:
            logger.error(f"归档失败: {str(e)}", exc_info=True)
            return Response(
                {"error": mlops_message(request, "error.dataset_release_archive_failed", detail=str(e))},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )

    @action(detail=True, methods=["post"], url_path="unarchive")
    @HasPermission("log_clustering-Edit")
    def unarchive(self, request, *args, **kwargs):
        """
        恢复已归档的数据集版本(将状态改为 published)
        """
        try:
            release = self.get_object()

            if release.status != DatasetReleaseStatus.ARCHIVED:
                return Response(
                    {"error": mlops_message(request, "error.dataset_release_not_archived")},
                    status=status.HTTP_400_BAD_REQUEST,
                )

            # 移除归档标记
            original_description = release.description or ""
            if original_description.startswith("[已归档] "):
                release.description = original_description.replace("[已归档] ", "", 1)

            release.status = DatasetReleaseStatus.PUBLISHED
            release.save(update_fields=["status", "description"])

            return Response({"message": mlops_message(request, "message.unarchive_success"), "release_id": release.id})

        except Exception as e:
            logger.error(f"恢复失败: {str(e)}", exc_info=True)
            return Response(
                {"error": mlops_message(request, "error.dataset_release_unarchive_failed", detail=str(e))},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )


class LogClusteringTrainDataViewSet(ModelViewSet):
    queryset = LogClusteringTrainData.objects.select_related("dataset").all()
    serializer_class = LogClusteringTrainDataSerializer
    pagination_class = CustomPageNumberPagination
    filterset_class = LogClusteringTrainDataFilter
    ordering = ("-id",)
    permission_key = "dataset.log_clustering_train_data"

    def get_queryset(self):
        return filter_queryset_by_parent_team(super().get_queryset(), self.request, "dataset__team")

    @HasPermission("log_clustering-View")
    def list(self, request, *args, **kwargs):
        return super().list(request, *args, **kwargs)

    @HasPermission("log_clustering-View")
    def retrieve(self, request, *args, **kwargs):
        return super().retrieve(request, *args, **kwargs)

    @HasPermission("log_clustering-Delete")
    def destroy(self, request, *args, **kwargs):
        return super().destroy(request, *args, **kwargs)

    @HasPermission("log_clustering-Add")
    def create(self, request, *args, **kwargs):
        return super().create(request, *args, **kwargs)

    @HasPermission("log_clustering-Edit")
    def update(self, request, *args, **kwargs):
        return super().update(request, *args, **kwargs)


class LogClusteringServingViewSet(TeamModelViewSet):
    queryset = LogClusteringServing.objects.select_related("train_job", "train_job__dataset_version", "train_job__dataset_version__dataset").all()
    serializer_class = LogClusteringServingSerializer
    pagination_class = CustomPageNumberPagination
    filterset_class = LogClusteringServingFilter
    ordering = ("-id",)
    permission_key = "serving.log_clustering_serving"

    MLFLOW_PREFIX = "LogClustering"  # MLflow 命名前缀

    @HasPermission("log_clustering-View")
    def list(self, request, *args, **kwargs):
        """列表查询，实时同步容器状态"""
        response = super().list(request, *args, **kwargs)

        if isinstance(response.data, dict):
            servings = response.data.get("items", [])
        else:
            servings = response.data

        if not servings:
            return response

        serving_ids = [f"LogClustering_Serving_{s['id']}" for s in servings]

        try:
            # 批量查询
            result = WebhookClient.get_status(serving_ids)
            status_map = {s.get("id"): s for s in result}

            # 批量获取所有需要更新的对象（避免N+1查询）
            serving_id_list = [s["id"] for s in servings]
            serving_objs = LogClusteringServing.objects.filter(id__in=serving_id_list)
            serving_obj_map = {obj.id: obj for obj in serving_objs}

            updates = []
            for serving_data in servings:
                serving_id = f"LogClustering_Serving_{serving_data['id']}"
                container_info = status_map.get(serving_id)

                if container_info:
                    # 直接使用 webhookd 响应
                    serving_data["container_info"] = container_info

                    # 同步到数据库：从缓存字典获取对象，无额外查询
                    serving_obj = serving_obj_map.get(serving_data["id"])
                    if serving_obj:
                        serving_obj.container_info = container_info
                        updates.append(serving_obj)
                else:
                    # webhookd 没返回这个容器的状态
                    serving_data["container_info"] = {
                        "status": "error",
                        "state": "unknown",
                        "message": mlops_message(request, "error.webhookd_container_status_missing"),
                    }

            if updates:
                LogClusteringServing.objects.bulk_update(updates, ["container_info"])

        except WebhookError as e:
            logger.error(f"查询容器状态失败: {e}")
            # 降级：使用数据库中的旧值，添加错误标记
            for serving_data in servings:
                old_info = serving_data.get("container_info") or {}
                serving_data["container_info"] = {
                    **old_info,
                    "status": "error",
                    "_query_failed": True,
                    "_error": mlops_exception_message(request, e),
                }

        return response

    @HasPermission("log_clustering-View")
    def retrieve(self, request, *args, **kwargs):
        """详情查询，实时同步容器状态"""
        response = super().retrieve(request, *args, **kwargs)

        serving_id = f"LogClustering_Serving_{response.data['id']}"

        try:
            result = WebhookClient.get_status([serving_id])
            container_info = result[0] if result else None

            if container_info:
                # 直接使用 webhookd 响应
                response.data["container_info"] = container_info

                # 更新数据库
                LogClusteringServing.objects.filter(id=response.data["id"]).update(container_info=container_info)
            else:
                # webhookd 没返回状态
                response.data["container_info"] = {
                    "status": "error",
                    "state": "unknown",
                    "message": mlops_message(request, "error.webhookd_container_status_unavailable"),
                }

        except WebhookError as e:
            logger.error(f"查询容器状态失败: {e}")
            # 降级：使用数据库中的旧值，添加错误标记
            old_info = response.data.get("container_info") or {}
            response.data["container_info"] = {
                **old_info,
                "status": "error",
                "_query_failed": True,
                "_error": mlops_exception_message(request, e),
            }

        return response

    @HasPermission("log_clustering-Delete")
    def destroy(self, request, *args, **kwargs):
        return self.destroy_serving_with_runtime_cleanup(request, *args, **kwargs)

    @HasPermission("log_clustering-Add")
    def create(self, request, *args, **kwargs):
        """
        创建 serving 服务并自动启动容器
        """
        # 创建 serving 记录
        response = super().create(request, *args, **kwargs)
        serving_id = response.data["id"]

        try:
            # 获取创建的 serving 对象
            serving = LogClusteringServing.objects.get(id=serving_id)

            # 获取 MLflow tracking URI
            mlflow_tracking_uri = get_mlflow_tracking_uri()
            if not mlflow_tracking_uri:
                logger.error("MLflow tracking URI not configured")
                return Response(
                    {"error": mlops_message(request, "error.system_configuration_error")},
                    status=status.HTTP_500_INTERNAL_SERVER_ERROR,
                )

            # 解析 model_uri
            try:
                model_uri = self._resolve_model_uri(serving)
            except ValueError as e:
                logger.error(f"解析 model URI 失败: {e}")
                serving.container_info = {
                    "status": "error",
                    "message": mlops_exception_message(request, e),
                }
                serving.save(update_fields=["container_info"])
                response.data["container_info"] = serving.container_info
                response.data["message"] = mlops_message(
                        request, "message.serving_created_start_failed", detail=mlops_exception_message(request, e)
                    )
                return response

            # 构建 serving ID
            container_id = f"LogClustering_Serving_{serving.id}"

            try:
                # 动态获取训练镜像
                train_image = get_image_by_prefix(self.MLFLOW_PREFIX, serving.train_job.algorithm)
                logger.info(f"  Train Image: {train_image}")

                # 调用 WebhookClient 启动服务
                result = WebhookClient.serve(
                    container_id,
                    mlflow_tracking_uri,
                    model_uri,
                    port=serving.port,
                    train_image=train_image,
                )

                # 启动成功，更新容器信息
                serving.container_info = result
                serving.port = int(result.get("port", 0)) if result.get("port") else serving.port
                serving.save(update_fields=["container_info", "port"])

                response.data["container_info"] = result
                response.data["message"] = mlops_message(request, "message.serving_created_and_started")

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
                                "message": mlops_message(request, "error.container_status_query_failed"),
                            }
                        )

                        serving.container_info = container_info
                        serving.save(update_fields=["container_info"])

                        response.data["container_info"] = container_info
                        response.data["message"] = mlops_message(request, "message.serving_created_existing_container_synced")
                        response.data["warning"] = mlops_message(request, "message.container_already_exists_synced")
                    except WebhookError:
                        serving.container_info = {
                            "status": "error",
                            "message": mlops_message(request, "error.serving_container_sync_failed", detail=mlops_exception_message(request, e)),
                        }
                        serving.save(update_fields=["container_info"])
                        response.data["container_info"] = serving.container_info
                        response.data["message"] = mlops_message(request, "message.serving_created_start_failed_generic")
                else:
                    # 其他错误
                    serving.container_info = {"status": "error", "message": mlops_exception_message(request, e)}
                    serving.save(update_fields=["container_info"])
                    response.data["container_info"] = serving.container_info
                    response.data["message"] = mlops_message(
                        request, "message.serving_created_start_failed", detail=mlops_exception_message(request, e)
                    )

        except Exception as e:
            logger.error(f"自动启动 serving 异常: {str(e)}", exc_info=True)
            response.data["message"] = mlops_message(request, "message.serving_created_start_exception", detail=mlops_exception_message(request, e))

        return response

    @HasPermission("log_clustering-Edit")
    def update(self, request, *args, **kwargs):
        """
        更新 serving 配置，自动检测并重启容器
        """
        instance = self.get_object()

        # 保存旧值用于判断变更
        old_port = instance.port
        old_model_version = instance.model_version
        old_train_job_id = instance.train_job.id

        # 检测是否更新了影响容器的字段
        model_version_changed = "model_version" in request.data and str(request.data["model_version"]) != str(old_model_version)
        train_job_changed = "train_job" in request.data and int(request.data["train_job"]) != old_train_job_id
        port_changed = "port" in request.data and request.data.get("port") != old_port

        container_id = f"LogClustering_Serving_{instance.id}"

        # 获取容器实际状态，防御性处理 container_info 为空的情况
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

        if model_version_changed or train_job_changed:
            need_restart = True
        elif port_changed:
            new_port = instance.port
            if new_port is None and old_port is not None:
                need_restart = False
            elif new_port is not None and old_port is None:
                need_restart = True
            elif new_port is not None and old_port is not None:
                if container_port and str(new_port) != str(container_port):
                    need_restart = True

        # 重启容器
        if need_restart:
            try:
                logger.warning(f"配置变更需要重启，删除旧容器: {container_id}")
                WebhookClient.remove(container_id)
                logger.warning(f"旧容器已删除: {container_id}")
            except WebhookError as e:
                logger.warning(f"删除旧容器失败（可能已不存在）: {e}")

            try:
                mlflow_tracking_uri = get_mlflow_tracking_uri()
                if not mlflow_tracking_uri:
                    raise ValueError("error.mlflow_tracker_url_not_configured")

                model_uri = self._resolve_model_uri(instance)

                # 动态获取训练镜像
                train_image = get_image_by_prefix(self.MLFLOW_PREFIX, instance.train_job.algorithm)

                result = WebhookClient.serve(
                    container_id,
                    mlflow_tracking_uri,
                    model_uri,
                    port=instance.port,
                    train_image=train_image,
                )

                instance.container_info = result
                instance.port = int(result.get("port", 0)) if result.get("port") else instance.port
                instance.save(update_fields=["container_info", "port"])

                response.data["container_info"] = result
                response.data["message"] = mlops_message(request, "message.serving_updated_and_restarted")

            except Exception as e:
                logger.error(f"自动重启失败: {str(e)}", exc_info=True)

                instance.container_info = {
                    "status": "error",
                    "message": mlops_message(request, "message.serving_updated_restart_failed", detail=mlops_exception_message(request, e)),
                }
                instance.save(update_fields=["container_info"])

                response.data["container_info"] = instance.container_info
                response.data["message"] = mlops_message(
                    request, "message.serving_updated_restart_failed", detail=mlops_exception_message(request, e)
                )
                response.data["warning"] = mlops_message(request, "message.serving_restart_manually")

        return response

    @action(detail=True, methods=["post"], url_path="start")
    @HasPermission("log_clustering-Start")
    def start(self, request, *args, **kwargs):
        """
        启动 serving 服务
        """
        try:
            serving = self.get_object()

            mlflow_tracking_uri = get_mlflow_tracking_uri()
            if not mlflow_tracking_uri:
                return Response(
                    {"error": mlops_message(request, "error.mlflow_tracker_url_not_configured")},
                    status=status.HTTP_500_INTERNAL_SERVER_ERROR,
                )

            try:
                model_uri = self._resolve_model_uri(serving)
            except ValueError as e:
                return Response({"error": mlops_exception_message(request, e)}, status=status.HTTP_400_BAD_REQUEST)

            serving_id = f"LogClustering_Serving_{serving.id}"

            try:
                # 动态获取训练镜像
                train_image = get_image_by_prefix(self.MLFLOW_PREFIX, serving.train_job.algorithm)

                result = WebhookClient.serve(
                    serving_id,
                    mlflow_tracking_uri,
                    model_uri,
                    port=serving.port,
                    train_image=train_image,
                )

                # 正常启动成功，更新容器信息
                serving.container_info = result
                serving.port = int(result.get("port", 0)) if result.get("port") else serving.port
                serving.save(update_fields=["container_info", "port"])

                return Response(
                    {
                        "message": mlops_message(request, "message.service_started"),
                        "serving_id": serving_id,
                        "container_info": result,
                    }
                )

            except WebhookError as e:
                error_msg = str(e)

                if e.code == "CONTAINER_ALREADY_EXISTS":
                    logger.warning(f"检测到容器已存在，同步容器信息: {serving_id}")
                    try:
                        result = WebhookClient.get_status([serving_id])
                        container_info = (
                            result[0]
                            if result
                            else {
                                "status": "error",
                                "id": serving_id,
                                "message": mlops_message(request, "error.container_status_query_failed"),
                            }
                        )

                        serving.container_info = container_info
                        serving.save(update_fields=["container_info"])

                        return Response(
                            {
                                "message": mlops_message(request, "message.container_already_exists_status_synced"),
                                "container_info": container_info,
                                "warning": mlops_message(request, "message.container_already_exists"),
                            }
                        )
                    except WebhookError as sync_error:
                        logger.error(f"同步容器状态失败: {sync_error}")
                        return Response(
                            {
                                "error": mlops_message(
                                    request,
                                    "error.serving_container_sync_failed",
                                    detail=mlops_exception_message(request, sync_error),
                                )
                            },
                            status=status.HTTP_500_INTERNAL_SERVER_ERROR,
                        )
                else:
                    logger.error(f"启动 serving 失败: {error_msg}")
                    return Response(
                        {"error": mlops_exception_message(request, e)},
                        status=status.HTTP_500_INTERNAL_SERVER_ERROR,
                    )

        except Exception as e:
            logger.error(f"启动 serving 服务失败: {str(e)}", exc_info=True)
            return Response(
                {"error": mlops_message(request, "error.serving_start_failed", detail=mlops_exception_message(request, e))},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )

    @action(detail=True, methods=["post"], url_path="stop")
    @HasPermission("log_clustering-Stop")
    def stop(self, request, *args, **kwargs):
        """
        停止 serving 服务（停止并删除容器）
        """
        try:
            serving = self.get_object()

            serving_id = f"LogClustering_Serving_{serving.id}"

            result = WebhookClient.stop(serving_id)

            return Response(
                {
                    "message": mlops_message(request, "message.service_stopped_and_deleted"),
                    "serving_id": serving_id,
                    "webhook_response": result,
                }
            )

        except WebhookError as e:
            logger.error(f"停止 serving 失败: {e}")
            return Response({"error": mlops_exception_message(request, e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
        except Exception as e:
            logger.error(f"停止 serving 服务失败: {str(e)}", exc_info=True)
            return Response(
                {"error": mlops_message(request, "error.serving_stop_failed", detail=mlops_exception_message(request, e))},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )

    @action(detail=True, methods=["post"], url_path="remove")
    @HasPermission("log_clustering-Remove")
    def remove(self, request, *args, **kwargs):
        """
        删除 serving 容器（可处理运行中的容器）
        """
        try:
            serving = self.get_object()

            serving_id = f"LogClustering_Serving_{serving.id}"

            result = WebhookClient.remove(serving_id)

            serving.container_info = {
                "status": "success",
                "id": serving_id,
                "state": "removed",
                "message": mlops_message(request, "message.container_deleted"),
            }
            serving.save(update_fields=["container_info"])

            return Response(
                {
                    "message": mlops_message(request, "message.container_deleted"),
                    "serving_id": serving_id,
                    "webhook_response": result,
                }
            )

        except WebhookError as e:
            logger.error(f"删除容器失败: {e}")
            return Response({"error": mlops_exception_message(request, e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
        except Exception as e:
            logger.error(f"删除 serving 容器失败: {str(e)}", exc_info=True)
            return Response(
                {"error": mlops_message(request, "error.serving_container_delete_failed", detail=mlops_exception_message(request, e))},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )

    @action(detail=True, methods=["post"], url_path="predict")
    @HasPermission("log_clustering-Predict")
    def predict(self, request, *args, **kwargs):
        """
        调用 serving 服务进行日志聚类

        请求参数:
            data: 日志原始文本列表，list[str]，例如 ["log line 1", "log line 2"]
            config: 可选推理配置参数（dict）
        """
        try:
            serving = self.get_object()

            data = request.data.get("data")
            config = request.data.get("config")

            if not data:
                return Response({"error": mlops_message(request, "error.predict_input_required", field="data")}, status=status.HTTP_400_BAD_REQUEST)

            if not isinstance(data, list):
                return Response(
                    {"error": mlops_message(request, "error.predict_input_must_be_array", field="data")}, status=status.HTTP_400_BAD_REQUEST
                )

            max_batch_size = int(os.getenv("MLOPS_PREDICT_MAX_BATCH_SIZE", "10000"))
            if len(data) > max_batch_size:
                return Response(
                    {"error": mlops_message(request, "error.predict_batch_limit_exceeded", limit=max_batch_size, count=len(data))},
                    status=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
                )

            try:
                predict_url = build_predict_url(
                    serving_id=f"LogClustering_Serving_{serving.id}",
                    container_info=serving.container_info,
                )
            except ValueError as e:
                return Response(
                    {"error": mlops_message(request, str(e))},
                    status=status.HTTP_400_BAD_REQUEST,
                )

            payload = {"data": data}
            if config is not None:
                payload["config"] = config

            response = requests.post(
                predict_url,
                json=payload,
                timeout=60,
                headers={"Content-Type": "application/json"},
            )

            if response.status_code == 200:
                result = response.json()

                if result.get("success") is False:
                    error_info = result.get("error") or {}
                    error_code = error_info.get("code", "UNKNOWN")
                    error_message = error_info.get("message") or mlops_message(request, "error.prediction_failed")

                    logger.error(f"预测服务返回失败: serving_id={serving.id}, code={error_code}, message={error_message}")
                    return Response(
                        {
                            "error": error_message,
                            "error_code": error_code,
                            "details": error_info.get("details"),
                        },
                        status=status.HTTP_400_BAD_REQUEST,
                    )
                return Response(result)
            else:
                error_msg = mlops_message(request, "error.serving_prediction_service_error", status_code=response.status_code)
                logger.error(f"{error_msg}, serving_id={serving.id}")
                return Response(
                    {"error": error_msg, "detail": response.text},
                    status=status.HTTP_500_INTERNAL_SERVER_ERROR,
                )

        except requests.exceptions.Timeout:
            logger.error(f"预测超时: serving_id={serving.id}, url={predict_url}")
            return Response(
                {"error": mlops_message(request, "error.serving_prediction_timeout_exceeded", seconds=60)},
                status=status.HTTP_504_GATEWAY_TIMEOUT,
            )
        except requests.exceptions.ConnectionError as e:
            logger.error(f"预测连接失败: serving_id={serving.id}, url={predict_url}, error={e}")
            return Response(
                {"error": mlops_message(request, "error.serving_prediction_connection_failed", detail=str(e))},
                status=status.HTTP_503_SERVICE_UNAVAILABLE,
            )
        except requests.exceptions.RequestException as e:
            logger.error(f"预测请求异常: serving_id={serving.id}, error={e}", exc_info=True)
            return Response(
                {"error": mlops_message(request, "error.serving_prediction_request_failed", detail=str(e))},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )
        except Exception as e:
            logger.error(f"预测失败: serving_id={serving.id}, error={str(e)}", exc_info=True)
            return Response(
                {"error": mlops_message(request, "error.serving_prediction_failed", detail=str(e))},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )

    def _resolve_model_uri(self, serving):
        """
        解析 MLflow Model URI
        """
        train_job = serving.train_job
        model_name = mlflow_service.build_model_name(
            prefix=self.MLFLOW_PREFIX,
            algorithm=train_job.algorithm,
            train_job_id=train_job.id,
        )

        return mlflow_service.resolve_model_uri(model_name, serving.model_version)


class LogClusteringAlgorithmConfigViewSet(ModelViewSet):
    """日志聚类算法配置视图集"""

    queryset = AlgorithmConfig.objects.filter(algorithm_type="log_clustering")
    serializer_class = AlgorithmConfigSerializer
    filterset_class = AlgorithmConfigFilter
    pagination_class = CustomPageNumberPagination
    ordering = ("id",)
    permission_key = "algorithm.log_clustering_algorithm_config"

    def get_serializer_class(self):
        if self.action == "list" and not self.request.query_params.get("include_form_config", "false").lower() == "true":
            return AlgorithmConfigListSerializer
        return AlgorithmConfigSerializer

    @HasPermission("log_clustering-View")
    def list(self, request, *args, **kwargs):
        return super().list(request, *args, **kwargs)

    @HasPermission("log_clustering-View")
    def retrieve(self, request, *args, **kwargs):
        return super().retrieve(request, *args, **kwargs)

    @HasPermission("log_clustering-Add")
    def create(self, request, *args, **kwargs):
        request.data["algorithm_type"] = "log_clustering"
        return super().create(request, *args, **kwargs)

    @HasPermission("log_clustering-Edit")
    def update(self, request, *args, **kwargs):
        return super().update(request, *args, **kwargs)

    @HasPermission("log_clustering-Edit")
    def partial_update(self, request, *args, **kwargs):
        instance = self.get_object()
        is_active_new = request.data.get("is_active")
        if instance.is_active and is_active_new is False:
            task_count = LogClusteringTrainJob.objects.filter(algorithm=instance.name).count()
            if task_count > 0:
                return Response(
                    {
                        "error": mlops_message(request, "error.algorithm_in_use_cannot_disable", task_count=task_count),
                        "task_count": task_count,
                    },
                    status=status.HTTP_400_BAD_REQUEST,
                )
        return super().partial_update(request, *args, **kwargs)

    @HasPermission("log_clustering-Delete")
    def destroy(self, request, *args, **kwargs):
        instance = self.get_object()
        task_count = LogClusteringTrainJob.objects.filter(algorithm=instance.name).count()
        if task_count > 0:
            return Response(
                {
                    "error": mlops_message(request, "error.algorithm_in_use_cannot_delete", task_count=task_count),
                    "task_count": task_count,
                },
                status=status.HTTP_400_BAD_REQUEST,
            )
        return super().destroy(request, *args, **kwargs)

    @action(detail=False, methods=["get"], url_path="by_type")
    @HasPermission("log_clustering-View")
    def by_type(self, request):
        queryset = self.get_queryset().filter(is_active=True)
        serializer = AlgorithmConfigSerializer(queryset, many=True)
        return Response(serializer.data)

    @action(detail=False, methods=["get"], url_path="get_image")
    @HasPermission("log_clustering-View")
    def get_image(self, request):
        name = request.query_params.get("name")
        if not name:
            return Response({"error": mlops_message(request, "error.algorithm_name_required")}, status=400)
        try:
            config = AlgorithmConfig.objects.get(algorithm_type="log_clustering", name=name, is_active=True)
            return Response({"image": config.image})
        except AlgorithmConfig.DoesNotExist:
            return Response({"error": mlops_message(request, "error.algorithm_config_not_found", algorithm=f"log_clustering/{name}")}, status=404)
