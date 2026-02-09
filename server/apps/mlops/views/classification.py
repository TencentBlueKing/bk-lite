from config.drf.viewsets import ModelViewSet
from rest_framework import status
from rest_framework.decorators import action
from rest_framework.response import Response
from django.http import FileResponse
import os
import requests
import pandas as pd
import numpy as np
import json

from apps.core.logger import mlops_logger as logger
from apps.core.decorators.api_permission import HasPermission
from apps.mlops.models.classification import *
from apps.mlops.serializers.classification import *
from apps.mlops.filters.classification import *
from config.drf.pagination import CustomPageNumberPagination
from apps.mlops.utils.webhook_client import (
    WebhookClient,
    WebhookError,
    WebhookConnectionError,
    WebhookTimeoutError,
)
from apps.mlops.utils import mlflow_service
from apps.mlops.services import (
    get_image_by_prefix,
    get_mlflow_train_config,
    get_mlflow_tracking_uri,
    ConfigurationError,
)
from apps.mlops.constants import TrainJobStatus, MLflowRunStatus
from apps.mlops.models import AlgorithmConfig
from apps.mlops.serializers.algorithm_config import (
    AlgorithmConfigSerializer,
    AlgorithmConfigListSerializer,
)
from apps.mlops.filters.algorithm_config import AlgorithmConfigFilter


class ClassificationDatasetViewSet(ModelViewSet):
    queryset = ClassificationDataset.objects.all()
    serializer_class = ClassificationDatasetSerializer
    pagination_class = CustomPageNumberPagination
    filterset_class = ClassificationDatasetFilter
    ordering = ("-id",)
    permission_key = "dataset.classification_dataset"

    @HasPermission("classification-View")
    def list(self, request, *args, **kwargs):
        return super().list(request, *args, **kwargs)

    @HasPermission("classification-View")
    def retrieve(self, request, *args, **kwargs):
        return super().retrieve(request, *args, **kwargs)

    @HasPermission("classification-Delete")
    def destroy(self, request, *args, **kwargs):
        return super().destroy(request, *args, **kwargs)

    @HasPermission("classification-Add")
    def create(self, request, *args, **kwargs):
        return super().create(request, *args, **kwargs)

    @HasPermission("classification-Edit")
    def update(self, request, *args, **kwargs):
        return super().update(request, *args, **kwargs)


