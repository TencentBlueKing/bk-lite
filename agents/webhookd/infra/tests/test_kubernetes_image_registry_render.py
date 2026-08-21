import json
import subprocess
from pathlib import Path

import pytest
import yaml

WEBHOOKD_ROOT = Path(__file__).resolve().parents[2]
SCRIPT = WEBHOOKD_ROOT / "infra/kubernetes.sh"
TEMPLATES = {
    "metric": WEBHOOKD_ROOT / "bk-lite-metric-collector.yaml",
    "resource": WEBHOOKD_ROOT / "bk-lite-resource-collector.yaml",
    "log": WEBHOOKD_ROOT / "bk-lite-log-collector.yaml",
}
DEFAULT_PREFIX = "bk-lite.tencentcloudcr.com/bklite"
VALID_REQUEST = {
    "cluster_name": "prod-k8s",
    "nats_url": "tls://nats.internal:4222",
    "nats_username": "collector",
    "nats_password": "secret",
    "nats_ca": "test-ca",
}


def _render(config_type, image_registry_prefix=None):
    payload = {**VALID_REQUEST, "type": config_type}
    if image_registry_prefix is not None:
        payload["image_registry_prefix"] = image_registry_prefix
    result = subprocess.run(
        ["bash", str(SCRIPT), json.dumps(payload)],
        check=False,
        capture_output=True,
        text=True,
    )
    return result, json.loads(result.stdout)


def _images(yaml_content):
    images = []
    for document in yaml.safe_load_all(yaml_content):
        if not isinstance(document, dict):
            continue
        pod_spec = None
        if document.get("kind") in {"Deployment", "DaemonSet"}:
            pod_spec = document["spec"]["template"]["spec"]
        if pod_spec:
            images.extend(container["image"] for container in pod_spec.get("containers", []))
    return images


@pytest.mark.parametrize("config_type", sorted(TEMPLATES))
def test_default_registry_preserves_public_image_contract(config_type):
    result, response = _render(config_type)

    assert result.returncode == 0, result.stderr
    images = _images(response["yaml"])
    assert images
    assert all(image.startswith(f"{DEFAULT_PREFIX}/") for image in images)
    assert "__IMAGE_REGISTRY_PREFIX__" not in response["yaml"]


@pytest.mark.parametrize("config_type", sorted(TEMPLATES))
def test_custom_registry_only_replaces_prefix(config_type):
    default_result, default_response = _render(config_type)
    custom_result, custom_response = _render(config_type, "harbor.internal:5000/offline/bklite")

    assert default_result.returncode == custom_result.returncode == 0
    default_suffixes = [image.removeprefix(DEFAULT_PREFIX) for image in _images(default_response["yaml"])]
    custom_suffixes = [image.removeprefix("harbor.internal:5000/offline/bklite") for image in _images(custom_response["yaml"])]
    assert custom_suffixes == default_suffixes


@pytest.mark.parametrize(
    "value",
    [
        "https://harbor.internal/bklite",
        "harbor.internal/bklite\nimage:evil",
        'harbor.internal/bklite"}}',
        "harbor.internal/{{template}}",
        "harbor.internal/bklite;curl",
    ],
)
def test_renderer_rejects_invalid_or_injectable_registry(value):
    result, response = _render("metric", value)

    assert result.returncode != 0
    assert response["status"] == "error"
    assert response["message"] == "Invalid image_registry_prefix"


def test_all_webhookd_manifests_use_the_same_registry_placeholder():
    for template in TEMPLATES.values():
        content = template.read_text()
        image_lines = [line.strip() for line in content.splitlines() if line.strip().startswith("image:")]
        assert image_lines
        assert all(line.startswith("image: __IMAGE_REGISTRY_PREFIX__/") for line in image_lines)
        assert DEFAULT_PREFIX not in content
