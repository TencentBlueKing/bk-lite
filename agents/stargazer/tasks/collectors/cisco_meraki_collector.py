"""Cisco Meraki Dashboard API v1 collector: one organization scrape for all MVP families."""

from __future__ import annotations

from typing import Any

from core.collection.contracts import AccessProbeResult
from core.logger import logger, safe_log_value
from tasks.collectors.base_collector import BaseCollector
from tasks.collectors.cisco_meraki_dashboard import (
    APPLIANCE_INVENTORY_RESOURCE,
    APPLIANCE_RESOURCE,
    DEVICE_INVENTORY_RESOURCE,
    DEVICE_RESOURCE,
    MONITOR_TYPE,
    NETWORK_RESOURCE,
    ORG_RESOURCE,
    SWITCH_INVENTORY_RESOURCE,
    SWITCH_RESOURCE,
    WIRELESS_INVENTORY_RESOURCE,
    WIRELESS_RESOURCE,
    MerakiDashboardClient,
    as_float,
    as_int,
    clamp_int,
    dim_gauge,
    failed_collect_output,
    family_connect_failed,
    gauge,
    optional_list,
    probe_organization,
    require_list,
    require_object,
    require_organization,
    required_params,
    status_code,
)
from utils.convert import convert_to_prometheus

AVAILABILITY_STATUS = {"offline": 0, "online": 1, "alerting": 2, "dormant": 3}
REACHABILITY = {"reachable": 1, "unreachable": 0}
_LINK_UP_VALUES = frozenset({"up", "connected", "link", "linkup", "true", "1"})
_LINK_DOWN_VALUES = frozenset({"down", "disconnected", "nolink", "false", "0"})

FAMILY_DEVICE = "device"
FAMILY_WIRELESS = "wireless"
FAMILY_SWITCH = "switch"
FAMILY_APPLIANCE = "appliance"


def _merge_metrics(target: dict[tuple[str, str], dict[str, Any]], extra: dict[tuple[str, str], dict[str, Any]]) -> None:
    for key, metrics in extra.items():
        bucket = target.setdefault(key, {})
        for name, value in metrics.items():
            existing = bucket.get(name)
            if isinstance(existing, dict) and isinstance(value, dict):
                existing.update(value)
            else:
                bucket[name] = value


def _ethernet_link_up(port: dict[str, Any]) -> int:
    for key in ("status", "linkStatus", "link_status", "linkState", "connected"):
        raw = port.get(key)
        if isinstance(raw, bool):
            return 1 if raw else 0
        if raw in (None, ""):
            continue
        text = str(raw).strip().lower()
        if text in _LINK_UP_VALUES:
            return 1
        if text in _LINK_DOWN_VALUES:
            return 0
    negotiation = port.get("linkNegotiation") if isinstance(port.get("linkNegotiation"), dict) else {}
    speed = as_float(negotiation.get("speed"))
    duplex = str(negotiation.get("duplex") or "").strip().lower()
    if speed is not None and speed > 0:
        return 1
    if duplex in {"full", "half"}:
        return 1
    return 0


def _packet_loss_serial(item: dict[str, Any]) -> str:
    device = item.get("device") if isinstance(item.get("device"), dict) else {}
    return str(device.get("serial") or item.get("serial") or "").strip()


def _serial_by_network(statuses: list) -> dict[str, str]:
    mapping: dict[str, str] = {}
    for row in statuses:
        if not isinstance(row, dict):
            continue
        serial = str(row.get("deviceSerial") or "").strip()
        network_id = str(row.get("networkId") or "").strip()
        if network_id and serial:
            mapping[network_id] = serial
    return mapping


def _appliance_resource_id(row: dict[str, Any], serial_by_network: dict[str, str]) -> str:
    serial = str(row.get("deviceSerial") or row.get("serial") or "").strip()
    if serial:
        return serial
    network_id = str(row.get("networkId") or "").strip()
    return serial_by_network.get(network_id, "")


