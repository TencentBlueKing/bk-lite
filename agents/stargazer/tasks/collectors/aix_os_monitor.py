"""AIX OS 监控：原始 ksh 包装、驻留安装与允许清单内的 Prometheus 映射。"""

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
AIX_RESIDENT_PATH = "/opt/bk-lite/aix/os_monitor.ksh"
AIX_KEEPER_PATH = "/opt/bk-lite/aix/os_monitor_src.ksh"
AIX_RESIDENT_DIR = "/opt/bk-lite/aix"
AIX_INSTALL_LOCK = "/opt/bk-lite/aix/.install.lock"
AIX_SRC_NAME = "bklite_osmon"
AIX_LOCAL_CONFIG_TYPE = "host_aix"
AIX_REMOTE_CONFIG_TYPE = "host_aix_remote"
AIX_CRON_BEGIN = "# BEGIN BK-LITE OS MONITOR"
AIX_CRON_END = "# END BK-LITE OS MONITOR"
AIX_COLLECT_EOF = "STARGAZER_AIX_COLLECT_EOF"
AIX_INSTALL_EOF = "STARGAZER_AIX_INSTALL_EOF"
AIX_SCRIPT_EOF = "STARGAZER_AIX_SCRIPT_BODY"
AIX_KEEPER_EOF = "STARGAZER_AIX_KEEPER_BODY"
AIX_KSH_C_PREFIX = "/usr/bin/ksh -c '. /dev/stdin'"
AIX_PROBE_PRESENT = "bklite_aix_os_monitor_present"
AIX_PROBE_ABSENT = "bklite_aix_os_monitor_absent"
AIX_KEEPER_BODY = "\n".join(
    [
        "#!/usr/bin/ksh",
        "# SRC residency keeper. Does not scrape; collection SSH-runs os_monitor.ksh.",
        "trap 'exit 0' TERM INT",
        "while true",
        "do",
        "  /usr/bin/sleep 3600",
        "done",
        "",
    ]
)

FILE_TRANSFER_TIMEOUT = int(os.getenv("FILE_TRANSFER_TIMEOUT", "1800"))
COMMAND_EXECUTE_TIMEOUT = int(os.getenv("COMMAND_EXECUTE_TIMEOUT", "900"))


def load_aix_monitor_script() -> str:
    return AIX_SCRIPT_PATH.read_text(encoding="utf-8")


def wrap_ksh_collect(script_body: str | None = None) -> str:
    body = script_body if script_body is not None else load_aix_monitor_script()
    return f"{AIX_KSH_C_PREFIX} <<'{AIX_COLLECT_EOF}'\n{body.rstrip()}\n{AIX_COLLECT_EOF}\n"


def wrap_ksh_resident_run() -> str:
    return f"/usr/bin/ksh -c '{AIX_RESIDENT_PATH}'\n"


def wrap_ksh_resident_probe() -> str:
    return (
        "/usr/bin/ksh -c '"
        f"if test -x {AIX_RESIDENT_PATH} && test -x {AIX_KEEPER_PATH}; "
        f"then printf {AIX_PROBE_PRESENT}; else printf {AIX_PROBE_ABSENT}; fi'\n"
    )


def aix_config_type(params: dict[str, Any] | None) -> str:
    data = params or {}
    tags = data.get("tags") if isinstance(data.get("tags"), dict) else {}
    return str(tags.get("config_type") or data.get("config_type") or "").strip().lower()


def is_aix_local_residency(params: dict[str, Any] | None) -> bool:
    data = params or {}
    os_type = str(data.get("os_type") or "").strip().lower()
    return os_type == "aix" and aix_config_type(data) == AIX_LOCAL_CONFIG_TYPE


