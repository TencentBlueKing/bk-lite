from rest_framework import serializers

from apps.monitor.models.monitor_metrics import Metric, MetricGroup
from apps.monitor.services.custom_script_plugin import RESERVED_SCRIPT_METRIC_NAME_ERROR, is_reserved_script_metric_name, is_script_collect_type
from apps.monitor.utils.instance_id_keys import resolve_metric_instance_id_keys
from apps.monitor.utils.metric_query_labels import ensure_metric_labels_placeholder

METRIC_BATCH_UPDATE_FIELDS = ("display_name", "metric_group", "unit", "data_type", "description", "dimensions")
METRIC_BATCH_UPDATE_MAX_SIZE = 100
METRIC_BATCH_DELETE_MAX_SIZE = 100
METRIC_DATA_TYPES = ("Number", "Enum")


class MetricGroupSerializer(serializers.ModelSerializer):
    # 这里定义 is_pre 但不给默认值，防止用户传递该字段
    is_pre = serializers.BooleanField(read_only=True)

    class Meta:
        model = MetricGroup
        fields = [
            "id",
            "monitor_object",
            "monitor_plugin",
            "name",
            "description",
            "is_pre",
            "sort_order",
            "created_at",
            "updated_at",
            "created_by",
            "updated_by",
            "domain",
            "updated_by_domain",
        ]

    def validate(self, attrs):
        attrs = super().validate(attrs)
        monitor_object = attrs.get("monitor_object", getattr(self.instance, "monitor_object", None))
        monitor_plugin = attrs.get("monitor_plugin", getattr(self.instance, "monitor_plugin", None))
        name = attrs.get("name", getattr(self.instance, "name", None))

        if monitor_plugin and monitor_plugin.template_type == "api" and not monitor_plugin.template_id:
            raise serializers.ValidationError({"monitor_plugin": "自建API模板配置异常"})

        queryset = MetricGroup.objects.filter(
            monitor_object=monitor_object,
            monitor_plugin=monitor_plugin,
            name=name,
        )
        if self.instance is not None:
            queryset = queryset.exclude(id=self.instance.id)
        if queryset.exists():
            raise serializers.ValidationError({"name": "同模板内指标分组名称不能重复"})

        return attrs

    def create(self, validated_data):
        """
        在创建时，手动设置 is_pre 为 False
        """
        # 手动设置 is_pre 为 False，表示用户创建的数据是非预制的
        validated_data["is_pre"] = False

        # 调用父类的 create 方法
        return super().create(validated_data)


