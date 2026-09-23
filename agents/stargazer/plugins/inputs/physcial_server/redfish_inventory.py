# -*- coding: utf-8 -*-
"""Redfish 标准资源到物理服务器库存字段的纯映射。"""
from typing import Any, Dict, List, Optional

from plugins.inputs.physcial_server.server_info_parse import normalize_nic_mac

_INSTRUCTION_SET_MAP = {
    "x86-64": "x86_64",
    "x86": "i686",
    "ARM-A64": "aarch64",
    "ARM-A32": "armv7l",
}

_GPU_PROCESSOR_TYPES = frozenset({"GPU", "Accelerator"})


def _is_absent(record: Dict[str, Any]) -> bool:
    status = record.get("Status")
    if not isinstance(status, dict):
        return False
    return status.get("State") == "Absent"


def _non_empty(value: Any) -> Optional[str]:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _set_field(target: Dict[str, Any], key: str, value: Any) -> None:
    if value is None:
        return
    if isinstance(value, str) and not value.strip():
        return
    target[key] = value


def _processor_type(record: Dict[str, Any]) -> str:
    return str(record.get("ProcessorType") or "CPU")


def _is_gpu_processor(record: Dict[str, Any]) -> bool:
    return _processor_type(record) in _GPU_PROCESSOR_TYPES


def _map_cpu_fields(processors: List[Dict[str, Any]], target: Dict[str, Any]) -> None:
    active_cpus = [processor for processor in processors if not _is_absent(processor) and not _is_gpu_processor(processor)]
    if not active_cpus:
        return

    vendor_model_source = active_cpus[0]
    _set_field(target, "cpu_vendor", _non_empty(vendor_model_source.get("Manufacturer")))
    _set_field(target, "cpu_model", _non_empty(vendor_model_source.get("Model")))

    cores = sum(processor["TotalCores"] for processor in active_cpus if isinstance(processor.get("TotalCores"), int))
    threads = sum(processor["TotalThreads"] for processor in active_cpus if isinstance(processor.get("TotalThreads"), int))
    if cores:
        target["cpu_cores"] = cores
    if threads:
        target["cpu_threads"] = threads

    instruction_set = _non_empty(vendor_model_source.get("InstructionSet"))
    if instruction_set and instruction_set in _INSTRUCTION_SET_MAP:
        target["cpu_arch"] = _INSTRUCTION_SET_MAP[instruction_set]


def _map_gpu_items(processors: List[Dict[str, Any]], ip_addr: str) -> List[Dict[str, Any]]:
    items: List[Dict[str, Any]] = []
    for processor in processors:
        if _is_absent(processor) or not _is_gpu_processor(processor):
            continue
        gpu_name = _non_empty(processor.get("Name")) or _non_empty(processor.get("Id"))
        if not gpu_name:
            continue
        item: Dict[str, Any] = {
            "gpu_name": gpu_name,
            "gpu_type": _processor_type(processor),
            "self_device": ip_addr,
        }
        _set_field(item, "gpu_desc", _non_empty(processor.get("Model")))
        items.append(item)
    return items


