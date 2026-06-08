# -- coding: utf-8 --
# @File: network.py
# @Time: 2025/11/12 14:00
# @Author: windyzhao
from collections import defaultdict

from apps.cmdb.collection.collect_plugin.base import CollectBase
from apps.cmdb.collection.collect_util import timestamp_gt_one_day_ago
from apps.cmdb.collection.constants import NETWORK_INTERFACES_RELATIONS, NETWORK_TOPOLOGY_FACTS
from apps.cmdb.collection.plugins import get_collection_plugin
from apps.cmdb.constants.constants import CollectPluginTypes
from apps.cmdb.models import OidMapping
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
        self.device_lookup_map = defaultdict(set)

    def set_metrics(self):
        if self.is_topo:
            for metric_name in (NETWORK_INTERFACES_RELATIONS, NETWORK_TOPOLOGY_FACTS):
                if metric_name not in self._metrics:
                    self._metrics.append(metric_name)
                self.collection_metrics_dict.update({metric_name: []})

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
                if "sysobjectid" in index_data:
                    self.index_device_lookup(index_data)
                if model_id == "interface":
                    self.interfaces_data[data["inst_name"]] = data
                    self.index_interface_lookup(index_data, data)

        if self.is_topo:
            relationships = self.collect_topology_relationships(topology_facts, topo_data)
            self.add_interface_assos(relationships)
            # 把接口的关联补充接口的关联关系中

    def collect_topology_relationships(self, topology_facts, topo_data):
        relationships = []
        seen = set()

        for relation in self.find_topology_fact_relationships(topology_facts):
            self.append_unique_relationship(relationships, seen, relation)

        for relation in self.find_interface_relationships(topo_data):
            self.append_unique_relationship(relationships, seen, relation)

        return relationships

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

    def index_device_lookup(self, index_data):
        instance_id = index_data["instance_id"]
        for key in (instance_id, index_data.get("ip_addr"), index_data.get("sysname")):
            normalized_key = self.normalize_lookup_value(key)
            if normalized_key:
                self.device_lookup_map[normalized_key].add(instance_id)

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

    def find_topology_fact_relationships(self, data):
        relations = []
        seen = set()
        for fact in data:
            source_inst_name = self.resolve_topology_fact_interface(fact, is_local=True)
            target_inst_name = self.resolve_topology_fact_interface(fact, is_local=False)
            if not source_inst_name or not target_inst_name or source_inst_name == target_inst_name:
                continue

            edge_key = (source_inst_name, target_inst_name)
            if edge_key in seen:
                continue
            seen.add(edge_key)
            relations.append({
                "source_inst_name": source_inst_name,
                "target_inst_name": target_inst_name,
                "model_id": "interface",
                "asst_id": "connect",
                "model_asst_id": "interface_connect_interface",
            })

        return relations

    def resolve_topology_fact_interface(self, fact, is_local=True):
        port_id_key = "local_port_id" if is_local else "remote_port_id"
        port_name_key = "local_port_name" if is_local else "remote_port_name"
        device_key = "local_device_id" if is_local else "remote_device_id"

        instance_id = fact.get("instance_id") if is_local else None
        if not instance_id:
            instance_id = self.resolve_device_instance_id(fact.get(device_key))
        if not instance_id:
            return None

        port_id = fact.get(port_id_key)
        if port_id is not None:
            interface_inst_name = self.interface_index_map.get((instance_id, str(port_id)))
            if interface_inst_name:
                return interface_inst_name

        for candidate in (port_id, fact.get(port_name_key)):
            normalized_candidate = self.normalize_lookup_value(candidate)
            if not normalized_candidate:
                continue
            interface_inst_name = self.interface_name_map[instance_id].get(normalized_candidate)
            if interface_inst_name:
                return interface_inst_name

        return None

    def resolve_device_instance_id(self, device_key):
        normalized_key = self.normalize_lookup_value(device_key)
        if not normalized_key:
            return None
        matched_instance_ids = self.device_lookup_map.get(normalized_key, set())
        if len(matched_instance_ids) != 1:
            return None
        return next(iter(matched_instance_ids))

    @staticmethod
    def normalize_lookup_value(value):
        if value is None:
            return ""
        return str(value).strip().lower()

    def find_interface_relationships(self, data):
        # 数据结构
        device_interfaces = defaultdict(dict)  # {instance_id: {ifindex: {"ifdescr": ..., "mac": ..., "ifalias": ...}}}
        ip_to_mac = defaultdict(dict)  # {instance_id: {ip: mac}}
        arp_table = defaultdict(dict)  # {instance_id: {ip: {"ifindex": ..., "mac": ...}}}

        # 预处理数据
        for entry in data:
            instance_id = entry['instance_id']
            tag = entry['tag']
            ifindex = entry.get('ifindex')
            value = entry.get('val')

            if tag == 'IFTable-IfDescr':  # 接口描述
                device_interfaces[instance_id].setdefault(ifindex, {})['ifdescr'] = value
            elif tag == 'IFTable-PhysAddress':  # 接口MAC地址
                device_interfaces[instance_id].setdefault(ifindex, {})['mac'] = self.normalize_mac(value)
            elif tag == 'IFTable-IfAlias':  # 接口别名
                device_interfaces[instance_id].setdefault(ifindex, {})['ifalias'] = value
            elif tag == 'IpAddr-IpAddr':  # IP地址与MAC地址的映射
                mac = device_interfaces[instance_id].get(ifindex, {}).get('mac')
                if mac:
                    ip_to_mac[instance_id][value] = mac
            elif tag == 'ARP-IfIndex':  # ARP表中的接口索引
                arp_table[instance_id].setdefault(ifindex, {})['ifindex'] = value
            elif tag == 'ARP-PhysAddress':  # ARP表中的MAC地址
                arp_table[instance_id].setdefault(ifindex, {})['mac'] = self.normalize_mac(value)

        # 构建 MAC 到设备和接口的索引
        mac_to_device = {}
        for instance_id, interfaces in device_interfaces.items():
            for ifindex, details in interfaces.items():
                mac = details.get('mac')
                if mac:
                    mac_to_device[mac] = (instance_id, ifindex)

        # 构建连接关系
        relations = []
        for src_instance, src_arp in arp_table.items():
            for ip, arp_info in src_arp.items():
                dst_mac = arp_info.get('mac')
                if not dst_mac:
                    continue

                # 使用索引快速查找目标设备和接口
                if dst_mac in mac_to_device:
                    dst_instance, dst_ifindex = mac_to_device[dst_mac]
                    if dst_instance == src_instance:
                        continue  # 跳过同一设备

                    if dst_instance not in self.instance_id_map or src_instance not in self.instance_id_map:
                        logger.info(
                            "This data is discarded because no feature library can be found for the OID. instance_id={}".format(
                                src_instance))
                        continue

                    src_ifindex = arp_info.get('ifindex')
                    src_interface = device_interfaces[src_instance].get(src_ifindex, {})
                    dst_interface = device_interfaces[dst_instance].get(dst_ifindex, {})
                    if not src_interface or not dst_interface:
                        continue

                    relations.append({
                        "source_device": src_instance,
                        # "source_interface": src_interface.get('ifalias') or src_interface.get('ifdescr'),
                        "source_inst_name": self.set_interface_inst_name(
                            data={"instance_id": src_instance, **self.set_alias_descr(src_interface)}),
                        "target_device": dst_instance,
                        # "target_interface": dst_interface.get('ifalias') or dst_interface.get('ifdescr'),
                        "target_inst_name": self.set_interface_inst_name(
                            data={"instance_id": dst_instance, **self.set_alias_descr(dst_interface)}),
                        "model_id": "interface",
                        "asst_id": "connect",
                        "model_asst_id": "interface_connect_interface",
                    })

        return relations

    @staticmethod
    def set_alias_descr(data):
        """设置别名"""
        result = {"description": data["ifdescr"]}
        if data.get("ifalias", ""):
            result["alias"] = data["ifalias"]

        return result

    @staticmethod
    def normalize_mac(mac):
        """将 MAC 地址标准化为统一格式"""
        if mac.startswith("0x"):
            mac = mac[2:]  # 去掉 "0x"
        return ":".join(mac[i:i + 2] for i in range(0, len(mac), 2)).lower()