class MetricSerializer(serializers.ModelSerializer):
    # 这里定义 is_pre 但不给默认值，防止用户传递该字段
    is_pre = serializers.BooleanField(read_only=True)
    is_ifmib = serializers.BooleanField(read_only=True)
    monitor_plugin_name = serializers.SerializerMethodField(read_only=True)

    class Meta:
        model = Metric
        fields = [
            "id",
            "monitor_object",
            "monitor_plugin",
            "monitor_plugin_name",
            "metric_group",
            "name",
            "display_name",
            "query",
            "view_query",
            "view_config",
            "unit",
            "data_type",
            "description",
            "dimensions",
            "instance_id_keys",
            "is_ifmib",
            "is_pre",
            "sort_order",
            "created_at",
            "updated_at",
            "created_by",
            "updated_by",
            "domain",
            "updated_by_domain",
        ]

    def _resolve_instance_id_keys(self, attrs, default_metric_keys=None):
        monitor_object = attrs.get("monitor_object", getattr(self.instance, "monitor_object", None))
        monitor_object_keys = getattr(monitor_object, "instance_id_keys", [])
        return resolve_metric_instance_id_keys(
            attrs.get("instance_id_keys", default_metric_keys),
            monitor_object_keys,
        )

    def to_representation(self, instance):
        data = super().to_representation(instance)
        monitor_object = getattr(instance, "monitor_object", None)
        data["instance_id_keys"] = resolve_metric_instance_id_keys(
            data.get("instance_id_keys", []),
            getattr(monitor_object, "instance_id_keys", []),
        )
        return data

    def get_monitor_plugin_name(self, instance):
        return instance.monitor_plugin.name if instance.monitor_plugin else ""

    def validate(self, attrs):
        attrs = super().validate(attrs)
        monitor_object = attrs.get("monitor_object", getattr(self.instance, "monitor_object", None))
        monitor_plugin = attrs.get("monitor_plugin", getattr(self.instance, "monitor_plugin", None))
        name = attrs.get("name", getattr(self.instance, "name", None))

        default_metric_keys = getattr(self.instance, "instance_id_keys", []) if self.instance is not None else []
        resolved_instance_id_keys = self._resolve_instance_id_keys(attrs, default_metric_keys=default_metric_keys)
        if not resolved_instance_id_keys:
            raise serializers.ValidationError({"instance_id_keys": "指标必须绑定有效的实例维度键"})
        if self.instance is None:
            attrs["instance_id_keys"] = resolved_instance_id_keys

        current_name = getattr(self.instance, "name", None) if self.instance is not None else None
        name_changed = self.instance is None or ("name" in attrs and attrs.get("name") != current_name)
        if name_changed and name and is_script_collect_type(getattr(monitor_plugin, "collect_type", None)):
            if is_reserved_script_metric_name(name):
                raise serializers.ValidationError({"name": RESERVED_SCRIPT_METRIC_NAME_ERROR})

        queryset = Metric.objects.filter(
            monitor_object=monitor_object,
            monitor_plugin=monitor_plugin,
            name=name,
        )
        if self.instance is not None:
            queryset = queryset.exclude(id=self.instance.id)
        if queryset.exists():
            raise serializers.ValidationError({"name": "同模板内指标 ID 不能重复"})

        if "query" in attrs and attrs.get("query") is not None:
            attrs["query"] = ensure_metric_labels_placeholder(attrs.get("query"))

        metric_group = attrs.get("metric_group", getattr(self.instance, "metric_group", None))
        if metric_group is not None:
            group_object_id = getattr(metric_group, "monitor_object_id", None)
            group_plugin_id = getattr(metric_group, "monitor_plugin_id", None)
            object_id = getattr(monitor_object, "id", monitor_object)
            plugin_id = getattr(monitor_plugin, "id", monitor_plugin) if monitor_plugin is not None else None
            if group_object_id != object_id or group_plugin_id != plugin_id:
                raise serializers.ValidationError({"metric_group": "指标分组必须属于同一监控对象和插件"})

        return attrs

    def get_unique_together_validators(self):
        # 禁用 DRF 默认 unique_together 文案，改由 validate() 给出字段级错误
        return []

    def create(self, validated_data):
        """
        在创建时，手动设置 is_pre 为 False
        """
        # 手动设置 is_pre 为 False，表示用户创建的数据是非预制的
        validated_data["instance_id_keys"] = self._resolve_instance_id_keys(validated_data, default_metric_keys=[])
        validated_data["is_pre"] = False

        # 调用父类的 create 方法
        return super().create(validated_data)

    def update(self, instance, validated_data):
        validated_data.pop("instance_id_keys", None)
        return super().update(instance, validated_data)


class MetricBatchUpdateItemSerializer(serializers.Serializer):
    id = serializers.IntegerField(min_value=1)
    display_name = serializers.CharField(required=False, allow_blank=False, max_length=100)
    metric_group = serializers.IntegerField(min_value=1, required=False)
    unit = serializers.CharField(required=False, allow_blank=True)
    data_type = serializers.ChoiceField(choices=METRIC_DATA_TYPES, required=False)
    description = serializers.CharField(required=False, allow_blank=True, allow_null=True)
    dimensions = serializers.ListField(
        child=serializers.CharField(allow_blank=True, max_length=100),
        required=False,
    )

    def validate_dimensions(self, value):
        return [str(item or "").strip() for item in value if str(item or "").strip()]


