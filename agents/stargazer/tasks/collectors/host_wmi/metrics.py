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
    _append_gauge(lines, "cpu_usage_total_gauge", base_labels, cpu.get("usage_percent"), timestamp)
    _append_gauge(lines, "host_cpu_core_count_gauge", base_labels, cpu.get("core_count"), timestamp)

    mem = results.get("mem") or {}
    _append_gauge(lines, "host_mem_total_bytes_gauge", base_labels, mem.get("total_bytes"), timestamp)
    _append_gauge(lines, "host_mem_available_bytes_gauge", base_labels, mem.get("available_bytes"), timestamp)
    _append_gauge(lines, "host_mem_used_bytes_gauge", base_labels, mem.get("used_bytes"), timestamp)
    _append_gauge(lines, "host_mem_used_percent_gauge", base_labels, mem.get("used_percent"), timestamp)
    _append_gauge(lines, "mem_total_gauge", base_labels, mem.get("total_bytes"), timestamp)
    _append_gauge(lines, "mem_available_gauge", base_labels, mem.get("available_bytes"), timestamp)
    _append_gauge(lines, "mem_used_percent_gauge", base_labels, mem.get("used_percent"), timestamp)

    for disk in results.get("disk") or []:
        disk_labels = {**base_labels, "device": disk.get("device")}
        _append_gauge(lines, "host_disk_total_bytes_gauge", disk_labels, disk.get("total_bytes"), timestamp)
        _append_gauge(lines, "host_disk_free_bytes_gauge", disk_labels, disk.get("free_bytes"), timestamp)
        _append_gauge(lines, "host_disk_used_bytes_gauge", disk_labels, disk.get("used_bytes"), timestamp)
        _append_gauge(lines, "host_disk_used_percent_gauge", disk_labels, disk.get("used_percent"), timestamp)
        _append_gauge(lines, "disk_total_gauge", disk_labels, disk.get("total_bytes"), timestamp)
        _append_gauge(lines, "disk_free_gauge", disk_labels, disk.get("free_bytes"), timestamp)
        _append_gauge(lines, "disk_used_percent_gauge", disk_labels, disk.get("used_percent"), timestamp)

    for net in results.get("net") or []:
        net_labels = {**base_labels, "interface": net.get("interface")}
        _append_gauge(lines, "net_bytes_recv_gauge", net_labels, net.get("rx_bytes"), timestamp)
        _append_gauge(lines, "net_bytes_sent_gauge", net_labels, net.get("tx_bytes"), timestamp)
        _append_gauge(lines, "net_packets_recv_gauge", net_labels, net.get("rx_packets"), timestamp)
        _append_gauge(lines, "net_packets_sent_gauge", net_labels, net.get("tx_packets"), timestamp)
        _append_gauge(lines, "net_err_in_gauge", net_labels, net.get("rx_errors"), timestamp)
        _append_gauge(lines, "net_err_out_gauge", net_labels, net.get("tx_errors"), timestamp)
        _append_gauge(lines, "net_drop_in_gauge", net_labels, net.get("rx_drops"), timestamp)
        _append_gauge(lines, "net_drop_out_gauge", net_labels, net.get("tx_drops"), timestamp)

    for diskio in results.get("diskio") or []:
        diskio_labels = {**base_labels, "name": diskio.get("name") or diskio.get("device")}
        _append_gauge(lines, "diskio_reads_gauge", diskio_labels, diskio.get("reads"), timestamp)
        _append_gauge(lines, "diskio_writes_gauge", diskio_labels, diskio.get("writes"), timestamp)
        _append_gauge(lines, "diskio_read_bytes_gauge", diskio_labels, diskio.get("read_bytes"), timestamp)
        _append_gauge(lines, "diskio_write_bytes_gauge", diskio_labels, diskio.get("write_bytes"), timestamp)
        _append_gauge(lines, "diskio_io_util_gauge", diskio_labels, diskio.get("io_time_ms"), timestamp)
        _append_gauge(lines, "diskio_read_time_gauge", diskio_labels, diskio.get("read_time_ms"), timestamp)
        _append_gauge(lines, "diskio_write_time_gauge", diskio_labels, diskio.get("write_time_ms"), timestamp)

    processes = results.get("processes") or {}
    _append_gauge(lines, "processes_running_gauge", base_labels, processes.get("running"), timestamp)
    _append_gauge(lines, "processes_blocked_gauge", base_labels, processes.get("blocked"), timestamp)
    _append_gauge(lines, "processes_zombies_gauge", base_labels, processes.get("zombies"), timestamp)
    _append_gauge(lines, "processes_sleeping_gauge", base_labels, processes.get("sleeping"), timestamp)

    system = results.get("system") or {}
    _append_gauge(lines, "system_uptime_gauge", base_labels, system.get("uptime_seconds"), timestamp)
    _append_gauge(lines, "system_load1_gauge", base_labels, system.get("load1"), timestamp)
    _append_gauge(lines, "system_load5_gauge", base_labels, system.get("load5"), timestamp)
    _append_gauge(lines, "system_load15_gauge", base_labels, system.get("load15"), timestamp)

    return "\n".join(lines) + ("\n" if lines else "")