class ClassificationServingViewSet(ModelViewSet):
    queryset = ClassificationServing.objects.select_related(
        "train_job", "train_job__dataset_version", "train_job__dataset_version__dataset"
    ).all()
    serializer_class = ClassificationServingSerializer
    pagination_class = CustomPageNumberPagination
    filterset_class = ClassificationServingFilter
    ordering = ("-id",)
    permission_key = "dataset.classification_serving"

    MLFLOW_PREFIX = "Classification"  # MLflow 命名前缀

    @HasPermission("classification-View")
    def list(self, request, *args, **kwargs):
        """列表查询，实时同步容器状态"""
        response = super().list(request, *args, **kwargs)

        if isinstance(response.data, dict):
            servings = response.data.get("items", [])
        else:
            servings = response.data

        if not servings:
            return response

        serving_ids = [f"Classification_Serving_{s['id']}" for s in servings]

        try:
            # 批量查询容器状态
            result = WebhookClient.get_status(serving_ids)
            status_map = {s.get("id"): s for s in result}

            # 批量获取所有需要更新的对象（避免N+1查询）
            serving_id_list = [s["id"] for s in servings]
            serving_objs = ClassificationServing.objects.filter(id__in=serving_id_list)
            serving_obj_map = {obj.id: obj for obj in serving_objs}

            updates = []
            for serving_data in servings:
                serving_id = f"Classification_Serving_{serving_data['id']}"
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
                ClassificationServing.objects.bulk_update(updates, ["container_info"])

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

    @HasPermission("classification-View")
    def retrieve(self, request, *args, **kwargs):
        """详情查询，实时同步容器状态"""
        response = super().retrieve(request, *args, **kwargs)

        serving_id = f"Classification_Serving_{response.data['id']}"

        try:
            result = WebhookClient.get_status([serving_id])
            container_info = result[0] if result else None

            if container_info:
                response.data["container_info"] = container_info

                # 更新数据库
                ClassificationServing.objects.filter(id=response.data["id"]).update(
                    container_info=container_info
                )
            else:
                response.data["container_info"] = {
                    "status": "error",
                    "state": "unknown",
                    "message": "webhookd 未返回容器状态",
                }

        except WebhookError as e:
            logger.error(f"查询容器状态失败: {e}")
            old_info = response.data.get("container_info") or {}
            response.data["container_info"] = {
                **old_info,
                "status": "error",
                "_query_failed": True,
                "_error": str(e),
            }

        return response

    @HasPermission("classification-Delete")
    def destroy(self, request, *args, **kwargs):
        return super().destroy(request, *args, **kwargs)

    @HasPermission("classification-Add")
    def create(self, request, *args, **kwargs):
        """创建 serving 服务并自动启动容器"""
        response = super().create(request, *args, **kwargs)
        serving_id = response.data["id"]

        try:
            serving = ClassificationServing.objects.get(id=serving_id)

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
            container_id = f"Classification_Serving_{serving.id}"

            logger.info(
                f"自动启动 serving 服务: {container_id}, Model URI: {model_uri}, Port: {serving.port or 'auto'}"
            )

            try:
                # 动态获取推理镜像
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
                )

                serving.container_info = result
                serving.save(update_fields=["container_info"])

                logger.info(
                    f"Serving 服务已自动启动: {container_id}, Port: {result.get('port')}"
                )

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

    @HasPermission("classification-Edit")
    def update(self, request, *args, **kwargs):
        return super().update(request, *args, **kwargs)

    @action(detail=True, methods=["post"], url_path="start")
    @HasPermission("classification-Start")
    def start(self, request, *args, **kwargs):
        """
        启动 serving 服务
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
            serving_id = f"Classification_Serving_{serving.id}"

            logger.info(
                f"启动 serving 服务: {serving_id}, Model URI: {model_uri}, Port: {serving.port or 'auto'}"
            )

            try:
                # 动态获取推理镜像
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

                        # 仅更新容器信息
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
    @HasPermission("classification-Stop")
    def stop(self, request, *args, **kwargs):
        """
        停止 serving 服务（停止并删除容器）
        """
        try:
            serving = self.get_object()

            # 构建 serving ID
            serving_id = f"Classification_Serving_{serving.id}"

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
    @HasPermission("classification-Remove")
    def remove(self, request, *args, **kwargs):
        """
        删除 serving 容器（可处理运行中的容器）
        """
        try:
            serving = self.get_object()

            # 构建 serving ID
            serving_id = f"Classification_Serving_{serving.id}"

            logger.info(f"删除 serving 容器: {serving_id}")

            # 调用 WebhookClient 删除容器
            result = WebhookClient.remove(serving_id)

            # 更新容器信息
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

    def _resolve_model_uri(self, serving):
        """
        解析 MLflow Model URI

        Args:
            serving: ClassificationServing 实例

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

        # 默认使用 'latest' 版本
        return mlflow_service.resolve_model_uri(model_name, "latest")

    @action(detail=True, methods=["post"], url_path="predict")
    @HasPermission("classification-Predict")
    def predict(self, request, *args, **kwargs):
        """
        调用 serving 服务进行分类预测
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

            # 获取实际运行端口，防御性处理 container_info 为空的情况
            port = (serving.container_info or {}).get("port")
            if not port:
                return Response(
                    {"error": "服务端口未配置，请确认服务已启动"},
                    status=status.HTTP_400_BAD_REQUEST,
                )

            # 构建预测服务 URL
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
                except (ValueError, json.JSONDecodeError) as e:
                    logger.warning(f"Failed to parse error response JSON: {e}")
                    error_msg = f"{error_msg} - {response.text[:200]}"

                logger.error(f"预测失败: {error_msg}")
                return Response(
                    {"error": error_msg}, status=status.HTTP_500_INTERNAL_SERVER_ERROR
                )

        except requests.exceptions.Timeout:
            error_msg = f"预测请求超时（超过 60 秒）"
            logger.error(f"预测超时: serving_id={serving.id}")
            return Response(
                {"error": error_msg}, status=status.HTTP_504_GATEWAY_TIMEOUT
            )
        except requests.exceptions.ConnectionError as e:
            error_msg = f"无法连接预测服务: {str(e)}"
            logger.error(f"预测连接失败: serving_id={serving.id}, error={e}")
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


class ClassificationTrainDataViewSet(ModelViewSet):
    queryset = ClassificationTrainData.objects.select_related("dataset").all()
    serializer_class = ClassificationTrainDataSerializer
    pagination_class = CustomPageNumberPagination
    filterset_class = ClassificationTrainDataFilter
    ordering = ("-id",)
    permission_key = "dataset.classification_train_data"

    @HasPermission("classification-View")
    def list(self, request, *args, **kwargs):
        return super().list(request, *args, **kwargs)

    @HasPermission("classification-View")
    def retrieve(self, request, *args, **kwargs):
        return super().retrieve(request, *args, **kwargs)

    @HasPermission("classification-Delete")
    def destroy(self, request, *args, **kwargs):
        return super().destroy(request, *args, **kwargs)

    @HasPermission("classification-Add")
    def create(self, request, *args, **kwargs):
        return super().create(request, *args, **kwargs)

    @HasPermission("classification-Edit")
    def update(self, request, *args, **kwargs):
        return super().update(request, *args, **kwargs)


class ClassificationTrainJobViewSet(ModelViewSet):
    queryset = ClassificationTrainJob.objects.select_related(
        "dataset_version", "dataset_version__dataset"
    ).all()
    serializer_class = ClassificationTrainJobSerializer
    pagination_class = CustomPageNumberPagination
    filterset_class = ClassificationTrainJobFilter
    ordering = ("-id",)
    permission_key = "dataset.classification_train_job"

    MLFLOW_PREFIX = "Classification"  # MLflow 命名前缀

    @HasPermission("classification-View")
    def list(self, request, *args, **kwargs):
        return super().list(request, *args, **kwargs)

    @HasPermission("classification-View")
    def retrieve(self, request, *args, **kwargs):
        return super().retrieve(request, *args, **kwargs)

    @HasPermission("classification-Delete")
    def destroy(self, request, *args, **kwargs):
        return super().destroy(request, *args, **kwargs)

    @HasPermission("classification-Add")
    def create(self, request, *args, **kwargs):
        return super().create(request, *args, **kwargs)

    @HasPermission("classification-Edit")
    def update(self, request, *args, **kwargs):
        return super().update(request, *args, **kwargs)

    @action(detail=True, methods=["post"], url_path="train")
    @HasPermission("classification-Train")
    def train(self, request, pk=None):
        """
        启动训练任务
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

            logger.info(f"启动训练任务: {job_id}")
            logger.info(f"  Dataset: {train_job.dataset_version.dataset_file.name}")
            logger.info(f"  Config: {train_job.config_url.name}")

            # 调用 WebhookClient 启动训练
            # 动态获取训练镜像
            train_image = get_image_by_prefix(self.MLFLOW_PREFIX, train_job.algorithm)

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

            # 更新任务状态
            train_job.status = TrainJobStatus.RUNNING
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

    @action(detail=True, methods=["get"], url_path="runs_data_list")
    @HasPermission("classification-View")
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
                    logger.info(
                        f"自动同步 TrainJob {train_job.id} 状态: running -> {new_status} (基于 MLflow: {latest_run_status})"
                    )

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
    @HasPermission("classification-View")
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
    @HasPermission("classification-View")
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
    @HasPermission("classification-View")
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
    @HasPermission("classification-View")
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
    @HasPermission("classification-View")
    def download_model(self, request, run_id: str):
        """
        从 MLflow 下载模型并直接返回 ZIP 文件
        """
        try:
            # 获取 run 信息（用于文件命名）
            run = mlflow_service.get_run_info(run_id)
            run_name = run.data.tags.get("mlflow.runName", run_id)

            # 下载并打包模型
            zip_buffer = mlflow_service.download_model_artifact(run_id)

            # 构建文件名
            filename = f"Classification_{run_name}_{run_id[:8]}.zip"

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


