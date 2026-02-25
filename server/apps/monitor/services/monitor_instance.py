import ast

from apps.core.exceptions.base_app_exception import BaseAppException
from apps.core.utils.loader import LanguageLoader
from apps.monitor.constants.language import LanguageConstants
from apps.monitor.constants.monitor_object import MonitorObjConstants
from apps.monitor.constants.plugin import PluginConstants
from apps.monitor.models import (
    Metric,
    MonitorObject,
    CollectConfig,
    MonitorPlugin,
    MonitorInstanceOrganization,
    MonitorInstance,
)
from apps.monitor.services.monitor_object import MonitorObjectService
from apps.monitor.utils.victoriametrics_api import VictoriaMetricsAPI
from datetime import datetime, timezone


class InstanceSearch:
    def __init__(self, monitor_obj, query_data, qs=None, locale=None):
        self.monitor_obj = monitor_obj
        self.query_data = query_data
        self.obj_metric_map = self.get_obj_metric_map()
        self.qs = qs
        self.locale = locale or "zh-Hans"

    @staticmethod
    def get_parent_instance_ids(query):
        """获取父对象实例ID列表"""
        metrics = VictoriaMetricsAPI().query(query, step="10m")
        instance_ids = [
            metric_info["metric"].get("instance_id")
            for metric_info in metrics.get("data", {}).get("result", [])
        ]
        return instance_ids

    @staticmethod
    def get_parent_instance_list(monitor_object_id):
        """获取父对象实例列表"""
        # 获取父对象实例ID
        _obj = MonitorObject.objects.filter(id=monitor_object_id).first()
        objs = MonitorInstance.objects.filter(monitor_object_id=_obj.parent_id).values(
            "id", "name"
        )

        data = []
        for obj in objs:
            try:
                _instance_id = ast.literal_eval(obj["id"])[0]
            except (ValueError, SyntaxError, IndexError):
                _instance_id = obj["id"]
            data.append({"id": str(_instance_id), "name": obj["name"]})
        return data

    @staticmethod
    def get_query_params_enum(monitor_obj_name, monitor_object_id=None):
        """获取查询参数枚举"""
        if monitor_obj_name == "Pod":
            query = (
                "count(prometheus_remote_write_kube_pod_info{}) by (instance_id, node)"
            )
            metrics = VictoriaMetricsAPI().query(query)

            # 使用 set 去重
            instance_ids = set()  # Cluster 实例 ID
            node_ids = set()  # Node 实例 ID

            for metric_info in metrics.get("data", {}).get("result", []):
                instance_id = metric_info["metric"].get("instance_id")
                node = metric_info["metric"].get("node")

                if instance_id:
                    # instance_id 作为单元素元组（对应 Cluster 监控实例）
                    instance_ids.add((instance_id,))

                if instance_id and node:
                    # node ID 由 (instance_id, node) 组合而成（对应 Node 监控实例）
                    node_ids.add((instance_id, node))

            # 转换为字符串格式的 ID 列表，用于数据库查询实例名称
            instance_id_strs = [str(iid) for iid in instance_ids]
            node_id_strs = [str(nid) for nid in node_ids]

            # 从数据库查询 Cluster 和 Node 实例名称
            instance_name_map = {}
            node_name_map = {}

            if instance_id_strs:
                # 查询 Cluster 实例名称
                cluster_instances = MonitorInstance.objects.filter(
                    id__in=instance_id_strs
                ).values("id", "name")
                instance_name_map = {
                    inst["id"]: inst["name"] for inst in cluster_instances
                }

            if node_id_strs:
                # 查询 Node 实例名称
                node_instances = MonitorInstance.objects.filter(
                    id__in=node_id_strs
                ).values("id", "name")
                node_name_map = {inst["id"]: inst["name"] for inst in node_instances}

            # 构建返回结果：id 使用原始维度值（用于查询），name 从数据库获取（用于展示）
            instance_list = [
                {
                    "id": iid[0],  # 原始 instance_id 维度值（如 "k8s-prod"）
                    "name": instance_name_map.get(str(iid), iid[0]),  # Cluster 名称
                }
                for iid in instance_ids
            ]

            node_list = [
                {
                    "id": nid[-1],  # 原始 node 维度值（如 "worker-node-1"）
                    "name": node_name_map.get(str(nid), nid[-1]),  # Node 名称
                }
                for nid in node_ids
            ]
            return {"cluster": instance_list, "node": node_list}
        elif monitor_obj_name == "Node":
            query = "count(prometheus_remote_write_kube_node_info) by (instance_id)"
            metrics = VictoriaMetricsAPI().query(query, step="10m")

            # 使用 set 去重
            instance_ids = set()  # Cluster 实例 ID

            for metric_info in metrics.get("data", {}).get("result", []):
                instance_id = metric_info["metric"].get("instance_id")
                if instance_id:
                    # instance_id 作为单元素元组（对应 Cluster 监控实例）
                    instance_ids.add((instance_id,))

            # 转换为字符串格式的 ID 列表，用于数据库查询实例名称
            instance_id_strs = [str(iid) for iid in instance_ids]

            # 从数据库查询 Cluster 实例名称
            instance_name_map = {}
            if instance_id_strs:
                cluster_instances = MonitorInstance.objects.filter(
                    id__in=instance_id_strs
                ).values("id", "name")
                instance_name_map = {
                    inst["id"]: inst["name"] for inst in cluster_instances
                }

            # 构建返回结果：id 使用原始维度值（用于查询），name 从数据库获取（用于展示）
            instance_list = [
                {
                    "id": iid[0],  # 原始 instance_id 维度值（如 "k8s-prod"）
                    "name": instance_name_map.get(str(iid), iid[0]),  # Cluster 名称
                }
                for iid in instance_ids
            ]

            return {"cluster": instance_list}
        elif monitor_obj_name in {"ESXI", "VM", "DataStorage"}:
            return InstanceSearch.get_parent_instance_list(monitor_object_id)
        elif monitor_obj_name in {"CVM"}:
            query = 'any({instance_type="qcloud"}) by (instance_id)'
            return InstanceSearch.get_parent_instance_ids(query)
        elif monitor_obj_name in {"Docker Container"}:
            return InstanceSearch.get_parent_instance_list(monitor_object_id)

    def get_obj_metric_map(self):
        monitor_objs = MonitorObject.objects.all().values(*MonitorObjConstants.OBJ_KEYS)
        obj_metric_map = {i["name"]: i for i in monitor_objs}
        obj_metric_map = obj_metric_map.get(self.monitor_obj.name)
        if not obj_metric_map:
            raise BaseAppException("Monitor object default metric does not exist")
        return obj_metric_map

    def search(self):
        """特殊搜索接口，特殊对象不通用的查询条件"""
        objs_map = self.get_objs()
        if not objs_map:
            return dict(count=0, results=[])
        vm_metrics = self.get_vm_metrics()
        if not vm_metrics:
            return dict(count=0, results=[])
        items = []
        instance_id_keys = self.obj_metric_map.get("instance_id_keys")
        for metric in vm_metrics:
            instance_id = str(
                tuple([metric["metric"].get(i) for i in instance_id_keys])
            )
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

    def search_by_primary_object(self):
        data = self.get_objs_v2()
        if data["count"] == 0:
            return data

        # 初始化语言加载器
        lan = LanguageLoader(app=LanguageConstants.APP, default_lang=self.locale)

        # 获取实例的插件采集状态
        confs = CollectConfig.objects.filter(
            monitor_instance_id__in=[i["instance_id"] for i in data["results"]],
        )
        confs_map = {}
        for conf in confs:
            if conf.monitor_instance_id not in confs_map:
                confs_map[conf.monitor_instance_id] = set()
            confs_map[conf.monitor_instance_id].add(
                (self.monitor_obj.id, conf.collector, conf.collect_type)
            )

        plugin_map, plugin_status_map = {}, {}
        plugins = MonitorPlugin.objects.filter(monitor_object=self.monitor_obj)

        instance_id_keys = self.obj_metric_map.get("instance_id_keys")

        for plugin in plugins:
            plugin_key = (self.monitor_obj.id, plugin.collector, plugin.collect_type)
            # 添加翻译属性
            plugin_key_name = f"{LanguageConstants.MONITOR_OBJECT_PLUGIN}.{plugin.name}"
            plugin_map[plugin_key] = dict(
                name=plugin.name,
                collector=plugin.collector,
                collect_type=plugin.collect_type,
                display_name=lan.get(f"{plugin_key_name}.name") or plugin.name,
                display_description=lan.get(f"{plugin_key_name}.desc")
                or plugin.description,
            )
            plugin_status_map[plugin_key] = self.get_plugin_normal_status_map(
                instance_id_keys, plugin.status_query
            )

        # 反转插件状态映射，方便后续查询
        instance_plugin_status_map = {}
        instance_plugin_time_map = {}

        for c_tuple, instance_map in plugin_status_map.items():
            for instance_id, _time in instance_map.items():
                if instance_id not in instance_plugin_status_map:
                    instance_plugin_status_map[instance_id] = set()
                instance_plugin_status_map[instance_id].add(c_tuple)
                instance_plugin_time_map[(instance_id, c_tuple)] = _time

        # 组织映射
        org_objs = MonitorInstanceOrganization.objects.filter(
            monitor_instance_id__in=[i["instance_id"] for i in data["results"]]
        )
        org_map = {}
        for org in org_objs:
            if org.monitor_instance_id not in org_map:
                org_map[org.monitor_instance_id] = set()
            org_map[org.monitor_instance_id].add(org.organization)

        for item in data["results"]:
            # 添加组织信息
            item["organization"] = list(org_map.get(item["instance_id"], []))
            item["plugins"] = []

            db_confs = confs_map.get(item["instance_id"], set())
            vm_confs = instance_plugin_status_map.get(item["instance_id"], set())

            # 计算插件配置的四种状态类别
            categories = [
                # 自动正常
                (
                    db_confs & vm_confs,
                    PluginConstants.STATUS_NORMAL,
                    PluginConstants.COLLECT_MODE_AUTO,
                ),
                # 自动失联
                (
                    db_confs - vm_confs,
                    PluginConstants.STATUS_OFFLINE,
                    PluginConstants.COLLECT_MODE_AUTO,
                ),
                # 手动正常
                (
                    vm_confs - db_confs,
                    PluginConstants.STATUS_NORMAL,
                    PluginConstants.COLLECT_MODE_MANUAL,
                ),
                # 手动失联理应不存在，如果你想加也可以放这里
                # (set(), PluginConstants.STATUS_OFFLINE, PluginConstants.COLLECT_MODE_MANUAL),
            ]

            # 统一处理插件信息
            for conf_set, status, collect_mode in categories:
                for c_tuple in conf_set:
                    plugin_info = plugin_map.get(c_tuple)
                    if not plugin_info:
                        continue
                    # 补充时间信息
                    plugin_time = instance_plugin_time_map.get(
                        (item["instance_id"], c_tuple)
                    )
                    if plugin_time:
                        plugin_info = dict(plugin_info)
                        plugin_info["time"] = plugin_time

                    # 为了避免修改原对象，复制一份
                    info = dict(plugin_info)
                    info.update(status=status, collect_mode=collect_mode)
                    item["plugins"].append(info)

        return data

    def get_objs(self):
        qs = self.qs.filter(monitor_object_id=self.monitor_obj.id, is_deleted=False)
        name = self.query_data.get("name")
        if name:
            qs = qs.filter(name__icontains=name)

        # 去除重复
        qs = qs.distinct("id")

        objs_map = {i.id: i for i in qs}
        return objs_map

    def get_objs_v2(self):
        qs = self.qs.filter(monitor_object_id=self.monitor_obj.id, is_deleted=False)
        name = self.query_data.get("name")
        if name:
            qs = qs.filter(name__icontains=name)

        # 去除重复
        qs = qs.distinct("id")

        count = qs.count()
        if count == 0:
            return dict(count=0, results=[])

        page = self.query_data.get("page", 1)
        page_size = self.query_data.get("page_size", 10)
        start = (page - 1) * page_size
        end = start + page_size
        results = qs[start:end]

        return dict(
            count=count,
            results=[
                {
                    "instance_id": obj.id,
                    "instance_name": obj.name,
                    "instance_id_values": [i for i in ast.literal_eval(obj.id)]
                    if isinstance(obj.id, str) and obj.id.startswith("(")
                    else [obj.id],
                }
                for obj in results
            ],
        )

    def get_plugin_normal_status_map(self, instance_id_keys, query):
        resp = VictoriaMetricsAPI().query(query, step="20m")
        metrics = resp.get("data", {}).get("result", [])
        status_map = {}
        for metric in metrics:
            instance_id = str(
                tuple([metric["metric"].get(i) for i in instance_id_keys])
            )
            iso_time = datetime.fromtimestamp(
                metric["value"][0], tz=timezone.utc
            ).isoformat()
            status_map[instance_id] = iso_time
        return status_map

    def get_vm_metrics(self):
        query = self.obj_metric_map.get("default_metric")
        vm_params = self.query_data.get("vm_params")
        params_str = ",".join([f'{k}="{v}"' for k, v in vm_params.items() if v])
        if vm_params:
            if "}" in query:
                query = query.replace("}", f",{params_str}}}")
            else:
                query = f"{query}{{{params_str}}}"
        metrics = VictoriaMetricsAPI().query(query, step="20m")
        return metrics.get("data", {}).get("result", [])

    def add_other_metrics(self, items):
        instance_ids = []
        for instance_info in items:
            instance_id = ast.literal_eval(instance_info["instance_id"])
            instance_ids.append(instance_id)

        metrics_obj = Metric.objects.filter(
            monitor_object_id=self.monitor_obj.id,
            name__in=self.obj_metric_map.get("supplementary_indicators", []),
        )

        for metric_obj in metrics_obj:
            query_parts = []
            for i, key in enumerate(metric_obj.instance_id_keys):
                values = "|".join(set(item[i] for item in instance_ids))  # 去重并拼接
                query_parts.append(f'{key}=~"{values}"')

            query = metric_obj.query
            query = query.replace("__$labels__", f"{', '.join(query_parts)}")
            metrics = VictoriaMetricsAPI().query(query, step="10m")
            _metric_map = {}
            for metric in metrics.get("data", {}).get("result", []):
                instance_id = str(
                    tuple(
                        [metric["metric"].get(i) for i in metric_obj.instance_id_keys]
                    )
                )
                value = metric["value"][1]
                if instance_id not in _metric_map:
                    _metric_map[instance_id] = value
                else:
                    try:
                        if float(value) > float(_metric_map[instance_id]):
                            _metric_map[instance_id] = value
                    except (ValueError, TypeError):
                        pass
            for instance in items:
                instance[metric_obj.name] = _metric_map.get(instance["instance_id"])

        return items
