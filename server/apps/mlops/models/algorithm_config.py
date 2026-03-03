from django.db import models

from apps.core.models.maintainer_info import MaintainerInfo
from apps.core.models.time_info import TimeInfo


class AlgorithmConfig(MaintainerInfo, TimeInfo):
    """算法配置模型 - 用于动态管理各算法场景的算法和表单配置"""

    ALGORITHM_TYPE_CHOICES = [
        ("anomaly_detection", "异常检测"),
        ("timeseries_predict", "时序预测"),
        ("log_clustering", "日志聚类"),
        ("classification", "文本分类"),
        ("image_classification", "图片分类"),
        ("object_detection", "目标检测"),
    ]

    algorithm_type = models.CharField(
        max_length=50,
        choices=ALGORITHM_TYPE_CHOICES,
        verbose_name="算法类型",
        help_text="算法所属的场景类型",
        db_index=True,
    )

    name = models.CharField(
        max_length=100,
        verbose_name="算法标识",
        help_text="算法的唯一标识，如 ECOD、IForest、XGBoost 等",
    )

    display_name = models.CharField(
        max_length=100,
        verbose_name="显示名称",
        help_text="在前端展示的算法名称",
    )

    scenario_description = models.TextField(
        blank=True,
        default="",
        verbose_name="场景描述",
        help_text="算法适用场景的描述说明",
    )

    image = models.CharField(
        max_length=255,
        verbose_name="Docker 镜像",
        help_text="用于训练和推理的 Docker 镜像地址",
    )

    form_config = models.JSONField(
        default=dict,
        blank=True,
        verbose_name="表单配置",
        help_text="前端动态表单的 JSON 配置，结构遵循 AlgorithmConfig 类型定义",
    )

    is_active = models.BooleanField(
        default=True,
        verbose_name="是否启用",
        help_text="禁用后该算法将不在前端算法选择列表中显示",
        db_index=True,
    )

    class Meta:
        db_table = "mlops_algorithm_config"
        verbose_name = "算法配置"
        verbose_name_plural = "算法配置"
        unique_together = [["algorithm_type", "name"]]
        ordering = ["algorithm_type", "id"]

    def __str__(self):
        return f"{self.get_algorithm_type_display()} - {self.display_name}"
