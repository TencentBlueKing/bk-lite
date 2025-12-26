# -- coding: utf-8 --
# @File: network_topo.py
# @Time: 2025/3/31 14:35
# @Author: windyzhao

from pysnmp.entity.rfc3413.oneliner import cmdgen
from pysnmp.proto.rfc1905 import EndOfMibView
from sanic.log import logger

ROOT = "root"  # 根oid
KEY = "key"  # oid
TAG = "tag"  # 名称
IF_INDEX = "ifindex"  # 索引
IF_INDEX_TYPE = "ifindex_type"  # 索引类型 default为单索引,ipaddr为后4位为ip地址
VAL = "val"  # oid对应值

OIDKEY = [ROOT, KEY, TAG, IF_INDEX, IF_INDEX_TYPE, VAL]

DEFAULT_OIDS = [
    # ARP表
    {
        "key": "1.3.6.1.2.1.4.22.1.1",
        "tag": "ARP-IfIndex",
        "ifindex_type": "ipaddr",
    },
    {
        "key": "1.3.6.1.2.1.4.22.1.2",
        "tag": "ARP-PhysAddress",
        "ifindex_type": "ipaddr",
    },
    # IFTable表
    {
        "key": "1.3.6.1.2.1.2.2.1.2",
        "tag": "IFTable-IfDescr",
        "ifindex_type": "default",
    },
    {
        "key": "1.3.6.1.2.1.2.2.1.6",
        "tag": "IFTable-PhysAddress",
        "ifindex_type": "default",
    },
    # 接口别名
    {
        "key": "1.3.6.1.2.1.31.1.1.1.18",
        "tag": "IFTable-IfAlias",
        "ifindex_type": "default",
    },
    # IPARR表
    {
        "key": "1.3.6.1.2.1.4.20.1.1",
        "tag": "IpAddr-IpAddr",
        "ifindex_type": "ipaddr",
    },
]

DEFAULT_OID_MAP = {i["key"]: i for i in DEFAULT_OIDS}


def get_root_oid(oid):
    for root_oid in DEFAULT_OID_MAP.keys():
        if root_oid in oid:
            return root_oid
        else:
            return None


def build_single_oid_dict(oid, val):
    """单值OID字典"""
    root_oid = get_root_oid(oid)
    if not root_oid:
        return
    oid_dict = DEFAULT_OID_MAP.get(root_oid, {})
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

    root_oid = get_root_oid(oid) or parent_oid or None
    if not root_oid:
        raise ValueError(f"OID {oid} not in DEFAULT_OID_MAP")

    oid_dict = DEFAULT_OID_MAP.get(root_oid, {})
    ifindex_type = oid_dict.get("ifindex_type", "default") or "default"
    if ifindex_type == "default":
        ifIndex = oid.rsplit(".", 1)[-1]
    elif ifindex_type == "ipaddr":
        ifIndex = ".".join(oid.rsplit(".", 4)[-4:])
    else:
        ifIndex = None

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


class SnmpTopo:
    def __init__(self, kwargs):
        """
        初始化 SNMP 客户端
        """
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
        self.oids = list(DEFAULT_OID_MAP.keys())
        self.cmdGen = cmdgen.CommandGenerator()
        self.auth = SnmpAuth(
            self.cmdGen, self.version, self.community, self.username, self.level, self.integrity, self.privacy,
            self.authkey, self.privkey
        ).auth()

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
                parent_oid = (
                    next((q_oid for q_oid in eval_oids if current_oid.startswith(q_oid)), None)
                    if eval_oids
                    else None
                )
                oid_dict = build_oid_dict(current_oid, current_val, parent_oid=parent_oid)
                if oid_dict:
                    result.append(oid_dict)
        return result

    def bulkCmd(self):
        """
        批量获取 OID 数据
        """
        eval_oids = self.oids
        transport_opts = {"timeout": self.timeout, "retries": self.retries}
        oids = self._format_oids(self.oids)
        errorIndication, errorStatus, errorIndex, varBindTable = self.cmdGen.bulkCmd(
            self.auth,
            cmdgen.UdpTransportTarget((self.host, self.snmp_port), **transport_opts),
            0,
            25,
            *oids,
            lookupMib=False,
        )
        if errorIndication:
            raise Exception(errorIndication)
        return self._format_result(varBindTable, eval_oids)

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
