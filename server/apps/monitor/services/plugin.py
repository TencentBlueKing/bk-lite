from django.db import transaction

from apps.monitor.constants.database import DatabaseConstants
from apps.monitor.models import MonitorPlugin, MonitorPluginUITemplate
from apps.monitor.models.monitor_metrics import MetricGroup, Metric
from apps.monitor.models.monitor_object import MonitorObject, MonitorObjectType
from apps.monitor.utils.display_fields_seed import build_seed_display_fields
from apps.monitor.utils.instance_id_keys import (
    resolve_metric_instance_id_keys,
    resolve_monitor_object_instance_id_keys,
)
from apps.monitor.utils.node_selector import normalize_node_selector


class MonitorPluginService:
    @staticmethod
    def normalize_metric_dimensions(dimensions):
        if not isinstance(dimensions, list):
            return []

        normalized = []
        seen = set()
        for dimension in dimensions:
            if isinstance(dimension, dict):
                name = str(dimension.get("name") or "").strip()
                if not name or name in seen:
                    continue
                item = dict(dimension)
                item["name"] = name
                normalized.append(item)
                seen.add(name)
                continue

            name = str(dimension or "").strip()
            if name and name not in seen:
                normalized.append({"name": name})
                seen.add(name)

        return normalized

    @staticmethod
    def _extract_monitor_object_names(data: dict) -> list[str]:
        if data.get("is_compound_object"):
            return [item.get("name") for item in data.get("objects", []) if item.get("name")]
        return [data.get("name")] if data.get("name") else []

    @staticmethod
    def _sync_plugin_monitor_objects(plugin_name: str, monitor_object_names: list[str]):
        if not plugin_name:
            return

        plugin_obj = MonitorPlugin.objects.filter(name=plugin_name).first()
        if not plugin_obj:
            return

        monitor_objects = MonitorObject.objects.filter(name__in=monitor_object_names)
        plugin_obj.monitor_object.set(monitor_objects)

    @staticmethod
    def get_ui_template_by_params(collector, collect_type, monitor_object_id):
        """获取插件的 UI 模板"""
        obj = (
            MonitorPluginUITemplate.objects.filter(
                plugin__monitor_object__id=monitor_object_id,
                plugin__collector=collector,
                plugin__collect_type=collect_type,
                plugin__template_type="builtin",
            )
            .select_related("plugin")
            .first()
        )
        return {
            "ui_template": obj.content if obj else None,
            "node_selector": getattr(obj.plugin, "node_selector", {}) if obj else {},
            "support_collect_detect": getattr(obj.plugin, "support_collect_detect", False) if obj else False,
        }

    @staticmethod
    def import_monitor_plugin(data: dict):
        """Import monitor plugin"""
        plugin_name = data.get("plugin", "")
        monitor_object_names = MonitorPluginService._extract_monitor_object_names(data)

        if data.get("is_compound_object"):
            MonitorPluginService.import_compound_monitor_object(data)
        else:
            MonitorPluginService.import_basic_monitor_object(data)

        MonitorPluginService._sync_plugin_monitor_objects(plugin_name, monitor_object_names)

    @staticmethod
    def _ensure_language_skeleton(plugin_dir, plugin_name: str) -> None:
        """为新 plugin 在 metrics.json 同目录生成 language/{en,zh-Hans}.yaml 空骨架。

        若文件已存在且非空,不覆盖。
        """
        import yaml
        from pathlib import Path

        lang_dir = Path(plugin_dir) / "language"
        lang_dir.mkdir(parents=True, exist_ok=True)
        skeleton = {plugin_name: {"name": "", "desc": ""}}
        for lang in ("en", "zh-Hans"):
            target = lang_dir / f"{lang}.yaml"
            if target.is_file() and target.stat().st_size > 0:
                continue
            with target.open("w", encoding="utf-8") as f:
                yaml.safe_dump(skeleton, f, allow_unicode=True, sort_keys=False, default_flow_style=False)

    @staticmethod
    def import_basic_monitor_object(data: dict):
        """导入基础监控对象"""
        metrics = data.pop("metrics")
        display_fields_block = data.pop("display_fields", None)
        plugin = data.pop("plugin")
        desc = data.pop("plugin_desc", "")
        status_query = data.pop("status_query", "")
        collector = data.pop("collector", "")
        collect_type = data.pop("collect_type", "")
        support_collect_detect = bool(data.pop("support_collect_detect", False))
        node_selector = normalize_node_selector(data.pop("node_selector", {}))

        # 处理type字段：确保MonitorObjectType存在
        type_value = data.get("type")
        if type_value:
            # 如果提供了type，确保对应的MonitorObjectType存在
            obj_type, created = MonitorObjectType.objects.get_or_create(
                id=type_value,
                defaults={"order": 999},  # 新导入的分类默认排序为999
            )
            data["type"] = obj_type

        monitor_obj = MonitorObject.objects.filter(name=data["name"]).first()
        object_level = data.get("level", getattr(monitor_obj, "level", "base"))
        object_name = data.get("name", getattr(monitor_obj, "name", ""))
        object_instance_id_keys = resolve_monitor_object_instance_id_keys(
            data.get("instance_id_keys", getattr(monitor_obj, "instance_id_keys", [])),
            level=object_level,
            object_name=object_name,
        )
        data["instance_id_keys"] = object_instance_id_keys

        if monitor_obj:
            supplementary_indicators = monitor_obj.supplementary_indicators + data.get("supplementary_indicators", [])
            monitor_obj.icon = data.get("icon", monitor_obj.icon)
            monitor_obj.type = data.get("type", monitor_obj.type)
            monitor_obj.description = data.get("description", monitor_obj.description)
            monitor_obj.level = data.get("level", monitor_obj.level)
            monitor_obj.default_metric = data.get("default_metric", monitor_obj.default_metric)
            monitor_obj.instance_id_keys = data.get("instance_id_keys", monitor_obj.instance_id_keys)
            monitor_obj.supplementary_indicators = list(set(supplementary_indicators))
            monitor_obj.save()
        else:
            monitor_obj = MonitorObject.objects.create(**data)

        # seed 展示列配置：仅当未被用户自定义
        if not monitor_obj.display_fields_customized:
            if display_fields_block:
                seeded = list(display_fields_block)
            else:
                # 从已合并保存的 supplementary_indicators 派生（含其它插件/历史导入贡献的指标）
                seeded = build_seed_display_fields(
                    plugin,
                    monitor_obj.supplementary_indicators,
                    metrics,
                )
            if seeded:
                monitor_obj.display_fields = seeded
                monitor_obj.save(update_fields=["display_fields"])

        with transaction.atomic():
            plugin_obj, _ = MonitorPlugin.objects.update_or_create(
                name=plugin,
                defaults=dict(
                    name=plugin,
                    description=desc,
                    status_query=status_query,
                    collector=collector,
                    collect_type=collect_type,
                    support_collect_detect=support_collect_detect,
                    node_selector=node_selector,
                ),
            )
            plugin_obj.monitor_object.add(monitor_obj)

        old_groups = MetricGroup.objects.filter(monitor_object=monitor_obj, monitor_plugin=plugin_obj)
        old_groups_name = {i.name for i in old_groups}

        new_groups_name = {i["metric_group"] for i in metrics if i["metric_group"] not in old_groups_name}
        create_metric_group = [
            MetricGroup(
                monitor_object=monitor_obj,
                monitor_plugin=plugin_obj,
                name=name,
            )
            for name in new_groups_name
        ]
        MetricGroup.objects.bulk_create(create_metric_group, batch_size=DatabaseConstants.BULK_CREATE_BATCH_SIZE)

        groups = MetricGroup.objects.filter(monitor_object=monitor_obj, monitor_plugin=plugin_obj)
        groups_map = {i.name: i.id for i in groups}

        metrics_to_update = []
        metrics_to_create = []
        existing_metrics = {metric.name: metric for metric in Metric.objects.filter(monitor_object=monitor_obj, monitor_plugin=plugin_obj)}

        # 删除is_pre=True但不在新指标列表中的旧指标（按插件删除）
        new_metric_names = {metric["name"] for metric in metrics}
        old_pre_metrics_to_delete = [
            metric_name for metric_name, metric in existing_metrics.items() if metric.is_pre and metric_name not in new_metric_names
        ]
        if old_pre_metrics_to_delete:
            Metric.objects.filter(monitor_object=monitor_obj, monitor_plugin=plugin_obj, name__in=old_pre_metrics_to_delete, is_pre=True).delete()
            # 从existing_metrics中移除已删除的指标
            for metric_name in old_pre_metrics_to_delete:
                existing_metrics.pop(metric_name)

        for metric in metrics:
            metric["dimensions"] = MonitorPluginService.normalize_metric_dimensions(
                metric.get("dimensions", [])
            )
            metric_instance_id_keys = resolve_metric_instance_id_keys(
                metric.get("instance_id_keys", []),
                monitor_obj.instance_id_keys,
                strict=True,
            )
            if metric["name"] in existing_metrics:
                existing_metric = existing_metrics[metric["name"]]
                existing_metric.metric_group_id = groups_map[metric["metric_group"]]
                existing_metric.monitor_plugin_id = plugin_obj.id
                existing_metric.display_name = metric["display_name"]
                existing_metric.query = metric["query"]
                existing_metric.unit = metric["unit"]
                existing_metric.data_type = metric["data_type"]
                existing_metric.description = metric["description"]
                existing_metric.dimensions = metric["dimensions"]
                existing_metric.instance_id_keys = metric_instance_id_keys
                metrics_to_update.append(existing_metric)
            else:
                metrics_to_create.append(
                    Metric(
                        monitor_object_id=monitor_obj.id,
                        monitor_plugin_id=plugin_obj.id,
                        metric_group_id=groups_map[metric["metric_group"]],
                        name=metric["name"],
                        display_name=metric["display_name"],
                        query=metric["query"],
                        unit=metric["unit"],
                        data_type=metric["data_type"],
                        description=metric["description"],
                        dimensions=metric["dimensions"],
                        instance_id_keys=metric_instance_id_keys,
                    )
                )

        if metrics_to_update:
            Metric.objects.bulk_update(
                metrics_to_update,
                ["metric_group_id", "display_name", "query", "unit", "data_type", "description", "dimensions", "instance_id_keys"],
                batch_size=DatabaseConstants.BULK_UPDATE_BATCH_SIZE,
            )

        if metrics_to_create:
            Metric.objects.bulk_create(metrics_to_create, batch_size=DatabaseConstants.BULK_CREATE_BATCH_SIZE)

        return monitor_obj

    @staticmethod
    def import_compound_monitor_object(data: dict):
        """导入复合监控对象"""
        base_object = {}
        derivative_objects = []
        collector = data.get("collector", "")
        collect_type = data.get("collect_type", "")
        support_collect_detect = bool(data.get("support_collect_detect", False))
        node_selector = data.get("node_selector", {})

        for object_info in data.get("objects", []):
            object_info.update(
                plugin=data["plugin"],
                plugin_desc=data["plugin_desc"],
                status_query=data["status_query"],
                collector=collector,
                collect_type=collect_type,
                support_collect_detect=support_collect_detect,
                node_selector=node_selector,
            )
            if object_info.get("level") == "base":
                base_object = object_info
            else:
                derivative_objects.append(object_info)

        base_obj = MonitorPluginService.import_basic_monitor_object(base_object)
        for derivative_object in derivative_objects:
            derivative_object["parent_id"] = base_obj.id
            MonitorPluginService.import_basic_monitor_object(derivative_object)

    @staticmethod
    def export_monitor_plugin(id: int):
        """导出监控对象"""
        plugin_obj = MonitorPlugin.objects.prefetch_related("monitor_object", "metric_set").get(id=id)
        monitor_objs = plugin_obj.monitor_object.all()
        metric_map = {}
        for metric in plugin_obj.metric_set.all():
            if metric.monitor_object_id not in metric_map:
                metric_map[metric.monitor_object_id] = []
            metric_map[metric.monitor_object_id].append(metric)

        if monitor_objs.count() > 1:
            return MonitorPluginService.export_compound_monitor_object(plugin_obj, monitor_objs, metric_map)
        else:
            return MonitorPluginService.export_basic_monitor_object(plugin_obj, monitor_objs[0], metric_map[monitor_objs[0].id])

    @staticmethod
    def export_basic_monitor_object(plugin_obj, monitor_obj, metrics):
        """导出基础监控对象"""
        data = {
            "plugin": plugin_obj.name,
            "plugin_desc": plugin_obj.description,
            "collector": plugin_obj.collector,
            "collect_type": plugin_obj.collect_type,
            "support_collect_detect": plugin_obj.support_collect_detect,
            "node_selector": plugin_obj.node_selector or {},
            "name": monitor_obj.name,
            "type": monitor_obj.type_id if monitor_obj.type else None,  # 导出type的id值
            "description": monitor_obj.description,
            "metrics": [
                {
                    "metric_group": i.metric_group.name,
                    "name": i.name,
                    "display_name": i.display_name,
                    "query": i.query,
                    "unit": i.unit,
                    "data_type": i.data_type,
                    "description": i.description,
                    "dimensions": i.dimensions,
                    "instance_id_keys": resolve_metric_instance_id_keys(i.instance_id_keys, monitor_obj.instance_id_keys),
                }
                for i in metrics
            ],
        }
        return data

    @staticmethod
    def export_compound_monitor_object(plugin_obj, monitor_objs, metrics_map):
        """导出复合监控对象"""
        data = {
            "plugin": plugin_obj.name,
            "plugin_desc": plugin_obj.description,
            "collector": plugin_obj.collector,
            "collect_type": plugin_obj.collector,
            "support_collect_detect": plugin_obj.support_collect_detect,
            "node_selector": plugin_obj.node_selector or {},
            "is_compound_object": True,
            "objects": [],
        }
        for monitor_obj in monitor_objs:
            object_data = MonitorPluginService.export_basic_monitor_object(plugin_obj, monitor_obj, metrics_map[monitor_obj.id])
            object_data.pop("plugin")
            object_data.pop("plugin_desc")
            object_data.pop("collector")
            object_data.pop("collect_type")
            data["objects"].append(object_data)
        return data
