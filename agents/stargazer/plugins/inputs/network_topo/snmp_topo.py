# -- coding: utf-8 --
# @File: network_topo.py
# @Time: 2025/3/31 14:35
# @Author: windyzhao

try:
    from pysnmp.hlapi.asyncio import CommunityData, ContextData, ObjectIdentity, ObjectType, UdpTransportTarget, UsmUserData
    from pysnmp.hlapi.asyncio import bulkCmd as hlapi_bulk_cmd
    from pysnmp.hlapi.asyncio import getCmd as hlapi_get_cmd
    from pysnmp.hlapi.asyncio import nextCmd as hlapi_next_cmd
    from pysnmp.hlapi.asyncio import usmAesCfb128Protocol, usmDESPrivProtocol, usmHMACMD5AuthProtocol, usmHMACSHAAuthProtocol
    from pysnmp.proto import errind
    from pysnmp.proto.rfc1902 import Null
    from pysnmp.proto.rfc1905 import EndOfMibView, endOfMibView

    _PYSNMP_AVAILABLE = True
except ModuleNotFoundError:  # pragma: no cover - exercised in environments without optional snmp deps
    _PYSNMP_AVAILABLE = False
    CommunityData = ContextData = ObjectIdentity = ObjectType = None  # type: ignore
    UdpTransportTarget = UsmUserData = None  # type: ignore
    hlapi_bulk_cmd = hlapi_get_cmd = hlapi_next_cmd = None  # type: ignore
    usmAesCfb128Protocol = usmDESPrivProtocol = None  # type: ignore
    usmHMACMD5AuthProtocol = usmHMACSHAAuthProtocol = None  # type: ignore
    errind = None  # type: ignore
    Null = None  # type: ignore
    endOfMibView = None  # type: ignore

    class EndOfMibView:  # type: ignore[no-redef]
        pass


from core.infra.snmp_engine_pool import shared_snmp_engine
from plugins.inputs.network_topo.protocol_oids import PROTOCOL_OID_GROUPS, flatten_oid_registry, get_oid_meta
from plugins.inputs.network_topo.protocol_oids import get_root_oid as lookup_root_oid
from plugins.inputs.network_topo.topology_facts import build_topology_fact as build_protocol_topology_fact
from plugins.inputs.network_topo.topology_facts import merge_topology_facts
from sanic.log import logger

ROOT = "root"  # 根oid
KEY = "key"  # oid
TAG = "tag"  # 名称
IF_INDEX = "ifindex"  # 索引
IF_INDEX_TYPE = "ifindex_type"  # 索引类型 default为单索引,ipaddr为后4位为ip地址
VAL = "val"  # oid对应值

OIDKEY = [ROOT, KEY, TAG, IF_INDEX, IF_INDEX_TYPE, VAL]

GROUP = "group"

OPTIONAL_FALLBACK_ROOTS = {
    "1.3.6.1.2.1.1.5",
    "1.3.6.1.4.1.9.9.23.1.2.1.1.3",
    "1.3.6.1.4.1.9.9.23.1.2.1.1.4",
    "1.3.6.1.4.1.9.9.23.1.2.1.1.6",
    "1.3.6.1.4.1.9.9.23.1.2.1.1.7",
    "1.3.6.1.4.1.9.9.23.1.2.1.1.8",
    "1.3.6.1.4.1.9.9.23.1.2.1.1.17",
    "1.3.6.1.4.1.1991.1.1.3.20.1.2.1.1.3",
    "1.3.6.1.4.1.1991.1.1.3.20.1.2.1.1.6",
    "1.3.6.1.4.1.1991.1.1.3.20.1.2.1.1.7",
    "1.3.6.1.4.1.1991.1.1.3.20.1.2.1.1.8",
    "1.3.6.1.2.1.17.7.1.2.2.1.2",
    "1.3.6.1.2.1.17.7.1.2.2.1.3",
}


class IncompleteFallbackError(RuntimeError):
    pass


class FallbackOidResult:
    def __init__(self, records, skipped=False):
        self.records = records
        self.skipped = skipped


def get_root_oid(oid, roots=None):
    # When roots is explicitly provided (e.g. during _format_result), restrict to that set.
    # Otherwise fall back to the full OID registry so bridge/lldp/cdp OIDs are found too.
    return lookup_root_oid(oid, roots)


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
        GROUP: oid_dict.get("group", "interfaces"),
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
        GROUP: oid_dict.get("group", "interfaces"),
    }


def _oid_text(oid) -> str:
    pretty = getattr(oid, "prettyPrint", None)
    text = pretty() if callable(pretty) else str(oid)
    return str(text).lstrip(".")


