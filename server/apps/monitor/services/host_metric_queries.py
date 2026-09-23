"""Shared PromQL fragments for Host object metrics across plugins.

Object dashboard, ops-analysis range/Top10, and zombie-host reports must use the
same selectors so Agent Telegraf, Host Remote, Windows WMI, and Unix remote stay
comparable. Frontend copies live in web host dashboard config.ts.

Host diskio util/latency: Windows Telegraf emits win_logicaldisk_{idle_percent,
read_latency_ms, write_latency_ms} (LogicalDisk % Idle Time and Avg. Disk
sec/Read|Write). Linux keeps rate(diskio_io_time)/10 and
rate(diskio_*_time)/rate(diskio_*s). Windows still has diskio_*_time zeros, so
the idle/ms branch is preferred and the zero line is dropped with unless on
(instance_id, name). Existing Windows nodes need Disk IO re-deploy; Host diskio
metric queries must be re-imported so the UI stops using stored PromQL.
"""

from __future__ import annotations

OS = 'instance_type="os"'
WMI = 'config_type="windows_wmi"'
UNIX_REMOTE = 'config_type=~"host_(aix|freebsd|hpux|solaris)_remote"'
UNIX_NOT_REMOTE = 'config_type!~"host_(aix|freebsd|hpux|solaris)_remote"'
CPU_TOTAL = 'cpu="cpu-total"'
WIN_DRIVE = 'instance=~"[A-Z]:"'


def _sel(*parts: str, labels: bool = False) -> str:
    items = [part for part in parts if part]
    if labels:
        items.append("__$labels__")
    return "{" + ", ".join(items) + "}"


def _label_replace_instance_to_name(expr: str) -> str:
    return f'label_replace({expr}, "name", "$1", "instance", "(.*)")'


def windows_logicaldisk_idle_query(*, labels: bool = False) -> str:
    return f"win_logicaldisk_idle_percent{_sel(OS, WIN_DRIVE, labels=labels)}"


def windows_diskio_io_util_query(*, labels: bool = False) -> str:
    idle = windows_logicaldisk_idle_query(labels=labels)
    return _label_replace_instance_to_name(f"clamp_max(clamp_min(100 - {idle}, 0), 100)")


def linux_diskio_io_util_query(*, labels: bool = False) -> str:
    return f"(rate(diskio_io_time{_sel(OS, labels=labels)}[5m]) / 10)"


def windows_read_latency_query(*, labels: bool = False) -> str:
    return _label_replace_instance_to_name(f"win_logicaldisk_read_latency_ms{_sel(OS, WIN_DRIVE, labels=labels)}")


def windows_write_latency_query(*, labels: bool = False) -> str:
    return _label_replace_instance_to_name(f"win_logicaldisk_write_latency_ms{_sel(OS, WIN_DRIVE, labels=labels)}")


def linux_read_latency_query(*, labels: bool = False) -> str:
    return (
        f"(rate(diskio_read_time{_sel(OS, labels=labels)}[5m])"
        f" / rate(diskio_reads{_sel(OS, labels=labels)}[5m]))"
    )


def linux_write_latency_query(*, labels: bool = False) -> str:
    return (
        f"(rate(diskio_write_time{_sel(OS, labels=labels)}[5m])"
        f" / rate(diskio_writes{_sel(OS, labels=labels)}[5m]))"
    )


def _prefer_windows_unless_linux(windows_expr: str, linux_expr: str) -> str:
    return f"{windows_expr} or ({linux_expr} unless on(instance_id, name) {windows_expr})"


def cpu_usage_query(*, labels: bool = False) -> str:
    return (
        f"(100 - cpu_usage_idle{_sel(CPU_TOTAL, OS, labels=labels)})"
        f" or host_cpu_usage_percent_gauge{_sel(OS, labels=labels)}"
        f" or cpu_usage_total_gauge_value{_sel(OS, WMI, labels=labels)}"
        f" or cpu_usage_total_gauge{_sel(OS, UNIX_REMOTE, labels=labels)}"
    )


def mem_used_percent_query(*, labels: bool = False) -> str:
    return (
        f"mem_used_percent{_sel(OS, labels=labels)}"
        f" or host_mem_used_percent_gauge{_sel(OS, labels=labels)}"
        f" or mem_used_percent_gauge_value{_sel(OS, WMI, labels=labels)}"
        f" or mem_used_percent_gauge{_sel(OS, UNIX_REMOTE, labels=labels)}"
    )


def disk_used_percent_query(*, labels: bool = False) -> str:
    return (
        f"disk_used_percent{_sel(OS, labels=labels)}"
        f" or host_disk_used_percent_gauge{_sel(OS, labels=labels)}"
        f" or disk_used_percent_gauge_value{_sel(OS, WMI, labels=labels)}"
        f" or disk_used_percent_gauge{_sel(OS, UNIX_REMOTE, labels=labels)}"
    )


def load5_query(*, labels: bool = False) -> str:
    # Windows has no loadavg; do not OR WMI placeholders.
    return (
        f"system_load5{_sel(OS, labels=labels)}"
        f" or system_load5_gauge{_sel(OS, labels=labels)}"
        f" or host_cpu_load_5m_gauge{_sel(OS, labels=labels)}"
    )


