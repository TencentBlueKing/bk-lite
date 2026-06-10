# -- coding: utf-8 --
# @File: network_topo.py
# @Time: 2025/3/31 14:35
# @Author: windyzhao

try:
    from pysnmp.entity.rfc3413.oneliner import cmdgen
    from pysnmp.proto.rfc1905 import EndOfMibView
except ModuleNotFoundError:  # pragma: no cover - exercised in environments without optional snmp deps
    cmdgen = None

    class EndOfMibView:  # type: ignore[no-redef]
        pass
from sanic.log import logger

from plugins.inputs.network_topo.protocol_oids import (
    NETWORK_TOPO_OIDS,
    PROTOCOL_OID_GROUPS,
    flatten_oid_registry,
    get_oid_meta,
    get_root_oid as lookup_root_oid,
)
from plugins.inputs.network_topo.topology_facts import (
    build_topology_fact as build_protocol_topology_fact,
    merge_topology_facts,
)

ROOT = "root"  # 根oid
KEY = "key"  # oid
TAG = "tag"  # 名称
IF_INDEX = "ifindex"  # 索引
IF_INDEX_TYPE = "ifindex_type"  # 索引类型 default为单索引,ipaddr为后4位为ip地址
VAL = "val"  # oid对应值

OIDKEY = [ROOT, KEY, TAG, IF_INDEX, IF_INDEX_TYPE, VAL]


def get_root_oid(oid, roots=None):
    return lookup_root_oid(oid, roots or NETWORK_TOPO_OIDS)


def build_single_oid_dict(oid, val):
    """单值OID字典"""
    root_oid = get_root_oid(oid)
    if not root_oid:
        return
    oid_dict = get_oid_meta(root_oid)
    return {
        ROOT: root_oid,
        KEY: oid,
        TAG: oid_dict.get("tag", "") or oid,
        IF_INDEX: None,
        IF_INDEX_TYPE: "None",
        VAL: val,
    }


def build_oid_dict(oid, val, parent_oid=None):
    """树形OID字典"""

    root_oid = parent_oid or get_root_oid(oid) or None
    if not root_oid:
        raise ValueError(f"OID {oid} not in protocol OID registry")

    oid_dict = get_oid_meta(root_oid)
    ifindex_type = oid_dict.get("ifindex_type", "default") or "default"
    index_parser = oid_dict.get("index_parser")
    ifIndex = index_parser(oid, root_oid) if callable(index_parser) else None

    return {
        ROOT: root_oid,
        KEY: oid,
        TAG: oid_dict.get("tag", "") or oid,
        IF_INDEX: ifIndex,
        IF_INDEX_TYPE: ifindex_type,
        VAL: val,
    }


class SnmpAuth(object):
    def __init__(
            self,
            cmdGen,
            version: str = "v2",
            community: str = None,
            username: str = "",
            level: str = "",
            integrity: str = None,
            privacy: str = None,
            authkey: str = None,
            privkey: str = None,
            timeout: int = 1,
            retries: int = 5,
    ):
        self.cmdGen = cmdGen
        self.version = version
        self.community = community
        self.username = username
        self.level = level
        self.integrity = integrity
        self.privacy = privacy
        self.authKey = authkey
        self.privKey = privkey
        self.timeout = timeout
        self.retries = retries
        self.validate()

    def validate(self):

        if self.version in ("v2", "v2c"):
            if self.community is None:
                raise Exception("Community not set when using network version 2")
        if self.version == "v3":
            if self.username is None:
                raise Exception("Username not set when using network version 3")

        if self.level == "authPriv" and self.privacy is None:
            raise Exception("Privacy algorithm not set when using authPriv")

    def auth(self):  # Use SNMP Version 2

        if self.version in ("v2", "v2c"):
            snmp_auth = cmdgen.CommunityData(self.community)

        # Use SNMP Version 3 with authNoPriv
        else:
            integrity_proto = None
            privacy_proto = None
            if self.integrity == "sha":
                integrity_proto = cmdgen.usmHMACSHAAuthProtocol
            elif self.integrity == "md5":
                integrity_proto = cmdgen.usmHMACMD5AuthProtocol

            if self.privacy == "aes":
                privacy_proto = cmdgen.usmAesCfb128Protocol
            elif self.privacy == "des":
                privacy_proto = cmdgen.usmDESPrivProtocol

            if self.level == "authNoPriv":
                snmp_auth = cmdgen.UsmUserData(self.username, authKey=self.authKey, authProtocol=integrity_proto)

            # Use SNMP Version 3 with authPriv
            else:
                snmp_auth = cmdgen.UsmUserData(
                    self.username,
                    authKey=self.authKey,
                    privKey=self.privKey,
                    authProtocol=integrity_proto,
                    privProtocol=privacy_proto,
                )
        return snmp_auth

    def get_transport_opts(self):
        """获取传输配置"""
        return {"timeout": self.timeout, "retries": self.retries}


