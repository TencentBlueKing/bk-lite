# -- coding: utf-8 --
# @File: network.py
# @Time: 2025/11/12 14:00
# @Author: windyzhao
from collections import defaultdict

from apps.cmdb.collection.collect_plugin.base import CollectBase
from apps.cmdb.collection.collect_util import timestamp_gt_one_day_ago
from apps.cmdb.collection.constants import NETWORK_INTERFACES_RELATIONS,NETWORK_COLLECT
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
        self.set_metrics()
        self.interfaces_data = {}

    def set_metrics(self):
        if self.is_topo:
            self._metrics.append(NETWORK_INTERFACES_RELATIONS)
            self.collection_metrics_dict.update({NETWORK_INTERFACES_RELATIONS: []})

    @property
    def _metrics(self):
        return NETWORK_COLLECT

    def prom_sql(self):
        sql = " or ".join(m for m in self._metrics)
        return sql

    @staticmethod
    def get_oid_map():
        result = OidMapping.objects.all().values()
        return {i["oid"]: i for i in result}

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
        # 网络设备
        mapping = {
            "inst_name": self.set_inst_name,
            "ip_addr": "ip_addr",
            "soid": "sysobjectid",
            "port": "port",
            "model": "model",
            "brand": "brand",
            "model_id": "model_id"
        }
        return mapping

    @staticmethod
    def interface_name(data, *args, **kwargs):
        return data.get("alias", data['description'])

    @property
    def model_field_mapping(self):
        # 接口
        mapping = {
            "inst_name": self.set_interface_inst_name,
            "self_device": self.set_self_device,
            "mac": "mac_address",
            "name": self.interface_name,
            "status": (self.set_interface_status, "oper_status"),
            self.asso: self.get_interface_asso,
        }
        return mapping

    def check_task_id(self, instance_id):
        # TODO 后续补tag字段后 修改查询的promsql 语句
        task_id, _ = instance_id.split("_", 1)
        return task_id == self.task_id

    def format_data(self, data):
        """格式化数据"""
        for index_data in data["result"]:
            metric_name = index_data["metric"]["__name__"]
            instance_id = index_data["metric"]["instance_id"]
            if not self.check_task_id(instance_id):
                continue

            if "sysobjectid" in index_data["metric"]:
                oid = index_data["metric"]["sysobjectid"]
                oid_data = self.oid_map.get(oid, "")
                if not oid_data:
                    logger.info("==OID does not exist, this instance data is skipped OID={}==".format(oid))
                    continue
                else:
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

        if self.is_topo:
            relationships = self.find_interface_relationships(topo_data)
            self.add_interface_assos(relationships)
            # 把接口的关联补充接口的关联关系中

    def add_interface_assos(self, relationships):
        for relationship in relationships:
            source_inst_name = relationship["source_inst_name"]
            if not self.interfaces_data.get(source_inst_name):
                continue
            data = {'asst_id': 'connect',
                    'inst_name': relationship["target_inst_name"],
                    'model_asst_id': 'interface_connect_interface',
                    'model_id': 'interface'
                    }
            self.interfaces_data.get(source_inst_name)["assos"].append(data)

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
