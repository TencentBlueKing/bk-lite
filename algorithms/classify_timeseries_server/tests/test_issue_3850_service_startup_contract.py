"""Service-level startup contracts for Issue #3850."""

import json
import os
import subprocess
import sys


def test_invalid_model_config_uses_dummy_only_when_explicitly_enabled():
    env = os.environ.copy()
    env.update(
        {
            "MODEL_SOURCE": "mlflow",
            "MLFLOW_MODEL_URI": "",
            "ALLOW_DUMMY_FALLBACK": "true",
            "SERVING_INSTANCE_ID": "issue-3850-instance",
        }
    )
    code = """
import asyncio
import json
from classify_timeseries_server.serving.models.dummy_model import DummyModel
from classify_timeseries_server.serving.service import MLService

service = MLService()
assert isinstance(service.model, DummyModel)
print(json.dumps(asyncio.run(service.health())))
"""

    result = subprocess.run(
        [sys.executable, "-c", code],
        check=False,
        capture_output=True,
        text=True,
        env=env,
        timeout=30,
    )

    assert result.returncode == 0, result.stderr
    health = json.loads(result.stdout.strip().splitlines()[-1])
    assert health["status"] == "healthy"
    assert health["startup_instance_id"] == "issue-3850-instance"


def test_invalid_model_config_still_fails_when_fallback_is_disabled():
    env = os.environ.copy()
    env.update(
        {
            "MODEL_SOURCE": "mlflow",
            "MLFLOW_MODEL_URI": "",
            "ALLOW_DUMMY_FALLBACK": "false",
        }
    )
    code = """
from classify_timeseries_server.serving.service import MLService
MLService()
"""

    result = subprocess.run(
        [sys.executable, "-c", code],
        check=False,
        capture_output=True,
        text=True,
        env=env,
        timeout=30,
    )

    assert result.returncode != 0
    assert "Service cannot start without a valid model" in result.stderr
