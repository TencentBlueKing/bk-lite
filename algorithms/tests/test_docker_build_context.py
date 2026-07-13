from pathlib import Path

import pytest


ALGORITHMS_DIR = Path(__file__).resolve().parents[1]
SERVICES = (
    "classify_anomaly_server",
    "classify_image_classification_server",
    "classify_log_server",
    "classify_object_detection_server",
    "classify_text_classification_server",
    "classify_timeseries_server",
)
REQUIRED_IGNORES = {
    ".git",
    ".env",
    ".env.*",
    ".venv/",
    "__pycache__/",
    "tests/",
    "support-files/scripts/data/",
}
SERVICE_IGNORES = {
    "classify_image_classification_server": {".yolo_runs/", "yolo_models/"},
    "classify_log_server": {"mlruns/"},
    "classify_object_detection_server": {
        ".vscode/",
        ".yolo_runs/",
        "mlruns/",
        "test_dataset/",
        "yolo_models/",
    },
    "classify_text_classification_server": {"mlruns/"},
    "classify_timeseries_server": {"mlruns/"},
}


@pytest.mark.parametrize("service", SERVICES)
def test_docker_context_excludes_sensitive_and_development_files(service: str) -> None:
    ignore_file = ALGORITHMS_DIR / service / ".dockerignore"

    patterns = {
        line.strip()
        for line in ignore_file.read_text(encoding="utf-8").splitlines()
        if line.strip() and not line.lstrip().startswith("#")
    }

    expected_patterns = REQUIRED_IGNORES | SERVICE_IGNORES.get(service, set())

    assert expected_patterns <= patterns


@pytest.mark.parametrize("service", SERVICES)
def test_dockerfile_copies_local_context_without_add_side_effects(service: str) -> None:
    dockerfile = ALGORITHMS_DIR / service / "support-files/release/Dockerfile"
    instructions = dockerfile.read_text(encoding="utf-8").splitlines()

    assert instructions.count("COPY . .") == 1
    assert "ADD . ." not in instructions
