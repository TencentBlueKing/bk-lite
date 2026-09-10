from copy import deepcopy

from django.db import transaction
from django.utils import timezone

from apps.core.exceptions.base_app_exception import BaseAppException
from apps.monitor.constants.database import DatabaseConstants
from apps.monitor.models import MonitorPlugin
from apps.monitor.models.monitor_metrics import Metric, MetricGroup
from apps.monitor.models.monitor_object import MonitorObject, MonitorObjectType
from apps.monitor.services.instance_facts import InstanceFactResolver
from apps.monitor.utils.display_fields_seed import build_seed_display_fields, merge_display_fields_bindings
from apps.monitor.utils.instance_id_keys import resolve_metric_instance_id_keys, resolve_monitor_object_instance_id_keys
from apps.monitor.utils.node_selector import normalize_node_selector

METRIC_UPDATE_FIELDS = [
    "metric_group_id",
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
]
PLUGIN_UPDATE_FIELDS = [
    "description",
    "status_query",
    "collector",
    "collect_type",
    "support_collect_detect",
    "node_selector",
    "instance_fact_bindings",
]
OBJECT_UPDATE_FIELDS = [
    "icon",
    "type",
    "description",
    "level",
    "default_metric",
    "instance_id_keys",
    "is_builtin",
    "display_fields",
    "instance_summary_columns",
    "parent",
]


def prepare_plugin_import_plan(data: dict) -> dict:
    """把单个插件文档转成可跨插件批量写入的计划。不访问数据库。"""
    payload = deepcopy(data)
    mark_objects_builtin = bool(payload.pop("_mark_objects_builtin", False))
    plugin_name = payload.get("plugin", "")
    plugin_plan = {
        "plugin_name": plugin_name,
        "description": payload.get("plugin_desc", ""),
        "status_query": payload.get("status_query", ""),
        "collector": payload.get("collector", ""),
        "collect_type": payload.get("collect_type", ""),
        "support_collect_detect": bool(payload.get("support_collect_detect", False)),
        "node_selector": normalize_node_selector(payload.get("node_selector", {})),
        "instance_fact_bindings": InstanceFactResolver.validate_bindings(payload.get("instance_fact_bindings", [])),
        "objects": [],
    }

    if payload.get("is_compound_object"):
        objects_raw = payload.get("objects") or []
        base_summary_columns = payload.get("instance_summary_columns")
        base_name = next(
            (item.get("name") for item in objects_raw if item.get("level") == "base"),
            None,
        )
        for object_info in objects_raw:
            if mark_objects_builtin:
                object_info["is_builtin"] = True
            else:
                object_info.pop("is_builtin", None)
            if object_info.get("level") == "base" and "instance_summary_columns" not in object_info:
                object_info["instance_summary_columns"] = base_summary_columns
            object_plan = _prepare_object_plan(
                object_info,
                plugin_name,
                plugin_plan["instance_fact_bindings"],
            )
            if object_info.get("level") != "base":
                object_plan["parent_name"] = base_name
            plugin_plan["objects"].append(object_plan)
    else:
        if mark_objects_builtin:
            payload["is_builtin"] = True
        else:
            payload.pop("is_builtin", None)
        plugin_plan["objects"].append(
            _prepare_object_plan(
                payload,
                plugin_name,
                plugin_plan["instance_fact_bindings"],
            )
        )

    plugin_plan["objects"].sort(key=lambda item: 0 if item["level"] == "base" else 1)
    return plugin_plan


