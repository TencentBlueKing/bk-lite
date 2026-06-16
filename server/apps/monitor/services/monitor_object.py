import re
import uuid

from django.db import transaction

from apps.core.exceptions.base_app_exception import BaseAppException
from apps.monitor.constants.database import DatabaseConstants
from apps.monitor.constants.monitor_object import MonitorObjConstants
from apps.monitor.models.monitor_metrics import Metric
from apps.monitor.models.monitor_object import (
    MonitorInstance,
    MonitorObject,
    MonitorInstanceOrganization,
    MonitorObjectType,
)
from apps.monitor.models.collect_config import CollectConfig
from apps.monitor.models.plugin import MonitorPlugin
from apps.monitor.utils.dimension import parse_instance_id
from apps.monitor.utils.display_fields_metrics import (
    display_field_key,
    extract_metric_bindings,
)
from apps.monitor.utils.victoriametrics_api import VictoriaMetricsAPI
from apps.monitor.tasks.grouping_rule import sync_instance_and_group


class MonitorObjectService:
    @staticmethod
    def _project_instance_identity(qs):
        return qs.only("id", "name", "cloud_region_id", "ip", "fallback_sampling_rate")

    @staticmethod
    def validate_new_instance_name_unique(monitor_object_id, monitor_instance_name):
        if not monitor_instance_name:
            return
        exists = MonitorInstance.objects.filter(
            monitor_object_id=monitor_object_id,
            name=monitor_instance_name,
            is_deleted=False,
        ).exists()
        if exists:
            raise BaseAppException("实例名称已存在")

    @staticmethod
    def validate_update_instance_name_unique(instance, monitor_instance_name):
        if not monitor_instance_name or instance.name == monitor_instance_name:
            return
        exists = (
            MonitorInstance.objects.filter(
                monitor_object_id=instance.monitor_object_id,
                name=monitor_instance_name,
                is_deleted=False,
            )
            .exclude(id=instance.id)
            .exists()
        )
        if exists:
            raise BaseAppException("实例名称已存在")

    @staticmethod
    def get_instances_by_metric(metric: str, instance_id_keys: list):
        """获取监控对象实例"""
        metrics = VictoriaMetricsAPI().query(metric, step="20m")
        instance_map = {}
        for metric_info in metrics.get("data", {}).get("result", []):
            instance_id = str(tuple([metric_info["metric"].get(i) for i in instance_id_keys]))
            if not instance_id:
                continue
            agent_id = metric_info.get("metric", {}).get("agent_id")
            _time = metric_info["value"][0]

            if instance_id not in instance_map:
                instance_map[instance_id] = {
                    "instance_id": instance_id,
                    "agent_id": agent_id,
                    "time": _time,
                }
            else:
                if _time > instance_map[instance_id]["time"]:
                    instance_map[instance_id] = {
                        "instance_id": instance_id,
                        "agent_id": agent_id,
                        "time": _time,
                    }

        return instance_map

    @staticmethod
    def add_attr(items: list):
        # 状态计算, 补充组织
        org_objs = MonitorInstanceOrganization.objects.filter(monitor_instance_id__in=[i["instance_id"] for i in items])
        org_map = {}
        for org in org_objs:
            if org.monitor_instance_id not in org_map:
                org_map[org.monitor_instance_id] = set()
            org_map[org.monitor_instance_id].add(org.organization)

        for conf_info in items:
            conf_info["organization"] = list(org_map.get(conf_info["instance_id"], []))

            if conf_info["time"]:
                conf_info["status"] = "normal"
            else:
                conf_info["status"] = "unavailable"

    @staticmethod
    def get_monitor_instance(
        monitor_object_id,
        page,
        page_size,
        name,
        qs,
        add_metrics=False,
        monitor_plugin_id=None,
    ):
        """获取监控对象实例"""
        qs = qs.filter(monitor_object_id=monitor_object_id, is_deleted=False)
        if name:
            qs = qs.filter(name__icontains=name)

        monitor_obj = MonitorObject.objects.filter(id=monitor_object_id).first()
        if not monitor_obj:
            raise BaseAppException("Monitor object does not exist")
        monitor_objs = MonitorObject.objects.all().values(*MonitorObjConstants.OBJ_KEYS)
        obj_metric_map = {i["name"]: i for i in monitor_objs}
        obj_metric_map = obj_metric_map.get(monitor_obj.name)
        if not obj_metric_map:
            raise BaseAppException("Monitor object default metric does not exist")

        status_query = obj_metric_map.get("default_metric", "")
        if monitor_plugin_id:
            plugin = (
                MonitorPlugin.objects.filter(
                    id=monitor_plugin_id,
                    monitor_object=monitor_object_id,
                )
                .only("id", "status_query")
                .first()
            )
            if not plugin:
                return {"count": 0, "results": []}
            if plugin.status_query:
                status_query = plugin.status_query

        instance_map = MonitorObjectService.get_instances_by_metric(
            status_query,
            obj_metric_map.get("instance_id_keys"),
        )
        if monitor_plugin_id:
            qs = qs.filter(id__in=instance_map.keys())

        # 去除重复
        qs = qs.distinct()

        count = qs.count()

        start = (page - 1) * page_size
        end = start + page_size
        projected_qs = MonitorObjectService._project_instance_identity(qs)
        if page_size == -1:
            objs = projected_qs
        else:
            objs = projected_qs[start:end]
        org_objs = MonitorInstanceOrganization.objects.filter(monitor_instance_id__in=[obj.id for obj in objs])
        org_map = {}
        for org in org_objs:
            if org.monitor_instance_id not in org_map:
                org_map[org.monitor_instance_id] = set()
            org_map[org.monitor_instance_id].add(org.organization)

        result = []

        for obj in objs:
            result.append(MonitorObjectService._serialize_instance_list_item(obj, instance_map, org_map))

        if add_metrics and page_size != -1:
            MonitorObjectService._fill_display_metrics(monitor_object_id, obj_metric_map, result)

        MonitorObjectService.add_attr(result)

        return dict(count=count, results=result)

    @staticmethod
    def _query_metric_values(metric_obj, target_instances):
        """对 target_instances 跑该指标的 VM 查询,返回 {instance_id: value}(同实例多值取最大)。"""
        target_ids = [parse_instance_id(inst["instance_id"]) for inst in target_instances]
        query_parts = []
        for i, key in enumerate(metric_obj.instance_id_keys):
            values_set = {re.escape(str(item[i])) for item in target_ids if len(item) > i and item[i] is not None}
            if not values_set:
                continue
            # re.escape 的反斜杠需再做一次 PromQL 字符串转义,否则 VM 侧报 invalid syntax
            values = MonitorObjectService._escape_promql_label_value("|".join(sorted(values_set)))
            query_parts.append(f'{key}=~"{values}"')

        query = metric_obj.query.replace("__$labels__", f"{', '.join(query_parts)}")
        metrics = VictoriaMetricsAPI().query(query)
        value_map = {}
        for metric in metrics.get("data", {}).get("result", []):
            instance_id = str(tuple([metric["metric"].get(i) for i in metric_obj.instance_id_keys]))
            value = metric["value"][1]
            if instance_id not in value_map:
                value_map[instance_id] = value
            else:
                try:
                    if float(value) > float(value_map[instance_id]):
                        value_map[instance_id] = value
                except (ValueError, TypeError):
                    pass
        return value_map

    @staticmethod
    def _fill_display_metrics(monitor_object_id, obj_metric_map, result):
        """按 display_fields 的 (plugin, metric) 绑定回填展示指标值。

        - 回填 key 用复合 key ``<plugin>::<metric>``(见 display_field_key),避免不同插件的同名
          指标互相覆盖;
        - 按插件(模板)隔离:只把“采集配置归属该插件”的实例纳入该绑定取数,别的插件的实例该列留空。
          无采集配置的实例无法判定插件归属,不展示带插件的绑定指标(显示 --)。
        - 兼容:绑定缺 plugin(遗留配置)时按指标名匹配、不做隔离、用裸指标名回填;display_fields
          为空时退回 supplementary_indicators(裸指标名,不区分插件)。
        """
        bindings = extract_metric_bindings(obj_metric_map.get("display_fields", []))

        if not bindings:
            supplementary = obj_metric_map.get("supplementary_indicators", [])
            if not supplementary:
                return
            for metric_obj in Metric.objects.filter(monitor_object_id=monitor_object_id, name__in=supplementary):
                value_map = MonitorObjectService._query_metric_values(metric_obj, result)
                for instance in result:
                    instance[metric_obj.name] = value_map.get(instance["instance_id"])
            return

        # 实例 -> 其采集配置覆盖的插件名集合(用于按插件隔离)
        instance_plugin_map = {}
        cc_qs = CollectConfig.objects.filter(
            monitor_instance_id__in=[inst["instance_id"] for inst in result],
            monitor_plugin__isnull=False,
        ).values_list("monitor_instance_id", "monitor_plugin__name")
        for inst_id, plugin_name in cc_qs:
            instance_plugin_map.setdefault(inst_id, set()).add(plugin_name)

        # 同名指标可能分属多个插件,按 (plugin, name) 精确取;另留 name 兜底给遗留无 plugin 的绑定
        metric_by_plugin = {}
        metric_by_name = {}
        for metric_obj in Metric.objects.filter(
            monitor_object_id=monitor_object_id,
            name__in=[b["metric"] for b in bindings],
        ).select_related("monitor_plugin"):
            plugin_name = metric_obj.monitor_plugin.name if metric_obj.monitor_plugin_id else ""
            metric_by_plugin[(plugin_name, metric_obj.name)] = metric_obj
            metric_by_name.setdefault(metric_obj.name, metric_obj)

        # 先把每个绑定解析成 (plugin, metric, metric_obj, eligible)
        resolved = []
        for binding in bindings:
            plugin_name, metric_name = binding["plugin"], binding["metric"]
            if plugin_name:
                metric_obj = metric_by_plugin.get((plugin_name, metric_name))
                eligible = [
                    inst for inst in result if plugin_name in instance_plugin_map.get(inst["instance_id"], set())
                ]
            else:
                # 遗留绑定无 plugin:按名取任一插件、不隔离,保持旧行为
                metric_obj = metric_by_name.get(metric_name)
                eligible = result
            if not metric_obj or not eligible:
                continue
            resolved.append((plugin_name, metric_name, metric_obj, eligible))

        # 按「查询模板 + instance_id_keys」分组合并:同名指标(各品牌 query 相同)只发一次 VM 查询,
        # 覆盖该组所有 eligible 实例,再按各绑定的插件分发回各自实例,避免 N 个品牌 = N 次串行查询。
        groups = {}
        for item in resolved:
            metric_obj = item[2]
            group_key = (metric_obj.query, tuple(metric_obj.instance_id_keys))
            groups.setdefault(group_key, []).append(item)

        for items in groups.values():
            union = {}
            for _, _, _, eligible in items:
                for inst in eligible:
                    union[inst["instance_id"]] = inst
            value_map = MonitorObjectService._query_metric_values(items[0][2], list(union.values()))
            for plugin_name, metric_name, _, eligible in items:
                out_key = display_field_key(plugin_name, metric_name)
                for instance in eligible:
                    instance[out_key] = value_map.get(instance["instance_id"])

    @staticmethod
    def _serialize_instance_list_item(obj, instance_map, org_map):
        return {
            "instance_id": obj.id,
            "instance_id_values": list(parse_instance_id(obj.id)),
            "instance_name": obj.name or obj.id,
            "agent_id": instance_map.get(obj.id, {}).get("agent_id", ""),
            "time": instance_map.get(obj.id, {}).get("time", ""),
            "cloud_region_id": obj.cloud_region_id,
            "ip": obj.ip,
            "fallback_sampling_rate": obj.fallback_sampling_rate,
            "organizations": list(org_map.get(obj.id, [])),
        }

    @staticmethod
    def _escape_promql_label_value(value):
        value_str = str(value)
        return value_str.replace("\\", "\\\\").replace('"', '\\"')

    @staticmethod
    def generate_monitor_instance_id(monitor_object_id, monitor_instance_name, interval):
        """生成监控对象实例ID"""
        obj = MonitorInstance.objects.filter(monitor_object_id=monitor_object_id, name=monitor_instance_name).first()
        if obj:
            obj.interval = interval
            obj.save()
            return obj.id
        else:
            # 生成一个uui
            instance_id = uuid.uuid4().hex
            MonitorInstance.objects.create(
                id=instance_id,
                name=monitor_instance_name,
                interval=interval,
                monitor_object_id=monitor_object_id,
            )

            return instance_id

    @staticmethod
    def check_monitor_instance(monitor_object_id, instance_info):
        """创建监控对象实例"""

        instance_id = str(tuple([instance_info["instance_id"]]))
        objs = MonitorInstance.objects.filter(id=instance_id).first()
        if objs:
            raise BaseAppException(f"实例已存在：{instance_info['instance_name']}")

    @staticmethod
    def autodiscover_monitor_instance():
        """同步监控实例数据"""
        sync_instance_and_group.delay()

    @staticmethod
    def set_object_order(order_data: list):
        """
        设置监控对象排序
        :param order_data: [{"type": "OS", "object_list": ["Host"]}, ...]
        """
        with transaction.atomic():
            type_updates = []
            object_updates = []

            # 仅当传入多个类型时才更新类型排序（单个类型表示只是对象内部重排）
            update_type_order = len(order_data) > 1

            # 批量收集需要更新的数据
            for idx, item in enumerate(order_data):
                type_id = item.get("type")
                object_list = item.get("object_list", [])

                # 创建或获取分类对象
                obj_type, created = MonitorObjectType.objects.get_or_create(id=type_id, defaults={"order": idx})
                if update_type_order and not created and obj_type.order != idx:
                    obj_type.order = idx
                    type_updates.append(obj_type)

                # 收集需要更新的监控对象
                for name_idx, name in enumerate(object_list):
                    objects = MonitorObject.objects.filter(name=name, type_id=type_id)
                    for obj in objects:
                        if obj.order != name_idx:
                            obj.order = name_idx
                            object_updates.append(obj)

            # 批量更新
            if type_updates:
                MonitorObjectType.objects.bulk_update(
                    type_updates,
                    ["order"],
                    batch_size=DatabaseConstants.MONITOR_OBJECT_BATCH_SIZE,
                )
            if object_updates:
                MonitorObject.objects.bulk_update(
                    object_updates,
                    ["order"],
                    batch_size=DatabaseConstants.MONITOR_OBJECT_BATCH_SIZE,
                )

    @staticmethod
    def update_instance(instance_id, name=None, organizations=None, **extra_fields):
        """更新监控对象实例"""
        instance = MonitorInstance.objects.filter(id=instance_id).first()
        if not instance:
            raise BaseAppException("Monitor instance does not exist")
        if name:
            MonitorObjectService.validate_update_instance_name_unique(instance, name)
            instance.name = name
        for field in ("cloud_region_id", "ip", "fallback_sampling_rate", "auto"):
            if field in extra_fields and extra_fields[field] is not None:
                setattr(instance, field, extra_fields[field])
        instance.save()

        # 更新组织信息
        if organizations is not None:
            instance.monitorinstanceorganization_set.all().delete()
            for org in organizations:
                instance.monitorinstanceorganization_set.create(organization=org)

    @staticmethod
    def remove_instances_organizations(instance_ids, organizations):
        """删除监控对象实例组织"""
        if not instance_ids or not organizations:
            return

        MonitorInstanceOrganization.objects.filter(monitor_instance_id__in=instance_ids, organization__in=organizations).delete()

    @staticmethod
    def add_instances_organizations(instance_ids, organizations):
        """添加监控对象实例组织"""
        if not instance_ids or not organizations:
            return

        creates = []
        for instance_id in instance_ids:
            for org in organizations:
                creates.append(MonitorInstanceOrganization(monitor_instance_id=instance_id, organization=org))
        MonitorInstanceOrganization.objects.bulk_create(creates, ignore_conflicts=True)

    @staticmethod
    def set_instances_organizations(instance_ids, organizations):
        """设置监控对象实例组织"""
        if not instance_ids:
            return
        organizations = organizations or []

        with transaction.atomic():
            # 删除旧的组织关联
            MonitorInstanceOrganization.objects.filter(monitor_instance_id__in=instance_ids).delete()

            # 添加新的组织关联
            creates = []
            for instance_id in instance_ids:
                for org in organizations:
                    creates.append(MonitorInstanceOrganization(monitor_instance_id=instance_id, organization=org))
            if creates:
                MonitorInstanceOrganization.objects.bulk_create(creates, ignore_conflicts=True)
