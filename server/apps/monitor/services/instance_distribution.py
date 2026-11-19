"""监控实例分布。按分类或对象计数，排序后再按返回条数截断。"""

from __future__ import annotations

from django.db.models import Count

from apps.core.utils.loader import LanguageLoader
from apps.monitor.constants.language import LanguageConstants
from apps.monitor.models.monitor_object import MonitorObject, MonitorObjectType
from apps.monitor.services.generic_query import GenericQueryError
from apps.monitor.services.generic_query_limits import STAT_GROUP_MAX

GROUP_BY_TYPE = "monitor_object_type"
GROUP_BY_OBJECT = "monitor_object"
_UNTYPED_ORDER = 10**9


def query_instance_distribution(
    queryset,
    *,
    group_by: str,
    zero_type_ids: list[str] | None,
    zero_object_ids: list[int] | None,
    locale: str | None,
    page_size: int | None,
) -> list[dict]:
    counts = {
        row["monitor_object_id"]: row["instance_count"]
        for row in queryset.values("monitor_object_id").annotate(instance_count=Count("id", distinct=True))
        if row["monitor_object_id"] is not None
    }
    if group_by == GROUP_BY_TYPE:
        rows = _type_rows(counts, zero_type_ids, locale)
    elif group_by == GROUP_BY_OBJECT:
        rows = _object_rows(counts, zero_object_ids, locale)
    else:
        raise GenericQueryError("分布维度必须是分类或对象")
    rows.sort(key=lambda row: (-row["instance_count"], row.pop("_order"), row["group_id"]))
    if page_size is None and len(rows) > STAT_GROUP_MAX:
        raise GenericQueryError("分布分组超过 500 组")
    if page_size is not None:
        rows = rows[:page_size]
    return rows


def _type_rows(counts: dict[int, int], zero_type_ids: list[str] | None, locale: str | None) -> list[dict]:
    object_types = {item["id"]: item["type_id"] for item in MonitorObject.objects.filter(id__in=list(counts)).values("id", "type_id")}
    totals: dict[str, int] = {}
    for object_id, count in counts.items():
        type_id = object_types.get(object_id)
        if not type_id:
            continue
        totals[type_id] = totals.get(type_id, 0) + count
    if zero_type_ids is None:
        type_ids = [type_id for type_id, count in totals.items() if count > 0]
    else:
        type_ids = list(zero_type_ids)
    catalog = {item.id: item for item in MonitorObjectType.objects.filter(id__in=type_ids)}
    labels = _type_labels(catalog.values(), locale)
    rows = []
    for type_id in type_ids:
        item = catalog.get(type_id)
        if item is None:
            continue
        rows.append(
            {
                "group_id": item.id,
                "group_value": labels.get(item.id) or item.id,
                "instance_count": totals.get(item.id, 0),
                "_order": (item.order, item.id),
            }
        )
    return rows


def _object_rows(counts: dict[int, int], zero_object_ids: list[int] | None, locale: str | None) -> list[dict]:
    if zero_object_ids is None:
        object_ids = [object_id for object_id, count in counts.items() if count > 0]
    else:
        object_ids = list(zero_object_ids)
    catalog = {item.id: item for item in MonitorObject.objects.select_related("type").filter(id__in=object_ids)}
    labels = _object_labels(catalog.values(), locale)
    rows = []
    for object_id in object_ids:
        item = catalog.get(object_id)
        if item is None:
            continue
        type_order = item.type.order if item.type_id and item.type is not None else _UNTYPED_ORDER
        rows.append(
            {
                "group_id": str(item.id),
                "group_value": labels.get(item.id) or item.name,
                "instance_count": counts.get(item.id, 0),
                "_order": (type_order, item.order, str(item.id)),
            }
        )
    return rows


def _type_labels(types, locale: str | None) -> dict[str, str]:
    loader = LanguageLoader(app=LanguageConstants.APP, default_lang=locale or "en")
    labels = {}
    for item in types:
        translated = loader.get(f"{LanguageConstants.MONITOR_OBJECT_TYPE}.{item.id}")
        if isinstance(translated, str) and translated.strip():
            labels[item.id] = translated.strip()
            continue
        stored = (item.name or "").strip()
        labels[item.id] = stored or item.id
    return labels


def _object_labels(objects, locale: str | None) -> dict[int, str]:
    loader = LanguageLoader(app=LanguageConstants.APP, default_lang=locale or "en")
    labels = {}
    for item in objects:
        translated = loader.get(f"{LanguageConstants.MONITOR_OBJECT}.{item.name}")
        if isinstance(translated, str) and translated.strip():
            labels[item.id] = translated.strip()
            continue
        stored = (item.display_name or "").strip()
        labels[item.id] = stored or item.name
    return labels
