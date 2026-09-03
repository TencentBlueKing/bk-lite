"""AIX OS 监控：原始 ksh 包装与允许清单内的 Prometheus 映射。"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any


def _escape_prometheus_label_value(value: Any) -> str:
    return str(value).replace("\\", "\\\\").replace("\n", "\\n").replace('"', '\\"')


def _format_prometheus_labels(**labels: Any) -> str:
    return ",".join(f'{key}="{_escape_prometheus_label_value(value)}"' for key, value in labels.items())


def _metric_value(data: dict[str, Any], *keys: str, default: Any = 0) -> Any:
    for key in keys:
        if key in data and data[key] is not None:
            return data[key]
    return default


def _append_gauge(lines: list[str], name: str, labels: str, value: Any, timestamp: int, help_text: str = "") -> None:
    lines.append(f"# HELP {name} {help_text or name}")
    lines.append(f"# TYPE {name} gauge")
    lines.append(f"{name}{{{labels}}} {value} {timestamp}")


AIX_SCRIPT_PATH = Path(__file__).parent / "scripts" / "aix" / "os_monitor.ksh"
AIX_COLLECT_EOF = "STARGAZER_AIX_COLLECT_EOF"
AIX_KSH_C_PREFIX = "/usr/bin/ksh -c '. /dev/stdin'"

COMMAND_EXECUTE_TIMEOUT = int(os.getenv("COMMAND_EXECUTE_TIMEOUT", "900"))


def load_aix_monitor_script() -> str:
    return AIX_SCRIPT_PATH.read_text(encoding="utf-8")


def wrap_ksh_collect(script_body: str | None = None) -> str:
    body = script_body if script_body is not None else load_aix_monitor_script()
    return f"{AIX_KSH_C_PREFIX} <<'{AIX_COLLECT_EOF}'\n{body.rstrip()}\n{AIX_COLLECT_EOF}\n"


def _as_float(value: Any, default: float = 0.0) -> float:
    try:
        if value is None or value == "":
            return default
        return float(value)
    except (TypeError, ValueError):
        return default


def _append_aix_diskio(lines: list[str], diskios: Any, base_labels: str, timestamp: int) -> None:
    if not isinstance(diskios, list):
        return
    for diskio in diskios:
        if not isinstance(diskio, dict):
            continue
        device = diskio.get("device", "unknown")
        diskio_labels = f"{base_labels},{_format_prometheus_labels(device=device)}"
        if "read_bytes_interval" in diskio:
            interval_r = diskio.get("read_bytes_interval", 0)
            total_r = diskio.get("read_bytes", 0)
        else:
            interval_r = diskio.get("read_bytes", 0)
            total_r = diskio.get("read_bytes_total") if "read_bytes_total" in diskio else None
        if "write_bytes_interval" in diskio:
            interval_w = diskio.get("write_bytes_interval", 0)
            total_w = diskio.get("write_bytes", 0)
        else:
            interval_w = diskio.get("write_bytes", 0)
            total_w = diskio.get("write_bytes_total") if "write_bytes_total" in diskio else None
        _append_gauge(
            lines,
            "diskio_read_bytes",
            diskio_labels,
            interval_r,
            timestamp,
            "Disk read bytes from iostat interval sample",
        )
        _append_gauge(
            lines,
            "diskio_write_bytes",
            diskio_labels,
            interval_w,
            timestamp,
            "Disk write bytes from iostat interval sample",
        )
        if total_r is not None:
            _append_gauge(
                lines,
                "diskio_read_bytes_total",
                diskio_labels,
                total_r,
                timestamp,
                "Disk read bytes counter from iostat since-boot report",
            )
        if total_w is not None:
            _append_gauge(
                lines,
                "diskio_write_bytes_total",
                diskio_labels,
                total_w,
                timestamp,
                "Disk write bytes counter from iostat since-boot report",
            )
        _append_gauge(lines, "disk_tm_act", diskio_labels, diskio.get("tm_act", 0), timestamp, "AIX disk tm_act busy percent")


def parse_aix_metrics_to_prometheus(
    data: dict[str, Any],
    instance_id: str,
    os_type: str,
    timestamp: int,
    *,
    extra_labels: dict[str, Any] | None = None,
) -> str:
    labels = {"instance_id": instance_id, "os_type": os_type}
    if extra_labels:
        labels.update({k: v for k, v in extra_labels.items() if v not in (None, "")})
    base_labels = _format_prometheus_labels(**labels)
    lines: list[str] = []

    cpu = data.get("cpu") if isinstance(data.get("cpu"), dict) else {}
    if cpu:
        user = _as_float(cpu.get("usage_user_percent"))
        system = _as_float(cpu.get("usage_system_percent"))
        iowait = _as_float(cpu.get("usage_iowait_percent"))
        usage_total = user + system + iowait
        if usage_total <= 0:
            usage_total = _as_float(cpu.get("usage_percent"))
        if usage_total < 0:
            usage_total = 0.0
        if usage_total > 100:
            usage_total = 100.0
        _append_gauge(lines, "cpu_usage_total", base_labels, usage_total, timestamp, "CPU usage percentage (user+sys+iowait)")
        _append_gauge(lines, "cpu_usage_user_total", base_labels, cpu.get("usage_user_percent", 0), timestamp, "CPU user usage percentage")
        _append_gauge(lines, "cpu_usage_system_total", base_labels, cpu.get("usage_system_percent", 0), timestamp, "CPU system usage percentage")
        _append_gauge(lines, "cpu_usage_iowait_total", base_labels, cpu.get("usage_iowait_percent", 0), timestamp, "CPU iowait usage percentage")

    mem = data.get("mem") if isinstance(data.get("mem"), dict) else {}
    if mem:
        total_bytes = _as_float(mem.get("total_bytes"))
        used_bytes = _as_float(mem.get("used_bytes"))
        used_percent = mem.get("used_percent")
        if used_percent is None:
            used_percent = round((used_bytes / total_bytes) * 100, 2) if total_bytes > 0 else 0
        swap_total = _as_float(mem.get("swap_total_bytes"))
        swap_free = _metric_value(mem, "swap_free_bytes", default=max(swap_total - _as_float(mem.get("swap_used_bytes")), 0))
        _append_gauge(lines, "mem_total", base_labels, mem.get("total_bytes", 0), timestamp, "Memory total bytes")
        _append_gauge(lines, "mem_used_percent", base_labels, used_percent, timestamp, "Memory used percent")
        _append_gauge(lines, "host_mem_used_percent", base_labels, used_percent, timestamp, "Memory used percent")
        _append_gauge(lines, "mem_swap_free", base_labels, swap_free, timestamp, "Paging space free bytes")

    svmon = data.get("svmon") if isinstance(data.get("svmon"), dict) else {}
    if svmon:
        _append_gauge(lines, "svmon_work", base_labels, svmon.get("work", 0), timestamp, "AIX svmon work segment bytes")
        _append_gauge(lines, "svmon_pers", base_labels, svmon.get("pers", 0), timestamp, "AIX svmon persistent segment bytes")
        _append_gauge(lines, "svmon_clnt", base_labels, svmon.get("clnt", 0), timestamp, "AIX svmon client segment bytes")
        _append_gauge(lines, "svmon_pin", base_labels, svmon.get("pin", 0), timestamp, "AIX svmon pinned pages bytes")

    lpar = data.get("lpar") if isinstance(data.get("lpar"), dict) else {}
    if lpar:
        _append_gauge(lines, "lpar_entitled_capacity", base_labels, lpar.get("entitled_capacity", 0), timestamp, "AIX entitled capacity")
        _append_gauge(lines, "lpar_virtual_cpus", base_labels, lpar.get("virtual_cpus", 0), timestamp, "AIX virtual CPUs")

    disks = data.get("disk")
    if isinstance(disks, list):
        for disk in disks:
            if not isinstance(disk, dict):
                continue
            mount = disk.get("mount", "unknown")
            path = disk.get("path") or mount
            disk_labels = f"{base_labels},{_format_prometheus_labels(mount=mount, path=path)}"
            used = _as_float(disk.get("used_bytes", 0))
            free = _as_float(_metric_value(disk, "free_bytes", "available_bytes", default=0))
            total = _as_float(disk.get("total_bytes", 0))
            if total <= 0:
                total = used + free
            if free <= 0 and total > used:
                free = total - used
            _append_gauge(lines, "disk_total", disk_labels, total, timestamp, "Disk total bytes")
            _append_gauge(lines, "disk_free", disk_labels, free, timestamp, "Disk free bytes")
            _append_gauge(lines, "disk_used_percent", disk_labels, disk.get("used_percent", 0), timestamp, "Disk used percent")
            _append_gauge(lines, "host_disk_used_percent", disk_labels, disk.get("used_percent", 0), timestamp, "Disk used percent")
            _append_gauge(lines, "disk_inodes_used_percent", disk_labels, disk.get("inodes_used_percent", 0), timestamp, "Disk inode used percent")
            _append_gauge(lines, "disk_iused", disk_labels, disk.get("iused", 0), timestamp, "Used inode count")
            _append_gauge(lines, "disk_ifree", disk_labels, disk.get("ifree", 0), timestamp, "Free inode count")

    nets = data.get("net")
    if isinstance(nets, list):
        for net in nets:
            if not isinstance(net, dict):
                continue
            iface = net.get("interface", "unknown")
            net_labels = f"{base_labels},{_format_prometheus_labels(interface=iface)}"
            _append_gauge(lines, "net_bytes_recv", net_labels, net.get("rx_bytes", 0), timestamp, "Network received bytes counter")
            _append_gauge(lines, "net_bytes_sent", net_labels, net.get("tx_bytes", 0), timestamp, "Network transmitted bytes counter")
            _append_gauge(lines, "net_err_in", net_labels, net.get("rx_errors", 0), timestamp, "Network receive errors counter")
            _append_gauge(lines, "net_err_out", net_labels, net.get("tx_errors", 0), timestamp, "Network transmit errors counter")

    _append_aix_diskio(lines, data.get("diskio"), base_labels, timestamp)

    processes = data.get("processes") if isinstance(data.get("processes"), dict) else {}
    states = processes.get("states") if isinstance(processes.get("states"), dict) else {}
    for state, count in states.items():
        letter = str(state).strip()
        if len(letter) != 1 or not letter.isalpha():
            continue
        state_labels = f"{base_labels},{_format_prometheus_labels(state=letter.upper())}"
        _append_gauge(
            lines,
            "processes_state",
            state_labels,
            count,
            timestamp,
            "AIX process state letter count",
        )

    system = data.get("system") if isinstance(data.get("system"), dict) else {}
    if system:
        _append_gauge(lines, "system_uptime", base_labels, system.get("uptime_seconds", 0), timestamp, "System uptime seconds")
        _append_gauge(lines, "system_load1", base_labels, system.get("load1", 0), timestamp, "System load 1 minute")
        _append_gauge(lines, "system_load5", base_labels, system.get("load5", 0), timestamp, "System load 5 minutes")
        _append_gauge(lines, "system_load15", base_labels, system.get("load15", 0), timestamp, "System load 15 minutes")

    return "\n".join(lines) + ("\n" if lines else "")
