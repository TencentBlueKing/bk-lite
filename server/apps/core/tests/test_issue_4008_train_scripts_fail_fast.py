import os
import subprocess
from pathlib import Path

import pytest


REPOSITORY_ROOT = Path(__file__).resolve().parents[4]
TRAIN_SCRIPTS = [
    REPOSITORY_ROOT / "algorithms" / service / "support-files" / "scripts" / "train-model.sh"
    for service in (
        "classify_image_classification_server",
        "classify_log_server",
        "classify_object_detection_server",
        "classify_text_classification_server",
        "classify_timeseries_server",
    )
]
REQUIRED_VARIABLES = (
    "MINIO_ENDPOINT",
    "MINIO_ACCESS_KEY",
    "MINIO_SECRET_KEY",
    "MLFLOW_TRACKING_URI",
)


@pytest.mark.parametrize("script", TRAIN_SCRIPTS, ids=lambda path: path.parents[2].name)
def test_train_script_has_no_internal_address_and_valid_shell_syntax(script):
    text = script.read_text()

    assert "10.10.41.149" not in text
    subprocess.run(["bash", "-n", str(script)], check=True)


@pytest.mark.parametrize("script", TRAIN_SCRIPTS, ids=lambda path: path.parents[2].name)
@pytest.mark.parametrize("missing_variable", REQUIRED_VARIABLES)
def test_train_script_fails_fast_when_required_variable_is_missing(script, missing_variable):
    env = os.environ.copy()
    env.update(
        {
            "MINIO_ENDPOINT": "minio:9000",
            "MINIO_ACCESS_KEY": "access-key",
            "MINIO_SECRET_KEY": "secret-key",
            "MLFLOW_TRACKING_URI": "http://mlflow:15000",
        }
    )
    env.pop(missing_variable)

    result = subprocess.run(
        ["bash", str(script)],
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode != 0
    assert missing_variable in result.stderr
    assert "10.10.41.149" not in result.stderr