def wrap_ksh_install(script_body: str | None = None) -> str:
    body = script_body if script_body is not None else load_aix_monitor_script()
    install_lines = [
        "umask 022",
        f"/usr/bin/mkdir -p {AIX_RESIDENT_DIR}",
        f"if /usr/bin/mkdir {AIX_INSTALL_LOCK} 2>/dev/null; then",
        f"  trap '/usr/bin/rmdir {AIX_INSTALL_LOCK} >/dev/null 2>&1' 0",
        f"  cat > {AIX_RESIDENT_PATH} <<'{AIX_SCRIPT_EOF}'",
        body.rstrip(),
        AIX_SCRIPT_EOF,
        f"  /usr/bin/chmod 755 {AIX_RESIDENT_PATH}",
        f"  cat > {AIX_KEEPER_PATH} <<'{AIX_KEEPER_EOF}'",
        AIX_KEEPER_BODY.rstrip(),
        AIX_KEEPER_EOF,
        f"  /usr/bin/chmod 755 {AIX_KEEPER_PATH}",
        "  _src_ok=0",
        "  if /usr/bin/whence mkssys >/dev/null 2>&1; then",
        f"    if /usr/bin/lssrc -s {AIX_SRC_NAME} >/dev/null 2>&1; then",
        "      _src_ok=1",
        f"      _src_line=`/usr/bin/lssrc -S -s {AIX_SRC_NAME} 2>/dev/null`",
        '      case "${_src_line}" in',
        f"        *{AIX_KEEPER_PATH}*) : ;;",
        (f"        *) /usr/bin/chssys -s {AIX_SRC_NAME} -p /usr/bin/ksh " f"-a {AIX_KEEPER_PATH} >/dev/null 2>&1 ;;"),
        "      esac",
        (f"    elif /usr/bin/mkssys -s {AIX_SRC_NAME} -p /usr/bin/ksh " f"-a {AIX_KEEPER_PATH} -u 0 -S -n 15 -f 9 -R >/dev/null 2>&1; then"),
        "      _src_ok=1",
        "    fi",
        '    if [ "${_src_ok}" -eq 1 ]; then',
        f"      _src_out=`/usr/bin/lssrc -s {AIX_SRC_NAME} 2>/dev/null`",
        "      if printf '%s\\n' \"${_src_out}\" | /usr/bin/grep -q inoperative; then",
        f"        /usr/bin/startsrc -s {AIX_SRC_NAME} >/dev/null 2>&1",
        "      elif printf '%s\\n' \"${_src_out}\" | /usr/bin/grep -q active; then",
        "        :",
        "      else",
        f"        /usr/bin/startsrc -s {AIX_SRC_NAME} >/dev/null 2>&1",
        "      fi",
        "    fi",
        "  fi",
        '  if [ "${_src_ok}" -eq 0 ]; then',
        "    _cron_old=`/usr/bin/crontab -l 2>/dev/null`",
        f"    if printf '%s\\n' \"${{_cron_old}}\" | /usr/bin/grep -F '{AIX_CRON_BEGIN}' >/dev/null 2>&1; then",
        "      :",
        "    else",
        "      {",
        "        printf '%s\\n' \"${_cron_old}\"",
        f"        printf '%s\\n' \"{AIX_CRON_BEGIN}\"",
        f"        printf '%s\\n' \"@reboot /usr/bin/ksh -c '{AIX_KEEPER_PATH}'\"",
        f"        printf '%s\\n' \"{AIX_CRON_END}\"",
        "      } | /usr/bin/crontab - >/dev/null 2>&1",
        "    fi",
        "  fi",
        "  printf '%s\\n' \"bklite_aix_os_monitor_installed\"",
        "else",
        "  _n=0",
        '  while [ "${_n}" -lt 90 ]; do',
        f"    if test -x {AIX_RESIDENT_PATH}; then",
        "      printf '%s\\n' \"bklite_aix_os_monitor_installed\"",
        "      exit 0",
        "    fi",
        "    /usr/bin/sleep 1",
        "    _n=$((_n + 1))",
        "  done",
        "  printf '%s\\n' \"bklite_aix_os_monitor_install_lock_timeout\"",
        "  exit 1",
        "fi",
    ]
    install = "\n".join(install_lines)
    return f"{AIX_KSH_C_PREFIX} <<'{AIX_INSTALL_EOF}'\n{install}\n{AIX_INSTALL_EOF}\n"


def _as_float(value: Any, default: float = 0.0) -> float:
    try:
        if value is None or value == "":
            return default
        return float(value)
    except (TypeError, ValueError):
        return default


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
            fstype = disk.get("fstype") or ""
            disk_labels = f"{base_labels},{_format_prometheus_labels(mount=mount, path=path, fstype=fstype)}"
            total = disk.get("total_bytes", 0)
            used = disk.get("used_bytes", 0)
            free = _metric_value(disk, "free_bytes", "available_bytes", default=max(_as_float(total) - _as_float(used), 0))
            _append_gauge(lines, "disk_total", disk_labels, total, timestamp, "Disk total bytes")
            _append_gauge(lines, "disk_free", disk_labels, free, timestamp, "Disk free bytes")
            _append_gauge(lines, "disk_used_percent", disk_labels, disk.get("used_percent", 0), timestamp, "Disk used percent")
            _append_gauge(lines, "host_disk_used_percent", disk_labels, disk.get("used_percent", 0), timestamp, "Disk used percent")

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

    diskios = data.get("diskio")
    if isinstance(diskios, list):
        for diskio in diskios:
            if not isinstance(diskio, dict):
                continue
            device = diskio.get("device", "unknown")
            diskio_labels = f"{base_labels},{_format_prometheus_labels(device=device)}"
            _append_gauge(
                lines, "diskio_read_bytes_total", diskio_labels, diskio.get("read_bytes", 0), timestamp, "Disk read bytes from iostat second report"
            )
            _append_gauge(
                lines,
                "diskio_write_bytes_total",
                diskio_labels,
                diskio.get("write_bytes", 0),
                timestamp,
                "Disk write bytes from iostat second report",
            )
            _append_gauge(lines, "disk_tm_act", diskio_labels, diskio.get("tm_act", 0), timestamp, "AIX disk tm_act busy percent")

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
