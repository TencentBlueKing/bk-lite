import ast
import uuid
from collections import defaultdict

from django.db import transaction

from apps.core.exceptions.base_app_exception import BaseAppException
from apps.monitor.constants import OBJ_ORDER, DEFAULT_OBJ_ORDER, MONITOR_OBJ_KEYS
from apps.monitor.models.monitor_metrics import Metric
from apps.monitor.models.monitor_object import MonitorInstance, MonitorObject, MonitorInstanceOrganization
from apps.monitor.models.setting import Setting
from apps.monitor.utils.victoriametrics_api import VictoriaMetricsAPI
from apps.monitor.tasks.grouping_rule import sync_instance_and_group

class MonitorObjectService:

    @staticmethod
    def get_instances_by_metric(metric: str, instance_id_keys: list):
        """获取监控对象实例"""
        metrics = VictoriaMetricsAPI().query(metric)
        instance_map = {}
        for metric_info in metrics.get("data", {}).get("result", []):
            instance_id = str(tuple([metric_info["metric"].get(i) for i in instance_id_keys]))
            if not instance_id:
                continue
            agent_id = metric_info.get("metric", {}).get("agent_id")
            _time = metric_info["value"][0]

            if instance_id not in instance_map:
                instance_map[instance_id] = {"instance_id": instance_id, "agent_id": agent_id, "time": _time}
            else:
                if _time > instance_map[instance_id]["time"]:
                    instance_map[instance_id] = {"instance_id": instance_id, "agent_id": agent_id, "time": _time}

        return instance_map

    @staticmethod
    def add_attr(items: list):
        # 状态计算, 补充组织
        org_objs = MonitorInstanceOrganization.objects.filter(
            monitor_instance_id__in=[i["instance_id"] for i in items])
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
    def get_monitor_instance(monitor_object_id, page, page_size, name, qs, add_metrics=False):
        """获取监控对象实例"""
        start = (page - 1) * page_size
        end = start + page_size

        qs = qs.filter(monitor_object_id=monitor_object_id, is_deleted=False)
        if name:
            qs = qs.filter(name__icontains=name)

        # 去除重复
        qs = qs.distinct("id")

        count = qs.count()

        if page_size == -1:
            objs = qs
        else:
            objs = qs[start:end]

        monitor_obj = MonitorObject.objects.filter(id=monitor_object_id).first()
        if not monitor_obj:
            raise BaseAppException("Monitor object does not exist")
        monitor_objs = MonitorObject.objects.all().values(*MONITOR_OBJ_KEYS)
        obj_metric_map = {i["name"]: i for i in monitor_objs}
        obj_metric_map = obj_metric_map.get(monitor_obj.name)
        if not obj_metric_map:
            raise BaseAppException("Monitor object default metric does not exist")
        instance_map = MonitorObjectService.get_instances_by_metric(obj_metric_map.get("default_metric", ""), obj_metric_map.get("instance_id_keys"))
        result = []

        for obj in objs:
            result.append({
                "instance_id": obj.id,
                "instance_id_values": [i for i in ast.literal_eval(obj.id)],
                "instance_name": obj.name or obj.id,
                "agent_id": instance_map.get(obj.id, {}).get("agent_id", ""),
                "time": instance_map.get(obj.id, {}).get("time", ""),
            })

        if add_metrics and page_size != -1:

            instance_ids = []
            for instance_info in result:
                instance_id = ast.literal_eval(instance_info["instance_id"])
                instance_ids.append(instance_id)

            metrics_obj = Metric.objects.filter(
                monitor_object_id=monitor_object_id, name__in=obj_metric_map.get("supplementary_indicators", []))
            for metric_obj in metrics_obj:
                query_parts = []
                for i, key in enumerate(metric_obj.instance_id_keys):
                    values = "|".join(set(item[i] for item in instance_ids))  # 去重并拼接
                    query_parts.append(f'{key}=~"{values}"')

                query = metric_obj.query
                query = query.replace("__$labels__", f"{', '.join(query_parts)}")
                metrics = VictoriaMetricsAPI().query(query)
                _metric_map = {}
                for metric in metrics.get("data", {}).get("result", []):
                    instance_id = str(tuple([metric["metric"].get(i) for i in metric_obj.instance_id_keys]))
                    value = metric["value"][1]
                    _metric_map[instance_id] = value
                for instance in result:
                    instance[metric_obj.name] = _metric_map.get(instance["instance_id"])

        MonitorObjectService.add_attr(result)

        return  dict(count=count, results=result)

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
                id=instance_id, name=monitor_instance_name, interval=interval, monitor_object_id=monitor_object_id)

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
    def set_object_order(order: list):
        """设置监控对象排序"""
        Setting.objects.update_or_create(name=OBJ_ORDER, defaults={"value": order})

    @staticmethod
    def sort_items(data):
        """
        :param data: list, 每个元素是 {"type": "G1", "name": "I1"}
        :return: 排序后的数据列表
        """

        order_obj = Setting.objects.filter(name=OBJ_ORDER).first()
        order_obj_value = order_obj.value if order_obj else DEFAULT_OBJ_ORDER
        item_order = {i["type"]: i["name_list"] for i in order_obj_value}
        group_order = [i["type"] for i in order_obj_value]

        # 按 type 分组
        grouped_data = defaultdict(list)
        group_appearance_order = []  # 记录 type 出现顺序
        for item in data:
            grouped_data[item["type"]].append(item)
            if item["type"] not in group_appearance_order:
                group_appearance_order.append(item["type"])  # 记录出现顺序

        # 确定分组排序
        if group_order:
            sorted_groups = sorted(grouped_data.keys(),
                                   key=lambda g: (group_order.index(g) if g in group_order else float('inf')))
        else:
            sorted_groups = group_appearance_order  # 按出现顺序排序（可改成 sorted(grouped_data.keys()) 变成字母序）

        sorted_result = []

        for group in sorted_groups:
            items = grouped_data[group]

            # 确定子数据排序
            if group in item_order and item_order[group]:
                sorted_items = sorted(items, key=lambda x: (
                    item_order[group].index(x["name"]) if x["name"] in item_order[group] else float('inf')))
            else:
                sorted_items = items  # 维持原始顺序（可改成 sorted(items, key=lambda x: x["name"]) 变成按 name 排序）

            sorted_result.extend(sorted_items)

        return sorted_result

    @staticmethod
    def update_instance(instance_id, name, organizations):
        """更新监控对象实例"""
        instance = MonitorInstance.objects.filter(id=instance_id).first()
        if not instance:
            raise BaseAppException("Monitor instance does not exist")
        if name:
            instance.name = name
            instance.save()

        # 更新组织信息
        instance.monitorinstanceorganization_set.all().delete()
        for org in organizations:
            instance.monitorinstanceorganization_set.create(organization=org)


    @staticmethod
    def remove_instances_organizations(instance_ids, organizations):
        """删除监控对象实例组织"""
        if not instance_ids or not organizations:
            return

        MonitorInstanceOrganization.objects.filter(
            monitor_instance_id__in=instance_ids,
            organization__in=organizations
        ).delete()

    @staticmethod
    def add_instances_organizations(instance_ids, organizations):
        """添加监控对象实例组织"""
        if not instance_ids or not organizations:
            return

        creates = []
        for instance_id in instance_ids:
            for org in organizations:
                creates.append(MonitorInstanceOrganization(
                    monitor_instance_id=instance_id,
                    organization=org
                ))
        MonitorInstanceOrganization.objects.bulk_create(creates, ignore_conflicts=True)

    @staticmethod
    def set_instances_organizations(instance_ids, organizations):
        """设置监控对象实例组织"""
        if not instance_ids or not organizations:
            return

        with transaction.atomic():
            # 删除旧的组织关联
            MonitorInstanceOrganization.objects.filter(
                monitor_instance_id__in=instance_ids
            ).delete()

            # 添加新的组织关联
            creates = []
            for instance_id in instance_ids:
                for org in organizations:
                    creates.append(MonitorInstanceOrganization(
                        monitor_instance_id=instance_id,
                        organization=org
                    ))
            MonitorInstanceOrganization.objects.bulk_create(creates, ignore_conflicts=True)