def _is_prefix_of(root: str, oid) -> bool:
    root = root.lstrip(".")
    oid_text = _oid_text(oid)
    return oid_text == root or oid_text.startswith(root + ".")


def _as_object_types(oids):
    return [ObjectType(ObjectIdentity(str(oid).lstrip("."))) for oid in oids]


def _is_ended_value(val) -> bool:
    return val is endOfMibView or isinstance(val, EndOfMibView)


class SnmpAuth(object):
    def __init__(
        self,
        cmdGen=None,
        version: str = "v2",
        community: str = None,
        username: str = "",
        level: str = "",
        integrity: str = None,
        privacy: str = None,
        authkey: str = None,
        privkey: str = None,
        timeout: int = 10,
        retries: int = 1,
    ):
        self.cmdGen = cmdGen  # 保留兼容参数；原生 asyncio 路径不再使用
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
            snmp_auth = CommunityData(self.community)

        # Use SNMP Version 3 with authNoPriv
        else:
            integrity_proto = None
            privacy_proto = None
            if self.integrity == "sha":
                integrity_proto = usmHMACSHAAuthProtocol
            elif self.integrity == "md5":
                integrity_proto = usmHMACMD5AuthProtocol

            if self.privacy == "aes":
                privacy_proto = usmAesCfb128Protocol
            elif self.privacy == "des":
                privacy_proto = usmDESPrivProtocol

            if self.level == "authNoPriv":
                snmp_auth = UsmUserData(self.username, authKey=self.authKey, authProtocol=integrity_proto)

            # Use SNMP Version 3 with authPriv
            else:
                snmp_auth = UsmUserData(
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
        if not _PYSNMP_AVAILABLE:
            raise ModuleNotFoundError("pysnmp is required for SNMP topology collection")
        self.kwargs = kwargs
        self.host = kwargs.get("host")
        self.version = kwargs.get("version")
        self.community = kwargs.get("community")
        self.username = kwargs.get("username")
        self.level = kwargs.get("level")
        self.integrity = kwargs.get("integrity")
        self.privacy = kwargs.get("privacy")
        self.authkey = kwargs.get("authkey")
        self.privkey = kwargs.get("privkey")
        self.timeout = int(kwargs.get("timeout", 10))
        self.retries = int(kwargs.get("retries", 1))
        self.snmp_port = int(kwargs.get("snmp_port", 161))  # 默认 SNMP 端口为 161
        self.topology_protocols = kwargs.get("topology_protocols")
        self.oids = self._build_oids(self.topology_protocols)
        self.snmp_auth_obj = SnmpAuth(
            None,
            self.version,
            self.community,
            self.username,
            self.level,
            self.integrity,
            self.privacy,
            self.authkey,
            self.privkey,
            self.timeout,
            self.retries,
        )
        self.auth = self.snmp_auth_obj.auth()
        self.transport_opts = self.snmp_auth_obj.get_transport_opts()
        self.collection_task_id = kwargs.get("collection_task_id")

    def _transport_target(self):
        return UdpTransportTarget(
            (self.host, self.snmp_port),
            timeout=self.transport_opts["timeout"],
            retries=self.transport_opts["retries"],
        )

    def _shared_engine(self):
        # 与 network 配置采集共用进程级 SnmpEngine 池，不再每目标新建 engine。
        return shared_snmp_engine(self.auth, target=(self.host, self.snmp_port))

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
        for protocol in [
            *cls.BASE_COLLECTION_PROTOCOLS,
            *cls.normalize_collection_protocols(enabled_protocols),
        ]:
            if protocol not in group_names:
                group_names.append(protocol)
        registry = flatten_oid_registry(group_names)
        return [entry["key"] for entry in registry]

    @staticmethod
    def _format_oids(oids):
        """
        格式化 OID 列表
        """
        return _as_object_types(oids)

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

    async def _bulk_walk_all(self):
        async with self._shared_engine() as engine:
            return await self._bulk_walk_all_with_engine(engine)

    async def _bulk_walk_all_with_engine(self, engine):
        """
        批量获取 OID 数据（原生 asyncio GETBULK 遍历）
        """
        eval_oids = self.oids
        var_binds = self._format_oids(self.oids)
        initial_roots = [str(oid).lstrip(".") for oid in self.oids]
        target = self._transport_target()
        context = ContextData()
        var_bind_table = []
        null_var_binds = [False] * len(initial_roots)
        stop_flag = False

        while not stop_flag and var_binds:
            previous_var_binds = var_binds
            (
                errorIndication,
                errorStatus,
                errorIndex,
                response_table,
            ) = await hlapi_bulk_cmd(
                engine,
                self.auth,
                target,
                context,
                0,
                25,
                *var_binds,
                lookupMib=False,
            )
            if errorIndication:
                raise RuntimeError(str(errorIndication))
            if errorStatus:
                raise RuntimeError(f"SNMP error: {errorStatus.prettyPrint()}")

            if not response_table:
                break

            processed_rows = []
            for row_index, raw_row in enumerate(response_table):
                row = list(raw_row)
                stop_flag = True
                if len(row) != len(initial_roots):
                    break
                for col in range(len(row)):
                    name, val = row[col]
                    if row_index:
                        previous_var_binds = processed_rows[row_index - 1]
                    if null_var_binds[col]:
                        row[col] = (previous_var_binds[col][0], endOfMibView)
                        continue
                    stop_flag = False
                    if isinstance(val, Null):
                        row[col] = (previous_var_binds[col][0], endOfMibView)
                        null_var_binds[col] = True
                        continue
                    if not _is_prefix_of(initial_roots[col], name):
                        row[col] = (previous_var_binds[col][0], endOfMibView)
                        null_var_binds[col] = True
                        continue
                if stop_flag:
                    break
                processed_rows.append(row)
                var_bind_table.append(row)
                var_binds = row

        return self._format_result(var_bind_table, eval_oids)

    @staticmethod
    def _is_retryable_fallback_error(error):
        message = str(error).lower()
        return "oid not increasing" in message or "empty snmp response message" in message

    async def bulkCmd(self):
        """批量获取 OID 数据，失败时按 OID 逐个降级采集"""
        try:
            return await self._bulk_walk_all()
        except RuntimeError as err:
            if not self._is_retryable_fallback_error(err):
                raise
            logger.warning(f"bulkCmd retryable error host={self.host}, falling back to per-OID walk: {err}")
            return await self._fallback_walk_cmd()

    @staticmethod
    def _is_scalar_oid(root_oid):
        return get_oid_meta(root_oid).get("ifindex_type") == "scalar"

    async def _next_walk_oid(self, oid, *, ignore_non_increasing_oid=True):
        async with self._shared_engine() as engine:
            return await self._next_walk_oid_with_engine(
                oid,
                engine,
                ignore_non_increasing_oid=ignore_non_increasing_oid,
            )

    async def _next_walk_oid_with_engine(self, oid, engine, *, ignore_non_increasing_oid=True):
        target = self._transport_target()
        context = ContextData()
        var_binds = self._format_oids([oid])
        initial_root = str(oid).lstrip(".")
        var_bind_table = []

        while var_binds:
            previous_var_binds = var_binds
            (
                errorIndication,
                errorStatus,
                errorIndex,
                response_table,
            ) = await hlapi_next_cmd(
                engine,
                self.auth,
                target,
                context,
                *var_binds,
                lookupMib=False,
            )
            if ignore_non_increasing_oid and errorIndication and isinstance(errorIndication, errind.OidNotIncreasing):
                errorIndication = None

            if errorIndication:
                return errorIndication, errorStatus, errorIndex, var_bind_table
            if errorStatus:
                return errorIndication, errorStatus, errorIndex, var_bind_table

            row = list(response_table[0]) if response_table else []
            if not row:
                break

            stop_flag = True
            for col, var_bind in enumerate(row):
                name, val = var_bind
                if isinstance(val, Null):
                    row[col] = (previous_var_binds[col][0], endOfMibView)
                elif not _is_prefix_of(initial_root, name):
                    row[col] = (previous_var_binds[col][0], endOfMibView)
                cell_val = row[col][1]
                if not _is_ended_value(cell_val):
                    stop_flag = False

            if stop_flag:
                break

            var_bind_table.append(row)
            var_binds = row

        return None, 0, 0, var_bind_table

    async def _walk_oid_with_next_cmd(self, oid):
        (
            errorIndication,
            errorStatus,
            errorIndex,
            varBindTable,
        ) = await self._next_walk_oid(oid)
        if errorIndication:
            if self._is_retryable_fallback_error(errorIndication):
                logger.warning(f"Skipping OID subtree host={self.host} oid={oid}: {errorIndication}")
                return FallbackOidResult(records=[], skipped=True)
            raise RuntimeError(str(errorIndication))
        if errorStatus:
            if self._is_retryable_fallback_error(errorStatus):
                logger.warning(f"Skipping OID subtree host={self.host} oid={oid}: {errorStatus.prettyPrint()}")
                return FallbackOidResult(records=[], skipped=True)
            raise RuntimeError(f"SNMP error: {errorStatus.prettyPrint()} (oid={oid})")
        return FallbackOidResult(records=self._format_result(varBindTable, [oid]))

    async def _get_scalar_oid(self, oid):
        async with self._shared_engine() as engine:
            errorIndication, errorStatus, errorIndex, varBinds = await hlapi_get_cmd(
                engine,
                self.auth,
                self._transport_target(),
                ContextData(),
                *self._format_oids([f"{oid}.0"]),
                lookupMib=False,
            )
        if errorIndication:
            if self._is_retryable_fallback_error(errorIndication):
                return FallbackOidResult(records=[], skipped=True)
            raise RuntimeError(str(errorIndication))
        if errorStatus:
            if self._is_retryable_fallback_error(errorStatus):
                return FallbackOidResult(records=[], skipped=True)
            raise RuntimeError(f"SNMP error: {errorStatus.prettyPrint()} (oid={oid})")
        return FallbackOidResult(records=self._format_result([varBinds], [oid]))

    async def _fallback_collect_oid(self, oid):
        if self._is_scalar_oid(oid):
            return await self._get_scalar_oid(oid)
        return await self._walk_oid_with_next_cmd(oid)

    async def _fallback_walk_cmd(self):
        records = []
        skipped_required_oids = []
        for oid in self.oids:
            oid_result = await self._fallback_collect_oid(oid)
            if oid_result.skipped:
                if oid in OPTIONAL_FALLBACK_ROOTS:
                    logger.info(f"Optional fallback OID unavailable host={self.host} oid={oid}; continuing")
                    continue
                skipped_required_oids.append(oid)
                continue
            records.extend(oid_result.records)
        if skipped_required_oids:
            raise IncompleteFallbackError("Fallback walk skipped required OIDs: " + ", ".join(skipped_required_oids))
        if records:
            return records
        raise RuntimeError("SNMP fallback collection returned no data: " "device did not respond with any requested MIB subtree")

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
        local_ports = {str(row.get(IF_INDEX)): row for row in snmp_rows if row.get(TAG) == "LLDP-LocPortId" and row.get(IF_INDEX)}
        remote_ports = {str(row.get(IF_INDEX)): row for row in snmp_rows if row.get(TAG) == "LLDP-RemPortId" and row.get(IF_INDEX)}
        remote_systems = [row for row in snmp_rows if row.get(TAG) == "LLDP-RemSysName" and row.get(IF_INDEX)]

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
        remote_ports = {str(row.get(IF_INDEX)): row for row in snmp_rows if row.get(TAG) == "CDP-DevicePort" and row.get(IF_INDEX)}
        remote_devices = [row for row in snmp_rows if row.get(TAG) == "CDP-DeviceId" and row.get(IF_INDEX)]

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
        interface_rows = {str(row.get(IF_INDEX)): row for row in snmp_rows if row.get(TAG) == "IFTable-IfDescr" and row.get(IF_INDEX)}
        interface_alias_rows = {str(row.get(IF_INDEX)): row for row in snmp_rows if row.get(TAG) == "IFTable-IfAlias" and row.get(IF_INDEX)}
        bridge_ports = {
            str(row.get(IF_INDEX)): row for row in snmp_rows if row.get(TAG) == "BRIDGE-BasePortIfIndex" and row.get(IF_INDEX) and row.get(VAL)
        }
        fdb_macs = {str(row.get(IF_INDEX)): row for row in snmp_rows if row.get(TAG) == "FDB-MacAddress" and row.get(IF_INDEX)}
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

    async def list_all_resources(self):
        """
        将采集到的 SNMP 数据转换为标准格式。
        """
        try:
            snmp_data = await self.bulkCmd()
            model_data = {"network_topo": snmp_data}
            inst_data = {"result": model_data, "success": True}
        except Exception as err:
            logger.exception(
                "event=snmp_topo_collect_failed host=%s task_id=%s failed_stage=%s error_type=%s",
                self.host,
                self.collection_task_id,
                "list_all_resources",
                type(err).__name__,
            )
            inst_data = {"result": {"cmdb_collect_error": str(err)}, "success": False}

        return inst_data

    async def find_interface_relationships(self):
        """
        寻找网络设备接口之间的关联关系
        """
        # Step 1: 获取 SNMP 数据
        snmp_data = await self.bulkCmd()

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
                relationships.append(
                    {
                        "mac_address": mac,
                        "ip_address": ip,
                        "interface_id": interface_id,
                        "interface_name": interface_name,
                    }
                )

        # Step 7: 返回结果
        return relationships
