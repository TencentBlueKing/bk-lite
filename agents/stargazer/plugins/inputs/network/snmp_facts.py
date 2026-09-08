# -- coding: utf-8 --
# @File: snmp_facts.py
# @Time: 2025/3/20 17:30
# @Author: windyzhao

import asyncio
import socket
import time

from core.infra.snmp_engine_pool import shared_snmp_engine
from core.plugin.error_logging import log_plugin_exception, should_log_plugin_exception
from pysnmp.hlapi.asyncio import (
    CommunityData,
    ContextData,
    ObjectIdentity,
    ObjectType,
    UdpTransportTarget,
    UsmUserData,
    bulkCmd,
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


def _oid_sort_key(oid) -> tuple[int, ...]:
    try:
        return tuple(int(part) for part in _oid_text(oid).split("."))
    except ValueError:
        return ()


def _var_bind_size(name, value) -> int:
    pretty_print = getattr(value, "prettyPrint", None)
    rendered = pretty_print() if callable(pretty_print) else str(value)
    return len(_oid_text(name).encode("utf-8")) + len(str(rendered).encode("utf-8"))


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
        self._probed_system_var_binds = None

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

    async def _next_walk(
        self,
        engine,
        oids,
        *,
        timeout=None,
        retries=None,
        lexicographic_mode=False,
        max_pdus=20000,
        max_rows=20000,
        max_response_bytes=16 * 1024 * 1024,
        deadline_seconds=60,
        row_consumer=None,
    ):
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
        previous_oid_keys = [_oid_sort_key(root) for root in initial_roots]
        response_bytes = 0
        pdu_count = 0
        row_count = 0
        deadline = asyncio.get_running_loop().time() + deadline_seconds

        while var_binds:
            pdu_count += 1
            if pdu_count > max_pdus:
                return RuntimeError("GETNEXT PDU limit exceeded"), 0, 0, var_bind_table
            previous_var_binds = var_binds
            try:
                async with asyncio.timeout_at(deadline):
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
            except TimeoutError:
                return RuntimeError("GETNEXT walk deadline exceeded"), 0, 0, var_bind_table
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
                else:
                    oid_key = _oid_sort_key(name)
                    if not oid_key or oid_key <= previous_oid_keys[col]:
                        return RuntimeError("GETNEXT OID not increasing"), 0, 0, var_bind_table
                    previous_oid_keys[col] = oid_key
                    response_bytes += _var_bind_size(name, val)
                    if response_bytes > max_response_bytes:
                        return RuntimeError("GETNEXT response byte limit exceeded"), 0, 0, var_bind_table
                cell_val = row[col][1]
                if cell_val is not endOfMibView and not isinstance(cell_val, EndOfMibView):
                    stop_flag = False

            if stop_flag:
                break

            row_count += 1
            if row_count > max_rows:
                return RuntimeError("GETNEXT row limit exceeded"), 0, 0, var_bind_table
            if row_consumer is None:
                var_bind_table.append(row)
            else:
                row_consumer(row)
            var_binds = row
            await self._yield_walk_loop()

        return None, 0, 0, var_bind_table

    async def _bulk_walk(
        self,
        engine,
        oids,
        *,
        timeout=None,
        retries=None,
        max_repetitions=25,
        max_pdus=2000,
        max_rows=20000,
        max_response_bytes=16 * 1024 * 1024,
        deadline_seconds=60,
        row_consumer=None,
    ):
        """使用 GETBULK 遍历多个接口列，并保持每列在自己的根 OID 内。"""

        auth = self._get_snmp_auth()
        target = self._transport_target(timeout=timeout, retries=retries)
        context = ContextData()
        var_binds = _as_object_types(oids)
        initial_roots = [str(oid).lstrip(".") for oid in oids]
        var_bind_table = []
        ended = [False] * len(initial_roots)
        previous_oid_keys = [_oid_sort_key(root) for root in initial_roots]
        response_bytes = 0
        pdu_count = 0
        row_count = 0
        current_max_repetitions = max_repetitions
        deadline = asyncio.get_running_loop().time() + deadline_seconds

        while var_binds and not all(ended):
            pdu_count += 1
            if pdu_count > max_pdus:
                return RuntimeError("GETBULK PDU limit exceeded"), 0, 0, var_bind_table
            previous_var_binds = var_binds
            try:
                async with asyncio.timeout_at(deadline):
                    error_indication, error_status, error_index, response_table = await bulkCmd(
                        engine,
                        auth,
                        target,
                        context,
                        0,
                        current_max_repetitions,
                        *var_binds,
                        lookupMib=False,
                    )
            except TimeoutError:
                return RuntimeError("GETBULK walk deadline exceeded"), 0, 0, var_bind_table
            walk_error = error_indication or error_status
            if walk_error and self._is_too_big_error(walk_error) and current_max_repetitions > 1:
                current_max_repetitions = max(1, current_max_repetitions // 2)
                increment = getattr(self._runtime_metrics, "increment", None)
                if callable(increment):
                    increment("snmp_getbulk_repetition_reduced_total")
                continue
            if walk_error:
                return error_indication, error_status, error_index, var_bind_table
            if not response_table:
                break

            processed_rows = []
            for raw_row in response_table:
                row = list(raw_row)
                if len(row) != len(initial_roots):
                    return RuntimeError("GETBULK returned an unexpected column count"), 0, 0, var_bind_table
                for column, (name, value) in enumerate(row):
                    if ended[column]:
                        row[column] = (previous_var_binds[column][0], endOfMibView)
                    elif isinstance(value, Null) or not _is_prefix_of(initial_roots[column], name):
                        row[column] = (previous_var_binds[column][0], endOfMibView)
                        ended[column] = True
                    else:
                        oid_key = _oid_sort_key(name)
                        if not oid_key or oid_key <= previous_oid_keys[column]:
                            return RuntimeError("GETBULK OID not increasing"), 0, 0, var_bind_table
                        previous_oid_keys[column] = oid_key
                        response_bytes += _var_bind_size(name, value)
                        if response_bytes > max_response_bytes:
                            return RuntimeError("GETBULK response byte limit exceeded"), 0, 0, var_bind_table
                if all(value is endOfMibView or isinstance(value, EndOfMibView) for _name, value in row):
                    break
                processed_rows.append(row)
                row_count += 1
                if row_count > max_rows:
                    return RuntimeError("GETBULK row limit exceeded"), 0, 0, var_bind_table
                if row_consumer is None:
                    var_bind_table.append(row)
                else:
                    row_consumer(row)
                previous_var_binds = row
            if not processed_rows:
                break
            var_binds = processed_rows[-1]
            await self._yield_walk_loop()

        return None, 0, 0, var_bind_table

    async def _yield_walk_loop(self):
        """在每个 WALK PDU 转换完成后把控制权交还事件循环。"""

        increment = getattr(self._runtime_metrics, "increment", None)
        if callable(increment):
            increment("snmp_walk_yield_total")
        await asyncio.sleep(0)

    @staticmethod
    def _is_too_big_error(error) -> bool:
        message = str(error).lower().replace("_", " ")
        return "too big" in message or "toobig" in message

    @staticmethod
    def _is_getbulk_fallback_error(error) -> bool:
        message = str(error).lower().replace("_", " ")
        return any(
            token in message
            for token in (
                "oid not increasing",
                "empty snmp response",
                "unexpected column count",
                "too big",
                "toobig",
                "generr",
                "not supported",
                "unsupported",
            )
        )

    async def collect(self):  # noqa: C901
        """
        采集 SNMP 数据，包括系统信息、接口信息和 IP 信息。
        """
        collect_started_at = time.monotonic()
        probe_timeout = min(self.timeout, 10)
        snmp_auth = self._get_snmp_auth()
        context = ContextData()

        # 定义 OID
        p = DefineOid(dotprefix=True)
        v = DefineOid(dotprefix=False)

        # 初始化结果字典
        results = {
            "system": {},
            "interfaces": [],  # 确保 interfaces 是一个列表
        }

        # 系统 GET 与接口 WALK 共用进程级共享 Engine（见 core.infra.snmp_engine_pool），
        # 上下文退出只归还引用，不关闭 dispatcher。
        async with shared_snmp_engine(snmp_auth, target=(self.host, self.snmp_port)) as engine:
            try:
                observe = getattr(self._runtime_metrics, "observe", None)
                if callable(observe):
                    observe(
                        "snmp_collect_to_first_io_seconds",
                        time.monotonic() - collect_started_at,
                    )
                if self._probed_system_var_binds is None:
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
                else:
                    errorIndication, errorStatus, errorIndex = None, 0, 0
                    varBinds = self._probed_system_var_binds
                    self._probed_system_var_binds = None
                if errorIndication:
                    raise RuntimeError(f"SNMP getCmd failed: {errorIndication}")
                if errorStatus:
                    pretty_print = getattr(errorStatus, "prettyPrint", None)
                    status_text = pretty_print() if callable(pretty_print) else str(errorStatus)
                    raise RuntimeError(f"SNMP system GET failed: {status_text}")

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

                def append_interface(var_binds):
                    interface = {}
                    for oid, val in var_binds:
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

                errorIndication, errorStatus, errorIndex, varTable = await self._bulk_walk(
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
                    row_consumer=append_interface,
                )
                walk_error = errorIndication or errorStatus
                if walk_error and self._is_getbulk_fallback_error(walk_error):
                    increment = getattr(self._runtime_metrics, "increment", None)
                    if callable(increment):
                        increment("snmp_getbulk_fallback_total")
                    logger.warning(
                        "event=snmp_getbulk_fallback host=%s error_type=%s",
                        self.host,
                        type(walk_error).__name__,
                    )
                    # GETBULK 失败前可能已产生部分结果；GETNEXT 会从头重试。
                    results["interfaces"].clear()
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
                        row_consumer=append_interface,
                    )
                if errorIndication:
                    raise RuntimeError(f"SNMP interface walk failed: {errorIndication}")
                if errorStatus:
                    raise RuntimeError(f"SNMP interface walk failed: {errorStatus}")

            except Exception as e:
                raise RuntimeError(f"Error during SNMP interface information collection: {str(e)}")

            return results

    async def probe(self):
        """最小只读 SNMP GET（sysName），用于 CredentialAttempt。"""
        from core.collection.contracts import AccessProbeResult, AccessProbeStatus

        oid = DefineOid(dotprefix=True)
        snmp_auth = self._get_snmp_auth()
        # access_probe：固定 10 秒超时、重试 1 次（与正式采集 timeout 解耦）
        async with shared_snmp_engine(snmp_auth, target=(self.host, self.snmp_port)) as engine:
            try:
                error_indication, error_status, _error_index, var_binds = await getCmd(
                    engine,
                    snmp_auth,
                    self._transport_target(timeout=10, retries=1),
                    ContextData(),
                    ObjectType(ObjectIdentity(oid.sysDescr.lstrip("."))),
                    ObjectType(ObjectIdentity(oid.sysObjectId.lstrip("."))),
                    ObjectType(ObjectIdentity(oid.sysContact.lstrip("."))),
                    ObjectType(ObjectIdentity(oid.sysName.lstrip("."))),
                    ObjectType(ObjectIdentity(oid.sysLocation.lstrip("."))),
                    lookupMib=False,
                )
            except Exception:  # noqa: BLE001 - 不把 SDK 异常正文写入结果
                return AccessProbeResult(
                    status=AccessProbeStatus.PROTOCOL_MISMATCH,
                    error_code="snmp_protocol_error",
                )
        if error_indication:
            indication = str(error_indication).lower()
            if "timeout" in indication or "no response" in indication:
                return AccessProbeResult(
                    status=AccessProbeStatus.NO_RESPONSE,
                    error_code="snmp_no_response",
                )
            if any(
                token in indication
                for token in (
                    "authorization",
                    "authentication",
                    "community",
                    "unknown user",
                    "unknownusername",
                    "wrong digest",
                    "wrongdigest",
                    "decryption error",
                    "decryptionerror",
                )
            ):
                return AccessProbeResult(
                    status=AccessProbeStatus.AUTH_FAILED,
                    error_code="snmp_authorization_failed",
                )
            return AccessProbeResult(
                status=AccessProbeStatus.PROTOCOL_MISMATCH,
                error_code="snmp_protocol_error",
            )
        if error_status:
            pretty_print = getattr(error_status, "prettyPrint", None)
            status_text = (pretty_print() if callable(pretty_print) else str(error_status)).lower()
            if any(
                token in status_text
                for token in (
                    "authorization",
                    "noaccess",
                    "not writable",
                    "notwritable",
                    "readonly",
                )
            ):
                return AccessProbeResult(
                    status=AccessProbeStatus.CAPABILITY_DENIED,
                    error_code="snmp_capability_denied",
                )
            return AccessProbeResult(
                status=AccessProbeStatus.PROTOCOL_MISMATCH,
                error_code="snmp_protocol_error",
            )
        if not var_binds:
            return AccessProbeResult(
                status=AccessProbeStatus.NO_RESPONSE,
                error_code="empty_snmp_response",
            )
        self._probed_system_var_binds = tuple(var_binds)
        return AccessProbeResult(status=AccessProbeStatus.READY)

    async def list_all_resources(self):
        """将设备与接口 SNMP 数据转换为标准格式。"""
        logger.debug(
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
            if should_log_plugin_exception(self.kwargs):
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