def apply_plugin_import_plans(plans: list[dict]) -> None:
    """跨插件批量写入 Type / Object / Plugin / M2M / MetricGroup / Metric。"""
    if not plans:
        return

    now = timezone.now()
    with transaction.atomic():
        _ensure_object_types(plans, now)
        objects_map = {item.name: item for item in MonitorObject.objects.all()}
        merged_objects = _merge_object_specs(plans)
        _upsert_monitor_objects(
            [spec for spec in merged_objects.values() if not spec.get("parent_name")],
            objects_map,
            now,
        )
        derivative_specs = []
        for spec in merged_objects.values():
            parent_name = spec.get("parent_name")
            if not parent_name:
                continue
            parent = objects_map.get(parent_name)
            derivative = dict(spec)
            derivative["parent_id"] = parent.id if parent else None
            derivative_specs.append(derivative)
        _upsert_monitor_objects(derivative_specs, objects_map, now)

        plugins_map = {item.name: item for item in MonitorPlugin.objects.all()}
        _upsert_plugins(plans, plugins_map, now)
        _sync_plugin_object_m2m(plans, plugins_map, objects_map)
        _sync_metric_groups_and_metrics(plans, objects_map, plugins_map)


def import_monitor_plugins(documents: list[dict]) -> None:
    apply_plugin_import_plans([prepare_plugin_import_plan(document) for document in documents])


def _prepare_object_plan(object_data: dict, plugin_name: str, instance_fact_bindings: list) -> dict:
    metrics = object_data.get("metrics") or []
    display_fields_block = object_data.get("display_fields", None)
    instance_summary_columns = object_data.get("instance_summary_columns", None)
    type_value = object_data.get("type")
    type_id = getattr(type_value, "id", type_value) or None
    name = object_data["name"]
    level = object_data.get("level", "base")
    instance_id_keys = resolve_monitor_object_instance_id_keys(
        object_data.get("instance_id_keys", []),
        level=level,
        object_name=name,
    )
    if instance_summary_columns is not None:
        _validate_instance_summary_columns(instance_summary_columns, instance_fact_bindings)

    prepared_metrics = []
    for metric in metrics:
        dimensions = _normalize_metric_dimensions(metric.get("dimensions", []))
        prepared_metrics.append(
            {
                "metric_group": metric["metric_group"],
                "name": metric["name"],
                "display_name": metric["display_name"],
                "query": metric["query"],
                "view_query": metric.get("view_query", ""),
                "view_config": metric.get("view_config", {}),
                "unit": metric["unit"],
                "data_type": metric["data_type"],
                "description": metric["description"],
                "dimensions": dimensions,
                "instance_id_keys": resolve_metric_instance_id_keys(
                    metric.get("instance_id_keys", []),
                    instance_id_keys,
                    strict=True,
                ),
                "is_ifmib": bool(metric.get("is_ifmib", False)),
            }
        )

    display_fields = None
    if display_fields_block:
        display_fields = list(display_fields_block)
    else:
        seeded = build_seed_display_fields(
            plugin_name,
            object_data.get("supplementary_indicators", []),
            prepared_metrics,
        )
        if seeded:
            display_fields = seeded

    return {
        "name": name,
        "level": level,
        "parent_name": None,
        "type_id": type_id,
        "icon": object_data["icon"] if "icon" in object_data else None,
        "description": object_data["description"] if "description" in object_data else None,
        "default_metric": object_data["default_metric"] if "default_metric" in object_data else None,
        "instance_id_keys": instance_id_keys,
        "is_builtin": bool(object_data.get("is_builtin")),
        "cleanup_policy": object_data.get("cleanup_policy"),
        "cleanup_timeout_days": object_data.get("cleanup_timeout_days"),
        "cleanup_timeout_unit": object_data.get("cleanup_timeout_unit"),
        "display_fields": display_fields,
        "instance_summary_columns": instance_summary_columns,
        "metrics": prepared_metrics,
        "plugin_name": plugin_name,
    }


def _normalize_metric_dimensions(dimensions):
    from apps.monitor.services.plugin import MonitorPluginService

    return MonitorPluginService.normalize_metric_dimensions(dimensions)


