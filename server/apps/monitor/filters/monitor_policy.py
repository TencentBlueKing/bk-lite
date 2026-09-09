from django_filters import CharFilter, FilterSet

from apps.monitor.filters.id_filters import filter_positive_int_field
from apps.monitor.models.monitor_policy import MonitorPolicy
from apps.monitor.utils.dimension import normalize_instance_identity


def policy_instance_id_candidates(value) -> list[str]:
    """兼容裸实例 ID 与存储用 tuple 串，供策略 source 过滤使用。"""
    text = str(value or "").strip()
    if not text:
        return []
    candidates = {text}
    try:
        identity = normalize_instance_identity(text)
    except ValueError:
        return [text]
    storage_key = identity.get("storage_instance_key")
    logical_value = identity.get("logical_instance_value")
    raw_input = identity.get("raw_input")
    if storage_key not in (None, ""):
        candidates.add(str(storage_key))
    if logical_value not in (None, ""):
        candidates.add(str(logical_value))
    if raw_input not in (None, ""):
        candidates.add(str(raw_input))
    return [item for item in candidates if item]


def _normalized_source_values(values) -> set:
    if not isinstance(values, list):
        return set()
    normalized = set()
    for item in values:
        if item in (None, ""):
            continue
        normalized.add(item)
        normalized.add(str(item))
    return normalized


def source_covers_instance(source, instance_ids) -> bool:
    """仅匹配显式绑定当前实例的策略，不含组织范围策略。"""
    if not isinstance(source, dict):
        return False
    if source.get("type") != "instance":
        return False
    value_set = _normalized_source_values(source.get("values"))
    return bool(value_set.intersection(instance_ids))


def filter_policy_queryset_by_instance(queryset, instance_id):
    """按实例显式绑定过滤策略。不依赖 JSON contains，SQLite / PostgreSQL 均可。"""
    instance_ids = set(policy_instance_id_candidates(instance_id))
    if not instance_ids:
        return queryset.none()

    matched_ids = [
        policy_id
        for policy_id, source in queryset.filter(source__type="instance").values_list("id", "source")
        if source_covers_instance(source, instance_ids)
    ]
    return queryset.filter(id__in=matched_ids)


class MonitorPolicyFilter(FilterSet):
    monitor_object_id = CharFilter(field_name="monitor_object", lookup_expr="exact", label="监控对象", method="filter_monitor_object_id")
    name = CharFilter(field_name="name", lookup_expr="icontains", label="策略名称")
    monitor_instance_id = CharFilter(method="filter_monitor_instance_id", label="监控实例ID")

    @staticmethod
    def filter_monitor_object_id(queryset, _name, value):
        return filter_positive_int_field(queryset, "monitor_object", value)

    @staticmethod
    def filter_monitor_instance_id(queryset, _name, value):
        if value in (None, ""):
            return queryset
        text = str(value).strip()
        if not text:
            return queryset
        return filter_policy_queryset_by_instance(queryset, text)

    class Meta:
        model = MonitorPolicy
        fields = ["monitor_object_id", "name", "monitor_instance_id"]
