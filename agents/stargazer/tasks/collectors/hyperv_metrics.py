# -*- coding: utf-8 -*-
"""Hyper-V 监控指标换算与 Prometheus 输出。延迟不进入 CMDB 字段。"""

from __future__ import annotations

from typing import Any, Iterable, Mapping

CMDB_HOST_FIELDS = (
    "inst_name",
    "resource_id",
    "ip_addr",
    "cpu_cores",
    "memory",
    "hyperv_version",
)
CMDB_VM_FIELDS = (
    "inst_name",
    "resource_id",
    "ip_addr",
    "power_state",
    "vcpus",
    "memory",
    "self_host",
)
LATENCY_FIELD_NAMES = frozenset(
    {
        "storage_read_latency",
        "storage_write_latency",
        "read_latency_ms",
        "write_latency_ms",
        "read_latency",
        "write_latency",
    }
)
RUNNING_POWER_STATES = frozenset({"running", "on", "enabled"})


def power_state_value(state: Any) -> int:
    return 1 if str(state or "").strip().lower() in RUNNING_POWER_STATES else 0


def latency_to_ms(value: Any, unit: str = "ms") -> float | None:
    if value in (None, ""):
        return None
    number = float(value)
    normalized = str(unit or "ms").strip().lower()
    if normalized in {"s", "sec", "secs", "second", "seconds"}:
        return number * 1000.0
    if normalized in {"ns", "nanosecond", "nanoseconds"}:
        return number / 1_000_000.0
    if normalized in {"us", "µs", "microsecond", "microseconds"}:
        return number / 1000.0
    return number


def cmdb_fields_exclude_latency(fields: Iterable[str]) -> list[str]:
    return [name for name in fields if name not in LATENCY_FIELD_NAMES]


def _escape(value: Any) -> str:
    return str(value).replace("\\", "\\\\").replace("\n", "\\n").replace('"', '\\"')


def _labels(pairs: Mapping[str, Any]) -> str:
    return ",".join(f'{key}="{_escape(value)}"' for key, value in pairs.items() if value is not None)


def _gauge(name: str, labels: str, value: Any, help_text: str) -> list[str]:
    if value in (None, ""):
        return []
    return [
        f"# HELP {name} {help_text}",
        f"# TYPE {name} gauge",
        f"{name}{{{labels}}} {float(value)}",
    ]


def parse_hyperv_metrics_to_prometheus(payload: Mapping[str, Any], tags: Mapping[str, Any]) -> str:
    instance_id = tags.get("instance_id") or tags.get("host") or ""
    instance_type = tags.get("instance_type") or "hyperv"
    collect_type = tags.get("collect_type") or "http"
    config_type = tags.get("config_type") or "hyperv"
    host = tags.get("host") or ""
    base = {
        "instance_id": instance_id,
        "instance_type": instance_type,
        "collect_type": collect_type,
        "config_type": config_type,
        "host": host,
    }
    lines: list[str] = []
    host_info = payload.get("host") or {}
    if isinstance(host_info, dict) and host_info:
        resource_id = host_info.get("resource_id") or host_info.get("inst_name") or host
        host_labels = _labels(
            {
                **base,
                "resource_id": resource_id,
                "resource_type": "hyperv_host",
            }
        )
        lines.extend(_gauge("cpu_usage_percent", host_labels, host_info.get("cpu_usage"), "Hyper-V host CPU usage"))
        lines.extend(_gauge("mem_usage_percent", host_labels, host_info.get("mem_usage"), "Hyper-V host memory usage"))
        lines.extend(_disk_latency_lines(host_info.get("disks") or [], host_labels))

    for vm in payload.get("vms") or []:
        if not isinstance(vm, dict):
            continue
        resource_id = vm.get("resource_id") or vm.get("vmid") or vm.get("inst_name") or vm.get("name")
        vm_labels = _labels(
            {
                **base,
                "resource_id": resource_id,
                "resource_type": "hyperv_vm",
                "vm": vm.get("inst_name") or vm.get("name") or resource_id,
            }
        )
        lines.extend(_gauge("cpu_usage_percent", vm_labels, vm.get("cpu_usage"), "Hyper-V VM CPU usage"))
        lines.extend(_gauge("mem_usage_percent", vm_labels, vm.get("mem_usage"), "Hyper-V VM memory usage"))
        lines.extend(
            _gauge(
                "power_state",
                vm_labels,
                power_state_value(vm.get("power_state")),
                "Hyper-V VM power state, 1=Running 0=Down",
            )
        )
        lines.extend(_disk_latency_lines(vm.get("disks") or [], vm_labels))

    return "\n".join(lines) + ("\n" if lines else "")


def _disk_latency_lines(disks: Iterable[Any], base_labels: str) -> list[str]:
    lines: list[str] = []
    for disk in disks:
        if not isinstance(disk, dict):
            continue
        name = disk.get("name") or disk.get("disk") or ""
        if not name:
            continue
        labels = f'{base_labels},disk="{_escape(name)}"'
        unit = disk.get("unit") or "ms"
        read_ms = latency_to_ms(disk.get("read_latency_ms", disk.get("read_latency")), unit)
        write_ms = latency_to_ms(disk.get("write_latency_ms", disk.get("write_latency")), unit)
        lines.extend(_gauge("storage_read_latency", labels, read_ms, "Virtual disk read latency in milliseconds"))
        lines.extend(_gauge("storage_write_latency", labels, write_ms, "Virtual disk write latency in milliseconds"))
    return lines


def cmdb_payload_from_discover(payload: Mapping[str, Any], host_ip: str = "") -> dict[str, list[dict[str, Any]]]:
    host_info = dict(payload.get("host") or {})
    if host_ip and not host_info.get("ip_addr"):
        host_info["ip_addr"] = host_ip
    host_row = {key: host_info.get(key, "") for key in CMDB_HOST_FIELDS}
    if host_info.get("memory_mb") not in (None, "") and host_row.get("memory") in (None, ""):
        host_row["memory"] = host_info.get("memory_mb")
    vms = []
    host_name = host_row.get("inst_name") or host_info.get("inst_name") or ""
    for vm in payload.get("vms") or []:
        if not isinstance(vm, dict):
            continue
        row = {key: vm.get(key, "") for key in CMDB_VM_FIELDS}
        if vm.get("memory_mb") not in (None, "") and row.get("memory") in (None, ""):
            row["memory"] = vm.get("memory_mb")
        if not row.get("self_host"):
            row["self_host"] = host_name
        vms.append(row)
    return {"hyperv_host": [host_row] if any(host_row.values()) else [], "hyperv_vm": vms}