def _validate_instance_summary_columns(instance_summary_columns, instance_fact_bindings):
    if not isinstance(instance_summary_columns, list):
        raise BaseAppException("instance_summary_columns 必须是列表")
    available_facts = {binding["fact"] for binding in instance_fact_bindings}
    for index, column in enumerate(instance_summary_columns):
        if not isinstance(column, dict) or not str(column.get("fact") or "").strip():
            raise BaseAppException(f"instance_summary_columns[{index}] 缺少 fact")
        if column["fact"] not in available_facts:
            raise BaseAppException(f"实例摘要列引用了插件未绑定的事实: {column['fact']}")


def _ensure_object_types(plans, now):
    types_map = {item.id: item for item in MonitorObjectType.objects.all()}
    to_create = []
    seen = set()
    for plan in plans:
        for object_plan in plan["objects"]:
            type_id = object_plan.get("type_id")
            if not type_id or type_id in types_map or type_id in seen:
                continue
            seen.add(type_id)
            to_create.append(MonitorObjectType(id=type_id, order=999, created_at=now, updated_at=now))
    if to_create:
        MonitorObjectType.objects.bulk_create(to_create, batch_size=DatabaseConstants.BULK_CREATE_BATCH_SIZE)
        for item in to_create:
            types_map[item.id] = item
    return types_map


def _merge_object_specs(plans):
    merged = {}
    for plan in plans:
        for object_plan in plan["objects"]:
            name = object_plan["name"]
            existing = merged.get(name)
            if existing is None:
                merged[name] = object_plan
                continue
            incoming = dict(object_plan)
            if existing.get("display_fields") or incoming.get("display_fields"):
                incoming["display_fields"] = merge_display_fields_bindings(
                    existing.get("display_fields"),
                    incoming.get("display_fields"),
                )
            merged[name] = incoming
    return merged


def _upsert_monitor_objects(specs, objects_map, now):
    to_create = []
    to_update = []
    for spec in specs:
        existing = objects_map.get(spec["name"])
        type_id = spec.get("type_id")
        if existing is None:
            create_kwargs = {
                "name": spec["name"],
                "icon": spec.get("icon") or "",
                "type_id": type_id,
                "description": spec.get("description") or "",
                "level": spec.get("level") or "base",
                "default_metric": spec.get("default_metric") or "",
                "instance_id_keys": spec.get("instance_id_keys") or [],
                "is_builtin": bool(spec.get("is_builtin")),
                "created_at": now,
                "updated_at": now,
            }
            if spec.get("parent_id") is not None:
                create_kwargs["parent_id"] = spec["parent_id"]
            if spec.get("display_fields") is not None:
                create_kwargs["display_fields"] = spec["display_fields"]
            if spec.get("instance_summary_columns") is not None:
                create_kwargs["instance_summary_columns"] = spec["instance_summary_columns"]
            if spec.get("cleanup_policy"):
                create_kwargs["cleanup_policy"] = spec["cleanup_policy"]
                if spec["cleanup_policy"] == MonitorObject.CLEANUP_POLICY_TIMEOUT:
                    create_kwargs["cleanup_policy_effective_at"] = now
            if spec.get("cleanup_timeout_days") is not None:
                create_kwargs["cleanup_timeout_days"] = spec["cleanup_timeout_days"]
            if spec.get("cleanup_timeout_unit"):
                create_kwargs["cleanup_timeout_unit"] = spec["cleanup_timeout_unit"]
            to_create.append(MonitorObject(**create_kwargs))
            continue

        changed = False
        if spec.get("icon") is not None and existing.icon != spec["icon"]:
            existing.icon = spec["icon"]
            changed = True
        if type_id and existing.type_id != type_id:
            existing.type_id = type_id
            changed = True
        if spec.get("description") is not None and existing.description != spec["description"]:
            existing.description = spec["description"]
            changed = True
        if spec.get("level") and existing.level != spec["level"]:
            existing.level = spec["level"]
            changed = True
        if spec.get("default_metric") is not None and existing.default_metric != spec["default_metric"]:
            existing.default_metric = spec["default_metric"]
            changed = True
        if spec.get("instance_id_keys") and existing.instance_id_keys != spec["instance_id_keys"]:
            existing.instance_id_keys = spec["instance_id_keys"]
            changed = True
        if spec.get("is_builtin") and not existing.is_builtin:
            existing.is_builtin = True
            changed = True
        if spec.get("parent_id") is not None and existing.parent_id != spec["parent_id"]:
            existing.parent_id = spec["parent_id"]
            changed = True
        if not existing.display_fields_customized and spec.get("display_fields") is not None and existing.display_fields != spec["display_fields"]:
            existing.display_fields = spec["display_fields"]
            changed = True
        if spec.get("instance_summary_columns") is not None and existing.instance_summary_columns != spec["instance_summary_columns"]:
            existing.instance_summary_columns = spec["instance_summary_columns"]
            changed = True
        if changed:
            existing.updated_at = now
            to_update.append(existing)

    if to_create:
        MonitorObject.objects.bulk_create(to_create, batch_size=DatabaseConstants.BULK_CREATE_BATCH_SIZE)
        created_names = [item.name for item in to_create]
        for item in MonitorObject.objects.filter(name__in=created_names):
            objects_map[item.name] = item
    if to_update:
        MonitorObject.objects.bulk_update(
            to_update,
            OBJECT_UPDATE_FIELDS,
            batch_size=DatabaseConstants.BULK_UPDATE_BATCH_SIZE,
        )


