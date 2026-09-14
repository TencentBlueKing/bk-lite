"""Solaris OS 监控：远程 ksh 包装与 Prometheus 映射。x86 与 SPARC 共用。"""

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


SOLARIS_SCRIPT_PATH = Path(__file__).parent / "scripts" / "solaris" / "os_monitor.ksh"
SOLARIS_COLLECT_EOF = "STARGAZER_SOLARIS_COLLECT_EOF"
SOLARIS_KSH_PREFIX = "LC_ALL=C LANG=C /usr/bin/ksh"

COMMAND_EXECUTE_TIMEOUT = int(os.getenv("COMMAND_EXECUTE_TIMEOUT", "900"))


def load_solaris_monitor_script() -> str:
    return SOLARIS_SCRIPT_PATH.read_text(encoding="utf-8")


def wrap_ksh_collect(script_body: str | None = None) -> str:
    body = script_body if script_body is not None else load_solaris_monitor_script()
    return f"{SOLARIS_KSH_PREFIX} <<'{SOLARIS_COLLECT_EOF}'\n{body.rstrip()}\n{SOLARIS_COLLECT_EOF}\n"


def _as_float(value: Any, default: float = 0.0) -> float:
    try:
        if value is None or value == "":
            return default
        return float(value)
    except (TypeError, ValueError):
        return default


def _append_solaris_diskio(lines: list[str], diskios: Any, base_labels: str, timestamp: int) -> None:
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
                "Disk read bytes from iostat since-boot report",
            )
        if total_w is not None:
            _append_gauge(
                lines,
                "diskio_write_bytes_total",
                diskio_labels,
                total_w,
                timestamp,
                "Disk write bytes from iostat since-boot report",
            )
        _append_gauge(lines, "disk_tm_act", diskio_labels, diskio.get("tm_act", 0), timestamp, "Disk busy percent from iostat %b")


# JSON → Prometheus lock-in: scripts/solaris/samples/os_monitor.sample.json
def parse_solaris_metrics_to_prometheus(
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

    os_info = data.get("os") if isinstance(data.get("os"), dict) else {}
    if os_info:
        version = os_info.get("version") or os_info.get("release") or ""
        arch = os_info.get("arch") or ""
        machine = os_info.get("machine") or ""
        info_labels = f"{base_labels},{_format_prometheus_labels(os_version=version, arch=arch, machine=machine)}"
        _append_gauge(lines, "os_info", info_labels, 1, timestamp, "Solaris uname version and architecture")

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
        _append_gauge(lines, "host_cpu_usage_percent", base_labels, usage_total, timestamp, "CPU usage percentage")
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
        _append_gauge(lines, "mem_swap_free", base_labels, swap_free, timestamp, "Swap free bytes")
        _append_gauge(lines, "mem_swap_total", base_labels, swap_total, timestamp, "Swap total bytes")

    disks = data.get("disk")
    if isinstance(disks, list):
        for disk in disks:
            if not isinstance(disk, dict):
                continue
            mount = disk.get("mount", "unknown")
            path = disk.get("path") or mount
            disk_label_kwargs = {"mount": mount, "path": path}
            fstype = disk.get("fstype") or ""
            if fstype:
                disk_label_kwargs["fstype"] = fstype
            disk_labels = f"{base_labels},{_format_prometheus_labels(**disk_label_kwargs)}"
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

    _append_solaris_diskio(lines, data.get("diskio"), base_labels, timestamp)

    system = data.get("system") if isinstance(data.get("system"), dict) else {}
    if system:
        _append_gauge(lines, "system_uptime", base_labels, system.get("uptime_seconds", 0), timestamp, "System uptime seconds")
        _append_gauge(lines, "system_load1", base_labels, system.get("load1", 0), timestamp, "System load 1 minute")
        _append_gauge(lines, "system_load5", base_labels, system.get("load5", 0), timestamp, "System load 5 minutes")
        _append_gauge(lines, "system_load15", base_labels, system.get("load15", 0), timestamp, "System load 15 minutes")

    return "\n".join(lines) + ("\n" if lines else "")
