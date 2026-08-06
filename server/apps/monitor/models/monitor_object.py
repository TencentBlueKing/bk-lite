from django.db import models
from django.core.validators import MaxValueValidator, MinValueValidator

from apps.core.models.maintainer_info import MaintainerInfo
from apps.core.models.time_info import TimeInfo


class MonitorObjectType(TimeInfo, MaintainerInfo):
    """监控对象分类"""
    id = models.CharField(primary_key=True, max_length=100, verbose_name='分类ID')
    name = models.CharField(max_length=100, blank=True, default='', verbose_name='分类名称')
    description = models.TextField(blank=True, verbose_name='分类描述')
    order = models.IntegerField(default=999, db_index=True, verbose_name='排序')

    class Meta:
        verbose_name = '监控对象分类'
        verbose_name_plural = '监控对象分类'
        ordering = ['order', 'id']


class MonitorObject(TimeInfo, MaintainerInfo):
    LEVEL_CHOICES = [('base', 'Base'), ('derivative', 'Derivative')]
    CLEANUP_POLICY_NO_CLEANUP = "no_cleanup"
    CLEANUP_POLICY_TIMEOUT = "timeout"
    CLEANUP_POLICY_CHOICES = [
        (CLEANUP_POLICY_NO_CLEANUP, "No cleanup"),
        (CLEANUP_POLICY_TIMEOUT, "Timeout cleanup"),
    ]
    CLEANUP_TIMEOUT_UNIT_DAY = "day"
    CLEANUP_TIMEOUT_UNIT_HOUR = "hour"
    CLEANUP_TIMEOUT_UNIT_MINUTE = "minute"
    CLEANUP_TIMEOUT_UNIT_CHOICES = [
        (CLEANUP_TIMEOUT_UNIT_MINUTE, "Minute"),
        (CLEANUP_TIMEOUT_UNIT_HOUR, "Hour"),
        (CLEANUP_TIMEOUT_UNIT_DAY, "Day"),
    ]
    CLEANUP_TIMEOUT_MAX_BY_UNIT = {
        CLEANUP_TIMEOUT_UNIT_MINUTE: 1440,
        CLEANUP_TIMEOUT_UNIT_HOUR: 720,
        CLEANUP_TIMEOUT_UNIT_DAY: 365,
    }
    CLEANUP_TIMEOUT_UNIT_LABELS = {
        CLEANUP_TIMEOUT_UNIT_MINUTE: "分钟",
        CLEANUP_TIMEOUT_UNIT_HOUR: "小时",
        CLEANUP_TIMEOUT_UNIT_DAY: "天",
    }
    CLEANUP_TIMEOUT_SECONDS_BY_UNIT = {
        CLEANUP_TIMEOUT_UNIT_MINUTE: 60,
        CLEANUP_TIMEOUT_UNIT_HOUR: 60 * 60,
        CLEANUP_TIMEOUT_UNIT_DAY: 24 * 60 * 60,
    }

    name = models.CharField(unique=True, max_length=100, verbose_name='监控对象')
    display_name = models.CharField(max_length=100, blank=True, default='', verbose_name='监控对象显示名称')
    icon = models.CharField(max_length=100, default="", verbose_name='监控对象图标')
    type = models.ForeignKey(
        MonitorObjectType,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        db_column='type',
        related_name='monitor_objects',
        verbose_name='监控对象分类'
    )
    order = models.IntegerField(default=999, db_index=True, verbose_name='监控对象排序')
    level = models.CharField(default="base", max_length=50, verbose_name='监控对象级别')
    parent = models.ForeignKey('self', on_delete=models.CASCADE, null=True, blank=True, related_name='children', verbose_name='父级监控对象')
    description = models.TextField(blank=True, verbose_name='监控对象描述')
    default_metric = models.TextField(blank=True, verbose_name='默认指标')
    instance_id_keys = models.JSONField(default=list, verbose_name='联合唯一实例ID键列表')
    supplementary_indicators = models.JSONField(default=list, verbose_name='对象实例补充指标')
    is_visible = models.BooleanField(default=True, verbose_name='是否可见')
    display_fields = models.JSONField(default=list, verbose_name='视图列表展示列配置')
    display_fields_customized = models.BooleanField(default=False, verbose_name='展示列是否被用户自定义')
    instance_summary_columns = models.JSONField(default=list, verbose_name='实例摘要列')
    is_builtin = models.BooleanField(default=False, db_index=True, verbose_name='是否为内置对象')
    cleanup_policy = models.CharField(
        max_length=20,
        choices=CLEANUP_POLICY_CHOICES,
        default=CLEANUP_POLICY_NO_CLEANUP,
        verbose_name='自动发现资产清理策略',
    )
    cleanup_timeout_days = models.PositiveSmallIntegerField(
        default=1,
        validators=[MinValueValidator(1), MaxValueValidator(1440)],
        verbose_name='自动发现资产超时清理时长数值',
    )
    cleanup_timeout_unit = models.CharField(
        max_length=10,
        choices=CLEANUP_TIMEOUT_UNIT_CHOICES,
        default=CLEANUP_TIMEOUT_UNIT_DAY,
        verbose_name='自动发现资产超时清理时长单位',
    )
    cleanup_policy_effective_at = models.DateTimeField(null=True, blank=True, verbose_name='清理策略生效时间')
    last_discovery_success_at = models.DateTimeField(null=True, blank=True, verbose_name='最近一次自动发现查询成功时间')

    class Meta:
        verbose_name = '监控对象'
        verbose_name_plural = '监控对象'
        ordering = ['type__order', 'order', 'id']

    @property
    def cleanup_timeout_value(self):
        """新 API 的时长数值；底层列名为兼容旧版本暂保留 days 后缀。"""
        return self.cleanup_timeout_days

    @property
    def cleanup_timeout_seconds(self):
        return self.cleanup_timeout_days * self.CLEANUP_TIMEOUT_SECONDS_BY_UNIT[self.cleanup_timeout_unit]