def _emit_vpn_peer_summaries(current: dict, peer: dict[str, Any], peer_id: str) -> None:
    latency_rows = peer.get("latencySummaries") if isinstance(peer.get("latencySummaries"), list) else []
    loss_rows = peer.get("lossPercentageSummaries") if isinstance(peer.get("lossPercentageSummaries"), list) else []
    for latency in latency_rows:
        if not isinstance(latency, dict):
            continue
        avg_latency = as_float(latency.get("avgLatencyMs"))
        if avg_latency is None:
            continue
        dims = [
            ("peer_network_id", peer_id),
            ("sender_uplink", str(latency.get("senderUplink") or "")),
            ("receiver_uplink", str(latency.get("receiverUplink") or "")),
        ]
        current.setdefault("meraki_appliance_vpn_avg_latency_ms", {}).update(dim_gauge(dims, avg_latency))
    for loss in loss_rows:
        if not isinstance(loss, dict):
            continue
        avg_loss = as_float(loss.get("avgLossPercentage"))
        if avg_loss is None:
            continue
        dims = [
            ("peer_network_id", peer_id),
            ("sender_uplink", str(loss.get("senderUplink") or "")),
            ("receiver_uplink", str(loss.get("receiverUplink") or "")),
        ]
        current.setdefault("meraki_appliance_vpn_avg_loss_percent", {}).update(dim_gauge(dims, avg_loss))


async def collect_organization(client: MerakiDashboardClient, organization_id: str) -> tuple[dict, int]:
    organization = await require_organization(client, organization_id)
    networks = await require_list(client, f"/organizations/{organization_id}/networks", {"perPage": 1000})
    api_enabled = 1 if ((organization.get("api") or {}).get("enabled") is True) else 0
    metric_dict: dict[tuple[str, str], dict[str, Any]] = {
        (organization_id, ORG_RESOURCE): {
            "meraki_org_connect_status": gauge(1),
            "meraki_org_api_enabled": gauge(api_enabled),
            "meraki_org_network_count": gauge(len(networks)),
        }
    }
    for network in networks:
        if not isinstance(network, dict):
            continue
        network_id = str(network.get("id") or "").strip()
        if not network_id:
            continue
        product_types = ",".join(str(item) for item in (network.get("productTypes") or []) if item)
        metric_dict[(network_id, NETWORK_RESOURCE)] = {
            "meraki_network_present": dim_gauge(
                [
                    ("network_name", str(network.get("name") or "")),
                    ("product_types", product_types),
                ],
                1,
            )
        }
    return metric_dict, len(networks)


async def collect_devices(client: MerakiDashboardClient, organization_id: str, timespan: int) -> tuple[dict, int]:
    uplink_timespan = clamp_int(timespan, 1, 300, 300)
    devices = await require_list(client, f"/organizations/{organization_id}/devices", {"perPage": 1000})
    availabilities = await require_list(
        client,
        f"/organizations/{organization_id}/devices/availabilities",
        {"perPage": 1000},
    )
    uplinks = await optional_list(
        client,
        f"/organizations/{organization_id}/devices/uplinksLossAndLatency",
        {"timespan": uplink_timespan},
    )
    availability_by_serial = {str(item.get("serial") or ""): item for item in availabilities if isinstance(item, dict) and item.get("serial")}
    online_count = sum(1 for item in availabilities if isinstance(item, dict) and str(item.get("status") or "").lower() == "online")
    metric_dict: dict[tuple[str, str], dict[str, Any]] = {
        (organization_id, DEVICE_INVENTORY_RESOURCE): {
            "meraki_device_connect_status": gauge(1),
            "meraki_device_inventory_count": gauge(len(devices)),
            "meraki_device_online_count": gauge(online_count),
        }
    }
    for device in devices:
        if not isinstance(device, dict):
            continue
        serial = str(device.get("serial") or "").strip()
        if not serial:
            continue
        availability = availability_by_serial.get(serial) or {}
        status_key = str(availability.get("status") or "").strip().lower()
        if status_key not in AVAILABILITY_STATUS:
            continue
        lan_ip = str(device.get("lanIp") or "").strip()
        dims = [
            ("serial", serial),
            ("model", str(device.get("model") or "")),
            ("product_type", str(device.get("productType") or "")),
        ]
        if lan_ip:
            dims.append(("resource_ip", lan_ip))
        metric_dict[(serial, DEVICE_RESOURCE)] = {"meraki_device_availability_status": dim_gauge(dims, AVAILABILITY_STATUS[status_key])}
    for row in uplinks:
        if not isinstance(row, dict):
            continue
        serial = str(row.get("serial") or "").strip()
        if not serial:
            continue
        series = row.get("timeSeries") if isinstance(row.get("timeSeries"), list) else []
        latest = next((item for item in reversed(series) if isinstance(item, dict)), None)
        if latest is None:
            continue
        latency = as_float(latest.get("latencyMs"))
        loss = as_float(latest.get("lossPercent"))
        current = metric_dict.setdefault((serial, DEVICE_RESOURCE), {})
        uplink_dims = [
            ("uplink", str(row.get("uplink") or "")),
            ("ip", str(row.get("ip") or "")),
        ]
        if latency is not None:
            current.setdefault("meraki_device_uplink_latency_ms", {}).update(dim_gauge(uplink_dims, latency))
        if loss is not None:
            current.setdefault("meraki_device_uplink_loss_percent", {}).update(dim_gauge(uplink_dims, loss))
    return metric_dict, len(devices)


