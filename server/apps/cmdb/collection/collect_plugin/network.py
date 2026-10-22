# -- coding: utf-8 --
# @File: network.py
# @Time: 2025/11/12 14:00
# @Author: windyzhao
import json
from collections import defaultdict

from apps.cmdb.collection.collect_plugin.base import CollectBase
from apps.cmdb.collection.collect_plugin.topology import build_pipeline_aggregate, parse_aggregate_result
from apps.cmdb.collection.collect_util import timestamp_gt_one_day_ago
from apps.cmdb.collection.constants import NETWORK_INTERFACES_RELATIONS, NETWORK_SN_METRICS, NETWORK_TOPOLOGY_FACTS
from apps.cmdb.collection.interface_nic_link import (
    _ENSURE_FAILED_STAGE,
    _ENSURE_FAILED_TEMPLATE,
    bind_fdb_learned_macs_to_nics,
    bind_unresolved_neighbors_to_nics,
    candidate_nic_lookup_macs,
    ensure_interface_connect_nic_association,
    inventory_interface_macs,
    load_nic_instances_by_mac,
    nic_index_from_instances,
)
from apps.cmdb.collection.plugins import get_collection_plugin
from apps.cmdb.collection.topology_interface_inventory import load_task_interfaces_safe, merge_inventory_port_index, port_index_needs_inventory
from apps.cmdb.constants.constants import CollectPluginTypes
from apps.cmdb.models import CollectModels, OidMapping
from apps.core.logger import cmdb_logger as logger

# sysObjectID 文本企业前缀展开为 1.3.6.1.4.1.<enterprise>...
_SNMP_ENTERPRISE_PREFIXES = (
    "SNMPv2-SMI::enterprises.",
    "enterprises.",
)
_NUMERIC_ENTERPRISE_ROOT = "1.3.6.1.4.1"
# 最短可作前缀命中的弧数：1.3.6.1.4.1.<enterprise>。禁止用 1.3.6.1.4.1 兜底。
_MIN_PREFIX_ARCS = 7


class _OmitField:
    """采集映射返回此值时，本次不写该字段。"""


