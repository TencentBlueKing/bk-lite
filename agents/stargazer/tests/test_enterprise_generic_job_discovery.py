"""没有产品进程时，通用 JOB 脚本不能把宿主机伪报为目标软件。"""

import json
import os
import subprocess
from pathlib import Path

import pytest

AGENT_ROOT = Path(__file__).resolve().parents[1]
GENERIC_JOB_MODELS = (
    "tonglinkq",
    "tonggtp",
    "ihs",
    "cics",
    "brocade_fc",
    "cisco_fc",
    "informix",
    "sybase",
    "mycat",
    "aix",
    "hpux",
    "hmc",
    "hdfs",
    "yarn",
    "storm",
    "redis_sentinel",
    "bes",
    "apusic",
    "inforsuite_as",
    "gbase8s",
    "oscar",
    "domestic_linux",
)


@pytest.mark.xfail(strict=True, reason="通用 JOB 脚本目前只检查任意进程和宿主机版本，不检测目标软件")
@pytest.mark.parametrize("model_id", GENERIC_JOB_MODELS)
def test_generic_job_does_not_discover_product_from_unrelated_process(tmp_path, model_id):
    fake_bin = tmp_path / "bin"
    fake_bin.mkdir()
    fake_ps = fake_bin / "ps"
    fake_ps.write_text("#!/bin/sh\nprintf 'UID PID CMD\\nroot 1 /usr/bin/sleep\\n'\n")
    fake_ps.chmod(0o755)
    fake_uname = fake_bin / "uname"
    fake_uname.write_text("#!/bin/sh\nprintf 'MockOS 1\\n'\n")
    fake_uname.chmod(0o755)
    script = AGENT_ROOT / "enterprise/plugins/inputs" / model_id / f"{model_id}_default_discover.sh"
    result = subprocess.run(
        ["bash", str(script)],
        capture_output=True,
        text=True,
        check=False,
        env={**os.environ, "PATH": f"{fake_bin}:{os.environ['PATH']}"},
    )
    assert result.returncode == 0, (model_id, result.stderr)
    records = [json.loads(line) for line in result.stdout.splitlines() if line.strip()]
    assert not any(record.get("object_type") == model_id for record in records), model_id