class SnmpTopo:
    BASE_COLLECTION_PROTOCOLS = ("system", "arp", "interface", "ipaddr")
    # fdp 仅采集证据行（由 server 端流水线按 tag 解析），不参与 agent 侧 facts 构建
    DEFAULT_TOPOLOGY_PROTOCOLS = ("lldp", "cdp", "fdp", "fdb", "arp")
    SUPPORTED_TOPOLOGY_FACT_PROTOCOLS = ("lldp", "cdp", "fdb", "arp")

    def __init__(self, kwargs):
        """
        初始化 SNMP 客户端
        """
        if cmdgen is None:
            raise ModuleNotFoundError("pysnmp is required for SNMP topology collection")
        self.kwargs = kwargs
        self.host = kwargs.get('host')
        self.version = kwargs.get('version')
        self.community = kwargs.get('community')
        self.username = kwargs.get('username')
        self.level = kwargs.get('level')
        self.integrity = kwargs.get('integrity')
        self.privacy = kwargs.get('privacy')
        self.authkey = kwargs.get('authkey')
        self.privkey = kwargs.get('privkey')
        self.timeout = int(kwargs.get('timeout', 1))
        self.retries = int(kwargs.get('retries', 5))
        self.snmp_port = int(kwargs.get('snmp_port', 161))  # 默认 SNMP 端口为 161
        self.topology_protocols = kwargs.get("topology_protocols")
        self.oids = self._build_oids(self.topology_protocols)
        self.cmdGen = cmdgen.CommandGenerator()
        self.snmp_auth_obj = SnmpAuth(
            self.cmdGen, self.version, self.community, self.username, self.level, self.integrity, self.privacy,
            self.authkey, self.privkey, self.timeout, self.retries
        )
        self.auth = self.snmp_auth_obj.auth()
        self.transport_opts = self.snmp_auth_obj.get_transport_opts()

    @classmethod
    def _normalize_protocols(cls, enabled_protocols=None, allowed_protocols=None):
        if enabled_protocols is None:
            return None
        if isinstance(enabled_protocols, str):
            protocols = [item.strip().lower() for item in enabled_protocols.split(",")]
        else:
            protocols = [str(item).strip().lower() for item in enabled_protocols]
        deduped_protocols = []
        allowed = set(allowed_protocols or PROTOCOL_OID_GROUPS.keys())
        for protocol in protocols:
            if protocol and protocol in allowed and protocol not in deduped_protocols:
                deduped_protocols.append(protocol)
        return tuple(deduped_protocols)

    @classmethod
    def normalize_enabled_protocols(cls, enabled_protocols=None):
        normalized = cls._normalize_protocols(
            enabled_protocols,
            allowed_protocols=cls.SUPPORTED_TOPOLOGY_FACT_PROTOCOLS,
        )
        return () if normalized is None else normalized

    @classmethod
    def normalize_collection_protocols(cls, enabled_protocols=None):
        normalized = cls._normalize_protocols(
            enabled_protocols,
            allowed_protocols=(set(PROTOCOL_OID_GROUPS.keys()) - set(cls.BASE_COLLECTION_PROTOCOLS)),
        )
        if normalized is None:
            return cls.DEFAULT_TOPOLOGY_PROTOCOLS
        return normalized

    @classmethod
    def _build_oids(cls, enabled_protocols=None):
        group_names = []
        for protocol in [*cls.BASE_COLLECTION_PROTOCOLS, *cls.normalize_collection_protocols(enabled_protocols)]:
            if protocol not in group_names:
                group_names.append(protocol)
        registry = flatten_oid_registry(group_names)
        return [entry["key"] for entry in registry]

    @staticmethod
    def _format_oids(oids):
        """
        格式化 OID 列表
        """
        return [cmdgen.MibVariable(oid.strip()) for oid in oids]

    @staticmethod
    def _format_result(varBinds, eval_oids=None):
        """
        格式化 SNMP 返回结果
        """
        result = []
        for varBindsRow in varBinds:
            for oid, val in varBindsRow:
                if isinstance(val, EndOfMibView):
                    continue
                current_oid = oid.prettyPrint()
                current_val = val.prettyPrint()
                parent_oid = get_root_oid(current_oid, eval_oids) if eval_oids else None
                oid_dict = build_oid_dict(current_oid, current_val, parent_oid=parent_oid)
                if oid_dict:
                    result.append(oid_dict)
        return result

    def bulkCmd(self):
        """
        批量获取 OID 数据
        """
        eval_oids = self.oids
        oids = self._format_oids(self.oids)
        errorIndication, errorStatus, errorIndex, varBindTable = self.cmdGen.bulkCmd(
            self.auth,
            cmdgen.UdpTransportTarget((self.host, self.snmp_port), **self.transport_opts),
            0,
            25,
            *oids,
            lookupMib=False,
        )
        if errorIndication:
            raise Exception(errorIndication)
        return self._format_result(varBindTable, eval_oids)

    @staticmethod
    def build_topology_fact(protocol, observation, raw_evidence=None, confidence=None):
        return build_protocol_topology_fact(
            protocol,
            observation,
            raw_evidence=raw_evidence,
            confidence=confidence,
        )

    @staticmethod
    def _extract_lldp_local_ifindex(index_value):
        if not index_value:
            return None
        index_parts = str(index_value).split(".")
        if len(index_parts) < 2:
            return None
        return index_parts[1]

    @staticmethod
    def _extract_cdp_local_ifindex(index_value):
        if not index_value:
            return None
        return str(index_value).split(".", 1)[0]

    @classmethod
    def _build_lldp_topology_facts(cls, snmp_rows):
        local_ports = {
            str(row.get(IF_INDEX)): row for row in snmp_rows if row.get(TAG) == "LLDP-LocPortId" and row.get(IF_INDEX)
        }
        remote_ports = {
            str(row.get(IF_INDEX)): row for row in snmp_rows if row.get(TAG) == "LLDP-RemPortId" and row.get(IF_INDEX)
        }
        remote_systems = [
            row for row in snmp_rows if row.get(TAG) == "LLDP-RemSysName" and row.get(IF_INDEX)
        ]

        facts = []
        for remote_system in remote_systems:
            remote_index = str(remote_system.get(IF_INDEX))
            local_ifindex = cls._extract_lldp_local_ifindex(remote_index)
            local_port = local_ports.get(local_ifindex)
            remote_port = remote_ports.get(remote_index)
            if not local_port or not remote_port:
                continue
            local_port_value = local_port.get(VAL)
            remote_port_value = remote_port.get(VAL)
            normalized_local_port_id = local_port.get(IF_INDEX) or local_ifindex
            facts.append(
                cls.build_topology_fact(
                    "lldp",
                    {
                        "local_device_id": None,
                        "local_port_id": str(normalized_local_port_id) if normalized_local_port_id is not None else None,
                        "local_port_name": local_port_value,
                        "remote_device_id": remote_system.get(VAL),
                        "remote_port_id": remote_port_value,
                        "remote_port_name": remote_port_value,
                    },
                    raw_evidence={
                        "local_port": local_port,
                        "remote_system": remote_system,
                        "remote_port": remote_port,
                    },
                )
            )
        return facts

    @classmethod
    def _build_cdp_topology_facts(cls, snmp_rows):
        interface_names = cls._build_interface_names(snmp_rows)
        remote_ports = {
            str(row.get(IF_INDEX)): row for row in snmp_rows if row.get(TAG) == "CDP-DevicePort" and row.get(IF_INDEX)
        }
        remote_devices = [
            row for row in snmp_rows if row.get(TAG) == "CDP-DeviceId" and row.get(IF_INDEX)
        ]

        facts = []
        for remote_device in remote_devices:
            cache_index = str(remote_device.get(IF_INDEX))
            local_ifindex = cls._extract_cdp_local_ifindex(cache_index)
            remote_port = remote_ports.get(cache_index)
            if not remote_port:
                continue
            facts.append(
                cls.build_topology_fact(
                    "cdp",
                    {
                        "local_device_id": None,
                        "local_port_id": local_ifindex,
                        "local_port_name": interface_names.get(local_ifindex),
                        "remote_device_id": remote_device.get(VAL),
                        "remote_port_id": remote_port.get(VAL),
                        "remote_port_name": remote_port.get(VAL),
                    },
                    raw_evidence={
                        "local_port": {
                            TAG: "IFTable-IfDescr",
                            IF_INDEX: local_ifindex,
                            VAL: interface_names.get(local_ifindex),
                        },
                        "remote_device": remote_device,
                        "remote_port": remote_port,
                    },
                )
            )
        return facts

    @classmethod
    def _build_interface_names(cls, snmp_rows):
        interface_names = {}
        for row in snmp_rows:
            if row.get(TAG) == "IFTable-IfDescr" and row.get(IF_INDEX):
                interface_names[str(row.get(IF_INDEX))] = row.get(VAL)
        for row in snmp_rows:
            if row.get(TAG) == "IFTable-IfAlias" and row.get(IF_INDEX):
                interface_names[str(row.get(IF_INDEX))] = row.get(VAL)
        return interface_names

    @classmethod
    def _build_fdb_topology_facts(cls, snmp_rows):
        interface_names = cls._build_interface_names(snmp_rows)
        interface_rows = {
            str(row.get(IF_INDEX)): row for row in snmp_rows if row.get(TAG) == "IFTable-IfDescr" and row.get(IF_INDEX)
        }
        interface_alias_rows = {
            str(row.get(IF_INDEX)): row for row in snmp_rows if row.get(TAG) == "IFTable-IfAlias" and row.get(IF_INDEX)
        }
        bridge_ports = {
            str(row.get(IF_INDEX)): row
            for row in snmp_rows
            if row.get(TAG) == "BRIDGE-BasePortIfIndex" and row.get(IF_INDEX) and row.get(VAL)
        }
        fdb_macs = {
            str(row.get(IF_INDEX)): row for row in snmp_rows if row.get(TAG) == "FDB-MacAddress" and row.get(IF_INDEX)
        }
        fdb_ports = [row for row in snmp_rows if row.get(TAG) == "FDB-Port" and row.get(IF_INDEX) and row.get(VAL)]

        facts = []
        for fdb_port in fdb_ports:
            mac_index = str(fdb_port.get(IF_INDEX))
            fdb_mac = fdb_macs.get(mac_index)
            bridge_port = bridge_ports.get(str(fdb_port.get(VAL)))
            if not fdb_mac or not bridge_port:
                continue
            local_ifindex = str(bridge_port.get(VAL))
            local_port_name = interface_names.get(local_ifindex)
            if not local_port_name:
                continue
            facts.append(
                cls.build_topology_fact(
                    "fdb",
                    {
                        "local_device_id": None,
                        "local_port_id": local_ifindex,
                        "local_port_name": local_port_name,
                        "remote_device_id": fdb_mac.get(VAL),
                        "remote_port_id": None,
                        "remote_port_name": None,
                    },
                    raw_evidence={
                        "local_port": interface_rows.get(local_ifindex),
                        "local_port_alias": interface_alias_rows.get(local_ifindex),
                        "bridge_port": bridge_port,
                        "fdb_mac": fdb_mac,
                        "fdb_port": fdb_port,
                    },
                )
            )
        return facts

    @classmethod
    def _build_arp_topology_facts(cls, snmp_rows):
        return []

    @classmethod
    def build_topology_facts(cls, snmp_rows, enabled_protocols=None):
        facts = []
        if enabled_protocols is None:
            protocols = cls.DEFAULT_TOPOLOGY_PROTOCOLS
        else:
            protocols = cls.normalize_enabled_protocols(enabled_protocols)
        if "lldp" in protocols:
            facts.extend(cls._build_lldp_topology_facts(snmp_rows))
        if "cdp" in protocols:
            facts.extend(cls._build_cdp_topology_facts(snmp_rows))
        if "fdb" in protocols:
            facts.extend(cls._build_fdb_topology_facts(snmp_rows))
        if "arp" in protocols:
            facts.extend(cls._build_arp_topology_facts(snmp_rows))
        return merge_topology_facts(facts)

    def list_all_resources(self):
        """
        将采集到的 SNMP 数据转换为标准格式。
        """
        try:
            snmp_data = self.bulkCmd()
            model_data = {"network_topo": snmp_data}
            inst_data = {"result": model_data, "success": True}
        except Exception as err:
            import traceback
            logger.error(f"snmp_topo collect error! {traceback.format_exc()}")
            inst_data = {"result": {"cmdb_collect_error": str(err)}, "success": False}
        
        return inst_data

    def find_interface_relationships(self):
        """
        寻找网络设备接口之间的关联关系
        """
        # Step 1: 获取 SNMP 数据
        snmp_data = self.bulkCmd()

        # Step 2: 数据分类
        arp_ifindex = [entry for entry in snmp_data if entry[TAG] == "ARP-IfIndex"]
        arp_physaddress = [entry for entry in snmp_data if entry[TAG] == "ARP-PhysAddress"]
        iparr_table = [entry for entry in snmp_data if entry[TAG] == "IpAddr-IpAddr"]
        iftable_descr = [entry for entry in snmp_data if entry[TAG] == "IFTable-IfDescr"]
        iftable_alias = [entry for entry in snmp_data if entry[TAG] == "IFTable-IfAlias"]

        # Step 3: 构建接口名称映射表（优先使用接口别名）
        interface_names = {}
        for entry in iftable_descr:
            interface_id = entry[IF_INDEX]
            interface_names[interface_id] = entry[VAL]  # 默认使用接口描述
        for entry in iftable_alias:
            interface_id = entry[IF_INDEX]
            interface_names[interface_id] = entry[VAL]  # 覆盖为接口别名（优先级更高）

        # Step 4: 构建 MAC-IP 映射表（基于 ARP 表）
        mac_ip_mapping = {}
        for arp_index, arp_phys in zip(arp_ifindex, arp_physaddress):
            if arp_index[IF_INDEX] == arp_phys[IF_INDEX]:  # 通过 IF_INDEX 关联
                mac_ip_mapping[arp_phys[VAL]] = arp_index[VAL]  # MAC -> IP

        # Step 5: 构建 IP-接口映射表（基于 IPARR 表）
        ip_interface_mapping = {}
        for entry in iparr_table:
            ip_address = entry[VAL]
            interface_id = entry[IF_INDEX]
            ip_interface_mapping[ip_address] = interface_id

        # Step 6: 寻找接口关联关系
        relationships = []
        for mac, ip in mac_ip_mapping.items():
            if ip in ip_interface_mapping:
                interface_id = ip_interface_mapping[ip]
                interface_name = interface_names.get(interface_id, f"Interface-{interface_id}")  # 默认值为接口 ID
                relationships.append({
                    "mac_address": mac,
                    "ip_address": ip,
                    "interface_id": interface_id,
                    "interface_name": interface_name,
                })

        # Step 7: 返回结果
        return relationships