OMIT_FIELD = _OmitField()


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
        self.interface_status_map = {"1": "UP", "2": "Down", "3": "Testing"}
        self.instance_id_map = {}
        self.collect_inst = self.get_collect_inst()
        # 拓扑拆分后：设备对账不再内联解析拓扑；拓扑由 topology_replay_service 触发。
        # 子类 TopologyReplayCollector 可强制 is_topo=True。
        self.is_topo = bool(kwargs.pop("force_topology_replay", False))
        self._instance_metrics = list(self._metrics)
        self.set_metrics()
        self.interfaces_data = {}
        self.interface_index_map = {}
        self.interface_name_map = defaultdict(dict)
        self.sn_rows = {}
        self.unresolved_by_soid = {}
        self.unresolved_ips = set()
        self.unresolved_groups = []

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
        # 启动期 init_oid 会把 built_in=True 重置为目录值；同一 OID 的 POST 会被 API 拒绝。
        # 用户覆盖只能 UPDATE 已有行并设 built_in=False，匹配时精确命中该行。
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
    def normalize_sysobjectid(sysobjectid):
        """规范化采集到的 sysObjectID：去空白、去前导点、展开 enterprises 文本前缀。"""
        oid = (sysobjectid or "").strip().lstrip(".")
        for prefix in _SNMP_ENTERPRISE_PREFIXES:
            if oid.startswith(prefix):
                return "{}.{}".format(_NUMERIC_ENTERPRISE_ROOT, oid[len(prefix) :])
        return oid

    @staticmethod
    def oid_arc_count(oid):
        if not oid:
            return 0
        return oid.count(".") + 1

    @classmethod
    def lookup_library_mapping(cls, sysobjectid, oid_map=None):
        """精确命中优先；否则按 OID 弧数取最长前缀（最短 7 弧）。未命中返回 None。"""
        if oid_map is None:
            oid_map = cls.get_oid_map()
        oid = cls.normalize_sysobjectid(sysobjectid)
        exact = oid_map.get(oid)
        if exact:
            return exact
        best_row = None
        best_arcs = 0
        for key, row in oid_map.items():
            if not key or not (oid == key or oid.startswith(key + ".")):
                continue
            arcs = cls.oid_arc_count(key)
            if arcs < _MIN_PREFIX_ARCS or arcs <= best_arcs:
                continue
            best_row = row
            best_arcs = arcs
        return best_row

    @classmethod
    def resolve_oid_mapping(cls, sysobjectid, oid_map=None):
        """库命中返回该行；未命中返回合成默认映射，形状与历史兜底一致。"""
        hit = cls.lookup_library_mapping(sysobjectid, oid_map)
        if hit is not None:
            return hit
        return cls.get_default_oid_map(cls.normalize_sysobjectid(sysobjectid))

    def get_device_sn(self, data, *args, **kwargs):
        """sn_collected=true 时写入实体序列号表；否则本次不带该字段。"""
        del args, kwargs
        if str(data.get("sn_collected") or "").strip().lower() != "true":
            return OMIT_FIELD
        host = data.get("instance_id") or data.get("host") or ""
        rows = getattr(self, "sn_rows", {}).get(host, [])
        return json.dumps(rows, ensure_ascii=False)

    def _append_sn_row(self, data):
        host = data.get("host") or data.get("instance_id") or ""
        oid = str(data.get("oid") or "").strip()
        serial = str(data.get("serial") or "").strip()
        if not host or not oid or not serial:
            return
        row = {"oid": oid, "serial": serial, "entity": str(data.get("entity") or "").strip()}
        bucket = self.sn_rows.setdefault(host, [])
        for existing in bucket:
            if existing.get("oid") == oid:
                existing.update(row)
                return
        bucket.append(row)

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
        return f"{inst_name}-{self.interface_name(data)}"

    def set_self_device(self, data, *args, **kwargs):
        instance_id = data["instance_id"]
        instance = self.instance_id_map[instance_id]
        return self.set_inst_name(instance)

    def get_interface_asso(self, data, *args, **kwargs):
        instance_id = data["instance_id"]
        instance = self.instance_id_map[instance_id]
        model_id = instance["device_type"]
        return [
            {"model_id": model_id, "inst_name": self.set_inst_name(instance), "asst_id": "belong", "model_asst_id": f"interface_belong_{model_id}"}
        ]

    @property
    def device_map(self):
        plugin_cls = get_collection_plugin(CollectPluginTypes.SNMP, self.model_id)
        return plugin_cls.device_map.fget(self)

    @staticmethod
    def interface_name(data, *args, **kwargs):
        """接口名称取 ifDescr；为空时退到 ifAlias，再空则用 if{index}。"""
        return data.get("description") or data.get("alias") or f"if{data.get('index', '')}"

    @staticmethod
    def interface_description(data, *args, **kwargs):
        """接口描述只取 ifAlias，没有则留空。"""
        return data.get("alias") or ""

    @property
    def model_field_mapping(self):
        plugin_cls = get_collection_plugin(CollectPluginTypes.SNMP, self.model_id)
        return plugin_cls.model_field_mapping.fget(self)

    def format_data(self, data):
        """格式化数据"""
        for index_data in data["result"]:
            metric_name = index_data["metric"]["__name__"]
            if "sysobjectid" in index_data["metric"]:
                oid = self.normalize_sysobjectid(index_data["metric"]["sysobjectid"])
                library = self.lookup_library_mapping(oid, self.oid_map)
                if library is None:
                    oid_data = self.get_default_oid_map(oid)
                    index_data["metric"]["_unresolved"] = True
                    logger.info("==OID does not exist, hold unresolved OID={}==".format(oid))
                else:
                    oid_data = library
                    if oid_data.get("brand") == "未知":
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

            # agent 给同一任务所有设备盖的是任务级 instance_id（cmdb_{task_id}），
            # 仅靠每行 host 区分设备。改用 host 作为设备身份键，避免多台设备因共享
            # instance_id 被合并成一台（否则跨设备拓扑关联无法建立）。
            host = index_dict.get("host")
            if host:
                index_dict["instance_id"] = host

            if "sysobjectid" in index_dict:
                self.instance_id_map[index_dict["instance_id"]] = index_dict

            if metric_name in NETWORK_SN_METRICS:
                self._append_sn_row(index_dict)
                continue

            self.collection_metrics_dict[metric_name].append(index_dict)

    def _parent_is_unresolved(self, index_data):
        parent = self.instance_id_map.get(index_data.get("instance_id")) or {}
        return bool(parent.get("_unresolved"))

    def _ensure_unresolved_device(self, source):
        if not hasattr(self, "unresolved_by_soid"):
            self.unresolved_by_soid = {}
        if not hasattr(self, "unresolved_ips"):
            self.unresolved_ips = set()
        soid = self.normalize_sysobjectid(source.get("sysobjectid") or source.get("oid"))
        ip_addr = str(source.get("ip_addr") or source.get("host") or source.get("instance_id") or "")
        if not soid or not ip_addr:
            return None
        self.unresolved_ips.add(ip_addr)
        devices = self.unresolved_by_soid.setdefault(soid, {})
        return devices.setdefault(
            ip_addr,
            {
                "ip_addr": ip_addr,
                "port": str(source.get("port") or ""),
                "sys_desc": source.get("sysdescr") or "",
                "interfaces": [],
            },
        )

    def _hold_unresolved_device(self, index_data):
        device = self._ensure_unresolved_device(index_data)
        if device is None:
            return
        if index_data.get("port"):
            device["port"] = str(index_data.get("port"))
        if index_data.get("sysdescr"):
            device["sys_desc"] = index_data.get("sysdescr")

    def _hold_unresolved_interface(self, index_data):
        parent = self.instance_id_map.get(index_data.get("instance_id")) or {}
        device = self._ensure_unresolved_device(parent)
        if device is None:
            return
        device["interfaces"].append(
            {
                "name": self.interface_name(index_data),
                "description": self.interface_description(index_data),
                "mac": index_data.get("mac_address") or "",
                "status": self.set_interface_status(index_data.get("oper_status")),
            }
        )

    def _materialize_unresolved_groups(self):
        grouped = getattr(self, "unresolved_by_soid", None) or {}
        self.unresolved_groups = [{"soid": soid, "devices": list(devices.values())} for soid, devices in grouped.items()]
        return self.unresolved_groups

    def _endpoint_is_unresolved(self, inst_name):
        ip_addr = str(inst_name or "").split("-", 1)[0]
        return bool(ip_addr) and ip_addr in (getattr(self, "unresolved_ips", None) or set())

    def format_metrics(self):
        """格式化数据"""
        topo_data = self.collection_metrics_dict.pop(NETWORK_INTERFACES_RELATIONS, [])
        topology_facts = self.collection_metrics_dict.pop(NETWORK_TOPOLOGY_FACTS, [])
        for metric_key, metrics in self.collection_metrics_dict.items():
            for index_data in metrics:
                if index_data["instance_id"] not in self.instance_id_map:
                    logger.info(
                        "This data is discarded because no feature library can be found for the OID. instance_id={}".format(index_data["instance_id"])
                    )
                    continue
                if index_data.get("_unresolved") or self._parent_is_unresolved(index_data):
                    if "sysobjectid" in index_data:
                        self._hold_unresolved_device(index_data)
                    else:
                        self._hold_unresolved_interface(index_data)
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
                        value = key_or_func(index_data)
                        if value is OMIT_FIELD:
                            continue
                        data[field] = value
                    else:
                        data[field] = index_data.get(key_or_func, "")

                self.result.setdefault(model_id, []).append(data)
                if model_id == "interface":
                    self.interfaces_data[data["inst_name"]] = data
                    self.index_interface_lookup(index_data, data)

        self._materialize_unresolved_groups()
        if self.is_topo:
            relationships = self.collect_topology_relationships(topology_facts, topo_data)
            self._topology_relationships = relationships
            self.add_interface_assos(relationships)
            # 把接口的关联补充接口的关联关系中

    def collect_topology_relationships(self, topology_facts, topo_data):
        # topology_facts（network_topology_facts_info_gauge）已废弃：新流水线直接消费
        # network_topo_info_gauge 原始证据行；参数保留以隔离 VM 中旧 agent 指标的残留期。
        del topology_facts
        aggregate = build_pipeline_aggregate(topo_data)
        parsed = parse_aggregate_result(aggregate, previous_links=self.get_previous_topology_links())
        ports = (parsed.get("normalized") or {}).get("ports") or []
        if port_index_needs_inventory(self.interface_index_map, ports):
            merge_inventory_port_index(
                self.interface_index_map,
                ports,
                load_task_interfaces_safe(self.task_id),
            )

        contract = self.collect_inst.topology_contract
        # 契约 min_confidence 为 0~1 浮点，流水线 confidence 为 0~100 整数
        min_confidence = int(float(contract.get("min_confidence", 0) or 0) * 100)

        relationships = []
        dropped = []
        seen = set()
        topology = parsed.get("topology", {})
        current_links = list(topology.get("authoritative_links", [])) + list(topology.get("inferred_links", []))
        for link in current_links:
            if str(link.get("relationship_type", "")) != "authoritative" and int(link.get("confidence", 0) or 0) < min_confidence:
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
            if self._endpoint_is_unresolved(source_inst_name) or self._endpoint_is_unresolved(target_inst_name):
                dropped.append(self.slim_topology_link(link, reason="unresolved_soid"))
                continue
            relation = {
                "source_inst_name": source_inst_name,
                "target_inst_name": target_inst_name,
                "model_id": "interface",
                "asst_id": "connect",
                "model_asst_id": "interface_connect_interface",
            }
            self.append_unique_relationship(relationships, seen, relation)

        nic_relationships, unmatched_macs, nic_dropped = self.collect_nic_connect_relationships(parsed)
        if nic_relationships:
            try:
                ensure_interface_connect_nic_association(task_id=self.task_id)
            except Exception as exc:  # noqa: BLE001 — 模型关联补齐失败不阻断拓扑主路径
                logger.warning(
                    _ENSURE_FAILED_TEMPLATE,
                    self.task_id or "",
                    _ENSURE_FAILED_STAGE,
                    type(exc).__name__,
                )
        for relation in nic_relationships:
            if self._endpoint_is_unresolved(relation.get("source_inst_name")) or self._endpoint_is_unresolved(relation.get("target_inst_name")):
                continue
            self.append_unique_relationship(relationships, seen, relation)
        dropped.extend(nic_dropped)

        summary = dict(parsed.get("summary") or {})
        summary["unmatched_macs"] = len(unmatched_macs)
        summary["nic_connects"] = len(nic_relationships)

        snapshot = {
            "summary": summary,
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

    def collect_nic_connect_relationships(self, parsed):
        """FDB（必做）以及未解析 LLDP/CDP（便宜路径）匹配已入库 nic。"""
        normalized = parsed.get("normalized") or {}
        unresolved = (parsed.get("topology") or {}).get("unresolved_neighbors") or []
        candidate_macs = candidate_nic_lookup_macs(normalized, unresolved)
        nic_index = self.load_nic_mac_index(candidate_macs)
        nic_relationships, unmatched_macs, dropped = bind_fdb_learned_macs_to_nics(
            normalized=normalized,
            nic_index=nic_index,
            resolve_source_inst_name=self.resolve_pipeline_inst_name,
        )
        neighbor_relationships = bind_unresolved_neighbors_to_nics(
            unresolved_neighbors=unresolved,
            nic_index=nic_index,
            interface_macs=inventory_interface_macs(normalized),
            resolve_source_inst_name=self.resolve_pipeline_inst_name,
        )
        seen = {(item["source_inst_name"], item["target_inst_name"], item["model_asst_id"]) for item in nic_relationships}
        for relation in neighbor_relationships:
            edge_key = (relation["source_inst_name"], relation["target_inst_name"], relation["model_asst_id"])
            if edge_key in seen:
                continue
            seen.add(edge_key)
            nic_relationships.append(relation)
        return nic_relationships, unmatched_macs, dropped

    def load_nic_mac_index(self, macs):
        """查询已入库 nic；失败时返回空索引，不编造 nic、不碰 host。"""
        if not macs:
            return {}
        try:
            instances = load_nic_instances_by_mac(macs)
        except Exception as exc:  # noqa: BLE001 — 拓扑主路径不因 nic 查询失败中断
            logger.warning(
                "event=network_topology_nic_index_load_failed task_id=%s failed_stage=%s error_type=%s",
                self.task_id or "",
                "load_nic_mac_index",
                type(exc).__name__,
            )
            return {}
        return nic_index_from_instances(instances)

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
        edge_key = (
            relation["source_inst_name"],
            relation["target_inst_name"],
            relation.get("model_asst_id", "interface_connect_interface"),
        )
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
            data = {
                "asst_id": relationship.get("asst_id", "connect"),
                "inst_name": relationship["target_inst_name"],
                "model_asst_id": relationship.get("model_asst_id", "interface_connect_interface"),
                "model_id": relationship.get("model_id", "interface"),
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
