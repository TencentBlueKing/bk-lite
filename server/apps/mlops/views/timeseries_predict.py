import json
import os
from copy import deepcopy
from uuid import uuid4

import numpy as np
import pandas as pd
import requests
from django.db import DatabaseError, transaction
from django.db.models import Case, F, JSONField, Q, Value, When
from django.http import FileResponse
from rest_framework import status
from rest_framework.decorators import action
from rest_framework.response import Response

from apps.core.decorators.api_permission import HasPermission
from apps.core.logger import mlops_logger as logger
from apps.mlops.constants import DatasetReleaseStatus, MLflowRunStatus, TrainJobStatus
from apps.mlops.filters.algorithm_config import AlgorithmConfigFilter
from apps.mlops.filters.timeseries_predict import (
    TimeSeriesPredictDatasetFilter,
    TimeSeriesPredictDatasetReleaseFilter,
    TimeSeriesPredictServingFilter,
    TimeSeriesPredictTrainDataFilter,
    TimeSeriesPredictTrainJobFilter,
)
from apps.mlops.models import AlgorithmConfig
from apps.mlops.models.timeseries_predict import (
    TimeSeriesPredictDataset,
    TimeSeriesPredictDatasetRelease,
    TimeSeriesPredictServing,
    TimeSeriesPredictTrainData,
    TimeSeriesPredictTrainJob,
)
from apps.mlops.predict_response import map_predict_upstream_status
from apps.mlops.predict_url_builder import build_predict_url
from apps.mlops.serializers.algorithm_config import AlgorithmConfigListSerializer, AlgorithmConfigSerializer
from apps.mlops.serializers.timeseries_predict import (
    TimeSeriesPredictDatasetReleaseSerializer,
    TimeSeriesPredictDatasetSerializer,
    TimeSeriesPredictServingSerializer,
    TimeSeriesPredictTrainDataSerializer,
    TimeSeriesPredictTrainJobSerializer,
)
from apps.mlops.services import ConfigurationError, get_image_by_prefix, get_mlflow_tracking_uri, get_mlflow_train_config
from apps.mlops.utils import mlflow_service
from apps.mlops.utils.group_scope import filter_queryset_by_parent_team
from apps.mlops.utils.i18n import mlops_exception_message, mlops_message
from apps.mlops.utils.validators import validate_serving_status_change
from apps.mlops.utils.webhook_client import WebhookClient, WebhookConnectionError, WebhookError, WebhookTimeoutError
from apps.mlops.views.base import BaseTrainJobViewSet, TeamModelViewSet
from config.drf.pagination import CustomPageNumberPagination
from config.drf.viewsets import ModelViewSet

TIMESERIES_PREDICT_PROXY_TIMEOUT_MARGIN_SECONDS = 5
MAX_TIMESERIES_PREDICT_TIMEOUT_SECONDS = 290
DEFAULT_MAX_RECURSIVE_FEATURE_ENGINEERING_WORK = 2_000_000


def get_timeseries_predict_budget_seconds() -> int:
    raw_timeout = os.getenv("TIMESERIES_PREDICT_TIMEOUT_SECONDS", "120")
    try:
        timeout = int(raw_timeout)
    except ValueError:
        raise ValueError("TIMESERIES_PREDICT_TIMEOUT_SECONDS must be an integer between 1 and 290") from None
    if not 1 <= timeout <= MAX_TIMESERIES_PREDICT_TIMEOUT_SECONDS:
        raise ValueError("TIMESERIES_PREDICT_TIMEOUT_SECONDS must be an integer between 1 and 290")
    return timeout


def get_timeseries_predict_timeout_seconds() -> int:
    return get_timeseries_predict_budget_seconds() + TIMESERIES_PREDICT_PROXY_TIMEOUT_MARGIN_SECONDS


def get_max_recursive_feature_engineering_work() -> int:
    raw_limit = os.getenv(
        "MAX_RECURSIVE_FEATURE_ENGINEERING_WORK",
        str(DEFAULT_MAX_RECURSIVE_FEATURE_ENGINEERING_WORK),
    )
    try:
        limit = int(raw_limit)
    except ValueError:
        raise ValueError("MAX_RECURSIVE_FEATURE_ENGINEERING_WORK must be a positive integer") from None
    if limit <= 0:
        raise ValueError("MAX_RECURSIVE_FEATURE_ENGINEERING_WORK must be a positive integer")
    return limit


class TimeSeriesPredictDatasetViewSet(TeamModelViewSet):
    queryset = TimeSeriesPredictDataset.objects.all()
    serializer_class = TimeSeriesPredictDatasetSerializer
    pagination_class = CustomPageNumberPagination
    filterset_class = TimeSeriesPredictDatasetFilter
    ordering = ("-id",)
    permission_key = "dataset.timeseries_predict_dataset"

    @HasPermission("timeseries_predict-View")
    def list(self, request, *args, **kwargs):
        return super().list(request, *args, **kwargs)

    @HasPermission("timeseries_predict-View")
    def retrieve(self, request, *args, **kwargs):
        return super().retrieve(request, *args, **kwargs)

    @HasPermission("timeseries_predict-Delete")
    def destroy(self, request, *args, **kwargs):
        return super().destroy(request, *args, **kwargs)

    @HasPermission("timeseries_predict-Add")
    def create(self, request, *args, **kwargs):
        return super().create(request, *args, **kwargs)

    @HasPermission("timeseries_predict-Edit")
    def update(self, request, *args, **kwargs):
        return super().update(request, *args, **kwargs)


