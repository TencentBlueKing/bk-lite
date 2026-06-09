from typing import Any, Callable

VALID_MODULES = ("cpu", "mem", "disk", "diskio", "net", "processes", "system")
DEFAULT_MODULES = ("cpu", "mem", "disk", "net")


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
        rows = client.query("SELECT DeviceID, Size, FreeSpace FROM Win32_LogicalDisk WHERE DriveType=3")
        disks = []
        for row in rows:
            total = int(row.get("Size") or 0)
            free = int(row.get("FreeSpace") or 0)
            used = max(total - free, 0)
            disks.append(
                {
                    "device": str(row.get("DeviceID") or ""),
                    "total_bytes": total,
                    "free_bytes": free,
                    "used_bytes": used,
                    "used_percent": round((used / total) * 100, 2) if total else 0,
                }
            )
        return disks


class EmptyModule(WmiModule):
    def __init__(self, name: str):
        self.name = name

    def collect(self, client):
        return []


MODULE_REGISTRY: dict[str, Callable[[], WmiModule]] = {
    "cpu": CpuModule,
    "mem": MemoryModule,
    "disk": DiskModule,
    "diskio": lambda: EmptyModule("diskio"),
    "net": lambda: EmptyModule("net"),
    "processes": lambda: EmptyModule("processes"),
    "system": lambda: EmptyModule("system"),
}
