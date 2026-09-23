from datetime import datetime, timezone
from typing import Any, Callable

VALID_MODULES = ("cpu", "mem", "disk", "diskio", "net", "processes", "system")
DEFAULT_MODULES = ("cpu", "mem", "disk", "diskio", "net", "processes", "system")


def resolve_modules(raw_modules: Any) -> list[str]:
    if isinstance(raw_modules, (list, tuple)):
        items = raw_modules
    else:
        items = str(raw_modules or "").split(",")

    selected = [str(item).strip() for item in items if str(item).strip() in VALID_MODULES]
    return selected or list(DEFAULT_MODULES)


class WmiModule:
    name: str

    def collect(self, client) -> Any:
        raise NotImplementedError


def _to_int(value: Any, default: int = 0) -> int:
    try:
        return int(value or default)
    except (TypeError, ValueError):
        return default


def _to_optional_int(value: Any) -> int | None:
    if value is None or value == "":
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _to_float(value: Any) -> float | None:
    if value is None or value == "":
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _clamp_percent(value: float) -> float:
    return round(min(100.0, max(0.0, value)), 2)


class CpuModule(WmiModule):
    name = "cpu"

    def collect(self, client):
        processor_rows = client.query_class("Win32_PerfFormattedData_PerfOS_Processor")
        total_row = next((row for row in processor_rows if str(row.get("Name") or "") == "_Total"), None)
        percent = _to_float((total_row or {}).get("PercentProcessorTime"))

        cpu_rows = client.query_class("Win32_Processor")
        logical_counts = [_to_int(row.get("NumberOfLogicalProcessors")) for row in cpu_rows]
        cores = sum(logical_counts) or len(cpu_rows)
        result = {"core_count": cores}
        if percent is not None:
            result["usage_percent"] = _clamp_percent(percent)
        return result


class MemoryModule(WmiModule):
    name = "mem"

    def collect(self, client):
        rows = client.query_class("Win32_OperatingSystem")
        row = rows[0] if rows else {}
        total = int(row.get("TotalVisibleMemorySize") or 0) * 1024
        raw_memory = client.query_class("Win32_PerfRawData_PerfOS_Memory")
        raw_row = raw_memory[0] if raw_memory else {}
        available = _to_optional_int(raw_row.get("AvailableBytes"))
        if available is None:
            formatted = client.query_class("Win32_PerfFormattedData_PerfOS_Memory")
            formatted_row = formatted[0] if formatted else {}
            available_mb = _to_optional_int(formatted_row.get("AvailableMBytes"))
            if available_mb is not None:
                available = available_mb * 1024 * 1024
        result = {"total_bytes": total}
        if available is None:
            return result
        if total and available > total:
            available = total
        used = max(total - available, 0)
        result["available_bytes"] = available
        result["used_bytes"] = used
        result["used_percent"] = round((used / total) * 100, 2) if total else 0
        return result


class DiskModule(WmiModule):
    name = "disk"

    def collect(self, client):
        rows = client.query("SELECT DeviceID, FileSystem, Size, FreeSpace FROM Win32_LogicalDisk WHERE DriveType=3")
        disks = []
        for row in rows:
            total = int(row.get("Size") or 0)
            free = int(row.get("FreeSpace") or 0)
            used = max(total - free, 0)
            disks.append(
                {
                    "device": str(row.get("DeviceID") or ""),
                    "path": str(row.get("DeviceID") or ""),
                    "fstype": str(row.get("FileSystem") or ""),
                    "total_bytes": total,
                    "free_bytes": free,
                    "used_bytes": used,
                    "used_percent": round((used / total) * 100, 2) if total else 0,
                }
            )
        return disks


class NetModule(WmiModule):
    name = "net"

    def collect(self, client):
        rows = client.query_class("Win32_PerfRawData_Tcpip_NetworkInterface")
        interfaces = []
        for row in rows:
            name = str(row.get("Name") or "")
            if not name or name == "_Total":
                continue
            interfaces.append(
                {
                    "interface": name,
                    "rx_bytes": _to_int(row.get("BytesReceivedPersec")),
                    "tx_bytes": _to_int(row.get("BytesSentPersec")),
                    "rx_packets": _to_int(row.get("PacketsReceivedPersec")),
                    "tx_packets": _to_int(row.get("PacketsSentPersec")),
                    "rx_errors": _to_int(row.get("PacketsReceivedErrors")),
                    "tx_errors": _to_int(row.get("PacketsOutboundErrors")),
                    "rx_drops": _to_int(row.get("PacketsReceivedDiscarded")),
                    "tx_drops": _to_int(row.get("PacketsOutboundDiscarded")),
                }
            )
        return interfaces


class DiskIOModule(WmiModule):
    name = "diskio"

    def collect(self, client):
        raw_rows = client.query_class("Win32_PerfRawData_PerfDisk_PhysicalDisk")
        formatted_rows = client.query_class("Win32_PerfFormattedData_PerfDisk_PhysicalDisk")
        formatted_by_name = {str(row.get("Name") or ""): row for row in formatted_rows}
        disks = []
        for row in raw_rows:
            name = str(row.get("Name") or "")
            if not name or name == "_Total":
                continue
            item = {
                "name": name,
                "reads": _to_int(row.get("DiskReadsPersec")),
                "writes": _to_int(row.get("DiskWritesPersec")),
                "read_bytes": _to_int(row.get("DiskReadBytesPersec")),
                "write_bytes": _to_int(row.get("DiskWriteBytesPersec")),
            }
            formatted = formatted_by_name.get(name) or {}
            util = _to_float(formatted.get("PercentDiskTime"))
            if util is not None:
                item["io_util_percent"] = _clamp_percent(util)
            read_sec = _to_float(formatted.get("AvgDiskSecPerRead"))
            if read_sec is not None:
                item["read_latency_ms"] = round(max(read_sec, 0.0) * 1000.0, 4)
            write_sec = _to_float(formatted.get("AvgDiskSecPerWrite"))
            if write_sec is not None:
                item["write_latency_ms"] = round(max(write_sec, 0.0) * 1000.0, 4)
            disks.append(item)
        return disks


class ProcessesModule(WmiModule):
    name = "processes"

    def collect(self, client):
        rows = client.query_class("Win32_Process")
        return {"running": len(rows)}


def _parse_wmi_datetime(value: Any) -> datetime | None:
    raw = str(value or "")
    if len(raw) < 14:
        return None
    try:
        return datetime.strptime(raw[:14], "%Y%m%d%H%M%S").replace(tzinfo=timezone.utc)
    except ValueError:
        return None


class SystemModule(WmiModule):
    name = "system"

    def collect(self, client):
        rows = client.query_class("Win32_OperatingSystem")
        row = rows[0] if rows else {}
        last_boot = _parse_wmi_datetime(row.get("LastBootUpTime"))
        uptime = int((datetime.now(timezone.utc) - last_boot).total_seconds()) if last_boot else 0
        return {"uptime_seconds": max(uptime, 0)}


class EmptyModule(WmiModule):
    def __init__(self, name: str):
        self.name = name

    def collect(self, client):
        return []


MODULE_REGISTRY: dict[str, Callable[[], WmiModule]] = {
    "cpu": CpuModule,
    "mem": MemoryModule,
    "disk": DiskModule,
    "diskio": DiskIOModule,
    "net": NetModule,
    "processes": ProcessesModule,
    "system": SystemModule,
}
