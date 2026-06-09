import time
from typing import Any


def _escape_label(value: Any) -> str:
    return str(value).replace("\\", "\\\\").replace('"', '\\"').replace("\n", "\\n")


def _labels(base_labels: dict[str, Any], extra_labels: dict[str, Any] | None = None) -> str:
    merged = {**base_labels, **(extra_labels or {})}
    return ",".join(f'{key}="{_escape_label(value)}"' for key, value in merged.items() if value is not None)


def _append_gauge(lines: list[str], name: str, labels: dict[str, Any], value: Any, timestamp: int):
    try:
        number = float(value)
    except (TypeError, ValueError):
        return
    if number.is_integer():
        rendered = str(int(number))
    else:
        rendered = str(number)
    lines.append(f"{name}{{{_labels(labels)}}} {rendered} {timestamp}")


def wmi_results_to_prometheus(
    results: dict[str, Any],
    tags: dict[str, Any],
    *,
    host: str,
    timestamp: int | None = None,
) -> str:
    timestamp = timestamp or int(time.time() * 1000)
    base_labels = {
        "instance_id": tags.get("instance_id") or host,
        "instance_type": tags.get("instance_type") or "os",
        "collect_type": tags.get("collect_type") or "http",
        "config_type": tags.get("config_type") or "windows_wmi",
        "host": host,
    }
    lines: list[str] = []

    cpu = results.get("cpu") or {}
    _append_gauge(lines, "host_cpu_usage_percent_gauge", base_labels, cpu.get("usage_percent"), timestamp)
    _append_gauge(lines, "host_cpu_core_count_gauge", base_labels, cpu.get("core_count"), timestamp)

    mem = results.get("mem") or {}
    _append_gauge(lines, "host_mem_total_bytes_gauge", base_labels, mem.get("total_bytes"), timestamp)
    _append_gauge(lines, "host_mem_available_bytes_gauge", base_labels, mem.get("available_bytes"), timestamp)
    _append_gauge(lines, "host_mem_used_bytes_gauge", base_labels, mem.get("used_bytes"), timestamp)
    _append_gauge(lines, "host_mem_used_percent_gauge", base_labels, mem.get("used_percent"), timestamp)

    for disk in results.get("disk") or []:
        disk_labels = {**base_labels, "device": disk.get("device")}
        _append_gauge(lines, "host_disk_total_bytes_gauge", disk_labels, disk.get("total_bytes"), timestamp)
        _append_gauge(lines, "host_disk_free_bytes_gauge", disk_labels, disk.get("free_bytes"), timestamp)
        _append_gauge(lines, "host_disk_used_bytes_gauge", disk_labels, disk.get("used_bytes"), timestamp)
        _append_gauge(lines, "host_disk_used_percent_gauge", disk_labels, disk.get("used_percent"), timestamp)

    return "\n".join(lines) + ("\n" if lines else "")