class ClassificationDatasetReleaseViewSet(ModelViewSet):
    """分类数据集发布版本视图集"""

    queryset = ClassificationDatasetRelease.objects.select_related("dataset").all()
    serializer_class = ClassificationDatasetReleaseSerializer
    pagination_class = CustomPageNumberPagination
    filterset_class = ClassificationDatasetReleaseFilter
    ordering = ("-id",)
    permission_key = "dataset.classification_dataset_release"

    @HasPermission("classification-View")
    def list(self, request, *args, **kwargs):
        return super().list(request, *args, **kwargs)

    @HasPermission("classification-View")
    def retrieve(self, request, *args, **kwargs):
        return super().retrieve(request, *args, **kwargs)

    @HasPermission("classification-Delete")
    def destroy(self, request, *args, **kwargs):
        return super().destroy(request, *args, **kwargs)

    @HasPermission("classification-Add")
    def create(self, request, *args, **kwargs):
        return super().create(request, *args, **kwargs)

    @HasPermission("classification-Edit")
    def update(self, request, *args, **kwargs):
        return super().update(request, *args, **kwargs)

    @action(detail=True, methods=["get"], url_path="download")
    @HasPermission("classification-View")
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


class ClassificationAlgorithmConfigViewSet(ModelViewSet):
    """文本分类算法配置视图集"""

    queryset = AlgorithmConfig.objects.filter(algorithm_type="classification")
    serializer_class = AlgorithmConfigSerializer
    filterset_class = AlgorithmConfigFilter
    pagination_class = CustomPageNumberPagination
    ordering = ("id",)
    permission_key = "algorithm.classification_algorithm_config"

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

    @HasPermission("classification-View")
    def list(self, request, *args, **kwargs):
        return super().list(request, *args, **kwargs)

    @HasPermission("classification-View")
    def retrieve(self, request, *args, **kwargs):
        return super().retrieve(request, *args, **kwargs)

    @HasPermission("classification-Add")
    def create(self, request, *args, **kwargs):
        request.data["algorithm_type"] = "classification"
        return super().create(request, *args, **kwargs)

    @HasPermission("classification-Edit")
    def update(self, request, *args, **kwargs):
        return super().update(request, *args, **kwargs)

    @HasPermission("classification-Edit")
    def partial_update(self, request, *args, **kwargs):
        instance = self.get_object()
        is_active_new = request.data.get("is_active")
        if instance.is_active and is_active_new is False:
            task_count = ClassificationTrainJob.objects.filter(
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

    @HasPermission("classification-Delete")
    def destroy(self, request, *args, **kwargs):
        instance = self.get_object()
        task_count = ClassificationTrainJob.objects.filter(
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
    @HasPermission("classification-View")
    def by_type(self, request):
        queryset = self.get_queryset().filter(is_active=True)
        serializer = AlgorithmConfigSerializer(queryset, many=True)
        return Response(serializer.data)

    @action(detail=False, methods=["get"], url_path="get_image")
    @HasPermission("classification-View")
    def get_image(self, request):
        name = request.query_params.get("name")
        if not name:
            return Response({"error": "name 参数必填"}, status=400)
        try:
            config = AlgorithmConfig.objects.get(
                algorithm_type="classification", name=name, is_active=True
            )
            return Response({"image": config.image})
        except AlgorithmConfig.DoesNotExist:
            return Response(
                {"error": f"未找到算法配置: classification/{name}"}, status=404
            )
