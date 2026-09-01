import json
import os
import re
from collections import Counter
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone

from apps.core.exceptions.base_app_exception import BaseAppException
from apps.core.logger import monitor_logger as logger
from apps.core.utils.loader import LanguageLoader
from apps.monitor.constants.language import LanguageConstants
from apps.monitor.constants.monitor_object import MonitorObjConstants
from apps.monitor.constants.plugin import PluginConstants
from apps.monitor.models import CollectConfig, Metric, MonitorInstance, MonitorInstanceOrganization, MonitorObject, MonitorPlugin
from apps.monitor.services.host_container_asset_ip import fill_missing_host_container_asset_ips
from apps.monitor.services.monitor_object import MonitorObjectService
from apps.monitor.utils.dimension import parse_instance_id
from apps.monitor.utils.instance import list_reporting_status
from apps.monitor.utils.last_sample import LAST_SAMPLE_LOOKBACK, last_sample_timestamp_query, last_sample_unix_seconds
from apps.monitor.utils.victoriametrics_api import VictoriaMetricsAPI
from apps.rpc.node_mgmt import NodeMgmt

# 实例列表页插件状态查询的最大并发度：每个插件的 status_query 是一次独立 VM 读，
# 去重后并发拉取以消除「插件越多越慢」的串行 N+1。保守默认 8，可经 env 调。
PLUGIN_STATUS_QUERY_MAX_WORKERS = int(os.getenv("MONITOR_PLUGIN_STATUS_QUERY_MAX_WORKERS", "8"))

# vm_params 中非 Enum 指标名的保留键（不参与通用 Enum 过滤）。
_VM_PARAM_RESERVED_KEYS = frozenset({"instance_id", "node", "status", "asset.ip"})

# 字段展示列（云平台子对象 IP 等）的筛选参数前缀。与主机 asset.ip 的筛选参数彼此独立，
# 取值来自指标 label 而非 summary_facts。
FIELD_PARAM_PREFIX = "field:"

# 字段展示列候选项上限：label 取值是开放集合，配合下拉内检索使用，避免下发超大列表。
FIELD_OPTION_LIMIT = int(os.getenv("MONITOR_FIELD_OPTION_LIMIT", "500"))


