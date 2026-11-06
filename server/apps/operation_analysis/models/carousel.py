"""运营分析轮播列表。

独立资源，不进入画布类型登记，也不挂目录。条目只保存画布引用。
"""

from django.core.validators import MaxValueValidator, MinValueValidator
from django.db import models

from apps.core.models.group_info import Groups
from apps.core.models.maintainer_info import MaintainerInfo
from apps.core.models.time_info import TimeInfo

CAROUSEL_RESOURCE_TYPES = (
    ("dashboard", "仪表盘"),
    ("topology", "拓扑图"),
    ("architecture", "架构图"),
    ("screen", "大屏"),
    ("report", "报表"),
    ("networkTopology", "网络拓扑"),
)

CAROUSEL_DWELL_MIN_SECONDS = 5
CAROUSEL_DWELL_MAX_SECONDS = 300
CAROUSEL_DEFAULT_DWELL_SECONDS = 30
CAROUSEL_MAX_ITEMS = 50

_DWELL_VALIDATORS = [
    MinValueValidator(CAROUSEL_DWELL_MIN_SECONDS),
    MaxValueValidator(CAROUSEL_DWELL_MAX_SECONDS),
]


class CanvasCarousel(MaintainerInfo, TimeInfo, Groups):
    name = models.CharField(max_length=128, verbose_name="轮播名称", db_index=True)
    desc = models.TextField(verbose_name="描述", blank=True, null=True)
    default_dwell_seconds = models.PositiveIntegerField(
        default=CAROUSEL_DEFAULT_DWELL_SECONDS,
        validators=_DWELL_VALIDATORS,
        verbose_name="默认停留时长（秒）",
    )

    class Meta:
        db_table = "operation_analysis_canvas_carousel"
        verbose_name = "轮播列表"
        constraints = [
            models.CheckConstraint(
                check=models.Q(
                    default_dwell_seconds__gte=CAROUSEL_DWELL_MIN_SECONDS,
                    default_dwell_seconds__lte=CAROUSEL_DWELL_MAX_SECONDS,
                ),
                name="canvas_carousel_dwell_range",
            ),
        ]

    def __str__(self):
        return self.name


class CanvasCarouselItem(models.Model):
    carousel = models.ForeignKey(
        CanvasCarousel,
        on_delete=models.CASCADE,
        related_name="items",
        verbose_name="轮播列表",
    )
    resource_type = models.CharField(max_length=32, choices=CAROUSEL_RESOURCE_TYPES, verbose_name="画布类型")
    canvas_id = models.PositiveIntegerField(verbose_name="画布 ID")
    dwell_seconds = models.PositiveIntegerField(
        null=True,
        blank=True,
        validators=_DWELL_VALIDATORS,
        verbose_name="停留时长覆盖（秒）",
    )
    position = models.PositiveIntegerField(default=0, verbose_name="顺序")

    class Meta:
        db_table = "operation_analysis_canvas_carousel_item"
        verbose_name = "轮播条目"
        ordering = ["position", "id"]
        indexes = [
            models.Index(fields=["carousel", "position"], name="op_carousel_item_order_idx"),
            models.Index(fields=["resource_type", "canvas_id"], name="op_carousel_item_canvas_idx"),
        ]
        constraints = [
            models.CheckConstraint(
                check=models.Q(dwell_seconds__isnull=True)
                | models.Q(
                    dwell_seconds__gte=CAROUSEL_DWELL_MIN_SECONDS,
                    dwell_seconds__lte=CAROUSEL_DWELL_MAX_SECONDS,
                ),
                name="canvas_carousel_item_dwell_range",
            ),
        ]

    def resolved_dwell_seconds(self):
        if self.dwell_seconds is None:
            return self.carousel.default_dwell_seconds
        return self.dwell_seconds