async def collect_wireless(client: MerakiDashboardClient, organization_id: str, timespan: int) -> tuple[dict, int]:
    loss_timespan = clamp_int(timespan, 300, 7776000, 86400)
    ethernet = await require_list(
        client,
        f"/organizations/{organization_id}/wireless/devices/ethernet/statuses",
        {"perPage": 1000},
    )
    packet_loss = await require_list(
        client,
        f"/organizations/{organization_id}/wireless/devices/packetLoss/byDevice",
        {"perPage": 1000, "timespan": loss_timespan},
    )
    serials: set[str] = set()
    metric_dict: dict[tuple[str, str], dict[str, Any]] = {}
    for item in ethernet:
        if not isinstance(item, dict):
            continue
        serial = str(item.get("serial") or "").strip()
        if not serial:
            continue
        serials.add(serial)
        current = metric_dict.setdefault((serial, WIRELESS_RESOURCE), {})
        for port in item.get("ports") or []:
            if not isinstance(port, dict):
                continue
            port_name = str(port.get("name") or "").strip()
            if not port_name:
                continue
            negotiation = port.get("linkNegotiation") if isinstance(port.get("linkNegotiation"), dict) else {}
            speed = as_float(negotiation.get("speed"))
            link_up = _ethernet_link_up(port)
            dims = [("port", port_name)]
            if speed is not None:
                current.setdefault("meraki_wireless_ap_ethernet_speed_mbps", {}).update(dim_gauge(dims, speed))
            current.setdefault("meraki_wireless_ap_ethernet_link_up", {}).update(dim_gauge(dims, link_up))
    for item in packet_loss:
        if not isinstance(item, dict):
            continue
        serial = _packet_loss_serial(item)
        if not serial:
            continue
        serials.add(serial)
        current = metric_dict.setdefault((serial, WIRELESS_RESOURCE), {})
        upstream = item.get("upstream") if isinstance(item.get("upstream"), dict) else {}
        downstream = item.get("downstream") if isinstance(item.get("downstream"), dict) else {}
        up_loss = as_float(upstream.get("lossPercentage"))
        down_loss = as_float(downstream.get("lossPercentage"))
        if up_loss is not None:
            current["meraki_wireless_ap_upstream_loss_percent"] = gauge(up_loss)
        if down_loss is not None:
            current["meraki_wireless_ap_downstream_loss_percent"] = gauge(down_loss)
    metric_dict[(organization_id, WIRELESS_INVENTORY_RESOURCE)] = {
        "meraki_wireless_connect_status": gauge(1),
        "meraki_wireless_ap_count": gauge(len(serials)),
    }
    return metric_dict, len(serials)