def _pick_system_board(assemblies: List[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
    boards = [assembly for assembly in assemblies if assembly.get("PhysicalContext") == "SystemBoard"]
    if not boards:
        return None
    for board in boards:
        if _non_empty(board.get("SerialNumber")):
            return board
    return boards[0]


def _map_board_fields(assemblies: List[Dict[str, Any]], target: Dict[str, Any]) -> None:
    board = _pick_system_board(assemblies)
    if board is None:
        return
    _set_field(target, "board_vendor", _non_empty(board.get("Vendor")))
    _set_field(target, "board_model", _non_empty(board.get("Model")))
    _set_field(target, "board_serial", _non_empty(board.get("SerialNumber")))


def _map_memory_items(memory: List[Dict[str, Any]], ip_addr: str) -> List[Dict[str, Any]]:
    items: List[Dict[str, Any]] = []
    for record in memory:
        if _is_absent(record):
            continue
        locator = _non_empty(record.get("DeviceLocator")) or _non_empty(record.get("Id"))
        if not locator:
            continue
        item: Dict[str, Any] = {"mem_locator": locator, "self_device": ip_addr}
        _set_field(item, "mem_part_number", _non_empty(record.get("PartNumber")))
        _set_field(item, "mem_type", _non_empty(record.get("MemoryDeviceType")))
        _set_field(item, "mem_sn", _non_empty(record.get("SerialNumber")))
        capacity_mib = record.get("CapacityMiB")
        if isinstance(capacity_mib, int) and capacity_mib > 0:
            mem_size = capacity_mib // 1024
            if mem_size:
                item["mem_size"] = mem_size
        items.append(item)
    return items


def _map_disk_items(drives: List[Dict[str, Any]], ip_addr: str) -> List[Dict[str, Any]]:
    items: List[Dict[str, Any]] = []
    for record in drives:
        if _is_absent(record):
            continue
        disk_name = _non_empty(record.get("Id")) or _non_empty(record.get("Name"))
        if not disk_name:
            continue
        item: Dict[str, Any] = {"disk_name": disk_name, "self_device": ip_addr}
        _set_field(item, "disk_vendor", _non_empty(record.get("Manufacturer")))
        _set_field(item, "disk_type", _non_empty(record.get("MediaType")))
        _set_field(item, "disk_sn", _non_empty(record.get("SerialNumber")))
        capacity_bytes = record.get("CapacityBytes")
        if isinstance(capacity_bytes, int) and capacity_bytes > 0:
            disk_gb = capacity_bytes // (1024**3)
            if disk_gb:
                item["disk"] = disk_gb
        items.append(item)
    return items


def _extract_nic_mac(record: Dict[str, Any]) -> str:
    function = record.get("function") or {}
    ethernet = function.get("Ethernet") or {}
    raw_mac = ethernet.get("MACAddress")
    if raw_mac is None:
        raw_mac = function.get("MACAddress")
    return normalize_nic_mac(raw_mac)


def _map_nic_items(nic_records: List[Dict[str, Any]], ip_addr: str) -> List[Dict[str, Any]]:
    items: List[Dict[str, Any]] = []
    seen_macs: set[str] = set()
    for record in nic_records:
        mac = _extract_nic_mac(record)
        if not mac or mac in seen_macs:
            continue
        seen_macs.add(mac)
        adapter = record.get("adapter") or {}
        function = record.get("function") or {}
        item: Dict[str, Any] = {"nic_mac": mac, "self_device": ip_addr}
        _set_field(item, "nic_vendor", _non_empty(adapter.get("Manufacturer")))
        _set_field(item, "nic_model", _non_empty(adapter.get("Model")))
        _set_field(item, "nic_type", _non_empty(function.get("NetDevFuncType")))
        items.append(item)
    return items


def build_redfish_result(
    server: Dict[str, Any],
    *,
    processors: Optional[List[Dict[str, Any]]],
    memory: Optional[List[Dict[str, Any]]],
    drives: Optional[List[Dict[str, Any]]],
    nic_records: Optional[List[Dict[str, Any]]],
    assemblies: Optional[List[Dict[str, Any]]],
) -> Dict[str, Any]:
    ip_addr = server.get("ip_addr", "")
    mapped_server: Dict[str, Any] = {}
    for key, value in server.items():
        if isinstance(value, str):
            if value.strip():
                mapped_server[key] = value
        elif value is not None:
            mapped_server[key] = value

    if processors is not None:
        _map_cpu_fields(processors, mapped_server)

    if assemblies is not None:
        _map_board_fields(assemblies, mapped_server)

    result: Dict[str, Any] = {"physcial_server": [mapped_server]}

    if processors is not None:
        gpu_items = _map_gpu_items(processors, ip_addr)
        if gpu_items:
            result["gpu"] = gpu_items

    if memory is not None:
        memory_items = _map_memory_items(memory, ip_addr)
        if memory_items:
            result["memory"] = memory_items

    if drives is not None:
        disk_items = _map_disk_items(drives, ip_addr)
        if disk_items:
            result["disk"] = disk_items

    if nic_records is not None:
        nic_items = _map_nic_items(nic_records, ip_addr)
        if nic_items:
            result["nic"] = nic_items

    return result