class MetricBatchUpdateSerializer(serializers.Serializer):
    monitor_plugin = serializers.IntegerField(min_value=1)
    items = serializers.ListField(
        child=MetricBatchUpdateItemSerializer(),
        allow_empty=False,
        max_length=METRIC_BATCH_UPDATE_MAX_SIZE,
    )

    def validate_items(self, value):
        seen = set()
        duplicates = []
        for item in value:
            metric_id = item["id"]
            if metric_id in seen:
                if metric_id not in duplicates:
                    duplicates.append(metric_id)
                continue
            seen.add(metric_id)
        if duplicates:
            duplicate_ids = ", ".join(str(metric_id) for metric_id in duplicates)
            raise serializers.ValidationError(f"items 中存在重复 id：{duplicate_ids}")
        return value


class MetricBatchDeleteSerializer(serializers.Serializer):
    """覆盖路径专用：必须带 monitor_plugin，只能删该插件指标。"""

    ids = serializers.ListField(
        child=serializers.IntegerField(min_value=1),
        allow_empty=False,
        max_length=METRIC_BATCH_DELETE_MAX_SIZE,
    )
    monitor_plugin = serializers.IntegerField(min_value=1)

    def validate_ids(self, value):
        unique_ids = []
        seen = set()
        for metric_id in value:
            if metric_id in seen:
                continue
            seen.add(metric_id)
            unique_ids.append(metric_id)
        if len(unique_ids) > METRIC_BATCH_DELETE_MAX_SIZE:
            raise serializers.ValidationError(f"单次批量删除不超过 {METRIC_BATCH_DELETE_MAX_SIZE} 条")
        return unique_ids


def dimension_entry_name(item):
    if isinstance(item, dict):
        return str(item.get("name") or "").strip()
    return str(item or "").strip()


# 脚本插件隐藏并在合并时原样保留的平台维度。前后端同内容。
PRESERVED_METRIC_DIMENSION_KEYS = (
    "instance_id",
    "agent_id",
    "plugin_id",
    "instance_type",
    "collect_type",
    "config_id",
    "config_type",
    "host",
    "script",
    "bklite_script_reserved_keys",
)
PRESERVED_METRIC_DIMENSION_PREFIX = "bklite_script_"
_PRESERVED_METRIC_DIMENSION_KEY_SET = {key.casefold() for key in PRESERVED_METRIC_DIMENSION_KEYS}


def is_preserved_metric_dimension_name(name):
    text = str(name or "").strip()
    if not text:
        return False
    lower = text.casefold()
    return lower in _PRESERVED_METRIC_DIMENSION_KEY_SET or lower.startswith(PRESERVED_METRIC_DIMENSION_PREFIX)


def validate_batch_dimension_names(names, metric_name="", preserve_hidden=False):
    seen = set()
    metric_label = str(metric_name or "").strip() or "未知指标"
    for dim in names:
        lower = dim.casefold()
        if preserve_hidden and is_preserved_metric_dimension_name(dim):
            return f"指标 {metric_label} 的维度 {dim} 与保留字段冲突"
        if lower in seen:
            return f"指标 {metric_label} 的维度 {dim} 重复"
        seen.add(lower)
    return ""


def _dimension_entry_for_name(name, existing_by_lower):
    prev = existing_by_lower.get(name.casefold())
    if isinstance(prev, dict):
        entry = dict(prev)
        entry["name"] = name
        if not str(entry.get("description") or "").strip():
            entry["description"] = name
        return entry
    return {"name": name, "description": name}


def _copy_dimension_entry(item, name):
    if isinstance(item, dict):
        return dict(item)
    return {"name": name, "description": name}


def merge_batch_dimensions(existing, names, preserve_hidden=False):
    existing_items = []
    existing_by_lower = {}
    for item in existing or []:
        name = dimension_entry_name(item)
        if not name:
            continue
        existing_items.append(item)
        existing_by_lower[name.casefold()] = item
    if not preserve_hidden:
        return [_dimension_entry_for_name(name, existing_by_lower) for name in names]
    user_names = iter(names)
    merged = []
    for item in existing_items:
        name = dimension_entry_name(item)
        if is_preserved_metric_dimension_name(name):
            merged.append(_copy_dimension_entry(item, name))
            continue
        try:
            user_name = next(user_names)
        except StopIteration:
            continue
        merged.append(_dimension_entry_for_name(user_name, existing_by_lower))
    merged.extend(_dimension_entry_for_name(user_name, existing_by_lower) for user_name in user_names)
    return merged