class InstanceSearch:
    def __init__(self, monitor_obj, query_data, qs=None, locale=None, visible_organization_ids=None):
        self.monitor_obj = monitor_obj
        self.query_data = query_data
        self.obj_metric_map = self.get_obj_metric_map()
        self.qs = qs
        self.locale = locale or "zh-Hans"
        self.visible_organization_ids = visible_organization_ids

    @staticmethod
    def get_parent_instance_ids(query):
        """获取父对象实例ID列表"""
        metrics = VictoriaMetricsAPI().query(query, step="10m")
        instance_ids = [metric_info["metric"].get("instance_id") for metric_info in metrics.get("data", {}).get("result", [])]
        return instance_ids

    @staticmethod
    def get_parent_instance_list(monitor_object_id):
        """获取父对象实例列表"""
        # 获取父对象实例ID
        _obj = MonitorObject.objects.filter(id=monitor_object_id).first()
        objs = MonitorInstance.objects.filter(monitor_object_id=_obj.parent_id).values("id", "name")

        data = []
        for obj in objs:
            try:
                _instance_id = parse_instance_id(obj["id"])[0]
            except IndexError:
                _instance_id = obj["id"]
            data.append({"id": str(_instance_id), "name": obj["name"]})
        return data

    @staticmethod
    def get_process_host_filter_enum():
        """进程列表过滤项：按进程实例归属主机枚举（形态对齐 K8s cluster）。"""
        process_ids = MonitorInstance.objects.filter(
            monitor_object__name="Process",
            is_deleted=False,
        ).values_list("id", flat=True)
        host_ids = []
        seen = set()
        for process_id in process_ids:
            parts = parse_instance_id(process_id)
            if not parts:
                continue
            host_id = str(parts[0])
            if not host_id or host_id in seen:
                continue
            seen.add(host_id)
            host_ids.append(host_id)

        host_name_map = {}
        if host_ids:
            host_storage_ids = [str((host_id,)) for host_id in host_ids]
            for host in MonitorInstance.objects.filter(
                monitor_object__name="Host",
                id__in=host_storage_ids,
                is_deleted=False,
            ).values("id", "name"):
                parts = parse_instance_id(host["id"])
                if not parts:
                    continue
                host_name_map[str(parts[0])] = host["name"] or str(parts[0])

        return {
            "cluster": [
                {
                    "id": host_id,
                    "name": host_name_map.get(host_id, host_id),
                }
                for host_id in sorted(host_ids)
            ],
            "asset_ips": InstanceSearch.collect_asset_ip_options("Process"),
        }

    @staticmethod
    def collect_asset_ip_options(monitor_obj_name):
        """收集监控对象实例的去重 asset.ip（摘要事实优先，其次模型 ip 字段）。"""
        if not monitor_obj_name:
            return []
        ips = set()
        for ip, facts in MonitorInstance.objects.filter(
            monitor_object__name=monitor_obj_name,
            is_deleted=False,
        ).values_list("ip", "summary_facts"):
            if isinstance(facts, dict):
                fact_ip = facts.get("asset.ip")
                if fact_ip not in (None, ""):
                    ips.add(str(fact_ip).strip())
                    continue
            if ip not in (None, ""):
                ips.add(str(ip).strip())
        return sorted(ip for ip in ips if ip)

    @staticmethod
    def get_query_params_enum(monitor_obj_name, monitor_object_id=None):
        """获取查询参数枚举。

        在对象各自的枚举之上，合并字段展示列（云平台子对象 IP 等）的候选取值。
        """
        data = InstanceSearch._get_query_params_enum(monitor_obj_name, monitor_object_id)
        field_options = InstanceSearch.collect_display_field_options(monitor_object_id)
        if not field_options:
            return data
        # ESXI/VM 等父实例枚举是 list；不能 dict(list) 丢掉，否则前端 colony 筛选为空。
        if isinstance(data, dict):
            merged = dict(data)
        elif isinstance(data, list):
            merged = {"items": data}
        else:
            merged = {}
        merged["field_options"] = field_options
        return merged

    @staticmethod
    def _get_query_params_enum(monitor_obj_name, monitor_object_id=None):
        """获取查询参数枚举"""
        if monitor_obj_name == "Host":
            return {"asset_ips": InstanceSearch.collect_asset_ip_options("Host")}
        if monitor_obj_name == "Pod":
            query = "count(prometheus_remote_write_kube_pod_info{}) by (instance_id, node)"
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

            # 从数据库查询 Cluster / Node 实例名称
            instance_name_map = {}
            node_name_map = {}

            if instance_id_strs:
                # 查询 Cluster 实例名称
                cluster_instances = MonitorInstance.objects.filter(id__in=instance_id_strs).values("id", "name")
                instance_name_map = {inst["id"]: inst["name"] for inst in cluster_instances}

            if node_id_strs:
                node_instances = MonitorInstance.objects.filter(id__in=node_id_strs).values("id", "name")
                node_name_map = {inst["id"]: inst["name"] for inst in node_instances}

            # 构建返回结果：id 使用原始维度值（用于查询），name 从数据库获取（用于展示）
            instance_list = [
                {
                    "id": iid[0],  # 原始 instance_id 维度值（如 "k8s-prod"）
                    "name": instance_name_map.get(str(iid), iid[0]),  # Cluster 名称
                }
                for iid in instance_ids
            ]

            # 节点过滤：保留手动改名；仅当库内名等于自动发现拼接名（uuid__hostname）
            # 时改展示 kube 节点名，避免 240px 下拉被截成一串 id。
            seen_nodes = set()
            node_list = []
            for nid in node_ids:
                node = nid[-1]
                if node in seen_nodes:
                    continue
                seen_nodes.add(node)
                db_name = node_name_map.get(str(nid))
                auto_joined = "__".join(str(part) for part in nid)
                display_name = node if (not db_name or db_name == auto_joined) else db_name
                node_list.append({"id": node, "name": display_name})
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
                cluster_instances = MonitorInstance.objects.filter(id__in=instance_id_strs).values("id", "name")
                instance_name_map = {inst["id"]: inst["name"] for inst in cluster_instances}

            # 构建返回结果：id 使用原始维度值（用于查询），name 从数据库获取（用于展示）
            instance_list = [
                {
                    "id": iid[0],  # 原始 instance_id 维度值（如 "k8s-prod"）
                    "name": instance_name_map.get(str(iid), iid[0]),  # Cluster 名称
                }
                for iid in instance_ids
            ]

            return {"cluster": instance_list}
        elif monitor_obj_name == "Process":
            return InstanceSearch.get_process_host_filter_enum()
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

    @staticmethod
    def _project_instance_identity(qs):
        return qs.only(
            "id",
            "name",
            "interval",
            "cloud_region_id",
            "ip",
            "summary_facts",
            "fallback_sampling_rate",
            "node_id",
            "cmdb_id",
        )

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
            instance_id = str(tuple(metric["metric"].get(i) for i in instance_id_keys))
            if instance_id not in objs_map:
                continue
            obj = objs_map[instance_id]
            item = dict(**metric["metric"])
            last_sample = last_sample_unix_seconds(metric)
            item.update(
                instance_id=instance_id,
                instance_id_values=list(parse_instance_id(instance_id)),
                instance_name=obj.name or obj.id,
                interval=obj.interval,
                ip=obj.ip,
                summary_facts=obj.summary_facts,
                time=last_sample or "",
                value=metric["value"][1],
            )
            items.append(item)

        vm_params = self.query_data.get("vm_params") or {}
        if isinstance(vm_params, dict):
            items = InstanceSearch.apply_status_filter_to_items(items, vm_params.get("status"))

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
            MonitorObjectService._fill_display_metrics(self.monitor_obj.id, self.obj_metric_map, results)

        MonitorObjectService.add_attr(results, self.visible_organization_ids)

        return dict(count=count, results=results)

    def search_by_primary_object(self):
        data = self.get_objs_v2()
        if data["count"] == 0:
            return data

        # 初始化语言加载器
        lan = LanguageLoader(app=LanguageConstants.APP, default_lang=self.locale)

        # 获取实例的插件采集状态
        confs = CollectConfig.objects.select_related("monitor_plugin").filter(
            monitor_instance_id__in=[i["instance_id"] for i in data["results"]],
        )
        confs_map = {}
        config_ids_by_instance_plugin = {}
        for conf in confs:
            if conf.monitor_instance_id not in confs_map:
                confs_map[conf.monitor_instance_id] = set()
            plugin_key = conf.monitor_plugin_id if conf.monitor_plugin_id else (self.monitor_obj.id, conf.collector, conf.collect_type)
            confs_map[conf.monitor_instance_id].add(plugin_key)
            if conf.is_child:
                config_ids_by_instance_plugin.setdefault((conf.monitor_instance_id, plugin_key), set()).add(conf.id)

        nodes_by_config_id = self._batch_collection_nodes_by_config_ids(
            {config_id for config_ids in config_ids_by_instance_plugin.values() for config_id in config_ids}
        )

        plugin_map, plugin_status_map = {}, {}
        plugins = list(MonitorPlugin.objects.filter(monitor_object=self.monitor_obj))
        legacy_plugin_key_counts = Counter((self.monitor_obj.id, plugin.collector, plugin.collect_type) for plugin in plugins)

        instance_id_keys = self.obj_metric_map.get("instance_id_keys")

        # 先去重各插件的 status_query 并并发拉取状态映射，避免在下面的插件循环里逐个串行发 VM 查询
        status_map_by_query = self._batch_plugin_status_maps(
            instance_id_keys,
            {plugin.status_query for plugin in plugins},
        )

        for plugin in plugins:
            # 添加翻译属性
            plugin_key_name = f"{LanguageConstants.MONITOR_OBJECT_PLUGIN}.{plugin.name}"
            plugin_info = dict(
                name=plugin.name,
                plugin_id=plugin.id,
                collector=plugin.collector,
                collect_type=plugin.collect_type,
                display_name=lan.get(f"{plugin_key_name}.name") or plugin.name,
                display_description=lan.get(f"{plugin_key_name}.desc") or plugin.description,
            )
            plugin_map[plugin.id] = plugin_info

            legacy_plugin_key = (self.monitor_obj.id, plugin.collector, plugin.collect_type)
            plugin_map.setdefault(legacy_plugin_key, plugin_info)

            status_map = status_map_by_query.get(plugin.status_query, {})
            plugin_status_map[plugin.id] = status_map
            if legacy_plugin_key_counts[legacy_plugin_key] == 1:
                plugin_status_map[legacy_plugin_key] = status_map

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
        org_objs = MonitorInstanceOrganization.objects.filter(monitor_instance_id__in=[i["instance_id"] for i in data["results"]])
        org_objs = MonitorObjectService._filter_visible_organizations(org_objs, self.visible_organization_ids)
        org_map = {}
        for org in org_objs:
            if org.monitor_instance_id not in org_map:
                org_map[org.monitor_instance_id] = set()
            org_map[org.monitor_instance_id].add(org.organization)

        for item in data["results"]:
            # 添加组织信息
            item["organization"] = list(org_map.get(item["instance_id"], []))
            item["plugins"] = []
            appended_plugin_ids = set()

            db_confs = confs_map.get(item["instance_id"], set())
            vm_confs = instance_plugin_status_map.get(item["instance_id"], set())

            # 计算插件配置的四种状态类别
            categories = [
                # 自动正常
                (
                    db_confs & vm_confs,
                    PluginConstants.STATUS_NORMAL,
                    PluginConstants.COLLECT_MODE_AUTO,
                    True,
                    PluginConstants.CONFIG_SOURCE_CONFIGURED_REPORTED,
                ),
                # 自动失联
                (
                    db_confs - vm_confs,
                    PluginConstants.STATUS_OFFLINE,
                    PluginConstants.COLLECT_MODE_AUTO,
                    True,
                    PluginConstants.CONFIG_SOURCE_CONFIGURED,
                ),
                # 手动正常
                (
                    vm_confs - db_confs,
                    PluginConstants.STATUS_NORMAL,
                    PluginConstants.COLLECT_MODE_MANUAL,
                    False,
                    PluginConstants.CONFIG_SOURCE_REPORTED_ONLY,
                ),
                # 手动失联理应不存在，如果你想加也可以放这里
                # (set(), PluginConstants.STATUS_OFFLINE, PluginConstants.COLLECT_MODE_MANUAL),
            ]

            # 统一处理插件信息
            for conf_set, status, collect_mode, configured, config_source in categories:
                for c_tuple in conf_set:
                    plugin_info = plugin_map.get(c_tuple)
                    if not plugin_info:
                        continue
                    # 补充时间信息
                    plugin_time = instance_plugin_time_map.get((item["instance_id"], c_tuple))
                    if plugin_time:
                        plugin_info = dict(plugin_info)
                        plugin_info["time"] = plugin_time

                    # 为了避免修改原对象，复制一份
                    info = dict(plugin_info)
                    plugin_id = info.get("plugin_id")
                    if plugin_id in appended_plugin_ids:
                        continue
                    appended_plugin_ids.add(plugin_id)
                    info.update(
                        status=status,
                        collect_mode=collect_mode,
                        configured=configured,
                        config_source=config_source,
                        collector_nodes=self._collection_nodes_for_plugin(
                            item["instance_id"],
                            c_tuple,
                            collect_mode,
                            config_ids_by_instance_plugin,
                            nodes_by_config_id,
                        ),
                    )
                    item["plugins"].append(info)

            # 同一物理插件可能同时以 plugin.id 与 legacy (obj, collector, collect_type)
            # 元组两种键出现在 vm_confs 中，导致「集成模板」列同一模板渲染两次（一条
            # 自动正常、一条幻影手动）。按模板身份去重，仅保留状态优先级最高的一条。
            item["plugins"] = self._dedupe_instance_plugins(item["plugins"])

        return data

    def _batch_collection_nodes_by_config_ids(self, config_ids):
        """一次 RPC 获取当前页所有子配置的授权采集节点。"""
        normalized_ids = sorted({str(config_id) for config_id in config_ids if config_id not in (None, "")})
        if not normalized_ids or not self.visible_organization_ids:
            return {}
        try:
            rows = NodeMgmt().get_child_config_nodes_by_ids(
                normalized_ids,
                sorted(self.visible_organization_ids),
            )
        except Exception:
            logger.exception("批量查询采集配置关联节点失败，实例列表将按未关联展示")
            return {}

        nodes_by_config_id = {}
        for row in rows or []:
            if not isinstance(row, dict) or row.get("id") in (None, ""):
                continue
            normalized_nodes = {}
            for node in row.get("nodes") or []:
                if not isinstance(node, dict) or node.get("id") in (None, ""):
                    continue
                node_id = str(node["id"])
                normalized_nodes[node_id] = {
                    "id": node_id,
                    "name": str(node.get("name") or node_id),
                }
            nodes_by_config_id[str(row["id"])] = list(normalized_nodes.values())
        return nodes_by_config_id

    @staticmethod
    def _collection_nodes_for_plugin(
        instance_id,
        plugin_key,
        collect_mode,
        config_ids_by_instance_plugin,
        nodes_by_config_id,
    ):
        if collect_mode != PluginConstants.COLLECT_MODE_AUTO:
            return []
        nodes_by_id = {}
        for config_id in config_ids_by_instance_plugin.get((instance_id, plugin_key), set()):
            for node in nodes_by_config_id.get(str(config_id), []):
                nodes_by_id[node["id"]] = node
        return sorted(
            nodes_by_id.values(),
            key=lambda node: (node["name"].casefold(), node["name"], node["id"]),
        )

    @staticmethod
    def _dedupe_instance_plugins(plugins):
        """按模板身份 (collector, collect_type, name) 去重实例插件徽标。

        一个物理插件模板可能因 plugin.id 与 legacy 元组双键而重复出现；本方法在
        保留不同模板（如 exporter 与 database）的前提下，折叠同一模板的重复条目，
        并保留采集状态优先级最高的一条：自动正常 > 自动失联 > 手动正常。返回新列表，
        不修改入参。
        """
        status_priority = {
            (PluginConstants.COLLECT_MODE_AUTO, PluginConstants.STATUS_NORMAL): 0,
            (PluginConstants.COLLECT_MODE_AUTO, PluginConstants.STATUS_OFFLINE): 1,
            (PluginConstants.COLLECT_MODE_MANUAL, PluginConstants.STATUS_NORMAL): 2,
        }
        best = {}
        order = []
        for plugin in plugins:
            key = (plugin.get("collector"), plugin.get("collect_type"), plugin.get("name"))
            rank = status_priority.get((plugin.get("collect_mode"), plugin.get("status")), 99)
            if key not in best:
                best[key] = (rank, plugin)
                order.append(key)
            elif rank < best[key][0]:
                best[key] = (rank, plugin)
        return [best[key][1] for key in order]

    def _apply_process_filters(self, qs):
        """列表/搜索共用：主机归属 + asset.ip + Enum 指标多值过滤。"""
        return InstanceSearch.apply_process_instance_filters(
            qs,
            getattr(self.monitor_obj, "name", None),
            self.query_data.get("vm_params"),
            monitor_object_id=getattr(self.monitor_obj, "id", None),
        )

    @staticmethod
    def apply_process_instance_filters(qs, monitor_obj_name, vm_params, monitor_object_id=None):
        """按 vm_params 过滤实例：Process 主机多选 + asset.ip 多选 + 字段展示列多选 + Enum 指标多选。"""
        qs = InstanceSearch.apply_process_host_filters(qs, monitor_obj_name, vm_params)
        qs = InstanceSearch.apply_asset_ip_filters(qs, vm_params)
        object_id = monitor_object_id
        if object_id is None and monitor_obj_name:
            object_id = MonitorObject.objects.filter(name=monitor_obj_name).values_list("id", flat=True).first()
        qs = InstanceSearch.apply_display_field_filters(qs, object_id, vm_params)
        return InstanceSearch.apply_enum_metric_filters(qs, object_id, vm_params)

    @staticmethod
    def display_field_param_key(field):
        """字段展示列的筛选参数键，与 asset.ip 等既有键隔离。"""
        return f"{FIELD_PARAM_PREFIX}{field}"

    @staticmethod
    def role_display_field_bindings(monitor_object_id):
        """取该对象带 role 的字段展示列绑定（当前为云平台子对象 IP）。

        只认 role 列：普通字段展示列由用户自由配置，不承诺筛选能力。
        """
        if not monitor_object_id:
            return []
        display_fields = MonitorObject.objects.filter(id=monitor_object_id).values_list("display_fields", flat=True).first() or []
        bindings = []
        seen = set()
        for col in display_fields:
            if not isinstance(col, dict) or (col.get("type") or "metric") != "field" or not col.get("role"):
                continue
            for binding in col.get("metrics") or []:
                if not isinstance(binding, dict):
                    continue
                field = (binding.get("field") or "").strip()
                metric = (binding.get("metric") or "").strip()
                if not field or not metric:
                    continue
                plugin = (binding.get("plugin") or "").strip()
                dedup_key = (plugin, metric, field)
                if dedup_key in seen:
                    continue
                seen.add(dedup_key)
                bindings.append({"plugin": plugin, "metric": metric, "field": field})
                break
        return bindings

    @staticmethod
    def _resolve_field_metric(monitor_object_id, binding):
        qs = Metric.objects.filter(monitor_object_id=monitor_object_id, name=binding["metric"])
        if binding["plugin"]:
            qs = qs.filter(monitor_plugin__name=binding["plugin"])
        return qs.first()

    @staticmethod
    def apply_display_field_filters(qs, monitor_object_id, vm_params):
        """按字段展示列 label 取值过滤实例：同列多值 OR，多列 AND。"""
        if not monitor_object_id or not isinstance(vm_params, dict):
            return qs
        if not any(str(key).startswith(FIELD_PARAM_PREFIX) for key in vm_params):
            return qs

        for binding in InstanceSearch.role_display_field_bindings(monitor_object_id):
            raw = vm_params.get(InstanceSearch.display_field_param_key(binding["field"]))
            if raw is None or raw == "" or raw == []:
                continue
            metric_obj = InstanceSearch._resolve_field_metric(monitor_object_id, binding)
            if not metric_obj:
                continue
            value_map = MonitorObjectService.query_field_label_values(metric_obj, binding["field"])
            # 候选取值本身可能含逗号（多网卡 IP），不能先按逗号拆再匹配。
            selected = InstanceSearch.normalize_field_filter_values(raw, value_map.values())
            if not selected:
                continue
            matched_ids = [instance_id for instance_id, value in value_map.items() if str(value) in selected]
            qs = qs.filter(id__in=matched_ids)
        return qs

    @staticmethod
    def collect_display_field_options(monitor_object_id):
        """收集字段展示列的候选取值，供列头筛选下拉使用。"""
        options = {}
        for binding in InstanceSearch.role_display_field_bindings(monitor_object_id):
            metric_obj = InstanceSearch._resolve_field_metric(monitor_object_id, binding)
            if not metric_obj:
                continue
            try:
                value_map = MonitorObjectService.query_field_label_values(metric_obj, binding["field"])
            except Exception:
                logger.warning(
                    "收集字段展示列候选值失败: monitor_object_id=%s field=%s",
                    monitor_object_id,
                    binding["field"],
                    exc_info=True,
                )
                continue
            values = sorted({str(value).strip() for value in value_map.values() if str(value).strip()})
            options[InstanceSearch.display_field_param_key(binding["field"])] = values[:FIELD_OPTION_LIMIT]
        return options

    @staticmethod
    def apply_instance_vm_param_filters(qs, monitor_object_id, monitor_obj_name, vm_params):
        return InstanceSearch.apply_process_instance_filters(qs, monitor_obj_name, vm_params, monitor_object_id=monitor_object_id)

    @staticmethod
    def apply_process_host_filters(qs, monitor_obj_name, vm_params):
        """Process：按归属主机 instance_id（支持逗号多值）过滤。"""
        if monitor_obj_name != "Process":
            return qs
        if not isinstance(vm_params, dict):
            return qs
        host_ids = InstanceSearch.normalize_csv_values(vm_params.get("instance_id"))
        if not host_ids:
            return qs
        matching_ids = []
        for process_id in qs.values_list("id", flat=True):
            parts = parse_instance_id(process_id)
            if parts and str(parts[0]) in host_ids:
                matching_ids.append(process_id)
        return qs.filter(id__in=matching_ids)

    @staticmethod
    def apply_asset_ip_filters(qs, vm_params):
        """按 summary_facts['asset.ip']（缺省回落模型 ip）多值过滤。"""
        if not isinstance(vm_params, dict):
            return qs
        ips = InstanceSearch.normalize_csv_values(vm_params.get("asset.ip"))
        if not ips:
            return qs
        matching_ids = []
        for instance_id, ip, facts in qs.values_list("id", "ip", "summary_facts"):
            fact_ip = None
            if isinstance(facts, dict):
                raw = facts.get("asset.ip")
                if raw not in (None, ""):
                    fact_ip = str(raw).strip()
            candidate = fact_ip or (str(ip).strip() if ip not in (None, "") else "")
            if candidate and candidate in ips:
                matching_ids.append(instance_id)
        return qs.filter(id__in=matching_ids)

    @staticmethod
    def normalize_csv_values(raw):
        """兼容单值、逗号分隔字符串与列表，去掉空串。"""
        if raw is None:
            return set()
        if isinstance(raw, (list, tuple, set)):
            parts = [str(item).strip() for item in raw]
        else:
            parts = [part.strip() for part in str(raw).split(",")]
        return {part for part in parts if part}

    @staticmethod
    def normalize_field_filter_values(raw, known_values):
        """解析字段展示列筛选值；已知候选取值优先整串匹配，避免多 IP 被逗号拆开。"""
        if raw is None:
            return set()
        if isinstance(raw, (list, tuple, set)):
            return {str(item).strip() for item in raw if str(item).strip()}

        text = str(raw).strip()
        if not text:
            return set()

        known = sorted(
            {str(value).strip() for value in known_values if str(value).strip()},
            key=len,
            reverse=True,
        )
        if text in known:
            return {text}

        selected = set()
        remaining = text
        while remaining:
            matched = next((value for value in known if remaining == value or remaining.startswith(value + ",")), None)
            if not matched:
                # 多 IP label 本身含逗号，禁止按逗号拆；整串作为单一筛选值。
                selected.add(remaining)
                break
            selected.add(matched)
            remaining = remaining[len(matched) :].lstrip(",")
        return selected

    @staticmethod
    def parse_enum_unit_option_ids(unit):
        """从 Enum metric.unit JSON 解析全部选项 id（字符串集合）。"""
        if not unit or not isinstance(unit, str):
            return set()
        try:
            options = json.loads(unit)
        except (TypeError, ValueError, json.JSONDecodeError):
            return set()
        if not isinstance(options, list):
            return set()
        ids = set()
        for item in options:
            if not isinstance(item, dict) or "id" not in item:
                continue
            ids.add(str(item["id"]).strip())
        return {i for i in ids if i}

    @staticmethod
    def enum_value_matches(raw_value, selected_values):
        """枚举取值匹配：支持 0.5 / 0.50 / 1.0 等数值等价。"""
        if not selected_values:
            return False
        raw = "" if raw_value is None else str(raw_value).strip()
        if raw in selected_values:
            return True
        try:
            numeric = float(raw)
        except (TypeError, ValueError):
            return False
        for selected in selected_values:
            try:
                if abs(numeric - float(selected)) < 1e-9:
                    return True
            except (TypeError, ValueError):
                continue
        return False

    @staticmethod
    def _replace_promql_labels(query, labels):
        if "__$labels__" not in query:
            return query
        if labels:
            return query.replace("__$labels__", labels)
        return (
            query.replace(", __$labels__", "")
            .replace(",__$labels__", "")
            .replace("__$labels__, ", "")
            .replace("__$labels__,", "")
            .replace("__$labels__", "")
        )

    @staticmethod
    def _promql_label_clause(key, raw_value):
        values = sorted(InstanceSearch.normalize_csv_values(raw_value))
        if not values:
            return None
        if len(values) == 1:
            return f'{key}="{InstanceSearch._escape_promql_label_value(values[0])}"'
        joined = "|".join(InstanceSearch._escape_promql_label_value(re.escape(v)) for v in values)
        return f'{key}=~"{joined}"'

    @staticmethod
    def apply_enum_metric_filters(qs, monitor_object_id, vm_params):
        """按 vm_params 中的 Enum 指标名做多值过滤；多指标 AND，同指标多值 OR。"""
        if not monitor_object_id or not isinstance(vm_params, dict):
            return qs

        metrics = Metric.objects.filter(monitor_object_id=monitor_object_id, data_type="Enum").exclude(query="").order_by("id")
        seen_names = set()
        unique_metrics = []
        for metric in metrics:
            if metric.name in seen_names or metric.name in _VM_PARAM_RESERVED_KEYS:
                continue
            if str(metric.name).startswith(FIELD_PARAM_PREFIX):
                continue
            seen_names.add(metric.name)
            unique_metrics.append(metric)

        label_parts = []
        instance_clause = InstanceSearch._promql_label_clause("instance_id", vm_params.get("instance_id"))
        if instance_clause:
            label_parts.append(instance_clause)
        node_clause = InstanceSearch._promql_label_clause("node", vm_params.get("node"))
        if node_clause:
            label_parts.append(node_clause)
        labels = ", ".join(label_parts)

        for metric in unique_metrics:
            selected = InstanceSearch.normalize_csv_values(vm_params.get(metric.name))
            if not selected:
                continue
            all_ids = InstanceSearch.parse_enum_unit_option_ids(metric.unit)
            if all_ids and selected >= all_ids:
                continue

            query = InstanceSearch._replace_promql_labels(metric.query, labels)
            metrics_result = VictoriaMetricsAPI().query(query, step="20m")
            matched_ids = []
            instance_id_keys = metric.instance_id_keys or []
            for metric_info in metrics_result.get("data", {}).get("result", []):
                metric_labels = metric_info.get("metric") or {}
                value = metric_info.get("value") or [None, None]
                raw = value[1]
                if not InstanceSearch.enum_value_matches(raw, selected):
                    continue
                if not instance_id_keys:
                    continue
                parts = [metric_labels.get(key) for key in instance_id_keys]
                if any(part is None or str(part).strip() == "" for part in parts):
                    continue
                matched_ids.append(str(tuple(str(part) for part in parts)))
            qs = qs.filter(id__in=matched_ids)
        return qs

    @staticmethod
    def apply_status_filter_to_qs(qs, instance_map, status_raw):
        """按上报状态过滤 QuerySet：normal=最近上报仍在窗口内，unavailable=已过期或无时间。"""
        statuses = InstanceSearch.normalize_csv_values(status_raw) & {
            "normal",
            "unavailable",
        }
        if not statuses or statuses == {"normal", "unavailable"}:
            return qs
        normal_ids = {
            instance_id
            for instance_id, info in (instance_map or {}).items()
            if list_reporting_status((info or {}).get("time")) == "normal"
        }
        if statuses == {"normal"}:
            return qs.filter(id__in=normal_ids)
        if statuses == {"unavailable"}:
            return qs.exclude(id__in=normal_ids)
        return qs

    @staticmethod
    def apply_status_filter_to_items(items, status_raw):
        """按上报状态过滤已带 time 字段的结果列表。"""
        statuses = InstanceSearch.normalize_csv_values(status_raw) & {
            "normal",
            "unavailable",
        }
        if not statuses or statuses == {"normal", "unavailable"}:
            return items
        if statuses == {"normal"}:
            return [item for item in items if list_reporting_status(item.get("time")) == "normal"]
        if statuses == {"unavailable"}:
            return [item for item in items if list_reporting_status(item.get("time")) != "normal"]
        return items

    @staticmethod
    def _normalize_process_alive_values(alive_raw):
        """兼容旧测试：仅保留 0/1。"""
        return InstanceSearch.normalize_csv_values(alive_raw) & {"0", "1"}

    def get_objs(self):
        qs = self.qs.filter(
            monitor_object_id=self.monitor_obj.id,
            is_deleted=False,
            is_active=True,
        )
        name = self.query_data.get("name")
        if name:
            qs = qs.filter(name__icontains=name)
        qs = self._apply_process_filters(qs)

        # 去除重复
        qs = qs.distinct()

        objs_map = {i.id: i for i in self._project_instance_identity(qs)}
        return objs_map

    def get_objs_v2(self):
        qs = self.qs.filter(
            monitor_object_id=self.monitor_obj.id,
            is_deleted=False,
            is_active=True,
        )
        name = self.query_data.get("name")
        if name:
            qs = qs.filter(name__icontains=name)
        qs = self._apply_process_filters(qs)

        # 去除重复
        qs = qs.distinct()

        count = qs.count()
        if count == 0:
            return dict(count=0, results=[])

        page = self.query_data.get("page", 1)
        page_size = self.query_data.get("page_size", 10)
        projected_qs = self._project_instance_identity(qs)
        if page_size == -1:
            results = projected_qs
        else:
            start = (page - 1) * page_size
            end = start + page_size
            results = projected_qs[start:end]
        org_objs = MonitorInstanceOrganization.objects.filter(monitor_instance_id__in=[obj.id for obj in results])
        org_objs = MonitorObjectService._filter_visible_organizations(org_objs, self.visible_organization_ids)
        org_map = {}
        for org in org_objs:
            if org.monitor_instance_id not in org_map:
                org_map[org.monitor_instance_id] = set()
            org_map[org.monitor_instance_id].add(org.organization)

        serialized = [
            {
                "instance_id": obj.id,
                "instance_name": obj.name,
                "instance_id_values": list(parse_instance_id(obj.id)),
                "interval": obj.interval,
                "cloud_region_id": obj.cloud_region_id,
                "ip": obj.ip,
                "summary_facts": obj.summary_facts,
                "fallback_sampling_rate": obj.fallback_sampling_rate,
                "node_id": obj.node_id or "",
                "cmdb_id": obj.cmdb_id or "",
                "organizations": list(org_map.get(obj.id, [])),
            }
            for obj in results
        ]
        fill_missing_host_container_asset_ips(serialized, getattr(self.monitor_obj, "name", None))
        return dict(count=count, results=serialized)

    def _batch_plugin_status_maps(self, instance_id_keys, queries):
        """并发拉取多个插件 status_query 的正常状态映射，返回 {query: status_map}。

        每个 query 是一次独立的 VM 读，去重相同 query 后并发执行——结果与逐个串行查询完全一致，
        只是把插件列表页的 N 次串行 VM 查询压成一批并发，消除「插件越多越慢」。
        单个 query 失败降级为空映射、不影响其余 query（与原逐个调用各自独立的语义一致）。
        """
        unique_queries = [query for query in queries if query and str(query).strip()]
        if not unique_queries:
            return {}
        max_workers = min(len(unique_queries), PLUGIN_STATUS_QUERY_MAX_WORKERS)
        status_map_by_query = {}
        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            future_to_query = {executor.submit(self.get_plugin_normal_status_map, instance_id_keys, query): query for query in unique_queries}
            for future in as_completed(future_to_query):
                query = future_to_query[future]
                try:
                    status_map_by_query[query] = future.result()
                except Exception as exc:
                    logger.warning("get_plugin_normal_status_map failed, query=%s, error=%s", query, exc)
                    status_map_by_query[query] = {}
        return status_map_by_query

    def get_plugin_normal_status_map(self, instance_id_keys, query):
        if not query or not str(query).strip():
            return {}
        resp = VictoriaMetricsAPI().query(last_sample_timestamp_query(query), step=LAST_SAMPLE_LOOKBACK)
        metrics = resp.get("data", {}).get("result", [])
        status_map = {}
        for metric in metrics:
            instance_id = str(tuple(metric["metric"].get(i) for i in instance_id_keys))
            last_sample = last_sample_unix_seconds(metric)
            if last_sample is None:
                continue
            current = status_map.get(instance_id)
            if current is None or last_sample > current[0]:
                status_map[instance_id] = (
                    last_sample,
                    datetime.fromtimestamp(last_sample, tz=timezone.utc).isoformat(),
                )
        return {instance_id: iso_time for instance_id, (_, iso_time) in status_map.items()}

    def get_vm_metrics(self):
        query = self.obj_metric_map.get("default_metric")
        vm_params = self.query_data.get("vm_params") or {}
        if not isinstance(vm_params, dict):
            raise BaseAppException("vm_params must be an object")

        # 仅把真实 PromQL 标签写入查询；status / Enum 指标名留给业务过滤。
        promql_keys = {"instance_id", "node"}
        label_parts = []
        for key in promql_keys:
            clause = InstanceSearch._promql_label_clause(key, vm_params.get(key))
            if clause:
                label_parts.append(clause)
        params_str = ",".join(label_parts)
        if params_str:
            if "}" in query:
                query = query.replace("}", f",{params_str}}}", 1)
            else:
                query = f"{query}{{{params_str}}}"
        metrics = VictoriaMetricsAPI().query(last_sample_timestamp_query(query), step=LAST_SAMPLE_LOOKBACK)
        return metrics.get("data", {}).get("result", [])

    @staticmethod
    def _escape_promql_label_value(value):
        value_str = str(value)
        return value_str.replace("\\", "\\\\").replace('"', '\\"')

    def add_other_metrics(self, items):
        instance_ids = []
        for instance_info in items:
            instance_id = parse_instance_id(instance_info["instance_id"])
            instance_ids.append(instance_id)

        metrics_obj = Metric.objects.filter(
            monitor_object_id=self.monitor_obj.id,
            name__in=self.obj_metric_map.get("supplementary_indicators", []),
        )

        for metric_obj in metrics_obj:
            query_parts = []
            for i, key in enumerate(metric_obj.instance_id_keys):
                values_set = {re.escape(str(item[i])) for item in instance_ids if len(item) > i and item[i] is not None}
                if not values_set:
                    continue
                # re.escape 生成的反斜杠需要再做一次 PromQL 字符串转义，
                # 否则会在 VM 侧触发 invalid syntax（例如 "\-" 被当作非法转义）
                values = "|".join(sorted(values_set))
                values = self._escape_promql_label_value(values)
                query_parts.append(f'{key}=~"{values}"')

            query = metric_obj.query
            query = query.replace("__$labels__", f"{', '.join(query_parts)}")
            metrics = VictoriaMetricsAPI().query(query, step="10m")
            _metric_map = {}
            for metric in metrics.get("data", {}).get("result", []):
                instance_id = str(tuple(metric["metric"].get(i) for i in metric_obj.instance_id_keys))
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