def net_bytes_recv_query(*, labels: bool = False, window: str = "5m") -> str:
    return (
        f"rate(net_bytes_recv{_sel(OS, labels=labels)}[{window}])"
        f" or rate(net_bytes_recv_gauge{_sel(OS, labels=labels)}[{window}])"
        f" or rate(net_bytes_recv_gauge_value{_sel(OS, WMI, labels=labels)}[{window}])"
    )


def net_bytes_sent_query(*, labels: bool = False, window: str = "5m") -> str:
    return (
        f"rate(net_bytes_sent{_sel(OS, labels=labels)}[{window}])"
        f" or rate(net_bytes_sent_gauge{_sel(OS, labels=labels)}[{window}])"
        f" or rate(net_bytes_sent_gauge_value{_sel(OS, WMI, labels=labels)}[{window}])"
    )


def diskio_io_util_query(*, labels: bool = False) -> str:
    windows = windows_diskio_io_util_query(labels=labels)
    idle_named = _label_replace_instance_to_name(windows_logicaldisk_idle_query(labels=labels))
    linux = linux_diskio_io_util_query(labels=labels)
    return (
        f"{windows}"
        f" or ({linux} unless on(instance_id, name) {idle_named})"
        f" or (rate(diskio_io_time_ms_gauge{_sel(OS, labels=labels)}[5m]) / 10)"
        f" or diskio_io_util{_sel(OS, labels=labels)}"
        f" or diskio_io_util_gauge{_sel(OS, labels=labels)}"
        f" or diskio_io_util_gauge_value{_sel(OS, WMI, labels=labels)}"
        f" or disk_tm_act_gauge{_sel(OS, UNIX_REMOTE, labels=labels)}"
    )


def diskio_read_bytes_query(*, labels: bool = False, window: str = "5m") -> str:
    return (
        f"rate(diskio_read_bytes{_sel(OS, labels=labels)}[{window}])"
        f" or rate(diskio_read_bytes_total_gauge{_sel(OS, UNIX_NOT_REMOTE, labels=labels)}[{window}])"
        f" or rate(diskio_read_bytes_gauge_value{_sel(OS, WMI, labels=labels)}[{window}])"
        f" or diskio_read_bytes_gauge{_sel(OS, UNIX_REMOTE, labels=labels)}"
    )


def diskio_write_bytes_query(*, labels: bool = False, window: str = "5m") -> str:
    return (
        f"rate(diskio_write_bytes{_sel(OS, labels=labels)}[{window}])"
        f" or rate(diskio_write_bytes_total_gauge{_sel(OS, UNIX_NOT_REMOTE, labels=labels)}[{window}])"
        f" or rate(diskio_write_bytes_gauge_value{_sel(OS, WMI, labels=labels)}[{window}])"
        f" or diskio_write_bytes_gauge{_sel(OS, UNIX_REMOTE, labels=labels)}"
    )


def disk_write_latency_query(*, labels: bool = False) -> str:
    windows = windows_write_latency_query(labels=labels)
    linux = linux_write_latency_query(labels=labels)
    return (
        f"{_prefer_windows_unless_linux(windows, linux)}"
        f" or disk_write_latency_gauge_value{_sel(OS, WMI, labels=labels)}"
        f" or disk_write_latency_gauge{_sel(OS, labels=labels)}"
        f" or (rate(diskio_write_time_ms_gauge{_sel(OS, labels=labels)}[5m])"
        f" / rate(diskio_writes_total_gauge{_sel(OS, labels=labels)}[5m]))"
    )


def disk_read_latency_query(*, labels: bool = False) -> str:
    windows = windows_read_latency_query(labels=labels)
    linux = linux_read_latency_query(labels=labels)
    return (
        f"{_prefer_windows_unless_linux(windows, linux)}"
        f" or disk_read_latency_gauge_value{_sel(OS, WMI, labels=labels)}"
        f" or disk_read_latency_gauge{_sel(OS, labels=labels)}"
        f" or (rate(diskio_read_time_ms_gauge{_sel(OS, labels=labels)}[5m])"
        f" / rate(diskio_reads_total_gauge{_sel(OS, labels=labels)}[5m]))"
    )


def processes_blocked_query(*, labels: bool = False) -> str:
    return f"processes_blocked{_sel(OS, labels=labels)}" f" or processes_blocked_gauge{_sel(OS, labels=labels)}"


def processes_zombies_query(*, labels: bool = False) -> str:
    return f"processes_zombies{_sel(OS, labels=labels)}" f" or processes_zombies_gauge{_sel(OS, labels=labels)}"


def net_packets_recv_query(*, labels: bool = False, window: str = "5m") -> str:
    return (
        f"rate(net_packets_recv{_sel(OS, labels=labels)}[{window}])"
        f" or rate(net_packets_recv_gauge{_sel(OS, labels=labels)}[{window}])"
        f" or rate(net_packets_recv_gauge_value{_sel(OS, WMI, labels=labels)}[{window}])"
    )
