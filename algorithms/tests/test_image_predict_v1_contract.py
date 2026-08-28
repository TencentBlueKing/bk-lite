"""图片分类与目标检测在独立运行时中验证同一契约（Issue #4012）。"""

import json
import subprocess
import sys
from pathlib import Path

import pytest

RUNNER = Path(__file__).with_name("image_predict_contract_runner.py")


@pytest.mark.parametrize("service_name", ["image_classification", "object_detection"])
def test_image_predict_v1_contract(service_name):
    result = subprocess.run(
        [sys.executable, str(RUNNER), service_name],
        check=False,
        capture_output=True,
        text=True,
        timeout=30,
    )

    assert result.returncode == 0, result.stderr or result.stdout
    report = json.loads(result.stdout.strip().splitlines()[-1])
    assert report == {
        "contract": "image-predict",
        "service": service_name,
        "version": 1,
    }
