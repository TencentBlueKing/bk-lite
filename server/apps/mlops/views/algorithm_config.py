from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework import status

from config.drf.viewsets import ModelViewSet
from config.drf.pagination import CustomPageNumberPagination
from apps.core.decorators.api_permission import HasPermission
from apps.core.logger import mlops_logger as logger
from apps.mlops.models import AlgorithmConfig
from apps.mlops.models.anomaly_detection import AnomalyDetectionTrainJob
from apps.mlops.models.timeseries_predict import TimeSeriesPredictTrainJob
from apps.mlops.models.log_clustering import LogClusteringTrainJob
from apps.mlops.models.classification import ClassificationTrainJob
from apps.mlops.models.image_classification import ImageClassificationTrainJob
from apps.mlops.models.object_detection import ObjectDetectionTrainJob
from apps.mlops.serializers.algorithm_config import (
    AlgorithmConfigSerializer,
    AlgorithmConfigListSerializer,
)
from apps.mlops.filters.algorithm_config import AlgorithmConfigFilter


# 算法类型到训练任务模型的映射
ALGORITHM_TYPE_TO_TRAIN_JOB_MODEL = {
    "anomaly_detection": AnomalyDetectionTrainJob,
    "timeseries_predict": TimeSeriesPredictTrainJob,
    "log_clustering": LogClusteringTrainJob,
    "classification": ClassificationTrainJob,
    "image_classification": ImageClassificationTrainJob,
    "object_detection": ObjectDetectionTrainJob,
}

# 统一的算法配置管理，algorithm_type区分不同类型
class AlgorithmConfigViewSet(ModelViewSet):
    """算法配置视图集"""

    queryset = AlgorithmConfig.objects.all()
    serializer_class = AlgorithmConfigSerializer
    filterset_class = AlgorithmConfigFilter
    pagination_class = CustomPageNumberPagination
    ordering = ("algorithm_type", "id")
    permission_key = "algorithm.algorithm_config"

    def get_serializer_class(self):
        """根据 action 返回不同的序列化器"""
        if (
            self.action == "list"
            and not self.request.query_params.get(
                "include_form_config", "false"
            ).lower()
            == "true"
        ):
            return AlgorithmConfigListSerializer
        return AlgorithmConfigSerializer

    @HasPermission("algorithm_config-View")
    def list(self, request, *args, **kwargs):
        return super().list(request, *args, **kwargs)

    @HasPermission("algorithm_config-View")
    def retrieve(self, request, *args, **kwargs):
        return super().retrieve(request, *args, **kwargs)

    @HasPermission("algorithm_config-Add")
    def create(self, request, *args, **kwargs):
        return super().create(request, *args, **kwargs)

    @HasPermission("algorithm_config-Edit")
    def update(self, request, *args, **kwargs):
        return super().update(request, *args, **kwargs)

    @HasPermission("algorithm_config-Edit")
    def partial_update(self, request, *args, **kwargs):
        """
        部分更新算法配置

        当禁用算法（is_active 从 True 变为 False）时，
        校验是否有训练任务正在使用该算法
        """
        instance = self.get_object()
        is_active_new = request.data.get("is_active")

        # 如果是禁用操作（从 True 变为 False）
        if instance.is_active and is_active_new is False:
            # 查询使用该算法的任务数量
            task_count = self._count_tasks_using_algorithm(
                instance.algorithm_type, instance.name
            )
            if task_count > 0:
                return Response(
                    {
                        "error": f"无法禁用：有 {task_count} 个训练任务正在使用此算法",
                        "task_count": task_count,
                    },
                    status=status.HTTP_400_BAD_REQUEST,
                )

        return super().partial_update(request, *args, **kwargs)

    def _count_tasks_using_algorithm(
        self, algorithm_type: str, algorithm_name: str
    ) -> int:
        """
        统计使用指定算法的训练任务数量

        Args:
            algorithm_type: 算法类型（如 anomaly_detection）
            algorithm_name: 算法名称（如 RandomForest）

        Returns:
            使用该算法的任务数量
        """
        train_job_model = ALGORITHM_TYPE_TO_TRAIN_JOB_MODEL.get(algorithm_type)
        if not train_job_model:
            logger.warning(f"未知的算法类型: {algorithm_type}")
            return 0

        return train_job_model.objects.filter(algorithm=algorithm_name).count()

    @HasPermission("algorithm_config-Delete")
    def destroy(self, request, *args, **kwargs):
        """
        删除算法配置

        删除前校验是否有训练任务正在使用该算法
        """
        instance = self.get_object()

        # 查询使用该算法的任务数量
        task_count = self._count_tasks_using_algorithm(
            instance.algorithm_type, instance.name
        )
        if task_count > 0:
            return Response(
                {
                    "error": f"无法删除：有 {task_count} 个训练任务正在使用此算法",
                    "task_count": task_count,
                },
                status=status.HTTP_400_BAD_REQUEST,
            )

        return super().destroy(request, *args, **kwargs)

    @action(
        detail=False, methods=["get"], url_path="by_type/(?P<algorithm_type>[^/.]+)"
    )
    @HasPermission("algorithm_config-View")
    def by_type(self, request, algorithm_type=None):
        """
        获取指定算法类型的所有启用算法

        用于前端训练表单动态渲染，返回完整配置（包含 form_config）
        仅返回 is_active=True 的记录
        """
        queryset = self.get_queryset().filter(
            algorithm_type=algorithm_type, is_active=True
        )
        # 使用完整序列化器，包含 form_config 用于表单渲染
        serializer = AlgorithmConfigSerializer(queryset, many=True)
        return Response(serializer.data)

    @action(detail=False, methods=["get"], url_path="get_image")
    @HasPermission("algorithm_config-View")
    def get_image(self, request):
        """
        根据 algorithm_type 和 name 获取 Docker 镜像

        用于训练/推理时动态获取镜像地址
        Query params:
        - algorithm_type: 算法类型
        - name: 算法标识
        """
        algorithm_type = request.query_params.get("algorithm_type")
        name = request.query_params.get("name")

        if not algorithm_type or not name:
            return Response(
                {"error": "algorithm_type 和 name 参数必填"},
                status=400,
            )

        try:
            config = AlgorithmConfig.objects.get(
                algorithm_type=algorithm_type, name=name, is_active=True
            )
            return Response({"image": config.image})
        except AlgorithmConfig.DoesNotExist:
            logger.warning(
                f"未找到算法配置: algorithm_type={algorithm_type}, name={name}"
            )
            return Response(
                {"error": f"未找到算法配置: {algorithm_type}/{name}"},
                status=404,
            )