async def collect_switch(client: MerakiDashboardClient, organization_id: str, timespan: int) -> tuple[dict, int]:
    overview_timespan = clamp_int(timespan, 43200, 16070400, 86400)
    power_timespan = clamp_int(timespan, 1, 16070400, 86400)
    overview = await require_object(
        client,
        f"/organizations/{organization_id}/switch/ports/overview",
        {"timespan": overview_timespan},
    )
    by_switch = await require_list(
        client,
        f"/organizations/{organization_id}/switch/ports/bySwitch",
        {"perPage": 50},
    )
    power_history = await optional_list(
        client,
        f"/organizations/{organization_id}/summary/switch/power/history",
        {"timespan": power_timespan},
    )
    by_status = (overview.get("counts") or {}).get("byStatus") or {}
    active_total = as_int((by_status.get("active") or {}).get("total"))
    inactive_total = as_int((by_status.get("inactive") or {}).get("total"))
    latest_draw = 0.0
    latest_ts = ""
    for row in power_history:
        if not isinstance(row, dict):
            continue
        ts = str(row.get("ts") or "")
        if latest_ts and ts < latest_ts:
            continue
        draw = as_float(row.get("draw"))
        if draw is None:
            continue
        latest_ts = ts
        latest_draw = draw
    metric_dict: dict[tuple[str, str], dict[str, Any]] = {
        (organization_id, SWITCH_INVENTORY_RESOURCE): {
            "meraki_switch_connect_status": gauge(1),
            "meraki_switch_port_active_count": gauge(active_total),
            "meraki_switch_port_inactive_count": gauge(inactive_total),
            "meraki_switch_power_draw_w": gauge(latest_draw),
        }
    }
    for switch in by_switch:
        if not isinstance(switch, dict):
            continue
        serial = str(switch.get("serial") or "").strip()
        if not serial:
            continue
        current = metric_dict.setdefault((serial, SWITCH_RESOURCE), {})
        for port in switch.get("ports") or []:
            if not isinstance(port, dict):
                continue
            port_id = str(port.get("portId") or "").strip()
            if not port_id:
                continue
            dims = [("port_id", port_id)]
            enabled = 1 if port.get("enabled") is True else 0
            poe_enabled = 1 if port.get("poeEnabled") is True else 0
            current.setdefault("meraki_switch_port_enabled", {}).update(dim_gauge(dims, enabled))
            current.setdefault("meraki_switch_port_poe_enabled", {}).update(dim_gauge(dims, poe_enabled))
    return metric_dict, len(by_switch)


async def collect_appliance(client: MerakiDashboardClient, organization_id: str, timespan: int) -> tuple[dict, int]:
    stats_timespan = clamp_int(timespan, 1, 2678400, 86400)
    utilization_timespan = clamp_int(timespan, 1500, 16070400, 86400)
    statuses = await require_list(
        client,
        f"/organizations/{organization_id}/appliance/vpn/statuses",
        {"perPage": 300},
    )
    stats = await optional_list(
        client,
        f"/organizations/{organization_id}/appliance/vpn/stats",
        {"perPage": 300, "timespan": stats_timespan},
    )
    utilization = await optional_list(
        client,
        f"/organizations/{organization_id}/summary/top/appliances/byUtilization",
        {"timespan": utilization_timespan},
    )
    metric_dict: dict[tuple[str, str], dict[str, Any]] = {
        (organization_id, APPLIANCE_INVENTORY_RESOURCE): {
            "meraki_appliance_connect_status": gauge(1),
            "meraki_appliance_vpn_network_count": gauge(len(statuses)),
        }
    }
    serial_by_network = _serial_by_network(statuses)
    for row in statuses:
        if not isinstance(row, dict):
            continue
        resource_id = _appliance_resource_id(row, serial_by_network)
        if not resource_id:
            continue
        current = metric_dict.setdefault((resource_id, APPLIANCE_RESOURCE), {})
        for peer in row.get("merakiVpnPeers") or []:
            if not isinstance(peer, dict):
                continue
            peer_id = str(peer.get("networkId") or "").strip()
            if not peer_id:
                continue
            dims = [("peer_network_id", peer_id)]
            reachable = status_code(peer.get("reachability"), REACHABILITY, 0)
            current.setdefault("meraki_appliance_vpn_peer_reachable", {}).update(dim_gauge(dims, reachable))
    for row in stats:
        if not isinstance(row, dict):
            continue
        resource_id = _appliance_resource_id(row, serial_by_network)
        if not resource_id:
            continue
        current = metric_dict.setdefault((resource_id, APPLIANCE_RESOURCE), {})
        for peer in row.get("merakiVpnPeers") or []:
            if not isinstance(peer, dict):
                continue
            peer_id = str(peer.get("networkId") or "").strip()
            if not peer_id:
                continue
            _emit_vpn_peer_summaries(current, peer, peer_id)
    for row in utilization:
        if not isinstance(row, dict):
            continue
        resource_id = str(row.get("serial") or "").strip()
        if not resource_id:
            continue
        utilization_obj = row.get("utilization") if isinstance(row.get("utilization"), dict) else {}
        average = utilization_obj.get("average") if isinstance(utilization_obj.get("average"), dict) else {}
        percent = as_float(average.get("percentage"))
        if percent is None:
            continue
        current = metric_dict.setdefault((resource_id, APPLIANCE_RESOURCE), {})
        current["meraki_appliance_utilization_percent"] = gauge(percent)
    return metric_dict, len(statuses)


