#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""在 macOS 本机执行并验证 PC 身份/全量发现脚本。

输出仅包含脱敏后的协议摘要，不展示硬件 UUID、序列号或软件明细。
"""

from __future__ import annotations

import argparse
import json
import platform
import re
import subprocess
import sys
from pathlib import Path
from typing import Any


UUID_RE = re.compile(
    r"^[0-9A-Fa-f]{8}-[0-9A-Fa-f]{4}-[0-9A-Fa-f]{4}-"
    r"[0-9A-Fa-f]{4}-[0-9A-Fa-f]{12}$"
)
SCRIPT_NAMES = ("pc_macos_identity.sh", "pc_macos_discover.sh")


class ContractError(RuntimeError):
    """脚本输出不满足 PC 采集公开协议。"""


def _run_script(path: Path, timeout: int) -> dict[str, Any]:
    if not path.is_file():
        raise ContractError(f"脚本不存在: {path}")
    result = subprocess.run(
        ["/bin/sh", str(path)],
        capture_output=True,
        text=True,
        timeout=timeout,
        check=False,
    )
    if result.returncode != 0:
        raise ContractError(f"脚本执行失败: {path.name} (exit={result.returncode})")
    try:
        payload = json.loads(result.stdout)
    except json.JSONDecodeError as exc:
        raise ContractError(f"脚本输出不是合法 JSON: {path.name}") from exc
    if not isinstance(payload, dict):
        raise ContractError(f"脚本输出顶层必须是对象: {path.name}")
    return payload


def _single_pc(payload: dict[str, Any], script_name: str) -> dict[str, Any]:
    pcs = payload.get("pc")
    if not isinstance(pcs, list) or len(pcs) != 1 or not isinstance(pcs[0], dict):
        raise ContractError(f"{script_name} 必须返回且只返回一台 PC")
    pc = pcs[0]
    if pc.get("os_type") != "macos":
        raise ContractError(f"{script_name} 的 os_type 必须是 macos")
    hardware_uuid = str(pc.get("hardware_uuid") or "")
    serial_number = str(pc.get("serial_number") or "").strip()
    if hardware_uuid and not UUID_RE.fullmatch(hardware_uuid):
        raise ContractError(f"{script_name} 返回了非标准硬件 UUID")
    if not hardware_uuid and not serial_number:
        raise ContractError(f"{script_name} 缺少可用的硬件 UUID 或序列号")
    return pc


def _validate_identity(payload: dict[str, Any]) -> dict[str, Any]:
    if payload.get("snapshot_status") != "complete":
        raise ContractError("身份脚本未返回 complete 快照")
    pc = _single_pc(payload, "pc_macos_identity.sh")
    software = payload.get("software")
    if software != [] or payload.get("software_expected_count") != 0:
        raise ContractError("身份脚本不得枚举安装软件")
    return {
        "snapshot_status": "complete",
        "os_type": "macos",
        "host_name_present": bool(str(pc.get("host_name") or "").strip()),
        "identity_present": True,
        "software_scanned": False,
    }


def _validate_discovery(payload: dict[str, Any]) -> dict[str, Any]:
    status = payload.get("snapshot_status")
    if status not in {"complete", "partial"}:
        raise ContractError("全量脚本必须返回 complete 或 partial 快照")
    pc = _single_pc(payload, "pc_macos_discover.sh")
    snapshot_id = str(payload.get("snapshot_id") or "")
    if not snapshot_id or pc.get("snapshot_id") != snapshot_id:
        raise ContractError("PC 记录必须关联当前 snapshot_id")
    if not str(pc.get("inst_name") or "").startswith("MAC-"):
        raise ContractError("全量脚本没有生成稳定的 Mac 实例名")

    software = payload.get("software")
    expected_count = payload.get("software_expected_count")
    error_count = payload.get("software_error_count")
    if not isinstance(software, list):
        raise ContractError("software 必须是数组")
    if expected_count != len(software):
        raise ContractError("software_expected_count 与实际软件数量不一致")
    if not isinstance(error_count, int) or error_count < 0:
        raise ContractError("software_error_count 必须是非负整数")
    if status == "complete" and error_count != 0:
        raise ContractError("complete 快照不得包含软件读取错误")
    for item in software:
        if not isinstance(item, dict):
            raise ContractError("软件记录必须是对象")
        if item.get("pc_inst_name") != pc.get("inst_name"):
            raise ContractError("软件记录必须关联当前 PC")
        if item.get("snapshot_id") != snapshot_id:
            raise ContractError("软件记录必须关联当前快照")
        if item.get("source") != "macos_application":
            raise ContractError("macOS 软件来源必须是 macos_application")

    return {
        "snapshot_status": status,
        "os_type": "macos",
        "host_name_present": bool(str(pc.get("host_name") or "").strip()),
        "identity_present": True,
        "memory_present": str(pc.get("men") or "").isdigit(),
        "disk_present": str(pc.get("disk") or "").isdigit(),
        "software_count": len(software),
        "software_error_count": error_count,
        "counts_match": True,
    }


def _default_script_dir() -> Path:
    return (
        Path(__file__).resolve().parents[1]
        / "enterprise"
        / "plugins"
        / "inputs"
        / "pc"
    )


def main() -> int:
    parser = argparse.ArgumentParser(description="验证本机 macOS PC 采集脚本")
    parser.add_argument("--script-dir", type=Path, default=_default_script_dir())
    parser.add_argument("--timeout", type=int, default=120)
    args = parser.parse_args()

    if platform.system() != "Darwin" and "--script-dir" not in sys.argv:
        print("仅支持在 macOS 本机运行", file=sys.stderr)
        return 2

    try:
        identity = _run_script(args.script_dir / SCRIPT_NAMES[0], args.timeout)
        discovery = _run_script(args.script_dir / SCRIPT_NAMES[1], args.timeout)
        summary = {
            "success": True,
            "script_dir": str(args.script_dir),
            "identity": _validate_identity(identity),
            "discovery": _validate_discovery(discovery),
        }
    except (ContractError, subprocess.TimeoutExpired) as exc:
        print(str(exc), file=sys.stderr)
        return 1

    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
