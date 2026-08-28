# -- coding: utf-8 --
# @File: snmp_facts.py
# @Time: 2025/3/20 17:30
# @Author: windyzhao

import socket
import time

from core.plugin.error_logging import log_plugin_exception
from pysnmp.hlapi.asyncio import (
    CommunityData,
    ContextData,
    ObjectIdentity,
    ObjectType,
    SnmpEngine,
    UdpTransportTarget,
    UsmUserData,
    getCmd,
    nextCmd,
    usmAesCfb128Protocol,
    usmDESPrivProtocol,
    usmHMACMD5AuthProtocol,
    usmHMACSHAAuthProtocol,
)
from pysnmp.proto.rfc1902 import Null
from pysnmp.proto.rfc1905 import EndOfMibView, endOfMibView
from sanic.log import logger


class DefineOid:
    """
    定义常用的 SNMP OID，用于采集设备的系统信息、接口信息和 IP 信息。
    """

    def __init__(self, dotprefix=False):
        dp = "." if dotprefix else ""
        # 系统信息 OIDs
        self.sysDescr = dp + "1.3.6.1.2.1.1.1.0"
        self.sysObjectId = dp + "1.3.6.1.2.1.1.2.0"
        # self.sysUpTime = dp + "1.3.6.1.2.1.1.3.0"
        self.sysContact = dp + "1.3.6.1.2.1.1.4.0"
        self.sysName = dp + "1.3.6.1.2.1.1.5.0"
        self.sysLocation = dp + "1.3.6.1.2.1.1.6.0"

        # 接口信息 OIDs
        self.ifIndex = dp + "1.3.6.1.2.1.2.2.1.1"
        self.ifDescr = dp + "1.3.6.1.2.1.2.2.1.2"
        self.ifMtu = dp + "1.3.6.1.2.1.2.2.1.4"
        self.ifSpeed = dp + "1.3.6.1.2.1.2.2.1.5"
        self.ifPhysAddress = dp + "1.3.6.1.2.1.2.2.1.6"
        self.ifAdminStatus = dp + "1.3.6.1.2.1.2.2.1.7"
        self.ifOperStatus = dp + "1.3.6.1.2.1.2.2.1.8"
        self.ifAlias = dp + "1.3.6.1.2.1.31.1.1.1.18"


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


def _close_snmp_engine(engine) -> None:
    dispatcher = getattr(engine, "transportDispatcher", None)
    close = getattr(dispatcher, "closeDispatcher", None)
    if callable(close):
        close()