class TimeSeriesPredictTrainJobViewSet(BaseTrainJobViewSet):
    queryset = TimeSeriesPredictTrainJob.objects.select_related("dataset_version", "dataset_version__dataset").all()
    serializer_class = TimeSeriesPredictTrainJobSerializer
    pagination_class = CustomPageNumberPagination
    filterset_class = TimeSeriesPredictTrainJobFilter
    ordering = ("-id",)
    permission_key = "train_job.timeseries_predict_train_job"

    MLFLOW_PREFIX = "TimeseriesPredict"  # MLflow 命名前缀

    @HasPermission("timeseries_predict-View")
    def list(self, request, *args, **kwargs):
        return super().list(request, *args, **kwargs)

    @HasPermission("timeseries_predict-View")
    def retrieve(self, request, *args, **kwargs):
        return super().retrieve(request, *args, **kwargs)

    @HasPermission("timeseries_predict-Delete")
    def destroy(self, request, *args, **kwargs):
        return self.destroy_train_job_with_runtime_cleanup(request, *args, **kwargs)

    @HasPermission("timeseries_predict-Add")
    def create(self, request, *args, **kwargs):
        return super().create(request, *args, **kwargs)

    @HasPermission("timeseries_predict-Edit")
    def update(self, request, *args, **kwargs):
        return super().update(request, *args, **kwargs)

    @action(detail=True, methods=["post"], url_path="train")
    @HasPermission("timeseries_predict-Train")
    def train(self, request, *args, **kwargs):
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

            # 获取环境变量配置
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
    @HasPermission("timeseries_predict-Stop")
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
                    "train_job_id": train_job.id,
                    "webhook_response": result,
                }
            )

        except WebhookTimeoutError as e:
            return Response({"error": mlops_exception_message(request, e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
        except WebhookConnectionError as e:
            return Response({"error": mlops_exception_message(request, e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
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
    @HasPermission("timeseries_predict-View")
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
                        "message": mlops_message(request, "message.training_run_not_found"),
                        "count": 0,
                        "items": [],
                    }
                )

            # 构建运行信息列表
            run_datas = []

            for idx, row in runs.iterrows():
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

                    # 获取 run_name
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
                    "total_runs": total_count,
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
    @HasPermission("timeseries_predict-Delete")
    def delete_run(self, request, pk=None, run_id=None):
        return super().delete_run(request, pk=pk, run_id=run_id)

    @action(detail=True, methods=["get"], url_path="runs/(?P<run_id>[^/]+)/metrics_list")
    @HasPermission("timeseries_predict-View")
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
    @HasPermission("timeseries_predict-View")
    def get_metric_data(self, request, pk=None, run_id: str = "", metric_name: str = ""):
        return super().get_metric_data(request, pk=pk, run_id=run_id, metric_name=metric_name)

    @action(detail=True, methods=["get"], url_path="runs/(?P<run_id>[^/]+)/run_params")
    @HasPermission("timeseries_predict-View")
    def get_run_params(self, request, pk=None, run_id: str = ""):
        return super().get_run_params(request, pk=pk, run_id=run_id)

    @action(detail=True, methods=["get"], url_path="model_versions")
    @HasPermission("timeseries_predict-View")
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
                return Response({"model_name": model_name, "total": 0, "versions": []})

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
    @HasPermission("timeseries_predict-View")
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


class TimeSeriesPredictTrainDataViewSet(ModelViewSet):
    queryset = TimeSeriesPredictTrainData.objects.select_related("dataset").all()
    serializer_class = TimeSeriesPredictTrainDataSerializer
    pagination_class = CustomPageNumberPagination
    filterset_class = TimeSeriesPredictTrainDataFilter
    ordering = ("-id",)
    permission_key = "dataset.timeseries_predict_train_data"

    def get_queryset(self):
        return filter_queryset_by_parent_team(super().get_queryset(), self.request, "dataset__team")

    @HasPermission("timeseries_predict-View")
    def list(self, request, *args, **kwargs):
        return super().list(request, *args, **kwargs)

    @HasPermission("timeseries_predict-View")
    def retrieve(self, request, *args, **kwargs):
        return super().retrieve(request, *args, **kwargs)

    @HasPermission("timeseries_predict-Delete")
    def destroy(self, request, *args, **kwargs):
        return super().destroy(request, *args, **kwargs)

    @HasPermission("timeseries_predict-Add")
    def create(self, request, *args, **kwargs):
        return super().create(request, *args, **kwargs)

    @HasPermission("timeseries_predict-Edit")
    def update(self, request, *args, **kwargs):
        return super().update(request, *args, **kwargs)


class TimeSeriesPredictServingViewSet(TeamModelViewSet):
    queryset = TimeSeriesPredictServing.objects.select_related("train_job", "train_job__dataset_version", "train_job__dataset_version__dataset").all()
    serializer_class = TimeSeriesPredictServingSerializer
    pagination_class = CustomPageNumberPagination
    filterset_class = TimeSeriesPredictServingFilter
    ordering = ("-id",)
    permission_key = "serving.timeseries_predict_serving"

    MLFLOW_PREFIX = "TimeseriesPredict"  # MLflow 命名前缀
    RUNTIME_GENERATION_KEY = "_runtime_generation"
    RUNTIME_QUERY_TOKEN_KEY = "_runtime_query_token"

    @staticmethod
    def _snapshot_database_state(instance):
        return {field.attname: deepcopy(getattr(instance, field.attname)) for field in instance._meta.concrete_fields if not field.primary_key}

    @classmethod
    def _restore_database_state(cls, instance, old_state, applied_state, **overrides):
        """只回滚仍保持本请求写入值的字段，避免覆盖并发请求。"""
        with transaction.atomic():
            current = instance.__class__.objects.select_for_update().get(pk=instance.pk)
            restored_state = {}
            for field_name, old_value in old_state.items():
                applied_value = applied_state[field_name]
                if old_value != applied_value and getattr(current, field_name) == applied_value:
                    restored_state[field_name] = deepcopy(old_value)
            for field_name, value in overrides.items():
                if getattr(current, field_name) == applied_state[field_name]:
                    if field_name == "container_info":
                        value = cls._next_runtime_container_info(current, value)
                    restored_state[field_name] = deepcopy(value)
            if restored_state:
                instance.__class__.objects.filter(pk=instance.pk).update(**restored_state)
                for field_name, value in restored_state.items():
                    setattr(instance, field_name, deepcopy(value))

    def _get_runtime_locked_object(self):
        """获取并锁定同一 serving，串行化所有运行时变更入口。"""
        unlocked_instance = self.get_object()
        return unlocked_instance.__class__.objects.select_for_update().get(pk=unlocked_instance.pk)

    @classmethod
    def _next_runtime_container_info(cls, instance, runtime_container_info):
        """运行时所有者每次变更都递增 generation，避免状态值 ABA。"""
        current_info = instance.container_info if isinstance(instance.container_info, dict) else {}
        try:
            current_generation = int(current_info.get(cls.RUNTIME_GENERATION_KEY, 0))
        except (TypeError, ValueError):
            current_generation = 0
        return {
            **(runtime_container_info or {}),
            cls.RUNTIME_GENERATION_KEY: current_generation + 1,
        }

    @classmethod
    def _assign_runtime_container_info(cls, instance, runtime_container_info):
        instance.container_info = cls._next_runtime_container_info(instance, runtime_container_info)
        return instance.container_info

    @classmethod
    def _runtime_status_generation(cls, container_info):
        info = container_info if isinstance(container_info, dict) else {}
        try:
            return int(info.get(cls.RUNTIME_GENERATION_KEY, 0))
        except (TypeError, ValueError):
            return 0

    @staticmethod
    def _runtime_status_map(runtime_statuses, expected_ids):
        """线性构建已校验状态映射；错 ID、缺 state 和畸形响应全部忽略。"""
        if not isinstance(runtime_statuses, list):
            return {}
        expected_ids = set(expected_ids)
        return {item["id"]: item for item in runtime_statuses if isinstance(item, dict) and item.get("id") in expected_ids and item.get("state")}

    @classmethod
    def _matching_runtime_status(cls, runtime_statuses, serving_id):
        """仅接受目标 ID 明确匹配且包含 state 的运行时状态。"""
        return cls._runtime_status_map(runtime_statuses, [serving_id]).get(serving_id)

    @classmethod
    def _reserve_runtime_status_sync(cls, observed_statuses):
        """查询 runtime 前批量认领 generation；并发查询只允许最新认领者写回。"""
        if not observed_statuses:
            return {}

        reserve_filter = Q(pk__in=[])
        reserve_cases = []
        claims_by_id = {}
        for instance_id, observed_container_info in observed_statuses:
            condition = Q(pk=instance_id, container_info=observed_container_info)
            observed_info = observed_container_info if isinstance(observed_container_info, dict) else {}
            claim = {
                **observed_info,
                cls.RUNTIME_GENERATION_KEY: cls._runtime_status_generation(observed_info) + 1,
                cls.RUNTIME_QUERY_TOKEN_KEY: uuid4().hex,
            }
            reserve_filter |= condition
            reserve_cases.append(
                When(
                    condition,
                    then=Value(claim, output_field=JSONField()),
                )
            )
            claims_by_id[instance_id] = claim

        TimeSeriesPredictServing.objects.filter(reserve_filter).update(
            container_info=Case(
                *reserve_cases,
                default=F("container_info"),
                output_field=JSONField(),
            )
        )
        return claims_by_id

    @classmethod
    def _finalize_runtime_status_sync(cls, claims_by_id, runtime_info_by_id):
        """仅当前查询 token 仍有效时批量写回，并容忍记录已并发删除。"""
        if claims_by_id and runtime_info_by_id:
            finalize_filter = Q(pk__in=[])
            finalize_cases = []
            for instance_id, runtime_container_info in runtime_info_by_id.items():
                claim = claims_by_id.get(instance_id)
                if claim is None:
                    continue
                condition = Q(pk=instance_id, container_info=claim)
                versioned_runtime_info = {
                    **runtime_container_info,
                    cls.RUNTIME_GENERATION_KEY: claim[cls.RUNTIME_GENERATION_KEY],
                }
                finalize_filter |= condition
                finalize_cases.append(
                    When(
                        condition,
                        then=Value(versioned_runtime_info, output_field=JSONField()),
                    )
                )

            if finalize_cases:
                TimeSeriesPredictServing.objects.filter(finalize_filter).update(
                    container_info=Case(
                        *finalize_cases,
                        default=F("container_info"),
                        output_field=JSONField(),
                    )
                )

        instance_ids = list(claims_by_id)
        if not instance_ids:
            return {}
        return dict(
            TimeSeriesPredictServing.objects.filter(pk__in=instance_ids).values_list(
                "pk",
                "container_info",
            )
        )

    @classmethod
    def _claim_runtime_transition(cls, instance, transition, request=None):
        """外部调用前推进 generation，并记录结果尚待对账。"""
        observed_info = instance.container_info if isinstance(instance.container_info, dict) else {}
        claim = cls._next_runtime_container_info(
            instance,
            {
                **observed_info,
                "status": "error",
                "state": "unknown",
                "message": mlops_message(request, "message.runtime_transition_pending", transition=transition),
                "_runtime_transition": transition,
            },
        )
        instance.container_info = claim
        instance.save(update_fields=["container_info"])
        return claim

    @classmethod
    def _reconcile_runtime_transition(cls, instance, serving_id, transition, error, request=None):
        """副作用结果不确定时查询实际状态；查询失败则持久化 unknown。"""
        detail = mlops_exception_message(request, error) if isinstance(error, BaseException) else str(error)
        try:
            observed_runtime = WebhookClient.get_status([serving_id])
            runtime_info = cls._matching_runtime_status(observed_runtime, serving_id)
            if runtime_info is None:
                runtime_info = {
                    "status": "error",
                    "id": serving_id,
                    "state": "unknown",
                    "message": mlops_message(
                        request,
                        "error.runtime_transition_unknown_status_missing",
                        transition=transition,
                        detail=detail,
                    ),
                }
        except Exception as status_error:
            runtime_info = {
                "status": "error",
                "id": serving_id,
                "state": "unknown",
                "message": mlops_message(
                    request,
                    "error.runtime_transition_unknown_reconcile_failed",
                    transition=transition,
                    detail=detail,
                    status_detail=mlops_exception_message(request, status_error),
                ),
            }
        cls._assign_runtime_container_info(instance, runtime_info)
        instance.save(update_fields=["container_info"])
        return instance.container_info

    @staticmethod
    def _cleanup_uncommitted_create_runtime(container_id, serving_id, cleanup_token):
        """事务回滚后先持久化清理意图，再同步清理并由任务持续补投。"""
        from apps.mlops.services.timeseries_runtime_cleanup import create_runtime_cleanup_intent, process_runtime_cleanup_intent

        try:
            intent = create_runtime_cleanup_intent(
                container_id,
                serving_id,
                cleanup_token,
            )
        except Exception as intent_error:
            from apps.mlops.tasks.runtime_cleanup import bootstrap_timeseries_runtime_cleanup

            try:
                bootstrap_timeseries_runtime_cleanup.apply_async(
                    args=(container_id, serving_id, cleanup_token),
                    retry=True,
                    retry_policy={
                        "max_retries": 5,
                        "interval_start": 0,
                        "interval_step": 1,
                        "interval_max": 5,
                    },
                )
            except Exception as dispatch_error:
                logger.critical(
                    "创建 serving 事务回滚后的补偿意图与 bootstrap 任务均未持久化: "
                    f"container_id={container_id}, intent_error={type(intent_error).__name__}, "
                    f"dispatch_error={type(dispatch_error).__name__}",
                    exc_info=True,
                )
            return

        try:
            process_runtime_cleanup_intent(intent.pk)
        except Exception as cleanup_error:
            from apps.mlops.tasks.runtime_cleanup import cleanup_orphan_timeseries_runtime

            try:
                cleanup_orphan_timeseries_runtime.apply_async(
                    args=(intent.pk,),
                    retry=True,
                    retry_policy={
                        "max_retries": 5,
                        "interval_start": 0,
                        "interval_step": 1,
                        "interval_max": 5,
                    },
                )
            except Exception as dispatch_error:
                logger.critical(
                    "创建 serving 事务回滚后的补偿任务投递失败: "
                    f"intent_id={intent.pk}, container_id={container_id}, "
                    f"cleanup_error={type(cleanup_error).__name__}, "
                    f"dispatch_error={type(dispatch_error).__name__}",
                    exc_info=True,
                )

    @HasPermission("timeseries_predict-View")
    def list(self, request, *args, **kwargs):
        """列表查询，实时同步容器状态"""
        response = super().list(request, *args, **kwargs)

        if isinstance(response.data, dict):
            servings = response.data.get("items", [])
        else:
            servings = response.data

        if not servings:
            return response

        serving_ids = [f"TimeseriesPredict_Serving_{s['id']}" for s in servings]
        claims_by_id = self._reserve_runtime_status_sync([(serving_data["id"], serving_data.get("container_info")) for serving_data in servings])

        try:
            # 批量查询
            result = WebhookClient.get_status(serving_ids)
            status_map = self._runtime_status_map(result, serving_ids)

            runtime_info_by_id = {}
            for serving_data in servings:
                serving_id = f"TimeseriesPredict_Serving_{serving_data['id']}"
                container_info = status_map.get(serving_id)

                if container_info:
                    runtime_info_by_id[serving_data["id"]] = container_info
                else:
                    # webhookd 没返回这个容器的状态（不应该发生）
                    serving_data["container_info"] = {
                        "status": "error",
                        "state": "unknown",
                        "message": mlops_message(request, "error.webhookd_container_status_missing"),
                    }

            current_info_by_id = self._finalize_runtime_status_sync(claims_by_id, runtime_info_by_id) if runtime_info_by_id else {}
            for serving_data in servings:
                instance_id = serving_data["id"]
                if instance_id in runtime_info_by_id:
                    # 并发 DELETE 时记录已不存在，保留本次已取得的运行时快照。
                    serving_data["container_info"] = current_info_by_id.get(
                        instance_id,
                        runtime_info_by_id[instance_id],
                    )

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

    @HasPermission("timeseries_predict-View")
    def retrieve(self, request, *args, **kwargs):
        """详情查询，实时同步容器状态"""
        response = super().retrieve(request, *args, **kwargs)

        serving_id = f"TimeseriesPredict_Serving_{response.data['id']}"
        claims_by_id = self._reserve_runtime_status_sync([(response.data["id"], response.data.get("container_info"))])

        try:
            result = WebhookClient.get_status([serving_id])
            container_info = self._matching_runtime_status(result, serving_id)

            if container_info:
                current_info_by_id = self._finalize_runtime_status_sync(
                    claims_by_id,
                    {response.data["id"]: container_info},
                )
                # 详情已在请求开始时形成快照；并发 DELETE 时返回已取得的运行时状态，
                # 不把正常竞争转换成 500。
                response.data["container_info"] = current_info_by_id.get(
                    response.data["id"],
                    container_info,
                )
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

    @HasPermission("timeseries_predict-Delete")
    @transaction.atomic
    def destroy(self, request, *args, **kwargs):
        serving = self._get_runtime_locked_object()
        access_error = self._validate_destroy_access(request, serving)
        if access_error is not None:
            return access_error
        serving_id = f"TimeseriesPredict_Serving_{serving.id}"
        self._claim_runtime_transition(serving, "delete", request)
        cleanup_error = self.cleanup_serving_runtime(serving)
        if cleanup_error is not None:
            self._reconcile_runtime_transition(serving, serving_id, "delete", cleanup_error.data, request)
            return cleanup_error
        kwargs["_destroy_access_prechecked"] = True
        return super().destroy(request, *args, **kwargs)

    @HasPermission("timeseries_predict-Add")
    def create(self, request, *args, **kwargs):
        cleanup_context = {}
        try:
            return self._create_under_runtime_lock(request, cleanup_context, *args, **kwargs)
        except Exception:
            container_id = cleanup_context.get("container_id")
            serving_id = cleanup_context.get("serving_id")
            cleanup_token = cleanup_context.get("cleanup_token")
            if container_id is not None and serving_id is not None and cleanup_token is not None:
                self._cleanup_uncommitted_create_runtime(
                    container_id,
                    serving_id,
                    cleanup_token,
                )
            raise

    @transaction.atomic
    def _create_under_runtime_lock(self, request, cleanup_context, *args, **kwargs):
        """
        创建 serving 服务并自动启动容器。

        新记录及外部运行时在同一事务内初始化，提交前对其他请求不可见；若事务
        或最终落库失败，外层会在事务退出后幂等清理可能已创建的运行时。
        """
        # 创建 serving 记录（初始状态为 inactive）
        response = super().create(request, *args, **kwargs)
        serving_id = response.data["id"]
        serving = None
        container_id = None

        try:
            # 新记录在提交前不可见；显式行锁使创建与其余运行时入口使用同一锁约定。
            serving = TimeSeriesPredictServing.objects.select_for_update().get(id=serving_id)

            # 获取 MLflow tracking URI
            mlflow_tracking_uri = get_mlflow_tracking_uri()
            if not mlflow_tracking_uri:
                logger.error("环境变量 MLFLOW_TRACKER_URL 未配置")
                self._assign_runtime_container_info(
                    serving,
                    {
                        "status": "error",
                        "message": mlops_message(request, "error.mlflow_tracker_url_not_configured"),
                    },
                )
                serving.save(update_fields=["container_info"])
                response.data["container_info"] = serving.container_info
                response.data["message"] = mlops_message(request, "message.serving_created_start_failed_config_missing")
                return response
            recursive_feature_work_limit = get_max_recursive_feature_engineering_work()

            # 解析 model_uri
            try:
                model_uri = self._resolve_model_uri(serving)
            except ValueError as e:
                logger.error(f"解析 model URI 失败: {e}")
                self._assign_runtime_container_info(
                    serving,
                    {
                        "status": "error",
                        "message": mlops_exception_message(request, e),
                    },
                )
                serving.save(update_fields=["container_info"])
                response.data["container_info"] = serving.container_info
                response.data["message"] = mlops_message(
                        request, "message.serving_created_start_failed", detail=mlops_exception_message(request, e)
                    )
                return response

            # 构建 serving ID
            container_id = f"TimeseriesPredict_Serving_{serving.id}"
            cleanup_context["container_id"] = container_id
            cleanup_context["serving_id"] = serving.id
            cleanup_context["cleanup_token"] = str(uuid4())

            try:
                from apps.mlops.services.timeseries_runtime_cleanup import lock_timeseries_runtime_id

                # create 与失败补偿使用同一永久 guard。即使业务行尚未提交，唯一
                # guard 插入也会阻塞并发 cleanup，直到本事务提交或回滚。
                lock_timeseries_runtime_id(serving.id)
                self._claim_runtime_transition(serving, "create", request)
                # 调用 WebhookClient 启动服务
                result = WebhookClient.serve(
                    container_id,
                    mlflow_tracking_uri,
                    model_uri,
                    port=serving.port,
                    train_image=get_image_by_prefix(self.MLFLOW_PREFIX, serving.train_job.algorithm),
                    timeseries_predict_timeout_seconds=get_timeseries_predict_budget_seconds(),
                    max_recursive_feature_engineering_work=recursive_feature_work_limit,
                )

                # 启动成功，仅更新容器信息
                versioned_result = self._assign_runtime_container_info(serving, result)
                serving.port = int(result.get("port", 0)) if result.get("port") else serving.port
                serving.save(update_fields=["container_info", "port"])

                # 更新返回数据（status 由用户控制，不修改）
                response.data["container_info"] = versioned_result
                response.data["message"] = mlops_message(request, "message.serving_created_and_started")

            except WebhookError as e:
                error_msg = str(e)
                logger.error(f"自动启动 serving 失败: {error_msg}")

                # 处理容器已存在的情况（同步容器状态）
                if e.code == "CONTAINER_ALREADY_EXISTS":
                    try:
                        result = WebhookClient.get_status([container_id])
                        container_info = self._matching_runtime_status(result, container_id)
                        if container_info is None:
                            container_info = {
                                "status": "error",
                                "id": container_id,
                                "state": "unknown",
                                "message": mlops_message(request, "error.runtime_status_not_returned"),
                            }

                        # 仅更新容器信息，不修改 status
                        container_info = self._assign_runtime_container_info(serving, container_info)
                        serving.save(update_fields=["container_info"])

                        response.data["container_info"] = container_info
                        response.data["message"] = mlops_message(request, "message.serving_created_existing_container_synced")
                        response.data["warning"] = mlops_message(request, "message.container_already_exists_synced")
                    except WebhookError:
                        self._assign_runtime_container_info(
                            serving,
                            {
                                "status": "error",
                                "state": "unknown",
                                "message": mlops_message(request, "error.serving_container_sync_failed", detail=mlops_exception_message(request, e)),
                            },
                        )
                        serving.save(update_fields=["container_info"])
                        response.data["container_info"] = serving.container_info
                        response.data["message"] = mlops_message(request, "message.serving_created_start_failed_generic")
                else:
                    # 调用失败可能已产生外部副作用，必须对账后再落库。
                    self._reconcile_runtime_transition(serving, container_id, "create", e, request)
                    response.data["container_info"] = serving.container_info
                    response.data["message"] = mlops_message(
                        request, "message.serving_created_start_failed", detail=mlops_exception_message(request, e)
                    )

        except DatabaseError:
            raise
        except Exception as e:
            logger.error(f"自动启动 serving 异常: {str(e)}", exc_info=True)
            if serving is not None and container_id is not None:
                self._reconcile_runtime_transition(serving, container_id, "create", e, request)
                response.data["container_info"] = serving.container_info
            # 确保至少有基本的错误信息
            response.data["message"] = mlops_message(request, "message.serving_created_start_exception", detail=mlops_exception_message(request, e))

        return response

    @HasPermission("timeseries_predict-Edit")
    @transaction.atomic
    def update(self, request, *args, **kwargs):  # noqa: C901
        """
        更新 serving 配置，自动检测并重启容器

        基于实际容器运行状态决策：
        - 容器 running + 配置变更 → 自动重启
        - 容器非 running → 仅更新数据库，用户自行决定是否启动
        """
        # 同一 serving 的数据库写入和外部运行时切换必须串行；普通并发 UPDATE
        # 也会在 PostgreSQL 行锁上等待，避免另一个请求接管同一 runtime ID。
        instance = self._get_runtime_locked_object()

        # 本方法在父类更新前会解析 MLflow、镜像和运行时配置，因此先复用父类的
        # 完整实例授权门禁；父类收到标记后不再重复执行同一校验。
        access_error = self._validate_update_access(request, instance, request.data)
        if access_error is not None:
            return access_error
        kwargs["_update_access_prechecked"] = True
        old_database_state = self._snapshot_database_state(instance)
        deferred_delete_teams = []
        if self.ORGANIZATION_FIELD in request.data:
            new_teams = self._normalize_org_values(request.data, self.ORGANIZATION_FIELD)
            deferred_delete_teams = [team for team in old_database_state.get(self.ORGANIZATION_FIELD, []) if team not in new_teams]
            kwargs["_skip_rule_cleanup"] = True

        # 兜底校验：容器未运行时不允许设置 status=active
        new_status = request.data.get("status")
        if error_response := validate_serving_status_change(request, instance, new_status):
            return error_response
        # 保存旧值用于判断变更
        old_port = instance.port
        old_model_version = instance.model_version
        old_train_job_id = instance.train_job.id

        # 检测是否更新了影响容器的字段（基于请求数据与旧值对比）
        model_version_changed = "model_version" in request.data and str(request.data["model_version"]) != str(old_model_version)
        train_job_changed = "train_job" in request.data and int(request.data["train_job"]) != old_train_job_id
        port_changed = "port" in request.data and request.data.get("port") != old_port

        container_id = f"TimeseriesPredict_Serving_{instance.id}"

        # 获取容器实际状态（更新前），防御性处理 container_info 为空的情况
        container_info = instance.container_info or {}
        container_state = container_info.get("state")
        container_port = container_info.get("port")

        # 需要重启时先校验全部旧服务恢复参数，避免系统配置错误导致旧容器下线。
        predict_budget_seconds = None
        recursive_feature_work_limit = None
        mlflow_tracking_uri = None
        old_model_uri = None
        old_train_image = None
        if container_state == "running" and (model_version_changed or train_job_changed or port_changed):
            try:
                predict_budget_seconds = get_timeseries_predict_budget_seconds()
                recursive_feature_work_limit = get_max_recursive_feature_engineering_work()
                mlflow_tracking_uri = get_mlflow_tracking_uri()
                if not mlflow_tracking_uri:
                    raise ValueError("error.mlflow_tracker_url_not_configured")
                old_model_uri = self._resolve_model_uri(instance)
                old_train_image = get_image_by_prefix(self.MLFLOW_PREFIX, instance.train_job.algorithm)
            except Exception as e:
                logger.error(f"时序预测重启前置配置无效: {e}")
                return Response(
                    {"error": mlops_message(request, "error.system_configuration_error")},
                    status=status.HTTP_500_INTERNAL_SERVER_ERROR,
                )

        # 更新数据库
        response = super().update(request, *args, **kwargs)
        if not isinstance(response, Response) or response.status_code >= 400:
            return response
        instance.refresh_from_db()
        applied_database_state = self._snapshot_database_state(instance)

        # 只有容器在运行时才考虑重启
        if container_state != "running":
            self.delete_rules(instance.id, deferred_delete_teams)
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

        if not need_restart:
            self.delete_rules(instance.id, deferred_delete_teams)
            return response

        # 如果需要重启，先删除旧容器
        if need_restart:
            try:
                model_uri = self._resolve_model_uri(instance)
                train_image = get_image_by_prefix(self.MLFLOW_PREFIX, instance.train_job.algorithm)
            except Exception as e:
                self._restore_database_state(instance, old_database_state, applied_database_state)
                logger.error(f"新 serving 配置校验失败，保留旧服务: {e}", exc_info=True)
                return Response(
                    {"error": mlops_message(request, "error.serving_update_configuration_failed", detail=mlops_exception_message(request, e))},
                    status=status.HTTP_500_INTERNAL_SERVER_ERROR,
                )

            try:
                logger.warning(f"配置变更需要重启，删除旧容器: {container_id}")
                transition_claim = self._claim_runtime_transition(instance, "update", request)
                applied_database_state["container_info"] = deepcopy(transition_claim)
                WebhookClient.remove(container_id)
            except Exception as e:
                try:
                    observed_runtime = WebhookClient.get_status([container_id])
                except Exception as status_error:
                    logger.error(f"删除旧容器失败且状态对账失败: {status_error}", exc_info=True)
                    rollback_result = {
                        "status": "error",
                        "state": "unknown",
                        "message": mlops_message(
                            request,
                            "error.old_service_delete_result_unknown",
                            detail=mlops_exception_message(request, status_error),
                        ),
                    }
                    rollback_port = old_port
                    rollback_message = mlops_message(request, "message.config_rolled_back_old_service_delete_unknown")
                else:
                    runtime_state = self._matching_runtime_status(observed_runtime, container_id) or {}
                    observed_state = runtime_state.get("state")
                    if runtime_state and observed_state not in {"running", "not_found"}:
                        try:
                            # stop 成功但 remove 失败时会留下 completed/failed/stopped
                            # 资源；再次幂等删除并确认消失后才能复用相同 ID。
                            WebhookClient.remove(container_id)
                            verified_runtime = WebhookClient.get_status([container_id])
                            runtime_state = self._matching_runtime_status(verified_runtime, container_id) or {}
                            observed_state = runtime_state.get("state")
                        except Exception as cleanup_error:
                            logger.error(f"清理非运行态旧 serving 失败: {cleanup_error}", exc_info=True)
                            runtime_state = {
                                "status": "error",
                                "state": "unknown",
                                "message": mlops_message(
                                    request,
                                    "error.old_service_stopped_cleanup_failed",
                                    detail=mlops_exception_message(request, cleanup_error),
                                ),
                            }
                            observed_state = "unknown"

                    if observed_state == "not_found":
                        try:
                            rollback_result = WebhookClient.serve(
                                container_id,
                                mlflow_tracking_uri,
                                old_model_uri,
                                port=old_port,
                                train_image=old_train_image,
                                timeseries_predict_timeout_seconds=predict_budget_seconds,
                                max_recursive_feature_engineering_work=recursive_feature_work_limit,
                            )
                            rollback_port = int(rollback_result.get("port", 0)) if rollback_result.get("port") else old_port
                            rollback_message = mlops_message(
                                request, "message.config_rolled_back_old_service_restored_after_delete"
                            )
                        except Exception as rollback_error:
                            logger.error(f"对账后恢复旧 serving 失败: {rollback_error}", exc_info=True)
                            rollback_result = {
                                "status": "error",
                                "state": "not_found",
                                "message": mlops_message(
                                    request,
                                    "error.old_service_deleted_restore_failed",
                                    detail=mlops_exception_message(request, rollback_error),
                                ),
                            }
                            rollback_port = old_port
                            rollback_message = mlops_message(request, "message.config_rolled_back_old_service_restore_failed")
                    elif observed_state == "running":
                        rollback_result = runtime_state
                        rollback_port = int(runtime_state.get("port", 0)) if runtime_state.get("port") else old_port
                        rollback_message = mlops_message(request, "message.config_rolled_back_old_service_still_running")
                    else:
                        rollback_result = runtime_state or {
                            "status": "error",
                            "state": "unknown",
                            "message": mlops_message(request, "error.old_service_delete_status_missing"),
                        }
                        rollback_port = old_port
                        rollback_message = mlops_message(request, "message.config_rolled_back_old_service_delete_unknown")

                self._restore_database_state(
                    instance,
                    old_database_state,
                    applied_database_state,
                    port=rollback_port,
                    container_info=rollback_result,
                )
                logger.error(f"删除旧容器失败，配置已回滚并完成状态对账: {e}", exc_info=True)
                return Response(
                    {
                        "error": mlops_message(
                            request,
                            "error.config_update_not_applied",
                            detail=mlops_exception_message(request, e),
                        ),
                        "message": rollback_message,
                        "container_info": rollback_result,
                    },
                    status=status.HTTP_500_INTERNAL_SERVER_ERROR,
                )

            try:
                # 启动新容器
                result = WebhookClient.serve(
                    container_id,
                    mlflow_tracking_uri,
                    model_uri,
                    port=instance.port,
                    train_image=train_image,
                    timeseries_predict_timeout_seconds=predict_budget_seconds,
                    max_recursive_feature_engineering_work=recursive_feature_work_limit,
                )

                # 更新容器信息（status 由用户控制，不修改）
                versioned_result = self._assign_runtime_container_info(instance, result)
                instance.port = int(result.get("port", 0)) if result.get("port") else instance.port
                instance.save(update_fields=["container_info", "port"])

                # 更新返回数据
                response.data["container_info"] = versioned_result
                response.data["message"] = mlops_message(request, "message.serving_updated_and_restarted")
                self.delete_rules(instance.id, deferred_delete_teams)

            except Exception as e:
                logger.error(f"自动重启失败: {str(e)}", exc_info=True)
                try:
                    # serve.sh 可能在返回失败前已创建容器或 Kubernetes 资源。
                    # remove 端点对不存在资源幂等；确认清理完成后才能复用同一 ID。
                    WebhookClient.remove(container_id)
                except Exception as cleanup_error:
                    logger.error(f"清理失败的新 serving 资源失败: {cleanup_error}", exc_info=True)
                    rollback_result = {
                        "status": "error",
                        "message": mlops_message(
                            request,
                            "error.new_service_start_residue_cleanup_failed",
                            detail=mlops_exception_message(request, cleanup_error),
                        ),
                    }
                    rollback_port = old_port
                    rollback_message = mlops_message(request, "message.new_serving_start_failed_residue_uncleared")
                else:
                    try:
                        rollback_result = WebhookClient.serve(
                            container_id,
                            mlflow_tracking_uri,
                            old_model_uri,
                            port=old_port,
                            train_image=old_train_image,
                            timeseries_predict_timeout_seconds=predict_budget_seconds,
                            max_recursive_feature_engineering_work=recursive_feature_work_limit,
                        )
                        rollback_port = int(rollback_result.get("port", 0)) if rollback_result.get("port") else old_port
                        rollback_message = mlops_message(request, "message.new_serving_start_failed_old_restored")
                    except Exception as rollback_error:
                        logger.error(f"恢复旧 serving 失败: {rollback_error}", exc_info=True)
                        rollback_result = {
                            "status": "error",
                            "message": mlops_message(
                                request,
                                "error.new_and_old_service_restore_failed",
                                detail=mlops_exception_message(request, rollback_error),
                            ),
                        }
                        rollback_port = old_port
                        rollback_message = mlops_message(request, "message.new_serving_start_failed_old_restore_failed")

                self._restore_database_state(
                    instance,
                    old_database_state,
                    applied_database_state,
                    port=rollback_port,
                    container_info=rollback_result,
                )
                return Response(
                    {
                        "error": mlops_message(
                            request,
                            "error.config_update_not_applied",
                            detail=mlops_exception_message(request, e),
                        ),
                        "message": rollback_message,
                        "container_info": rollback_result,
                    },
                    status=status.HTTP_500_INTERNAL_SERVER_ERROR,
                )

        return response

    @action(detail=True, methods=["post"], url_path="start")
    @HasPermission("timeseries_predict-Start")
    @transaction.atomic
    def start(self, request, *args, **kwargs):
        """
        启动 serving 服务
        """
        serving = None
        serving_id = None
        try:
            serving = self._get_runtime_locked_object()

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
                return Response({"error": mlops_exception_message(request, e)}, status=status.HTTP_400_BAD_REQUEST)

            # 构建 serving ID
            serving_id = f"TimeseriesPredict_Serving_{serving.id}"

            try:
                recursive_feature_work_limit = get_max_recursive_feature_engineering_work()
                self._claim_runtime_transition(serving, "start", request)
                # 调用 WebhookClient 启动服务
                result = WebhookClient.serve(
                    serving_id,
                    mlflow_tracking_uri,
                    model_uri,
                    port=serving.port,
                    train_image=get_image_by_prefix(self.MLFLOW_PREFIX, serving.train_job.algorithm),
                    timeseries_predict_timeout_seconds=get_timeseries_predict_budget_seconds(),
                    max_recursive_feature_engineering_work=recursive_feature_work_limit,
                )

                # 正常启动成功，更新容器信息
                versioned_result = self._assign_runtime_container_info(serving, result)
                serving.port = int(result.get("port", 0)) if result.get("port") else serving.port
                serving.save(update_fields=["container_info", "port"])

                return Response(
                    {
                        "message": mlops_message(request, "message.service_started"),
                        "serving_id": serving_id,
                        "container_info": versioned_result,
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
                        container_info = self._matching_runtime_status(result, serving_id)
                        if container_info is None:
                            container_info = {
                                "status": "error",
                                "id": serving_id,
                                "state": "unknown",
                                "message": mlops_message(request, "error.runtime_status_not_returned"),
                            }

                        # 仅更新容器信息，不修改 status
                        container_info = self._assign_runtime_container_info(serving, container_info)
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
                    # 其他错误直接返回
                    logger.error(f"启动 serving 失败: {error_msg}")
                    self._reconcile_runtime_transition(serving, serving_id, "start", e, request)
                    return Response(
                        {"error": mlops_exception_message(request, e)},
                        status=status.HTTP_500_INTERNAL_SERVER_ERROR,
                    )

        except WebhookTimeoutError as e:
            if serving is not None and serving_id is not None:
                self._reconcile_runtime_transition(serving, serving_id, "start", e, request)
            return Response({"error": mlops_exception_message(request, e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
        except WebhookConnectionError as e:
            if serving is not None and serving_id is not None:
                self._reconcile_runtime_transition(serving, serving_id, "start", e, request)
            return Response({"error": mlops_exception_message(request, e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
        except Exception as e:
            logger.error(f"启动 serving 服务失败: {str(e)}", exc_info=True)
            if serving is not None and serving_id is not None:
                self._reconcile_runtime_transition(serving, serving_id, "start", e, request)
            return Response(
                {"error": mlops_message(request, "error.serving_start_failed", detail=mlops_exception_message(request, e))},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )

    @action(detail=True, methods=["post"], url_path="stop")
    @HasPermission("timeseries_predict-Stop")
    @transaction.atomic
    def stop(self, request, *args, **kwargs):
        """
        停止 serving 服务（停止并删除容器）
        """
        serving = None
        serving_id = None
        try:
            serving = self._get_runtime_locked_object()

            # 构建 serving ID
            serving_id = f"TimeseriesPredict_Serving_{serving.id}"

            # 调用 WebhookClient 停止服务（默认删除容器）
            self._claim_runtime_transition(serving, "stop", request)
            result = WebhookClient.stop(serving_id)

            # Kubernetes stop 使用异步删除并可能返回 terminating；必须保留
            # webhookd 的真实状态，不能提前宣称资源已 removed。
            self._assign_runtime_container_info(
                serving,
                {
                    **result,
                    "id": result.get("id", serving_id),
                },
            )
            serving.save(update_fields=["container_info"])

            return Response(
                {
                    "message": mlops_message(request, "message.service_stopped_and_deleted"),
                    "serving_id": serving_id,
                    "webhook_response": result,
                }
            )

        except WebhookTimeoutError as e:
            if serving is not None and serving_id is not None:
                self._reconcile_runtime_transition(serving, serving_id, "stop", e, request)
            return Response({"error": mlops_exception_message(request, e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
        except WebhookConnectionError as e:
            if serving is not None and serving_id is not None:
                self._reconcile_runtime_transition(serving, serving_id, "stop", e, request)
            return Response({"error": mlops_exception_message(request, e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
        except WebhookError as e:
            logger.error(f"停止 serving 失败: {e}")
            if serving is not None and serving_id is not None:
                self._reconcile_runtime_transition(serving, serving_id, "stop", e, request)
            return Response({"error": mlops_exception_message(request, e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
        except Exception as e:
            logger.error(f"停止 serving 服务失败: {str(e)}", exc_info=True)
            if serving is not None and serving_id is not None:
                self._reconcile_runtime_transition(serving, serving_id, "stop", e, request)
            return Response(
                {"error": mlops_message(request, "error.serving_stop_failed", detail=mlops_exception_message(request, e))},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )

    @action(detail=True, methods=["post"], url_path="remove")
    @HasPermission("timeseries_predict-Remove")
    @transaction.atomic
    def remove(self, request, *args, **kwargs):
        """
        删除 serving 容器（可处理运行中的容器）
        """
        serving = None
        serving_id = None
        try:
            serving = self._get_runtime_locked_object()

            # 构建 serving ID
            serving_id = f"TimeseriesPredict_Serving_{serving.id}"

            # 调用 WebhookClient 删除容器
            self._claim_runtime_transition(serving, "remove", request)
            result = WebhookClient.remove(serving_id)

            # 更新容器信息（status 由用户控制，不修改）
            self._assign_runtime_container_info(
                serving,
                {
                    "status": "success",
                    "id": serving_id,
                    "state": "removed",
                    "message": mlops_message(request, "message.container_deleted"),
                },
            )
            serving.save(update_fields=["container_info"])

            return Response(
                {
                    "message": mlops_message(request, "message.container_deleted"),
                    "serving_id": serving_id,
                    "webhook_response": result,
                }
            )

        except WebhookTimeoutError as e:
            if serving is not None and serving_id is not None:
                self._reconcile_runtime_transition(serving, serving_id, "remove", e, request)
            return Response({"error": mlops_exception_message(request, e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
        except WebhookConnectionError as e:
            if serving is not None and serving_id is not None:
                self._reconcile_runtime_transition(serving, serving_id, "remove", e, request)
            return Response({"error": mlops_exception_message(request, e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
        except WebhookError as e:
            logger.error(f"删除容器失败: {e}")
            if serving is not None and serving_id is not None:
                self._reconcile_runtime_transition(serving, serving_id, "remove", e, request)
            return Response({"error": mlops_exception_message(request, e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
        except Exception as e:
            logger.error(f"删除 serving 容器失败: {str(e)}", exc_info=True)
            if serving is not None and serving_id is not None:
                self._reconcile_runtime_transition(serving, serving_id, "remove", e, request)
            return Response(
                {"error": mlops_message(request, "error.serving_container_delete_failed", detail=mlops_exception_message(request, e))},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )

    @action(detail=True, methods=["post"], url_path="predict")
    @HasPermission("timeseries_predict-Predict")
    def predict(self, request, *args, **kwargs):
        """
        调用 serving 服务进行时间序列预测

        URL: POST /api/v1/mlops/timeseries_predict_servings/{pk}/predict/

        请求参数:
            url: 预测服务主机地址（如 http://192.168.1.100，不含端口）
            data: 历史时间序列数据数组 [{"timestamp": "...", "value": ...}, ...]
            config: { "steps": 预测步长 }

        返回格式:
            预测服务的响应（通常为 {"success": true, "history": [...], "prediction": [...], "metadata": {...}, "error": null}）
        """
        try:
            serving = self.get_object()

            # 获取参数
            data = request.data.get("data")
            config = request.data.get("config", {})
            steps = config.get("steps", 5)

            # 参数校验
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
                    serving_id=f"TimeseriesPredict_Serving_{serving.id}",
                    container_info=serving.container_info,
                )
            except ValueError as e:
                return Response(
                    {"error": mlops_message(request, str(e))},
                    status=status.HTTP_400_BAD_REQUEST,
                )

            # 构建请求体
            payload = {"data": data, "config": {"steps": steps}}
            proxy_timeout_seconds = get_timeseries_predict_timeout_seconds()

            # 发起 HTTP POST 请求
            response = requests.post(
                predict_url,
                json=payload,
                timeout=proxy_timeout_seconds,
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
                    error_message = error_info.get("message") or mlops_message(request, "error.prediction_failed")

                    logger.error(f"预测服务返回失败: serving_id={serving.id}, code={error_code}, message={error_message}")
                    return Response(
                        {
                            "error": error_message,
                            "code": error_code,
                            "error_code": error_code,
                            "details": error_info.get("details"),
                        },
                        status=status.HTTP_400_BAD_REQUEST,
                    )

                # 预测成功
                return Response(result)
            else:
                error_msg = mlops_message(request, "error.serving_prediction_service_error", status_code=response.status_code)
                logger.error(f"{error_msg}, serving_id={serving.id}")
                return Response(
                    {"error": error_msg, "detail": response.text},
                    status=map_predict_upstream_status(response.status_code),
                )

        except requests.exceptions.Timeout:
            logger.error(f"预测超时: serving_id={serving.id}, url={predict_url}")
            return Response(
                {
                    "error": mlops_message(
                        request,
                        "error.serving_prediction_timeout_exceeded",
                        seconds=proxy_timeout_seconds,
                    )
                },
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

        Args:
            serving: TimeSeriesPredictServing 实例

        Returns:
            str: MLflow model URI，如 "models:/TimeseriesPredict_Prophet_1/28"

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


class TimeSeriesPredictDatasetReleaseViewSet(ModelViewSet):
    queryset = TimeSeriesPredictDatasetRelease.objects.select_related("dataset").all()
    serializer_class = TimeSeriesPredictDatasetReleaseSerializer
    pagination_class = CustomPageNumberPagination
    filterset_class = TimeSeriesPredictDatasetReleaseFilter
    ordering = ("-id",)
    permission_key = "dataset.timeseries_predict_dataset_release"

    def get_queryset(self):
        return filter_queryset_by_parent_team(super().get_queryset(), self.request, "dataset__team")

    @HasPermission("timeseries_predict-View")
    def list(self, request, *args, **kwargs):
        return super().list(request, *args, **kwargs)

    @HasPermission("timeseries_predict-View")
    def retrieve(self, request, *args, **kwargs):
        return super().retrieve(request, *args, **kwargs)

    @HasPermission("timeseries_predict-Delete")
    def destroy(self, request, *args, **kwargs):
        return super().destroy(request, *args, **kwargs)

    @HasPermission("timeseries_predict-Add")
    def create(self, request, *args, **kwargs):
        return super().create(request, *args, **kwargs)

    @HasPermission("timeseries_predict-Edit")
    def update(self, request, *args, **kwargs):
        return super().update(request, *args, **kwargs)

    @action(detail=True, methods=["get"], url_path="download")
    @HasPermission("timeseries_predict-View")
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
    @HasPermission("timeseries_predict-Edit")
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
    @HasPermission("timeseries_predict-Edit")
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


class TimeSeriesPredictAlgorithmConfigViewSet(ModelViewSet):
    """时序预测算法配置视图集"""

    queryset = AlgorithmConfig.objects.filter(algorithm_type="timeseries_predict")
    serializer_class = AlgorithmConfigSerializer
    filterset_class = AlgorithmConfigFilter
    pagination_class = CustomPageNumberPagination
    ordering = ("id",)
    permission_key = "algorithm.timeseries_predict_algorithm_config"

    def get_serializer_class(self):
        if self.action == "list" and not self.request.query_params.get("include_form_config", "false").lower() == "true":
            return AlgorithmConfigListSerializer
        return AlgorithmConfigSerializer

    @HasPermission("timeseries_predict-View")
    def list(self, request, *args, **kwargs):
        return super().list(request, *args, **kwargs)

    @HasPermission("timeseries_predict-View")
    def retrieve(self, request, *args, **kwargs):
        return super().retrieve(request, *args, **kwargs)

    @HasPermission("timeseries_predict-Add")
    def create(self, request, *args, **kwargs):
        request.data["algorithm_type"] = "timeseries_predict"
        return super().create(request, *args, **kwargs)

    @HasPermission("timeseries_predict-Edit")
    def update(self, request, *args, **kwargs):
        return super().update(request, *args, **kwargs)

    @HasPermission("timeseries_predict-Edit")
    def partial_update(self, request, *args, **kwargs):
        instance = self.get_object()
        is_active_new = request.data.get("is_active")
        if instance.is_active and is_active_new is False:
            task_count = TimeSeriesPredictTrainJob.objects.filter(algorithm=instance.name).count()
            if task_count > 0:
                return Response(
                    {
                        "error": mlops_message(request, "error.algorithm_in_use_cannot_disable", task_count=task_count),
                        "task_count": task_count,
                    },
                    status=status.HTTP_400_BAD_REQUEST,
                )
        return super().partial_update(request, *args, **kwargs)

    @HasPermission("timeseries_predict-Delete")
    def destroy(self, request, *args, **kwargs):
        instance = self.get_object()
        task_count = TimeSeriesPredictTrainJob.objects.filter(algorithm=instance.name).count()
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
    @HasPermission("timeseries_predict-View")
    def by_type(self, request):
        queryset = self.get_queryset().filter(is_active=True)
        serializer = AlgorithmConfigSerializer(queryset, many=True)
        return Response(serializer.data)

    @action(detail=False, methods=["get"], url_path="get_image")
    @HasPermission("timeseries_predict-View")
    def get_image(self, request):
        name = request.query_params.get("name")
        if not name:
            return Response({"error": mlops_message(request, "error.algorithm_name_required")}, status=400)
        try:
            config = AlgorithmConfig.objects.get(algorithm_type="timeseries_predict", name=name, is_active=True)
            return Response({"image": config.image})
        except AlgorithmConfig.DoesNotExist:
            return Response({"error": mlops_message(request, "error.algorithm_config_not_found", algorithm=f"timeseries_predict/{name}")}, status=404)
