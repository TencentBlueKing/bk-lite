from django.db import transaction

from apps.monitor.constants.database import DatabaseConstants
from apps.monitor.models import MonitorPlugin
from apps.monitor.models.monitor_metrics import MetricGroup, Metric
from apps.monitor.models.monitor_object import MonitorObject, MonitorObjectType


class MonitorPluginService:

    @staticmethod
    def import_monitor_plugin(data: dict):
        """Import monitor plugin"""
        if data.get("is_compound_object"):
            MonitorPluginService.import_compound_monitor_object(data)
        else:
            MonitorPluginService.import_basic_monitor_object(data)

    @staticmethod
    def import_basic_monitor_object(data: dict):
        """导入基础监控对象"""
        metrics = data.pop("metrics")
        plugin = data.pop("plugin")
        desc = data.pop("plugin_desc", "")

        # 处理type字段：确保MonitorObjectType存在
        type_value = data.get("type")
        if type_value:
            # 如果提供了type，确保对应的MonitorObjectType存在
            obj_type, created = MonitorObjectType.objects.get_or_create(
                id=type_value,
                defaults={'order': 999}  # 新导入的分类默认排序为999
            )
            data["type"] = obj_type

        monitor_obj = MonitorObject.objects.filter(name=data["name"]).first()

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

        with transaction.atomic():
            plugin_obj, _ = MonitorPlugin.objects.update_or_create(
                name=plugin,
                defaults=dict(name=plugin, description=desc),
            )
            plugin_obj.monitor_object.add(monitor_obj)

        old_groups = MetricGroup.objects.filter(monitor_object=monitor_obj)
        old_groups_name = {i.name for i in old_groups}

        new_groups_name = {i["metric_group"] for i in metrics if i["metric_group"] not in old_groups_name}
        create_metric_group = [
            MetricGroup(
                monitor_object=monitor_obj,
                monitor_plugin=plugin_obj,
                name=name,
            ) for name in new_groups_name
        ]
        MetricGroup.objects.bulk_create(create_metric_group, batch_size=DatabaseConstants.BULK_CREATE_BATCH_SIZE)

        groups = MetricGroup.objects.filter(monitor_object=monitor_obj)
        groups_map = {i.name: i.id for i in groups}

        metrics_to_update = []
        metrics_to_create = []
        existing_metrics = {
            metric.name: metric
            for metric in Metric.objects.filter(monitor_object=monitor_obj)
        }

        for metric in metrics:
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
                existing_metric.instance_id_keys = metric.get("instance_id_keys", [])
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
                        instance_id_keys=metric.get("instance_id_keys", []),
                    )
                )

        if metrics_to_update:
            Metric.objects.bulk_update(metrics_to_update, [
                "metric_group_id", "display_name", "query", "unit", "data_type", "description", "dimensions", "instance_id_keys"
            ], batch_size=DatabaseConstants.BULK_UPDATE_BATCH_SIZE)

        if metrics_to_create:
            Metric.objects.bulk_create(metrics_to_create, batch_size=DatabaseConstants.BULK_CREATE_BATCH_SIZE)

        return monitor_obj

    @staticmethod
    def import_compound_monitor_object(data: dict):
        """导入复合监控对象"""
        base_object = {}
        derivative_objects = []
        for object_info in data.get("objects", []):
            object_info.update(plugin=data["plugin"], plugin_desc=data["plugin_desc"])
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
                    "instance_id_keys": i.instance_id_keys,
                } for i in metrics
            ]
        }
        return data

    @staticmethod
    def export_compound_monitor_object(plugin_obj, monitor_objs, metrics_map):
        """导出复合监控对象"""
        data = {"plugin":plugin_obj.name, "plugin_desc":plugin_obj.description, "is_compound_object": True, "objects": []}
        for monitor_obj in monitor_objs:
            object_data = MonitorPluginService.export_basic_monitor_object(plugin_obj, monitor_obj, metrics_map[monitor_obj.id])
            object_data.pop("plugin")
            object_data.pop("plugin_desc")
            data["objects"].append(object_data)
        return data
