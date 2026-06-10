# -- coding: utf-8 --
# @File: network.py
# @Time: 2025/11/12 14:00
# @Author: windyzhao
from collections import defaultdict

from apps.cmdb.collection.collect_plugin.base import CollectBase
from apps.cmdb.collection.collect_plugin.topology import build_pipeline_aggregate, parse_aggregate_result
from apps.cmdb.collection.collect_util import timestamp_gt_one_day_ago
from apps.cmdb.collection.constants import NETWORK_INTERFACES_RELATIONS, NETWORK_TOPOLOGY_FACTS
from apps.cmdb.collection.plugins import get_collection_plugin
from apps.cmdb.constants.constants import CollectPluginTypes
from apps.cmdb.models import CollectModels, OidMapping
from apps.core.logger import cmdb_logger as logger


class CollectNetworkMetrics(CollectBase):
    ROOT = "root"  # 根oid
    KEY = "key"  # oid
    TAG = "tag"  # 名称
    IF_INDEX = "ifindex"  # 索引
    IF_INDEX_TYPE = "ifindex_type"  # 索引类型 default为单索引,ipaddr为后4位为ip地址
    VAL = "val"  # oid对应值

    def __init__(self, inst_name, inst_id, task_id, *args, **kwargs):
        super().__init__(inst_name, inst_id, task_id, *args, **kwargs)
        self.oid_map = self.get_oid_map()
        # 4：other  （冗余用的）
        self.interface_status_map = {
            "1": "UP",
            "2": "Down",
            "3": "Testing"
        }
        self.instance_id_map = {}
        self.collect_inst = self.get_collect_inst()
        self.is_topo = self.collect_inst.is_network_topo
        self._instance_metrics = list(self._metrics)
        self.set_metrics()
        self.interfaces_data = {}
        self.interface_index_map = {}
        self.interface_name_map = defaultdict(dict)

    def set_metrics(self):
        if self.is_topo:
            # 新流水线只消费 network_topo_info_gauge，不再查询 network_topology_facts_info_gauge
            if NETWORK_INTERFACES_RELATIONS not in self._metrics:
                self._metrics.append(NETWORK_INTERFACES_RELATIONS)
            self.collection_metrics_dict.update({NETWORK_INTERFACES_RELATIONS: []})

    @property
    def _metrics(self):
        if hasattr(self, "_instance_metrics"):
            return self._instance_metrics
        plugin_cls = get_collection_plugin(CollectPluginTypes.SNMP, self.model_id)
        return list(plugin_cls._metrics.fget(self))

    @staticmethod
    def get_oid_map():
        result = OidMapping._default_manager.all().values("model", "oid", "brand", "device_type", "built_in")
        return {i["oid"]: i for i in result}

    @staticmethod
    def get_default_oid_map(oid):
        return {
            "model": "未知",
            "oid": oid,
            "brand": "未知",
            "device_type": "switch",
            "built_in": False,
        }

    @staticmethod
    def set_inst_name(*args, **kwargs):
        # ip-switch
        data = args[0]
        inst_name = f"{data['ip_addr']}-{data['device_type']}"
        return inst_name

    def set_interface_status(self, data, *args, **kwargs):
        return self.interface_status_map.get(data, "other")

    def set_interface_inst_name(self, data, *args, **kwargs):
        inst_name = self.set_self_device(data)
        return f"{inst_name}-{data.get('alias', data['description'])}"

    def set_self_device(self, data, *args, **kwargs):
        instance_id = data["instance_id"]
        instance = self.instance_id_map[instance_id]
        return self.set_inst_name(instance)

    def get_interface_asso(self, data, *args, **kwargs):
        instance_id = data["instance_id"]
        instance = self.instance_id_map[instance_id]
        model_id = instance["device_type"]
        return [
            {
                "model_id": model_id,
                "inst_name": self.set_inst_name(instance),
                "asst_id": "belong",
                "model_asst_id": f"interface_belong_{model_id}"
            }
        ]

    @property
    def device_map(self):
        plugin_cls = get_collection_plugin(CollectPluginTypes.SNMP, self.model_id)
        return plugin_cls.device_map.fget(self)

    @staticmethod
    def interface_name(data, *args, **kwargs):
        return data.get("alias", data['description'])

    @property
    def model_field_mapping(self):
        plugin_cls = get_collection_plugin(CollectPluginTypes.SNMP, self.model_id)
        return plugin_cls.model_field_mapping.fget(self)

    def format_data(self, data):
        """格式化数据"""
        for index_data in data["result"]:
            metric_name = index_data["metric"]["__name__"]
            if "sysobjectid" in index_data["metric"]:
                oid = index_data["metric"]["sysobjectid"]
                oid_data = self.oid_map.get(oid, "")
                if not oid_data:
                    oid_data = self.get_default_oid_map(oid)
                    logger.info("==OID does not exist, use default mapping OID={}==".format(oid))
                index_data["metric"].update(oid_data)

            value = index_data["value"]
            _time, value = value[0], value[1]
            if not self.timestamp_gt:
                if timestamp_gt_one_day_ago(_time):
                    break
                else:
                    self.timestamp_gt = True

            index_dict = dict(
                index_key=metric_name,
                index_value=value,
                **index_data["metric"],
            )

            if "sysobjectid" in index_dict:
                self.instance_id_map[index_dict["instance_id"]] = index_dict

            self.collection_metrics_dict[metric_name].append(index_dict)

    def format_metrics(self):
        """格式化数据"""
        topo_data = self.collection_metrics_dict.pop(NETWORK_INTERFACES_RELATIONS, [])
        topology_facts = self.collection_metrics_dict.pop(NETWORK_TOPOLOGY_FACTS, [])
        for metric_key, metrics in self.collection_metrics_dict.items():
            for index_data in metrics:
                if index_data["instance_id"] not in self.instance_id_map:
                    logger.info(
                        "This data is discarded because no feature library can be found for the OID. instance_id={}".format(
                            index_data["instance_id"]))
                    continue
                if "sysobjectid" in index_data:
                    model_id = index_data["device_type"]
                    mapping = self.device_map
                else:
                    model_id = "interface"
                    mapping = self.model_field_mapping

                data = {}
                for field, key_or_func in mapping.items():
                    if isinstance(key_or_func, tuple):
                        data[field] = key_or_func[0](index_data[key_or_func[1]])
                    elif callable(key_or_func):
                        data[field] = key_or_func(index_data)
                    else:
                        data[field] = index_data.get(key_or_func, "")

                self.result.setdefault(model_id, []).append(data)
                if model_id == "interface":
                    self.interfaces_data[data["inst_name"]] = data
                    self.index_interface_lookup(index_data, data)

        if self.is_topo:
            relationships = self.collect_topology_relationships(topology_facts, topo_data)
            self.add_interface_assos(relationships)
            # 把接口的关联补充接口的关联关系中

    def collect_topology_relationships(self, topology_facts, topo_data):
        # topology_facts（network_topology_facts_info_gauge）已废弃：新流水线直接消费
        # network_topo_info_gauge 原始证据行；参数保留以隔离 VM 中旧 agent 指标的残留期。
        del topology_facts
        aggregate = build_pipeline_aggregate(topo_data)
        parsed = parse_aggregate_result(aggregate, previous_links=self.get_previous_topology_links())

        contract = self.collect_inst.topology_contract
        # 契约 min_confidence 为 0~1 浮点，流水线 confidence 为 0~100 整数
        min_confidence = int(float(contract.get("min_confidence", 0) or 0) * 100)

        relationships = []
        dropped = []
        seen = set()
        topology = parsed.get("topology", {})
        current_links = list(topology.get("authoritative_links", [])) + list(topology.get("inferred_links", []))
        for link in current_links:
            if (
                str(link.get("relationship_type", "")) != "authoritative"
                and int(link.get("confidence", 0) or 0) < min_confidence
            ):
                dropped.append(self.slim_topology_link(link, reason="below_min_confidence"))
                continue
            source_inst_name = self.resolve_pipeline_inst_name(link.get("source_port_id"))
            target_inst_name = self.resolve_pipeline_inst_name(link.get("target_port_id"))
            if not source_inst_name or not target_inst_name:
                dropped.append(self.slim_topology_link(link, reason="interface_not_in_inventory"))
                continue
            if source_inst_name == target_inst_name:
                dropped.append(self.slim_topology_link(link, reason="self_loop"))
                continue
            relation = {
                "source_inst_name": source_inst_name,
                "target_inst_name": target_inst_name,
                "model_id": "interface",
                "asst_id": "connect",
                "model_asst_id": "interface_connect_interface",
            }
            self.append_unique_relationship(relationships, seen, relation)

        snapshot = {
            "summary": parsed.get("summary", {}),
            "links": [self.slim_topology_link(link) for link in current_links],
            "stale_links": [self.slim_topology_link(link) for link in topology.get("stale_links", [])],
            "unresolved_neighbors": [
                {key: value for key, value in item.items() if key != "raw_remote_fields"}
                for item in topology.get("unresolved_neighbors", [])
                if isinstance(item, dict)
            ],
            "dropped": dropped,
        }
        self.save_topology_snapshot(snapshot)
        return relationships

    def resolve_pipeline_inst_name(self, port_id):
        """流水线 port_id 形如 "{instance_id}:{ifindex}"，映射到 CMDB 接口实例名"""
        if not port_id:
            return None
        instance_id, _, ifindex = str(port_id).rpartition(":")
        if not instance_id:
            return None
        return self.interface_index_map.get((instance_id, ifindex))

    @staticmethod
    def slim_topology_link(link, reason=None):
        """快照瘦身：剔除体积大的证据明细字段"""
        slim = {key: value for key, value in link.items() if key not in ("supporting_evidence", "provenance")}
        if reason is not None:
            slim["drop_reason"] = reason
        return slim

    def get_previous_topology_links(self):
        snapshot = getattr(self.collect_inst, "topology_snapshot", None) or {}
        links = snapshot.get("links", [])
        return [item for item in links if isinstance(item, dict)]

    def save_topology_snapshot(self, snapshot):
        try:
            CollectModels.objects.filter(id=self.task_id).update(topology_snapshot=snapshot)
        except Exception as err:  # noqa: BLE001
            logger.warning("==保存拓扑快照失败，跳过（不影响采集主流程）task_id={} error={}==".format(self.task_id, err))

    @staticmethod
    def append_unique_relationship(relationships, seen, relation):
        edge_key = (relation["source_inst_name"], relation["target_inst_name"])
        if edge_key in seen:
            return
        seen.add(edge_key)
        relationships.append(relation)

    def add_interface_assos(self, relationships):
        for relationship in relationships:
            source_inst_name = relationship["source_inst_name"]
            source_interface_data = self.interfaces_data.get(source_inst_name)
            if not source_interface_data:
                continue
            data = {'asst_id': 'connect',
                    'inst_name': relationship["target_inst_name"],
                    'model_asst_id': 'interface_connect_interface',
                    'model_id': 'interface'
                    }
            assos = source_interface_data.setdefault("assos", [])
            if data not in assos:
                assos.append(data)

    def index_interface_lookup(self, index_data, data):
        instance_id = index_data["instance_id"]
        index = index_data.get("index")
        if index is not None:
            self.interface_index_map[(instance_id, str(index))] = data["inst_name"]

        for key in (
            data.get("name"),
            index_data.get("alias"),
            index_data.get("description"),
            index_data.get("index"),
        ):
            normalized_key = self.normalize_lookup_value(key)
            if normalized_key:
                self.interface_name_map[instance_id][normalized_key] = data["inst_name"]

    @staticmethod
    def normalize_lookup_value(value):
        if value is None:
            return ""
        return str(value).strip().lower()