def _upsert_plugins(plans, plugins_map, now):
    to_create = []
    to_update = []
    seen_names = set()
    for plan in plans:
        name = plan["plugin_name"]
        if not name or name in seen_names:
            continue
        seen_names.add(name)
        defaults = {
            "description": plan["description"],
            "status_query": plan["status_query"],
            "collector": plan["collector"],
            "collect_type": plan["collect_type"],
            "support_collect_detect": plan["support_collect_detect"],
            "node_selector": plan["node_selector"],
            "instance_fact_bindings": plan["instance_fact_bindings"],
        }
        existing = plugins_map.get(name)
        if existing is None:
            to_create.append(
                MonitorPlugin(
                    name=name,
                    created_at=now,
                    updated_at=now,
                    **defaults,
                )
            )
            continue
        changed = False
        for field, value in defaults.items():
            if getattr(existing, field) != value:
                setattr(existing, field, value)
                changed = True
        if changed:
            existing.updated_at = now
            to_update.append(existing)

    if to_create:
        MonitorPlugin.objects.bulk_create(to_create, batch_size=DatabaseConstants.BULK_CREATE_BATCH_SIZE)
        created_names = [item.name for item in to_create]
        for item in MonitorPlugin.objects.filter(name__in=created_names):
            plugins_map[item.name] = item
    if to_update:
        MonitorPlugin.objects.bulk_update(
            to_update,
            PLUGIN_UPDATE_FIELDS,
            batch_size=DatabaseConstants.BULK_UPDATE_BATCH_SIZE,
        )


def _sync_plugin_object_m2m(plans, plugins_map, objects_map):
    through = MonitorPlugin.monitor_object.through
    plugin_ids = []
    desired_rows = []
    seen_pairs = set()
    for plan in plans:
        plugin = plugins_map.get(plan["plugin_name"])
        if plugin is None:
            continue
        plugin_ids.append(plugin.id)
        for object_plan in plan["objects"]:
            monitor_object = objects_map.get(object_plan["name"])
            if monitor_object is None:
                continue
            pair = (plugin.id, monitor_object.id)
            if pair in seen_pairs:
                continue
            seen_pairs.add(pair)
            desired_rows.append(through(monitorplugin_id=plugin.id, monitorobject_id=monitor_object.id))
    if plugin_ids:
        through.objects.filter(monitorplugin_id__in=plugin_ids).delete()
    if desired_rows:
        through.objects.bulk_create(desired_rows, batch_size=DatabaseConstants.BULK_CREATE_BATCH_SIZE)


