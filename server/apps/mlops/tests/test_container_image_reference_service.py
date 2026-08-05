import json
import os
import subprocess
from io import StringIO
from pathlib import Path
from types import SimpleNamespace

import pytest
import yaml

from apps.mlops.management.commands.init_algorithm_config import Command
from apps.mlops.models import AlgorithmConfig
from apps.mlops.serializers.algorithm_config import AlgorithmConfigSerializer

pytestmark = pytest.mark.integration

REPO_ROOT = Path(__file__).resolve().parents[4]
KUBERNETES_DIR = REPO_ROOT / "agents/webhookd/mlops/kubernetes"
ALGORITHM_CONFIG_DIR = REPO_ROOT / "server/apps/mlops/support-files/algorithm-configs"

VALID_IMAGE_REFERENCES = [
    "ubuntu",
    "library/ubuntu:22.04",
    "registry.example.com:5000/team/service:v1.2_3",
    "localhost:5000/team/service:release-1",
    "[2001:db8::1]:5000/team/service:v1",
    f"registry.example.com/team/service@sha256:{'a' * 64}",
    f"registry.example.com/team/service:v1@sha256:{'b' * 64}",
]

INVALID_IMAGE_REFERENCES = [
    "https://registry.example.com/team/service:v1",
    "registry.example.com/Team/service:v1",
    "registry.example.com/team//service:v1",
    "registry.example.com/team/service:tag:extra",
    f"registry.example.com/team/service:{'a' * 129}",
    "registry.example.com/team/service:v1\nnot-an-image",
    "registry.example.com/team/service:v1\x1fnot-an-image",
]


class _ImageOnlyAlgorithmConfigSerializer(AlgorithmConfigSerializer):
    class Meta(AlgorithmConfigSerializer.Meta):
        validators = []


def _serializer(image, locale="en"):
    request = SimpleNamespace(user=SimpleNamespace(locale=locale))
    return _ImageOnlyAlgorithmConfigSerializer(
        data={"image": image},
        partial=True,
        context={"request": request},
    )


@pytest.mark.parametrize("image", VALID_IMAGE_REFERENCES)
def test_algorithm_config_serializer_accepts_legacy_image_references(image):
    serializer = _serializer(image)

    assert serializer.is_valid(), serializer.errors


@pytest.mark.parametrize("image", INVALID_IMAGE_REFERENCES)
def test_algorithm_config_serializer_rejects_invalid_image_references(image):
    serializer = _serializer(image)

    assert not serializer.is_valid()
    assert serializer.errors["image"] == ["Enter a valid container image reference"]


def test_init_algorithm_config_rejects_invalid_image_reference(tmp_path):
    config_file = tmp_path / "Example.json"
    config_file.write_text(
        json.dumps(
            {
                "name": "Example",
                "display_name": "Example",
                "image": "registry.example.com/team/service:v1\nnot-an-image",
                "scenario_description": "",
                "form_config": {},
            }
        ),
        encoding="utf-8",
    )

    valid, _, reason = Command()._load_and_validate_file(config_file)

    assert valid is False
    assert reason == "image 不是合法的容器镜像引用"


@pytest.mark.parametrize("image", VALID_IMAGE_REFERENCES)
def test_init_algorithm_config_accepts_legacy_image_references(tmp_path, image):
    config_file = tmp_path / "Example.json"
    payload = {
        "name": "Example",
        "display_name": "Example",
        "image": image,
        "scenario_description": "",
        "form_config": {},
    }
    config_file.write_text(json.dumps(payload), encoding="utf-8")

    assert Command()._load_and_validate_file(config_file) == (True, payload, "")


def _shell_validation_result(image):
    env = os.environ.copy()
    env["IMAGE_UNDER_TEST"] = image
    return subprocess.run(
        [
            "bash",
            "-c",
            'source "$1" && validate_container_image_reference "$IMAGE_UNDER_TEST"',
            "_",
            str(KUBERNETES_DIR / "common.sh"),
        ],
        capture_output=True,
        check=False,
        env=env,
        text=True,
    )


@pytest.mark.parametrize("image", VALID_IMAGE_REFERENCES)
def test_webhookd_validator_accepts_legacy_image_references(image):
    result = _shell_validation_result(image)

    assert result.returncode == 0, result.stderr


@pytest.mark.parametrize("image", INVALID_IMAGE_REFERENCES)
def test_webhookd_validator_rejects_invalid_image_references(image):
    result = _shell_validation_result(image)

    assert result.returncode != 0


def test_checked_in_algorithm_config_images_remain_compatible():
    config_files = sorted(ALGORITHM_CONFIG_DIR.glob("*/*.json"))

    assert config_files
    for config_file in config_files:
        image = json.loads(config_file.read_text(encoding="utf-8"))["image"]
        assert _serializer(image).is_valid(), config_file
        assert _shell_validation_result(image).returncode == 0, config_file


