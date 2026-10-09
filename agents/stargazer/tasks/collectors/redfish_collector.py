"""Targeted Redfish hardware-server monitor collector.

Follows Systems / Managers / Chassis Thermal+Power, then bounded Storage,
Storage.Drives, and Chassis NetworkAdapters. Does not crawl Sensors, logs,
or DIMMs. EthernetInterfaces and Chassis/Drives are fallback-only when the
standard Storage.Drives or NetworkAdapters walk returns nothing.
"""

from __future__ import annotations

import ipaddress
import json
import ssl
import time
from typing import Any
from urllib.parse import urlparse, urlsplit

import httpx
from core.logger import logger, safe_log_value
from tasks.collectors.base_collector import BaseCollector
from utils.convert import convert_to_prometheus

MONITOR_TYPE = "redfish"
RESOURCE_TYPE = "hardware_server"
HEALTH_CODES = {"ok": 1, "warning": 2, "non-critical": 2, "critical": 3}
POWER_STATE_CODES = {"on": 1, "off": 0}
LINK_UP_VALUES = frozenset({"linkup", "up", "connected"})
LINK_DOWN_VALUES = frozenset({"linkdown", "down", "disconnected", "nolink"})
FORBIDDEN_URI_PARTS = (
    "/sensors",
    "/logservices",
    "/logs/",
    "/memory",
    "/processors",
    "/ethernetinterfaces",
    "/telemetryservice",
)
MAX_RESPONSE_BYTES = 1024 * 1024
MAX_STORAGE_RESOURCES = 8
MAX_DRIVES = 32
MAX_NETWORK_ADAPTERS = 8
MAX_NETWORK_PORTS = 16
PSU_DELIVERING_MIN_WATTS = 20.0
# 部分 BMC（如 H3C HDM）仅提供 TLS_RSA_WITH_AES_256_GCM_SHA384；OpenSSL 3 默认 SECLEVEL 不含该套件。
_TLS_CIPHERS = ("DEFAULT:@SECLEVEL=0", "DEFAULT:@SECLEVEL=1", "DEFAULT")


def now_ms() -> int:
    return int(time.time() * 1000)


def gauge(value: Any) -> list[tuple[int, Any]]:
    return [(now_ms(), value)]


def dim_gauge(dims: list[tuple[str, str]], value: Any) -> dict:
    return {tuple(dims): gauge(value)}


def as_float(value: Any) -> float | None:
    if value is None or value == "":
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def as_text(value: Any) -> str:
    if value in (None, ""):
        return ""
    return str(value).strip()


def member_name(*candidates: Any) -> str:
    for candidate in candidates:
        text = as_text(candidate)
        if text:
            return text
    return ""


def _normalize_health_token(raw: Any) -> str:
    text = str(raw).strip().lower()
    return text.rstrip("!.,;:")


def health_code(status: Any, *, prefer_rollup: bool = False) -> int | None:
    if not isinstance(status, dict):
        return None
    primary = status.get("HealthRollup") if prefer_rollup else status.get("Health")
    fallback = status.get("Health") if prefer_rollup else status.get("HealthRollup")
    raw = primary if primary not in (None, "") else fallback
    if raw in (None, ""):
        return None
    return HEALTH_CODES.get(_normalize_health_token(raw), 0)


def power_state_code(value: Any) -> int | None:
    if value in (None, ""):
        return None
    return POWER_STATE_CODES.get(str(value).strip().lower(), 2)


def link_up_code(value: Any) -> int | None:
    if value in (None, ""):
        return None
    if isinstance(value, bool):
        return 1 if value else 0
    text = str(value).strip().lower()
    if text in LINK_UP_VALUES:
        return 1
    if text in LINK_DOWN_VALUES:
        return 0
    return None


def as_bool(value: Any, default: bool = True) -> bool:
    if value in (None, ""):
        return default
    if isinstance(value, bool):
        return value
    return str(value).strip().lower() not in {"0", "false", "no", "off"}


def _tls_verify(verify_tls: bool):
    """构造 httpx verify：保留校验证书开关，只放宽套件以完成握手。"""
    if verify_tls:
        ctx = ssl.create_default_context()
    else:
        ctx = ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
        ctx.check_hostname = False
        ctx.verify_mode = ssl.CERT_NONE
    for cipher in _TLS_CIPHERS:
        try:
            ctx.set_ciphers(cipher)
            break
        except ssl.SSLError:
            continue
    return ctx


