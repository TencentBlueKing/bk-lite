import ast

from apps.core.exceptions.base_app_exception import BaseAppException
from apps.monitor.constants.monitor_object import MonitorObjConstants
from apps.monitor.models import Metric, MonitorObject
from apps.monitor.services.monitor_object import MonitorObjectService
from apps.monitor.utils.victoriametrics_api import VictoriaMetricsAPI


class InstanceSearch:
    def __init__(self, monitor_obj, query_data, qs=None):
        self.monitor_obj = monitor_obj
        self.query_data = query_data
        self.obj_metric_map = self.get_obj_metric_map()
        self.qs = qs

    @staticmethod
    def get_parent_instance_ids(query):
        """获取父对象实例ID列表"""
        metrics = VictoriaMetricsAPI().query(query)
        instance_ids = [metric_info["metric"].get("instance_id") for metric_info in
                    metrics.get("data", {}).get("result", [])]
        return instance_ids

    @staticmethod
    def get_query_params_enum(monitor_obj_name):
        """获取查询参数枚举"""
        if monitor_obj_name == "Pod":
            query = "count(prometheus_remote_write_kube_pod_info{}) by (instance_id, namespace, created_by_kind, created_by_name, node)"
            metrics = VictoriaMetricsAPI().query(query)
            map = {}
            for metric_info in  metrics.get("data", {}).get("result", []):
                instance_id = metric_info["metric"].get("instance_id")
                if instance_id not in map:
                    map[instance_id] = {}
                namespace = metric_info["metric"].get("namespace")
                if namespace not in map[instance_id]:
                    map[instance_id][namespace] = {}
                created_by_kind = metric_info["metric"].get("created_by_kind")
                created_by_name = metric_info["metric"].get("created_by_name")
                if "workload" not in map[instance_id][namespace]:
                    map[instance_id][namespace]["workload"] = []
                map[instance_id][namespace]["workload"].append({"created_by_kind": created_by_kind, "created_by_name": created_by_name})
                node = metric_info["metric"].get("node")
                if "node" not in map[instance_id][namespace]:
                    map[instance_id][namespace]["node"] = []
                map[instance_id][namespace]["node"].append(node)
            return map
        elif monitor_obj_name == "Node":
            query = "count(prometheus_remote_write_kube_node_info) by (instance_id)"
            return InstanceSearch.get_parent_instance_ids(query)
        elif monitor_obj_name in {"ESXI", "VM", "DataStorage"}:
            query = 'any({instance_type="vmware"}) by (instance_id)'
            return InstanceSearch.get_parent_instance_ids(query)
        elif monitor_obj_name in {"CVM"}:
            query = 'any({instance_type="qcloud"}) by (instance_id)'
            return InstanceSearch.get_parent_instance_ids(query)
        elif monitor_obj_name in {"Docker Container"}:
            query = 'any({instance_type="docker"}) by (instance_id)'
            return InstanceSearch.get_parent_instance_ids(query)

    def get_obj_metric_map(self):

        monitor_objs = MonitorObject.objects.all().values(*MonitorObjConstants.OBJ_KEYS)
        obj_metric_map = {i["name"]: i for i in monitor_objs}
        obj_metric_map = obj_metric_map.get(self.monitor_obj.name)
        if not obj_metric_map:
            raise BaseAppException("Monitor object default metric does not exist")
        return obj_metric_map

    def search(self):
        objs_map = self.get_objs()
        if not objs_map:
            return dict(count=0, results=[])
        vm_metrics = self.get_vm_metrics()
        if not vm_metrics:
            return dict(count=0, results=[])
        items = []
        instance_id_keys = self.obj_metric_map.get("instance_id_keys")
        for metric in vm_metrics:
            instance_id = str(tuple([metric["metric"].get(i) for i in instance_id_keys]))
            if instance_id not in objs_map:
                continue
            obj = objs_map[instance_id]
            item = dict(**metric["metric"])
            item.update(
                instance_id=instance_id,
                instance_id_values=[i for i in ast.literal_eval(instance_id)],
                instance_name=obj.name or obj.id,
                time=metric["value"][0],
                value=metric["value"][1],
            )
            items.append(item)
        # 数据合并，取objs和vm_metrics的交集
        page = self.query_data.get("page", 1)
        page_size = self.query_data.get("page_size", 10)
        start = (page - 1) * page_size
        end = start + page_size
        count = len(items)
        if page_size == -1:
            results = items
        else:
            results = items[start:end]

        if self.query_data.get("add_metrics", False) and page_size != -1:
            results = self.add_other_metrics(results)

        MonitorObjectService.add_attr(results)

        return dict(count=count, results=results)

    def get_objs(self):
        qs = self.qs.filter(monitor_object_id=self.monitor_obj.id, is_deleted=False)
        name = self.query_data.get("name")
        if name:
            qs = qs.filter(name__icontains=name)

        # 去除重复
        qs = qs.distinct("id")

        objs_map = {i.id: i for i in qs}
        return objs_map

    def get_vm_metrics(self):
        query = self.obj_metric_map.get("default_metric")
        vm_params = self.query_data.get("vm_params")
        params_str = ",".join([f'{k}="{v}"' for k, v in vm_params.items() if v])
        if vm_params:
            if "}" in query:
                query = query.replace("}", f",{params_str}}}")
            else:
                query = f"{query}{{{params_str}}}"
        metrics = VictoriaMetricsAPI().query(query)
        return metrics.get("data", {}).get("result", [])

    def add_other_metrics(self, items):
        instance_ids = []
        for instance_info in items:
            instance_id = ast.literal_eval(instance_info["instance_id"])
            instance_ids.append(instance_id)

        metrics_obj = Metric.objects.filter(
            monitor_object_id=self.monitor_obj.id, name__in=self.obj_metric_map.get("supplementary_indicators", []))

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
            for instance in items:
                instance[metric_obj.name] = _metric_map.get(instance["instance_id"])

        return items