def _sync_metric_groups_and_metrics(plans, objects_map, plugins_map):
    groups = {(item.monitor_object_id, item.monitor_plugin_id, item.name): item for item in MetricGroup.objects.all()}
    metrics = {(item.monitor_object_id, item.monitor_plugin_id, item.name): item for item in Metric.objects.all()}

    groups_to_create = []
    seen_groups = set()
    for plan in plans:
        plugin = plugins_map.get(plan["plugin_name"])
        if plugin is None:
            continue
        for object_plan in plan["objects"]:
            monitor_object = objects_map.get(object_plan["name"])
            if monitor_object is None:
                continue
            for metric in object_plan["metrics"]:
                key = (monitor_object.id, plugin.id, metric["metric_group"])
                if key in groups or key in seen_groups:
                    continue
                seen_groups.add(key)
                groups_to_create.append(
                    MetricGroup(
                        monitor_object_id=monitor_object.id,
                        monitor_plugin_id=plugin.id,
                        name=metric["metric_group"],
                    )
                )
    if groups_to_create:
        MetricGroup.objects.bulk_create(groups_to_create, batch_size=DatabaseConstants.BULK_CREATE_BATCH_SIZE)
        for item in MetricGroup.objects.filter(monitor_plugin_id__in={row.monitor_plugin_id for row in groups_to_create}):
            groups[(item.monitor_object_id, item.monitor_plugin_id, item.name)] = item

    stale_metric_ids = []
    metrics_to_update = []
    metrics_to_create = []
    expected_names = {}
    for plan in plans:
        plugin = plugins_map.get(plan["plugin_name"])
        if plugin is None:
            continue
        for object_plan in plan["objects"]:
            monitor_object = objects_map.get(object_plan["name"])
            if monitor_object is None:
                continue
            scope = (monitor_object.id, plugin.id)
            expected_names.setdefault(scope, set()).update(metric["name"] for metric in object_plan["metrics"])
            for metric in object_plan["metrics"]:
                group = groups.get((monitor_object.id, plugin.id, metric["metric_group"]))
                if group is None:
                    continue
                metric_key = (monitor_object.id, plugin.id, metric["name"])
                existing = metrics.get(metric_key)
                values = {
                    "metric_group_id": group.id,
                    "name": metric["name"],
                    "display_name": metric["display_name"],
                    "query": metric["query"],
                    "view_query": metric["view_query"],
                    "view_config": metric["view_config"],
                    "unit": metric["unit"],
                    "data_type": metric["data_type"],
                    "description": metric["description"],
                    "dimensions": metric["dimensions"],
                    "instance_id_keys": metric["instance_id_keys"],
                    "is_ifmib": metric["is_ifmib"],
                }
                if existing is None:
                    metrics_to_create.append(
                        Metric(
                            monitor_object_id=monitor_object.id,
                            monitor_plugin_id=plugin.id,
                            **values,
                        )
                    )
                    continue
                changed = False
                for field, value in values.items():
                    if field == "name" or getattr(existing, field) == value:
                        continue
                    setattr(existing, field, value)
                    changed = True
                if changed:
                    metrics_to_update.append(existing)

    for (metric_object_id, metric_plugin_id, metric_name), metric in metrics.items():
        names = expected_names.get((metric_object_id, metric_plugin_id))
        if names is None or not metric.is_pre or metric_name in names:
            continue
        stale_metric_ids.append(metric.id)

    if stale_metric_ids:
        Metric.objects.filter(id__in=stale_metric_ids, is_pre=True).delete()
    if metrics_to_update:
        Metric.objects.bulk_update(
            metrics_to_update,
            METRIC_UPDATE_FIELDS,
            batch_size=DatabaseConstants.BULK_UPDATE_BATCH_SIZE,
        )
    if metrics_to_create:
        Metric.objects.bulk_create(metrics_to_create, batch_size=DatabaseConstants.BULK_CREATE_BATCH_SIZE)