def odata_id(node: Any) -> str:
    if isinstance(node, dict):
        raw = node.get("@odata.id")
        return str(raw) if isinstance(raw, str) else ""
    return str(node) if isinstance(node, str) else ""


def member_ids(payload: Any) -> list[str]:
    if not isinstance(payload, dict):
        return []
    members = payload.get("Members") or []
    ids = []
    for item in members:
        link = odata_id(item)
        if link:
            ids.append(link)
    return ids


def reading_units(value: Any, default: str = "RPM") -> str:
    if isinstance(value, list):
        value = value[0] if value else default
    text = str(value or default).strip()
    return text or default


def put_metric(current: dict[str, Any], name: str, value: Any, dims: list[tuple[str, str]] | None = None) -> None:
    if value is None:
        return
    if dims:
        current.setdefault(name, {}).update(dim_gauge(dims, value))
        return
    current[name] = gauge(value)


def resource_state(status: Any) -> str:
    if not isinstance(status, dict):
        return ""
    return str(status.get("State") or "").strip().lower()


def is_inlet_sensor(sensor: dict[str, Any], name: str) -> bool:
    haystacks = (name, as_text(sensor.get("PhysicalContext")))
    return any(token in text.lower() for text in haystacks for token in ("inlet", "intake"))


def port_speed_mbps(port: dict[str, Any]) -> float | None:
    mbps = as_float(port.get("CurrentLinkSpeedMbps"))
    if mbps is not None:
        return mbps
    gbps = as_float(port.get("CurrentSpeedGbps"))
    if gbps is not None:
        return gbps * 1000.0
    return as_float(port.get("SpeedMbps"))


class RedfishMonitorError(ValueError):
    pass


