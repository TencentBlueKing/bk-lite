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


class CpuModule(WmiModule):
    name = "cpu"

    def collect(self, client):
        rows = client.query_class("Win32_Processor")
        load_values = [float(row.get("LoadPercentage") or 0) for row in rows]
        logical_counts = [int(row.get("NumberOfLogicalProcessors") or 0) for row in rows]
        usage = sum(load_values) / len(load_values) if load_values else 0
        cores = sum(logical_counts) or len(rows)
        return {"usage_percent": round(usage, 2), "core_count": cores}


class MemoryModule(WmiModule):
    name = "mem"

    def collect(self, client):
        rows = client.query_class("Win32_OperatingSystem")
        row = rows[0] if rows else {}
        total = int(row.get("TotalVisibleMemorySize") or 0) * 1024
        free = int(row.get("FreePhysicalMemory") or 0) * 1024
        used = max(total - free, 0)
        used_percent = round((used / total) * 100, 2) if total else 0
        return {
            "total_bytes": total,
            "available_bytes": free,
            "used_bytes": used,
            "used_percent": used_percent,
        }


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


def _to_int(value: Any, default: int = 0) -> int:
    try:
        return int(value or default)
    except (TypeError, ValueError):
        return default


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
        rows = client.query_class("Win32_PerfRawData_PerfDisk_PhysicalDisk")
        disks = []
        for row in rows:
            name = str(row.get("Name") or "")
            if not name or name == "_Total":
                continue
            disks.append(
                {
                    "name": name,
                    "reads": _to_int(row.get("DiskReadsPersec")),
                    "writes": _to_int(row.get("DiskWritesPersec")),
                    "read_bytes": _to_int(row.get("DiskReadBytesPersec")),
                    "write_bytes": _to_int(row.get("DiskWriteBytesPersec")),
                    "io_time_ms": _to_int(row.get("PercentDiskTime")),
                    "read_time_ms": 0,
                    "write_time_ms": 0,
                }
            )
        return disks


class ProcessesModule(WmiModule):
    name = "processes"

    def collect(self, client):
        rows = client.query_class("Win32_Process")
        return {
            "running": len(rows),
            "blocked": 0,
            "sleeping": 0,
            "zombies": 0,
        }


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
        return {
            "uptime_seconds": max(uptime, 0),
            "load1": 0,
            "load5": 0,
            "load15": 0,
        }


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