class CiscoMerakiCollector(BaseCollector):
    """Collect organization, device, wireless AP, switch, and MX families with one Dashboard credential."""

    async def probe(self) -> AccessProbeResult:
        return await probe_organization(self)

    async def collect(self) -> str:
        try:
            params = required_params(self)
        except ValueError as error:
            organization_id = str(self.params.get("organization_id") or "").strip() or "unknown"
            return failed_collect_output(organization_id, failed_stage="params", error=error)
        organization_id = params["organization_id"]
        timespan = params["timespan"]
        uplink_override = self.params.get("uplink_timespan")
        if uplink_override not in (None, ""):
            try:
                device_timespan = int(uplink_override)
            except (TypeError, ValueError):
                device_timespan = timespan
        else:
            device_timespan = timespan
        logger.info(
            "event=meraki_collect_start monitor_type=%s organization_id=%s",
            MONITOR_TYPE,
            safe_log_value(organization_id),
        )
        failed_families: list[str] = []
        counts = {"network": 0, "device": 0, "ap": 0, "switch": 0, "vpn_network": 0}
        try:
            async with MerakiDashboardClient(
                base_url=params["base_url"],
                api_key=params["api_key"],
                timeout=params["timeout"],
            ) as client:
                try:
                    metric_dict, counts["network"] = await collect_organization(client, organization_id)
                except Exception as error:  # noqa: BLE001 - 组织失败导出全部 connect_status=0
                    return failed_collect_output(organization_id, failed_stage="organization", error=error)
                family_jobs = (
                    (
                        FAMILY_DEVICE,
                        DEVICE_INVENTORY_RESOURCE,
                        "meraki_device_connect_status",
                        collect_devices,
                        device_timespan,
                        "device",
                    ),
                    (
                        FAMILY_WIRELESS,
                        WIRELESS_INVENTORY_RESOURCE,
                        "meraki_wireless_connect_status",
                        collect_wireless,
                        timespan,
                        "ap",
                    ),
                    (
                        FAMILY_SWITCH,
                        SWITCH_INVENTORY_RESOURCE,
                        "meraki_switch_connect_status",
                        collect_switch,
                        timespan,
                        "switch",
                    ),
                    (
                        FAMILY_APPLIANCE,
                        APPLIANCE_INVENTORY_RESOURCE,
                        "meraki_appliance_connect_status",
                        collect_appliance,
                        timespan,
                        "vpn_network",
                    ),
                )
                for family, resource_type, metric_name, collector, family_timespan, count_key in family_jobs:
                    try:
                        family_metrics, counts[count_key] = await collector(client, organization_id, family_timespan)
                        _merge_metrics(metric_dict, family_metrics)
                    except Exception as error:  # noqa: BLE001 - 分族失败只置该族 connect_status=0
                        failed_families.append(family)
                        logger.warning(
                            "event=meraki_family_collect_failed monitor_type=%s organization_id=%s " "family=%s failed_stage=collect error_type=%s",
                            MONITOR_TYPE,
                            safe_log_value(organization_id),
                            family,
                            type(error).__name__,
                        )
                        _merge_metrics(metric_dict, family_connect_failed(organization_id, resource_type, metric_name))
        except Exception as error:  # noqa: BLE001 - 会话级失败仍导出 connect_status=0
            return failed_collect_output(organization_id, failed_stage="collect", error=error)
        output = "\n".join(convert_to_prometheus(metric_dict)) + "\n"
        logger.info(
            "event=meraki_collect_success monitor_type=%s network_count=%s device_count=%s "
            "ap_count=%s switch_count=%s vpn_network_count=%s failed_family_count=%s",
            MONITOR_TYPE,
            counts["network"],
            counts["device"],
            counts["ap"],
            counts["switch"],
            counts["vpn_network"],
            len(failed_families),
        )
        return output
