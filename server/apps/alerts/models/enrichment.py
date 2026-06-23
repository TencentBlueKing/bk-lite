from django.db import models
from django.db.models import JSONField

from apps.core.models.maintainer_info import MaintainerInfo
from apps.core.models.time_info import TimeInfo


class EnrichmentRule(MaintainerInfo, TimeInfo):
    """告警丰富规则：声明式 Lookup 的一条配置。"""

    ON_MULTIPLE_CHOICES = (
        ("first", "取首条"),
        ("merge", "合并"),
        ("list", "列表"),
    )

    name = models.CharField(max_length=100, help_text="规则名称")
    is_active = models.BooleanField(default=True, help_text="是否启用")
    match_rules = JSONField(default=list, help_text="作用范围(OR-of-AND)")
    provider_type = models.CharField(max_length=32, default="cmdb", help_text="数据源类型")
    input_binding = JSONField(default=dict, help_text="入参绑定 provider_param->event_field")
    provider_config = JSONField(default=dict, help_text="Provider 专属配置")
    output_projection = JSONField(default=list, help_text="出参投影 [{source, as}]，空=全取")
    on_multiple = models.CharField(max_length=16, choices=ON_MULTIPLE_CHOICES, default="first", help_text="多结果策略")
    namespace = models.CharField(max_length=64, blank=True, default="", help_text="enrichment 命名空间键")
    team = JSONField(default=list, help_text="关联组织")

    class Meta:
        db_table = "alerts_enrichment_rule"
        verbose_name = "告警丰富规则"
        verbose_name_plural = "告警丰富规则"

    def __str__(self):
        return self.name

    @property
    def resolved_namespace(self) -> str:
        return self.namespace or self.provider_type
