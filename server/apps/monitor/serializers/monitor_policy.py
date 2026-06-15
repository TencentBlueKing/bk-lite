import logging

from rest_framework import serializers

from apps.monitor.constants.alert_policy import AlertConstants
from apps.monitor.models.monitor_policy import MonitorPolicy

logger = logging.getLogger(__name__)

# 阈值条件合法等级 —— 取自 MonitorPolicy.LEVEL_CHOICES 的用户可选档（排除系统在无数据时自动生成的 no_data）
_VALID_THRESHOLD_LEVELS = {"info", "warning", "error", "critical"}
# source 合法类型 —— 其余类型在扫描器/基线构建时静默返回空目标（策略不生效），instance/organization 之外即误配
_VALID_SOURCE_TYPES = {"instance", "organization"}
# 聚合算法合法集合 —— 来源 apps/monitor/tasks/utils/policy_methods.py 的 METHOD 字典键；
# 非法值会在扫描聚合处（metric_query 取 METHOD.get(algorithm)）抛 BaseAppException。改 METHOD 时需同步此集合。
_VALID_AGGREGATION_ALGORITHMS = {
    "sum",
    "avg",
    "max",
    "min",
    "count",
    "max_over_time",
    "min_over_time",
    "avg_over_time",
    "sum_over_time",
    "last_over_time",
}


class MonitorPolicySerializer(serializers.ModelSerializer):
    class Meta:
        model = MonitorPolicy
        fields = "__all__"

    def validate_threshold(self, value):
        """校验阈值列表：每条须含合法 method/value/level，否则后台扫描计算阈值时崩。

        仅校验已填写的阈值条目（空列表=未配阈值，放行）。只挡下游 policy_calculate 一定会
        KeyError/BaseAppException 的非法配置（缺 method/value/level、method 不在合法运算符内），
        把错误从「后台扫描时静默报错」前移到 API 边界，不误伤当前可用配置。
        """
        if not value:
            return value
        if not isinstance(value, list):
            raise serializers.ValidationError("threshold 必须是列表")
        valid_methods = set(AlertConstants.THRESHOLD_METHODS)
        for index, item in enumerate(value):
            if not isinstance(item, dict):
                raise serializers.ValidationError(f"threshold[{index}] 必须是对象")
            if item.get("method") not in valid_methods:
                raise serializers.ValidationError(f"threshold[{index}].method 非法，须为 {sorted(valid_methods)} 之一")
            if "value" not in item:
                raise serializers.ValidationError(f"threshold[{index}] 缺少 value")
            if item.get("level") not in _VALID_THRESHOLD_LEVELS:
                raise serializers.ValidationError(f"threshold[{index}].level 非法，须为 {sorted(_VALID_THRESHOLD_LEVELS)} 之一")
        return value

    def validate_query_condition(self, value):
        """校验查询条件：pmq 自定义查询须带非空 query，否则（指标型）须带 metric_id。

        空 dict（未配/草稿）放行；只挡非空但下游扫描一定会 KeyError（缺 metric_id）或对 None 做
        PromQL 查询（pmq 缺 query）的缺键配置。
        """
        if not value:
            return value
        if not isinstance(value, dict):
            raise serializers.ValidationError("query_condition 必须是对象")
        if value.get("type") == "pmq":
            if not value.get("query"):
                raise serializers.ValidationError("query_condition.type=pmq 时必须提供非空 query")
        elif "metric_id" not in value:
            raise serializers.ValidationError("query_condition 缺少 metric_id")
        return value

    def validate_source(self, value):
        """校验策略适用资源：非空时须含 type 与 values，且 type 为 instance/organization。

        空 dict 放行；缺 type/values 会让扫描器/基线构建 KeyError，未知 type 则静默无目标=策略不生效。
        """
        if not value:
            return value
        if not isinstance(value, dict):
            raise serializers.ValidationError("source 必须是对象")
        if "type" not in value or "values" not in value:
            raise serializers.ValidationError("source 必须同时包含 type 与 values")
        if value.get("type") not in _VALID_SOURCE_TYPES:
            raise serializers.ValidationError(f"source.type 非法，须为 {sorted(_VALID_SOURCE_TYPES)} 之一")
        return value

    def validate_algorithm(self, value):
        """校验聚合算法须为下游支持的聚合函数，否则扫描聚合时抛 BaseAppException。"""
        if value and value not in _VALID_AGGREGATION_ALGORITHMS:
            raise serializers.ValidationError(f"algorithm 非法，须为 {sorted(_VALID_AGGREGATION_ALGORITHMS)} 之一")
        return value

    def validate_group_by(self, value):
        """校验 group_by 首位必须是监控对象的实例主键，防止下游扫描链路误判实例归属。"""
        if not value:
            return value

        monitor_object = self._get_monitor_object()
        if monitor_object is None:
            return value

        instance_id_keys = getattr(monitor_object, "instance_id_keys", None)
        if not instance_id_keys:
            return value

        primary_key = instance_id_keys[0]
        if value[0] != primary_key:
            logger.warning(
                "group_by[0]=%s does not match instance_id_keys[0]=%s, auto-correcting",
                value[0],
                primary_key,
            )
            value = [primary_key] + [k for k in value if k != primary_key]

        return value

    def _get_monitor_object(self):
        """从请求数据或已有实例中获取关联的监控对象。"""
        request_data = self.initial_data if hasattr(self, "initial_data") else {}
        monitor_object_id = request_data.get("monitor_object")

        if monitor_object_id:
            from apps.monitor.models.monitor_object import MonitorObject

            try:
                return MonitorObject.objects.get(pk=monitor_object_id)
            except MonitorObject.DoesNotExist:
                return None

        if self.instance and hasattr(self.instance, "monitor_object"):
            return self.instance.monitor_object

        return None
