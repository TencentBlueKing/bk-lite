# -*- coding: utf-8 -*-
"""macOS PC 本机采集测试入口的公共 CLI 合同。"""

import json
import subprocess
import sys
from pathlib import Path


RUNNER = Path(__file__).resolve().parents[1] / "scripts" / "test_pc_macos_local.py"


def _write_script(path: Path, payload: dict) -> None:
    path.write_text(
        "#!/bin/sh\nprintf '%s\\n' " + repr(json.dumps(payload)) + "\n",
        encoding="utf-8",
    )
    path.chmod(0o755)


def test_local_runner_accepts_valid_snapshot_and_redacts_identity(tmp_path):
    hardware_uuid = "12345678-1234-1234-1234-123456789ABC"
    identity = {
        "snapshot_status": "complete",
        "snapshot_id": "identity-snapshot",
        "pc": [{
            "os_type": "macos",
            "host_name": "test-mac",
            "hardware_uuid": hardware_uuid,
            "serial_number": "",
        }],
        "software": [],
        "software_expected_count": 0,
        "software_error_count": 0,
    }
    discovery = {
        "snapshot_status": "complete",
        "snapshot_id": "discovery-snapshot",
        "pc": [{
            "inst_name": f"MAC-{hardware_uuid}",
            "host_name": "test-mac",
            "ip_addr": "",
            "os_type": "macos",
            "hardware_uuid": hardware_uuid,
            "serial_number": "",
            "men": "17179869184",
            "disk": "500000000000",
            "snapshot_id": "discovery-snapshot",
            "software_snapshot_status": "complete",
        }],
        "software": [],
        "software_expected_count": 0,
        "software_error_count": 0,
    }
    _write_script(tmp_path / "pc_macos_identity.sh", identity)
    _write_script(tmp_path / "pc_macos_discover.sh", discovery)

    result = subprocess.run(
        [sys.executable, str(RUNNER), "--script-dir", str(tmp_path)],
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 0, result.stderr
    summary = json.loads(result.stdout)
    assert summary["success"] is True
    assert summary["discovery"]["software_count"] == 0
    assert summary["discovery"]["counts_match"] is True
    assert hardware_uuid not in result.stdout