def test_init_algorithm_config_skips_invalid_image_and_reports_reason(monkeypatch):
    class FakeManager:
        def __init__(self):
            self.calls = []

        def get_or_create(self, **kwargs):
            self.calls.append(kwargs)
            return object(), False

    stdout = StringIO()
    stderr = StringIO()
    command = Command(stdout=stdout, stderr=stderr)
    original_loader = command._load_and_validate_file
    invalidated = False

    def load_with_one_invalid_image(config_file):
        nonlocal invalidated
        if not invalidated:
            invalidated = True
            return False, {}, "image 不是合法的容器镜像引用"
        return original_loader(config_file)

    manager = FakeManager()
    monkeypatch.setattr(AlgorithmConfig, "objects", manager, raising=False)
    monkeypatch.setattr(command, "_load_and_validate_file", load_with_one_invalid_image)

    command.handle()

    config_count = sum(1 for _ in ALGORITHM_CONFIG_DIR.glob("*/*.json"))
    assert len(manager.calls) == config_count - 1
    assert "image 不是合法的容器镜像引用" in stderr.getvalue()
    assert "skipped_existing=9, skipped_invalid=1" in stdout.getvalue()


def _write_executable(path, source):
    path.write_text(source, encoding="utf-8")
    path.chmod(0o755)


def _run_kubernetes_script(tmp_path, script_name, image, payload_suffix=""):
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    calls_file = tmp_path / "kubectl-calls"
    manifest_file = tmp_path / "manifest.yaml"
    _write_executable(
        bin_dir / "kubectl",
        """#!/bin/bash
echo "$*" >> "$CALLS_FILE"
case "$1 $2" in
  "get namespace") exit 0 ;;
  "get job"|"get deployment") exit 1 ;;
  "create secret") exit 0 ;;
  "apply -f") cat > "$MANIFEST_FILE"; exit 0 ;;
  "get svc") echo "31001"; exit 0 ;;
esac
exit 0
""",
    )
    payloads = {
        "train.sh": {
            "id": "train-proof",
            "bucket": "datasets",
            "dataset": "data.zip",
            "config": "config.yml",
            "minio_endpoint": "http://minio:9000",
            "mlflow_tracking_uri": "http://mlflow:15000",
            "minio_access_key": "access",
            "minio_secret_key": "secret",
            "device": "cpu",
            "train_image": image,
        },
        "serve.sh": {
            "id": "serve-proof",
            "mlflow_tracking_uri": "http://mlflow:15000",
            "mlflow_model_uri": "models:/example/1",
            "device": "cpu",
            "train_image": image,
        },
    }
    env = os.environ.copy()
    env["PATH"] = f"{bin_dir}:{env['PATH']}"
    env["CALLS_FILE"] = str(calls_file)
    env["MANIFEST_FILE"] = str(manifest_file)
    result = subprocess.run(
        ["bash", str(KUBERNETES_DIR / script_name), json.dumps(payloads[script_name]) + payload_suffix],
        capture_output=True,
        check=False,
        env=env,
        text=True,
    )
    calls = calls_file.read_text(encoding="utf-8") if calls_file.exists() else ""
    manifest = manifest_file.read_text(encoding="utf-8") if manifest_file.exists() else ""
    return result, calls, manifest


@pytest.mark.parametrize("script_name", ["train.sh", "serve.sh"])
@pytest.mark.parametrize("invalid_suffix", ["\nnot-an-image", "\n", "\x00"])
def test_kubernetes_entrypoint_rejects_invalid_image_before_kubectl(tmp_path, script_name, invalid_suffix):
    result, calls, manifest = _run_kubernetes_script(
        tmp_path,
        script_name,
        f"registry.example.com/team/service:v1{invalid_suffix}",
    )

    assert result.returncode != 0
    assert json.loads(result.stdout)["code"] == "INVALID_TRAIN_IMAGE"
    assert calls == ""
    assert manifest == ""


@pytest.mark.parametrize("script_name", ["train.sh", "serve.sh"])
@pytest.mark.parametrize("invalid_suffix", ["\n", "\x00"])
def test_kubernetes_entrypoint_rejects_control_character_with_multiple_json_values(
    tmp_path,
    script_name,
    invalid_suffix,
):
    result, calls, manifest = _run_kubernetes_script(
        tmp_path,
        script_name,
        f"registry.example.com/team/service:v1{invalid_suffix}",
        payload_suffix="\n{}",
    )

    assert result.returncode != 0
    assert json.loads(result.stdout)["code"] == "INVALID_TRAIN_IMAGE"
    assert calls == ""
    assert manifest == ""


@pytest.mark.parametrize("script_name", ["train.sh", "serve.sh"])
@pytest.mark.parametrize(
    "image",
    [
        "registry.example.com:5000/team/service:v1.2_3",
        "[2001:db8::1]:5000/team/service:v1",
    ],
)
def test_kubernetes_entrypoint_keeps_legacy_image_reference_working(tmp_path, script_name, image):
    result, calls, manifest = _run_kubernetes_script(
        tmp_path,
        script_name,
        image,
    )

    assert result.returncode == 0, result.stderr
    assert "apply -f -" in calls
    documents = [document for document in yaml.safe_load_all(manifest) if document]
    workload = next(document for document in documents if document["kind"] in {"Job", "Deployment"})
    assert workload["spec"]["template"]["spec"]["containers"][0]["image"] == image