class SnmpFacts:
    """
    SNMP 数据采集类，支持 SNMP v2 和 v3 协议。
    """

    def __init__(self, kwargs):
        # 初始化参数
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
        self.timeout = 10
        self.retries = 1
        self.snmp_port = int(kwargs.get("snmp_port", 161))  # 默认 SNMP 端口为 161
        self._runtime_metrics = kwargs.get("_runtime_metrics")

        # 校验参数
        self._validate_params()

    def _validate_params(self):
        """
        校验传入的参数是否合法。
        """
        if not self.host:
            raise ValueError("Host is required.")
        try:
            socket.gethostbyname(self.host)
        except socket.error:
            raise ValueError("Invalid host or IP address.")
        if self.version not in ["v2", "v2c", "v3"]:
            raise ValueError("Invalid SNMP version. Must be 'v2', 'v2c', or 'v3'.")
        if self.version in ["v2", "v2c"] and not self.community:
            raise ValueError("Community is required for SNMP version 2.")
        if self.version == "v3":
            if not self.username:
                raise ValueError("Username is required for SNMP version 3.")
            if self.level == "authPriv" and not self.privacy:
                raise ValueError("Privacy algorithm is required for authPriv level.")
            if len(self.authkey) < 8 or len(self.privkey) < 8:
                raise ValueError("authkey and privkey must be at least 8 characters long.")
        if not (1 <= self.snmp_port <= 65535):
            raise ValueError("Invalid SNMP port. Must be between 1 and 65535.")

    def _get_snmp_auth(self):
        """
        根据 SNMP 版本和认证参数生成认证对象。
        """
        if self.version in ["v2", "v2c"]:
            return CommunityData(self.community)
        elif self.level == "authNoPriv":
            return UsmUserData(
                self.username,
                authKey=self.authkey,
                authProtocol=self._get_integrity_proto(),
            )
        else:
            return UsmUserData(
                self.username,
                authKey=self.authkey,
                privKey=self.privkey,
                authProtocol=self._get_integrity_proto(),
                privProtocol=self._get_privacy_proto(),
            )

    def _get_integrity_proto(self):
        """
        获取 SNMP v3 的认证协议。
        """
        if self.integrity == "sha":
            return usmHMACSHAAuthProtocol
        elif self.integrity == "md5":
            return usmHMACMD5AuthProtocol
        return None

    def _get_privacy_proto(self):
        """
        获取 SNMP v3 的隐私协议。
        """
        if self.privacy == "aes":
            return usmAesCfb128Protocol
        elif self.privacy == "des":
            return usmDESPrivProtocol
        return None

    def _transport_target(self, timeout=None, retries=None):
        return UdpTransportTarget(
            (self.host, self.snmp_port),
            timeout=self.timeout if timeout is None else timeout,
            retries=self.retries if retries is None else retries,
        )

    async def _next_walk(self, engine, oids, *, timeout=None, retries=None, lexicographic_mode=False):
        """
        原生异步 GETNEXT 遍历，行为对齐 oneliner CommandGenerator.nextCmd
        （默认 lexicographicMode=False）。
        """
        auth = self._get_snmp_auth()
        target = self._transport_target(timeout=timeout, retries=retries)
        context = ContextData()
        var_binds = _as_object_types(oids)
        initial_roots = [str(oid).lstrip(".") for oid in oids]
        var_bind_table = []

        while var_binds:
            previous_var_binds = var_binds
            (
                error_indication,
                error_status,
                error_index,
                response_table,
            ) = await nextCmd(
                engine,
                auth,
                target,
                context,
                *var_binds,
                lookupMib=False,
            )
            if error_indication:
                return error_indication, error_status, error_index, var_bind_table
            if error_status:
                return error_indication, error_status, error_index, var_bind_table

            row = list(response_table[0]) if response_table else []
            if not row:
                break

            stop_flag = True
            for col, var_bind in enumerate(row):
                name, val = var_bind
                if isinstance(val, Null):
                    row[col] = (previous_var_binds[col][0], endOfMibView)
                elif not lexicographic_mode and not _is_prefix_of(initial_roots[col], name):
                    row[col] = (previous_var_binds[col][0], endOfMibView)
                cell_val = row[col][1]
                if cell_val is not endOfMibView and not isinstance(cell_val, EndOfMibView):
                    stop_flag = False

            if stop_flag:
                break

            var_bind_table.append(row)
            var_binds = row

        return None, 0, 0, var_bind_table

    async def collect(self):  # noqa: C901
        """
        采集 SNMP 数据，包括系统信息、接口信息和 IP 信息。
        """
        collect_started_at = time.monotonic()
        probe_timeout = min(self.timeout, 10)
        snmp_auth = self._get_snmp_auth()
        engine = SnmpEngine()
        context = ContextData()

        # 定义 OID
        p = DefineOid(dotprefix=True)
        v = DefineOid(dotprefix=False)

        # 初始化结果字典
        results = {
            "system": {},
            "interfaces": [],  # 确保 interfaces 是一个列表
        }

        try:
            # 系统 GET 与接口 WALK 共用目标级 Engine，避免重复初始化。
            try:
                observe = getattr(self._runtime_metrics, "observe", None)
                if callable(observe):
                    observe(
                        "snmp_collect_to_first_io_seconds",
                        time.monotonic() - collect_started_at,
                    )
                errorIndication, errorStatus, errorIndex, varBinds = await getCmd(
                    engine,
                    snmp_auth,
                    self._transport_target(timeout=probe_timeout, retries=self.retries),
                    context,
                    ObjectType(ObjectIdentity(p.sysDescr.lstrip("."))),
                    ObjectType(ObjectIdentity(p.sysObjectId.lstrip("."))),
                    ObjectType(ObjectIdentity(p.sysContact.lstrip("."))),
                    ObjectType(ObjectIdentity(p.sysName.lstrip("."))),
                    ObjectType(ObjectIdentity(p.sysLocation.lstrip("."))),
                    lookupMib=False,
                )
                if errorIndication:
                    raise RuntimeError(f"SNMP getCmd failed: {errorIndication}")

                for oid, val in varBinds:
                    current_oid = oid.prettyPrint()
                    current_val = val.prettyPrint()
                    if current_oid == v.sysDescr:
                        try:
                            current_val = val._value.decode()
                        except Exception:
                            current_val = str(current_val)
                        results["system"]["sysdescr"] = current_val
                    elif current_oid == v.sysObjectId:
                        results["system"]["sysobjectid"] = current_val
                    elif current_oid == v.sysContact:
                        results["system"]["syscontact"] = current_val
                    elif current_oid == v.sysName:
                        results["system"]["sysname"] = current_val
                    elif current_oid == v.sysLocation:
                        results["system"]["syslocation"] = current_val

                results["system"]["ip_addr"] = self.host
                results["system"]["port"] = self.snmp_port
            except Exception as e:
                raise RuntimeError(f"Error during SNMP system information collection: {str(e)}")

            try:
                errorIndication, errorStatus, errorIndex, varTable = await self._next_walk(
                    engine,
                    [
                        p.ifIndex,
                        p.ifDescr,
                        p.ifMtu,
                        p.ifSpeed,
                        p.ifPhysAddress,
                        p.ifAdminStatus,
                        p.ifOperStatus,
                        p.ifAlias,
                    ],
                    timeout=self.timeout,
                    retries=self.retries,
                    lexicographic_mode=False,
                )
                if errorIndication:
                    raise RuntimeError(f"SNMP nextCmd failed: {errorIndication}")

                for varBinds in varTable:
                    interface = {}
                    for oid, val in varBinds:
                        current_oid = oid.prettyPrint()
                        current_val = val.prettyPrint()
                        if current_oid.startswith(v.ifIndex):
                            interface["index"] = current_val
                        elif current_oid.startswith(v.ifDescr):
                            interface["description"] = current_val
                        elif current_oid.startswith(v.ifMtu):
                            interface["mtu"] = current_val
                        elif current_oid.startswith(v.ifSpeed):
                            interface["speed"] = current_val
                        elif current_oid.startswith(v.ifPhysAddress):
                            interface["mac_address"] = current_val
                        elif current_oid.startswith(v.ifAdminStatus):
                            interface["admin_status"] = current_val
                        elif current_oid.startswith(v.ifOperStatus):
                            interface["oper_status"] = current_val
                        elif current_oid.startswith(v.ifAlias):
                            interface["alias"] = current_val
                    if interface:
                        results["interfaces"].append(interface)
            except Exception as e:
                raise RuntimeError(f"Error during SNMP interface information collection: {str(e)}")

            return results
        finally:
            _close_snmp_engine(engine)

    async def probe(self):
        """最小只读 SNMP GET（sysName），用于 CredentialAttempt。"""
        from core.collection.contracts import AccessProbeResult, AccessProbeStatus

        oid = DefineOid(dotprefix=True)
        # access_probe：固定 10 秒超时、重试 1 次（与正式采集 timeout 解耦）
        engine = SnmpEngine()
        try:
            error_indication, error_status, _error_index, var_binds = await getCmd(
                engine,
                self._get_snmp_auth(),
                self._transport_target(timeout=10, retries=1),
                ContextData(),
                ObjectType(ObjectIdentity(oid.sysName.lstrip("."))),
                lookupMib=False,
            )
        except Exception:  # noqa: BLE001 - 不把 SDK 异常正文写入结果
            return AccessProbeResult(
                status=AccessProbeStatus.NO_RESPONSE,
                error_code="snmp_probe_error",
            )
        finally:
            _close_snmp_engine(engine)
        if error_indication:
            indication = str(error_indication).lower()
            if "timeout" in indication or "no response" in indication:
                return AccessProbeResult(
                    status=AccessProbeStatus.NO_RESPONSE,
                    error_code="protocol_no_response",
                )
            if any(token in indication for token in ("authorization", "authentication", "community")):
                return AccessProbeResult(
                    status=AccessProbeStatus.AUTH_FAILED,
                    error_code="snmp_authorization_failed",
                )
            return AccessProbeResult(
                status=AccessProbeStatus.NO_RESPONSE,
                error_code="protocol_no_response",
            )
        if error_status:
            return AccessProbeResult(
                status=AccessProbeStatus.AUTH_FAILED,
                error_code="snmp_error_status",
            )
        if not var_binds:
            return AccessProbeResult(
                status=AccessProbeStatus.NO_RESPONSE,
                error_code="empty_snmp_response",
            )
        return AccessProbeResult(status=AccessProbeStatus.READY)

    async def list_all_resources(self):
        """将设备与接口 SNMP 数据转换为标准格式。"""
        logger.info(
            "event=snmp_facts_collection_started task_id=%s plugin_ref=%s " "model_id=%s plugin_name=%s target=%s | SNMP采集开始 IP=%s",
            self.kwargs.get("collection_task_id") or "-",
            self.kwargs.get("collection_plugin_ref") or "network.config",
            self.kwargs.get("model_id") or "network",
            self.kwargs.get("plugin_name") or "snmp_facts",
            self.host,
            self.host,
        )
        try:
            snmp_data = await self.collect()
            system_data = snmp_data.get("system", {})
            interfaces_data = snmp_data.get("interfaces", [])
            model_data = {
                "network_system": [system_data],
                "network_interfaces": interfaces_data,
            }

            inst_data = {"result": model_data, "success": True}
        except Exception as err:
            log_plugin_exception(
                logger,
                error=err,
                task_id=self.kwargs.get("collection_task_id"),
                plugin_ref=self.kwargs.get("collection_plugin_ref") or "network.config",
                model_id=self.kwargs.get("model_id") or "network",
                plugin_name=self.kwargs.get("plugin_name") or "snmp_facts",
                target=self.host,
            )
            inst_data = {"result": {"cmdb_collect_error": str(err)}, "success": False}

        return inst_data
