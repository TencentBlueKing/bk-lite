"""主机机器类型：采集结果只接受虚拟机、物理服务器、未知。"""

from __future__ import annotations

from typing import Any

MACHINE_TYPE_UNKNOWN = "unknown"
MACHINE_TYPE_VIRTUAL = "virtual"
MACHINE_TYPE_PHYSICAL_SERVER = "physical_server"
POSITIVE_MACHINE_TYPES = frozenset({MACHINE_TYPE_VIRTUAL, MACHINE_TYPE_PHYSICAL_SERVER})
MACHINE_TYPES = POSITIVE_MACHINE_TYPES | {MACHINE_TYPE_UNKNOWN}


def normalize_machine_type(value: Any) -> str:
    text = str(value or "").strip().lower()
    if text in MACHINE_TYPES:
        return text
    return MACHINE_TYPE_UNKNOWN


def preserve_collected_host_machine_type(old_rows: list | None, new_rows: list | None) -> None:
    """未知采集结果保留实例上已经识别出的虚拟机或物理服务器。"""
    previous: dict[str, str] = {}
    for row in old_rows or []:
        if not isinstance(row, dict):
            continue
        inst_name = str(row.get("inst_name") or "").strip()
        if not inst_name or inst_name in previous:
            continue
        machine_type = normalize_machine_type(row.get("machine_type"))
        if machine_type in POSITIVE_MACHINE_TYPES:
            previous[inst_name] = machine_type

    for row in new_rows or []:
        if not isinstance(row, dict):
            continue
        detected = normalize_machine_type(row.get("machine_type"))
        if detected in POSITIVE_MACHINE_TYPES:
            row["machine_type"] = detected
            continue
        inst_name = str(row.get("inst_name") or "").strip()
        row["machine_type"] = previous.get(inst_name, MACHINE_TYPE_UNKNOWN)