class MonitorInstance(TimeInfo, MaintainerInfo):
    id = models.CharField(primary_key=True, max_length=200, verbose_name='监控对象实例ID')
    name = models.CharField(db_index=True, max_length=200, default="", verbose_name='监控对象实例名称')
    interval = models.IntegerField(default=60, verbose_name='监控实例采集间隔(s)')
    monitor_object = models.ForeignKey(MonitorObject, on_delete=models.CASCADE, verbose_name='监控对象')
    auto = models.BooleanField(default=False, verbose_name='是否自动发现')
    is_deleted = models.BooleanField(db_index=True, default=False, verbose_name='是否删除')
    is_active = models.BooleanField(default=True)
    cloud_region_id = models.IntegerField(null=True, blank=True, db_index=True, verbose_name='云区域ID')
    ip = models.GenericIPAddressField(null=True, blank=True, verbose_name='接入IP')
    node_id = models.CharField(
        max_length=100,
        null=True,
        blank=True,
        unique=True,
        db_index=True,
        verbose_name='关联节点ID',
    )
    cmdb_id = models.CharField(
        max_length=100,
        null=True,
        blank=True,
        unique=True,
        db_index=True,
        verbose_name='关联CMDB实例ID',
    )
    summary_facts = models.JSONField(default=dict, verbose_name='实例摘要事实')
    fallback_sampling_rate = models.IntegerField(default=1000, verbose_name='兜底采样率')
    enabled_protocols = models.JSONField(default=list, verbose_name='已启用的Flow协议')
    last_seen_at = models.DateTimeField(null=True, blank=True, db_index=True, verbose_name='自动发现最近上报时间')
    missing_duration_seconds = models.PositiveIntegerField(default=0, verbose_name='确认无上报累计时长')

    class Meta:
        verbose_name = '监控对象实例'
        verbose_name_plural = '监控对象实例'


class MonitorInstanceOrganization(TimeInfo, MaintainerInfo):
    monitor_instance = models.ForeignKey(MonitorInstance, on_delete=models.CASCADE, verbose_name='监控对象实例')
    organization = models.IntegerField(verbose_name='组织id')

    class Meta:
        verbose_name = '监控对象实例组织'
        verbose_name_plural = '监控对象实例组织'
        unique_together = ('monitor_instance', 'organization')


class MonitorObjectOrganizationRule(TimeInfo, MaintainerInfo):
    monitor_object = models.ForeignKey(MonitorObject, on_delete=models.CASCADE, verbose_name='监控对象')
    name = models.CharField(max_length=100, verbose_name='分组规则名称')
    organizations = models.JSONField(default=list, verbose_name='所属组织')
    rule = models.JSONField(default=dict, verbose_name='分组规则详情')
    is_active = models.BooleanField(default=True, verbose_name='是否启用')
    monitor_instance_id = models.CharField(db_index=True, max_length=200, default="", verbose_name='关联监控对象实例ID')