class RedfishCollector(BaseCollector):
    """Collect BMC health, thermal, power, storage/drive, and NIC metrics over Redfish."""

    def __init__(self, params: dict[str, Any], *, transport=None):
        super().__init__(params)
        raw_host = str(params.get("host") or params.get("ip") or "").strip()
        parsed = urlparse(raw_host if "://" in raw_host else f"https://{raw_host}")
        self.host = parsed.hostname or raw_host
        self.port = int(parsed.port or params.get("port") or 443)
        self.username = str(params.get("username") or params.get("user") or "")
        self.password = str(params.get("password") or "")
        self.verify_tls = as_bool(params.get("verify_tls"), True)
        try:
            self.timeout = float(params.get("timeout") or 30)
        except (TypeError, ValueError):
            self.timeout = 30.0
        self._transport = transport or params.get("_transport")
        self.session_uri = ""
        self.base_url = f"https://{self._url_host()}:{self.port}"

    def _url_host(self) -> str:
        try:
            address = ipaddress.ip_address(self.host)
        except ValueError:
            if not self.host or "/" in self.host:
                raise RedfishMonitorError("Redfish target host is invalid")
            return self.host
        return f"[{address}]" if address.version == 6 else str(address)

    def _client(self) -> httpx.AsyncClient:
        headers = {
            "Accept": "application/json",
            "Content-Type": "application/json",
            "OData-Version": "4.0",
        }
        return httpx.AsyncClient(
            auth=httpx.BasicAuth(self.username, self.password) if self.username or self.password else None,
            follow_redirects=False,
            headers=headers,
            limits=httpx.Limits(max_connections=2, max_keepalive_connections=1),
            timeout=httpx.Timeout(self.timeout, connect=min(5.0, self.timeout)),
            transport=self._transport,
            trust_env=False,
            verify=_tls_verify(self.verify_tls),
        )

    def _resource_url(self, resource_link: Any, *, allowed_parts: tuple[str, ...] = ()) -> str:
        raw_link = odata_id(resource_link)
        parsed = urlsplit(raw_link)
        path = parsed.path or ""
        lower = path.lower()
        decoded = path.split("/")
        is_service_path = path == "/redfish/v1" or path.startswith("/redfish/v1/")
        is_absolute = bool(parsed.scheme or parsed.netloc)
        extra_allowed = {str(part).lower() for part in allowed_parts}
        forbidden = tuple(part for part in FORBIDDEN_URI_PARTS if part not in extra_allowed)
        if (
            not is_service_path
            or ".." in decoded
            or parsed.fragment
            or (is_absolute and not self._is_same_origin(parsed))
            or any(part in lower for part in forbidden)
        ):
            raise RedfishMonitorError("Redfish resource link is not allowed")
        query = f"?{parsed.query}" if parsed.query else ""
        return f"{self.base_url}{path}{query}"

    def _is_same_origin(self, parsed) -> bool:
        if parsed.scheme.lower() != "https" or parsed.username or parsed.password:
            return False
        parsed_port = parsed.port if parsed.port is not None else 443
        if parsed_port != self.port:
            return False
        try:
            return ipaddress.ip_address(parsed.hostname or "") == ipaddress.ip_address(self.host)
        except (ValueError, TypeError):
            return str(parsed.hostname or "").lower() == str(self.host).lower()

    async def _get_json(
        self,
        client: httpx.AsyncClient,
        resource_link: Any,
        *,
        optional: bool = False,
        allowed_parts: tuple[str, ...] = (),
    ) -> dict[str, Any] | None:
        url = self._resource_url(resource_link, allowed_parts=allowed_parts)
        async with client.stream("GET", url) as response:
            if response.status_code in {401, 403}:
                raise RedfishMonitorError("Redfish authentication failed")
            if response.status_code == 404 and optional:
                return None
            if response.status_code >= 400:
                if optional:
                    return None
                raise RedfishMonitorError(f"Redfish resource returned HTTP {response.status_code}")
            body = bytearray()
            async for chunk in response.aiter_bytes():
                body.extend(chunk)
                if len(body) > MAX_RESPONSE_BYTES:
                    raise RedfishMonitorError("Redfish response exceeds size limit")
        try:
            payload = json.loads(body)
        except (TypeError, ValueError, UnicodeError) as exc:
            raise RedfishMonitorError("Redfish resource returned invalid JSON") from exc
        if not isinstance(payload, dict):
            raise RedfishMonitorError("Redfish resource returned invalid JSON")
        return payload

    async def _login(self, client: httpx.AsyncClient) -> None:
        url = f"{self.base_url}/redfish/v1/SessionService/Sessions"
        try:
            response = await client.post(url, json={"UserName": self.username, "Password": self.password})
        except httpx.HTTPError:
            return
        if response.status_code not in (200, 201):
            return
        token = response.headers.get("X-Auth-Token")
        if not token:
            try:
                body = response.json()
            except (ValueError, json.JSONDecodeError):
                body = None
            token = body.get("X-Auth-Token") if isinstance(body, dict) else None
        if token:
            client.headers["X-Auth-Token"] = token
            client.auth = None
        location = response.headers.get("Location")
        if location:
            try:
                self.session_uri = self._resource_url(location)
            except RedfishMonitorError:
                self.session_uri = ""

    async def _logout(self, client: httpx.AsyncClient) -> None:
        if not self.session_uri:
            return
        try:
            await client.delete(self.session_uri)
        except httpx.HTTPError:
            return

    async def _follow_collection(self, client: httpx.AsyncClient, link: Any) -> dict[str, Any] | None:
        collection = await self._get_json(client, link, optional=True)
        members = member_ids(collection)
        if not members:
            return None
        return await self._get_json(client, members[0], optional=True)

    async def _list_resources(
        self,
        client: httpx.AsyncClient,
        link: Any,
        *,
        limit: int,
        allowed_parts: tuple[str, ...] = (),
    ) -> list[dict[str, Any]]:
        if not link or limit <= 0:
            return []
        collection = await self._get_json(
            client,
            link,
            optional=True,
            allowed_parts=allowed_parts,
        )
        payloads: list[dict[str, Any]] = []
        for member in member_ids(collection)[:limit]:
            payload = await self._get_json(
                client,
                member,
                optional=True,
                allowed_parts=allowed_parts,
            )
            if isinstance(payload, dict):
                payloads.append(payload)
        return payloads

    async def _chassis_thermal_power(
        self, client: httpx.AsyncClient, chassis_link: Any
    ) -> tuple[dict | None, dict | None, str, list[dict[str, Any]]]:
        collection = await self._get_json(client, chassis_link, optional=True)
        thermal = None
        power = None
        network_link = ""
        chassis_payloads: list[dict[str, Any]] = []
        for member in member_ids(collection):
            chassis = await self._get_json(client, member, optional=True)
            if not isinstance(chassis, dict):
                continue
            if not odata_id(chassis):
                chassis = {**chassis, "@odata.id": member}
            chassis_payloads.append(chassis)
            if thermal is None:
                thermal_link = odata_id(chassis.get("Thermal")) or f"{urlsplit(self._resource_url(member)).path.rstrip('/')}/Thermal"
                thermal = await self._get_json(client, thermal_link, optional=True)
                if isinstance(thermal, dict):
                    network_link = odata_id(chassis.get("NetworkAdapters"))
            if power is None:
                power_link = odata_id(chassis.get("Power")) or f"{urlsplit(self._resource_url(member)).path.rstrip('/')}/Power"
                power = await self._get_json(client, power_link, optional=True)
            if thermal is not None and power is not None:
                break
        return thermal, power, network_link, chassis_payloads

    async def _adapter_ports(self, client: httpx.AsyncClient, adapter: dict[str, Any], remaining: int) -> list[dict[str, Any]]:
        if remaining <= 0:
            return []
        embedded: list[str] = []
        for controller in adapter.get("Controllers") or []:
            if not isinstance(controller, dict):
                continue
            links = controller.get("Links") if isinstance(controller.get("Links"), dict) else {}
            for item in links.get("NetworkPorts") or []:
                link = odata_id(item)
                if link:
                    embedded.append(link)
        if embedded:
            ports: list[dict[str, Any]] = []
            for link in embedded[:remaining]:
                payload = await self._get_json(client, link, optional=True)
                if isinstance(payload, dict):
                    ports.append(payload)
            return ports
        collection_link = odata_id(adapter.get("Ports")) or odata_id(adapter.get("NetworkPorts"))
        return await self._list_resources(client, collection_link, limit=remaining)

    async def _list_drives(self, client: httpx.AsyncClient, storages: list[dict[str, Any]]) -> list[dict[str, Any]]:
        drives: list[dict[str, Any]] = []
        for storage in storages:
            if len(drives) >= MAX_DRIVES:
                break
            remaining = MAX_DRIVES - len(drives)
            for item in (storage.get("Drives") or [])[:remaining]:
                link = odata_id(item)
                if not link:
                    continue
                payload = await self._get_json(client, link, optional=True)
                if isinstance(payload, dict):
                    drives.append(payload)
        return drives

    async def _list_chassis_drives(
        self,
        client: httpx.AsyncClient,
        chassis_list: list[dict[str, Any]],
    ) -> list[dict[str, Any]]:
        """Fallback: Chassis.Drives / Links.Drives / {chassis}/Drives collection."""
        drives: list[dict[str, Any]] = []
        for chassis in chassis_list:
            if len(drives) >= MAX_DRIVES:
                break
            remaining = MAX_DRIVES - len(drives)
            drives_node = chassis.get("Drives")
            if isinstance(drives_node, dict) and odata_id(drives_node):
                drives.extend(
                    await self._list_resources(
                        client,
                        odata_id(drives_node),
                        limit=remaining,
                    )
                )
                continue
            drive_refs: list[Any] = []
            if isinstance(drives_node, list):
                drive_refs.extend(drives_node)
            links = chassis.get("Links") if isinstance(chassis.get("Links"), dict) else {}
            drive_refs.extend(links.get("Drives") or [])
            if drive_refs:
                for item in drive_refs[:remaining]:
                    link = odata_id(item)
                    if not link:
                        continue
                    payload = await self._get_json(client, link, optional=True)
                    if isinstance(payload, dict):
                        drives.append(payload)
                continue
            chassis_id = odata_id(chassis)
            if not chassis_id:
                continue
            drives.extend(
                await self._list_resources(
                    client,
                    f"{chassis_id.rstrip('/')}/Drives",
                    limit=remaining,
                )
            )
        return drives

    async def _resolve_drives(
        self,
        client: httpx.AsyncClient,
        storages: list[dict[str, Any]],
        chassis_list: list[dict[str, Any]],
    ) -> list[dict[str, Any]]:
        drives = await self._list_drives(client, storages)
        if drives:
            return drives
        return await self._list_chassis_drives(client, chassis_list)

    async def _resolve_nics(
        self,
        client: httpx.AsyncClient,
        network_link: str,
        system: dict[str, Any],
    ) -> list[tuple[dict[str, Any], list[dict[str, Any]]]]:
        adapters = await self._list_resources(
            client,
            network_link,
            limit=MAX_NETWORK_ADAPTERS,
        )
        if adapters:
            nic_rows: list[tuple[dict[str, Any], list[dict[str, Any]]]] = []
            remaining_ports = MAX_NETWORK_PORTS
            for adapter in adapters:
                ports = await self._adapter_ports(client, adapter, remaining_ports)
                remaining_ports -= len(ports)
                nic_rows.append((adapter, ports))
            if self._nic_rows_usable(nic_rows):
                return nic_rows
        return await self._ethernet_interface_fallback(client, system)

    @staticmethod
    def _nic_rows_usable(nic_rows: list[tuple[dict[str, Any], list[dict[str, Any]]]]) -> bool:
        for adapter, ports in nic_rows:
            if health_code(adapter.get("Status")) is not None:
                return True
            if ports:
                return True
        return False

    async def _ethernet_interface_fallback(
        self,
        client: httpx.AsyncClient,
        system: dict[str, Any],
    ) -> list[tuple[dict[str, Any], list[dict[str, Any]]]]:
        link = odata_id(system.get("EthernetInterfaces"))
        if not link:
            return []
        ifaces = await self._list_resources(
            client,
            link,
            limit=MAX_NETWORK_PORTS,
            allowed_parts=("/ethernetinterfaces",),
        )
        rows: list[tuple[dict[str, Any], list[dict[str, Any]]]] = []
        for iface in ifaces:
            if not member_name(iface.get("Id"), iface.get("Name")):
                continue
            rows.append((iface, [iface]))
        return rows

    def _emit_system_metrics(self, current: dict[str, Any], system: dict[str, Any], manager: dict[str, Any] | None) -> None:
        put_metric(current, "redfish_system_health", health_code(system.get("Status")))
        put_metric(current, "redfish_system_power_state", power_state_code(system.get("PowerState")))
        processor = system.get("ProcessorSummary") if isinstance(system.get("ProcessorSummary"), dict) else {}
        memory = system.get("MemorySummary") if isinstance(system.get("MemorySummary"), dict) else {}
        put_metric(current, "redfish_processor_health_rollup", health_code(processor.get("Status")))
        put_metric(current, "redfish_memory_health_rollup", health_code(memory.get("Status")))
        firmware_dims: list[tuple[str, str]] = []
        bios_version = as_text(system.get("BiosVersion"))
        if bios_version:
            firmware_dims.append(("bios_version", bios_version))
        if isinstance(manager, dict):
            put_metric(current, "redfish_manager_health", health_code(manager.get("Status")))
            bmc_firmware = as_text(manager.get("FirmwareVersion"))
            if bmc_firmware:
                firmware_dims.append(("bmc_firmware", bmc_firmware))
        if firmware_dims:
            put_metric(current, "redfish_firmware_info", 1, firmware_dims)

    def _emit_thermal_metrics(self, current: dict[str, Any], thermal: dict | None) -> None:
        if not isinstance(thermal, dict):
            return
        for sensor in thermal.get("Temperatures") or []:
            if not isinstance(sensor, dict):
                continue
            name = member_name(sensor.get("Name"), sensor.get("PhysicalContext"))
            if not name:
                continue
            dims = [("name", name)]
            reading = as_float(sensor.get("ReadingCelsius"))
            upper = as_float(sensor.get("UpperThresholdCritical"))
            put_metric(current, "redfish_temperature_celsius", reading, dims)
            put_metric(current, "redfish_temperature_upper_critical_celsius", upper, dims)
            if is_inlet_sensor(sensor, name) and reading is not None:
                previous = current.get("redfish_inlet_temperature_celsius")
                previous_value = previous[0][1] if isinstance(previous, list) else None
                if previous_value is None or reading > previous_value:
                    current["redfish_inlet_temperature_celsius"] = gauge(reading)
                    if upper is not None:
                        current["redfish_inlet_temperature_upper_critical_celsius"] = gauge(upper)
                    else:
                        current.pop("redfish_inlet_temperature_upper_critical_celsius", None)
        for fan in thermal.get("Fans") or []:
            if not isinstance(fan, dict):
                continue
            name = member_name(fan.get("Name"), fan.get("FanName"), fan.get("Id"), fan.get("MemberId"))
            if not name:
                continue
            dims = [("name", name)]
            reading = as_float(fan.get("Reading"))
            if reading is not None:
                put_metric(
                    current,
                    "redfish_fan_speed",
                    reading,
                    [("name", name), ("unit", reading_units(fan.get("ReadingUnits")))],
                )
            put_metric(current, "redfish_fan_health", health_code(fan.get("Status")), dims)

    def _emit_power_metrics(self, current: dict[str, Any], power: dict | None) -> None:
        if not isinstance(power, dict):
            return
        over_limit = 0
        delivering = 0
        psu_count = 0
        for control in power.get("PowerControl") or []:
            if not isinstance(control, dict):
                continue
            consumed = as_float(control.get("PowerConsumedWatts"))
            limit_node = control.get("PowerLimit") if isinstance(control.get("PowerLimit"), dict) else {}
            limit = as_float(limit_node.get("LimitInWatts"))
            name = member_name(control.get("Name"), control.get("MemberId"))
            if consumed is not None:
                if name:
                    put_metric(current, "redfish_power_consumed_watts", consumed, [("name", name)])
                else:
                    put_metric(current, "redfish_power_consumed_watts", consumed)
            if limit is not None:
                put_metric(current, "redfish_power_limit_watts", limit, [("name", name)] if name else None)
                if consumed is not None and consumed > limit:
                    over_limit = 1
        if current.get("redfish_power_limit_watts") is not None:
            put_metric(current, "redfish_power_over_limit", over_limit)
        for supply in power.get("PowerSupplies") or []:
            if not isinstance(supply, dict):
                continue
            name = member_name(supply.get("Name"), supply.get("Id"), supply.get("MemberId"))
            if not name:
                continue
            dims = [("name", name)]
            input_watts = as_float(supply.get("PowerInputWatts"))
            output_watts = as_float(supply.get("PowerOutputWatts"))
            delivering_watts = input_watts if input_watts is not None else output_watts
            is_delivering = 1 if delivering_watts is not None and delivering_watts > PSU_DELIVERING_MIN_WATTS else 0
            psu_count += 1
            delivering += is_delivering
            put_metric(current, "redfish_psu_health", health_code(supply.get("Status")), dims)
            put_metric(current, "redfish_psu_input_watts", input_watts, dims)
            put_metric(current, "redfish_psu_output_watts", output_watts, dims)
            put_metric(current, "redfish_psu_capacity_watts", as_float(supply.get("PowerCapacityWatts")), dims)
            put_metric(current, "redfish_psu_input_voltage", as_float(supply.get("LineInputVoltage")), dims)
            put_metric(current, "redfish_psu_delivering", is_delivering, dims)
        if psu_count:
            put_metric(current, "redfish_psu_redundant", 1 if delivering >= 2 else 0)
        for voltage in power.get("Voltages") or []:
            if not isinstance(voltage, dict):
                continue
            name = member_name(voltage.get("Name"), voltage.get("Id"), voltage.get("MemberId"))
            if not name:
                continue
            put_metric(current, "redfish_voltage_volts", as_float(voltage.get("ReadingVolts")), [("name", name)])

    def _emit_storage_metrics(self, current: dict[str, Any], storages: list[dict[str, Any]]) -> None:
        for storage in storages:
            storage_id = member_name(storage.get("Id"), storage.get("Name"))
            if not storage_id:
                continue
            put_metric(
                current,
                "redfish_storage_health",
                health_code(storage.get("Status"), prefer_rollup=True),
                [("id", storage_id)],
            )
            for controller in storage.get("StorageControllers") or []:
                if not isinstance(controller, dict):
                    continue
                controller_id = member_name(controller.get("MemberId"), controller.get("Id"), controller.get("Name"))
                if not controller_id:
                    continue
                put_metric(
                    current,
                    "redfish_storage_controller_health",
                    health_code(controller.get("Status")),
                    [("id", controller_id), ("storage_id", storage_id)],
                )

    def _emit_drive_metrics(self, current: dict[str, Any], drives: list[dict[str, Any]]) -> None:
        present = 0
        for drive in drives:
            if resource_state(drive.get("Status")) == "absent":
                continue
            name = member_name(drive.get("Name"), drive.get("Id"))
            if not name:
                continue
            present += 1
            dims = [("name", name)]
            media_type = as_text(drive.get("MediaType"))
            protocol = as_text(drive.get("Protocol"))
            if media_type:
                dims.append(("media_type", media_type))
            if protocol:
                dims.append(("protocol", protocol))
            put_metric(current, "redfish_drive_health", health_code(drive.get("Status")), dims)
            put_metric(current, "redfish_drive_life_percent", as_float(drive.get("PredictedMediaLifeLeftPercent")), dims)
        put_metric(current, "redfish_drive_present_count", present)

    def _emit_nic_metrics(
        self,
        current: dict[str, Any],
        nic_rows: list[tuple[dict[str, Any], list[dict[str, Any]]]],
    ) -> None:
        for adapter, ports in nic_rows:
            adapter_id = member_name(adapter.get("Id"), adapter.get("Name"))
            if not adapter_id:
                continue
            put_metric(current, "redfish_nic_health", health_code(adapter.get("Status")), [("id", adapter_id)])
            for port in ports:
                port_id = member_name(port.get("Id"), port.get("Name"), port.get("MemberId"))
                if not port_id:
                    continue
                dims = [("adapter_id", adapter_id), ("id", port_id)]
                put_metric(current, "redfish_nic_port_health", health_code(port.get("Status")), dims)
                put_metric(current, "redfish_nic_port_link_up", link_up_code(port.get("LinkStatus")), dims)
                put_metric(current, "redfish_nic_port_speed_mbps", port_speed_mbps(port), dims)

    def _emit_metrics(
        self,
        system: dict[str, Any],
        manager: dict[str, Any] | None,
        thermal: dict | None,
        power: dict | None,
        storages: list[dict[str, Any]],
        nic_rows: list[tuple[dict[str, Any], list[dict[str, Any]]]],
        drives: list[dict[str, Any]] | None = None,
    ) -> dict:
        resource_id = str(system.get("Id") or odata_id(system) or self.host)
        current: dict[str, Any] = {}
        self._emit_system_metrics(current, system, manager)
        self._emit_thermal_metrics(current, thermal)
        self._emit_power_metrics(current, power)
        self._emit_storage_metrics(current, storages)
        self._emit_drive_metrics(current, drives or [])
        self._emit_nic_metrics(current, nic_rows)
        if not current:
            raise RedfishMonitorError("Redfish scrape produced no metrics")
        return {(resource_id, RESOURCE_TYPE): current}

    async def collect(self) -> str:
        if not self.host:
            raise RedfishMonitorError("missing required host")
        logger.info("event=redfish_collect_start monitor_type=%s host=%s", MONITOR_TYPE, safe_log_value(self.host))
        client = self._client()
        try:
            await self._login(client)
            root = await self._get_json(client, "/redfish/v1")
            if not root:
                raise RedfishMonitorError("Redfish service root is empty")
            system = await self._follow_collection(client, odata_id(root.get("Systems")) or "/redfish/v1/Systems")
            if not isinstance(system, dict):
                raise RedfishMonitorError("Redfish Systems collection is empty")
            manager = await self._follow_collection(client, odata_id(root.get("Managers")) or "/redfish/v1/Managers")
            thermal, power, network_link, chassis_list = await self._chassis_thermal_power(
                client, odata_id(root.get("Chassis")) or "/redfish/v1/Chassis"
            )
            storage_link = odata_id(system.get("Storage")) or odata_id(system.get("Storages"))
            storages = await self._list_resources(client, storage_link, limit=MAX_STORAGE_RESOURCES)
            if not storages:
                alt = odata_id(system.get("Storages"))
                if alt and alt != storage_link:
                    storages = await self._list_resources(client, alt, limit=MAX_STORAGE_RESOURCES)
            drives = await self._resolve_drives(client, storages, chassis_list)
            nic_rows = await self._resolve_nics(client, network_link, system)
            metric_dict = self._emit_metrics(system, manager, thermal, power, storages, nic_rows, drives)
            output = "\n".join(convert_to_prometheus(metric_dict)) + "\n"
            logger.info(
                "event=redfish_collect_success monitor_type=%s system_id=%s",
                MONITOR_TYPE,
                safe_log_value(str(system.get("Id") or "")),
            )
            return output
        finally:
            await self._logout(client)
            await client.aclose()
