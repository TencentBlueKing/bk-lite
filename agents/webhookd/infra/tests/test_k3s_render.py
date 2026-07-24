import base64
import json
import subprocess
from pathlib import Path

import pytest
import yaml


SCRIPT = Path(__file__).resolve().parents[1] / "k3s.sh"
VALID_REQUEST = {
    "cluster_name": "k3s-prod_1",
    "nats_url": "tls://nats.example:4222",
    "nats_username": "collector",
    "nats_password": "secret-value",
    "nats_ca": "-----BEGIN CERTIFICATE-----\ntest\n-----END CERTIFICATE-----",
}


def _render(payload):
    result = subprocess.run(
        ["bash", str(SCRIPT), json.dumps(payload)],
        check=False,
        capture_output=True,
        text=True,
    )
    return result, json.loads(result.stdout)


@pytest.mark.parametrize("field", sorted(VALID_REQUEST))
def test_k3s_renderer_rejects_missing_required_fields(field):
    payload = {**VALID_REQUEST}
    payload.pop(field)

    result, response = _render(payload)

    assert result.returncode != 0
    assert response["status"] == "error"
    assert response["field"] == field
    assert result.stderr == ""


@pytest.mark.parametrize("field", ["type", "config_type", "distribution"])
def test_k3s_renderer_rejects_platform_switch_fields(field):
    result, response = _render({**VALID_REQUEST, field: "k8s"})

    assert result.returncode != 0
    assert response["status"] == "error"
    assert response["field"] == field


def test_k3s_renderer_returns_only_independent_k3s_resources_and_secret():
    result, response = _render(VALID_REQUEST)

    assert result.returncode == 0
    assert result.stderr == ""
    assert response["status"] == "success"
    assert response["id"] == VALID_REQUEST["cluster_name"]

    documents = [
        document
        for document in yaml.safe_load_all(response["yaml"])
        if document is not None
    ]
    secret = next(
        document
        for document in documents
        if document["kind"] == "Secret"
    )
    assert secret["metadata"] == {
        "name": "k3s-monitor-config-secret",
        "namespace": "bk-lite-k3s-collector",
    }
    assert {
        key: base64.b64decode(value).decode()
        for key, value in secret["data"].items()
    } == {
        "CLUSTER_NAME": VALID_REQUEST["cluster_name"],
        "NATS_URL": VALID_REQUEST["nats_url"],
        "NATS_USERNAME": VALID_REQUEST["nats_username"],
        "NATS_PASSWORD": VALID_REQUEST["nats_password"],
        "ca.crt": VALID_REQUEST["nats_ca"],
    }

    rendered = response["yaml"]
    assert "bk-lite-k3s-collector" in rendered
    assert "bk-lite-collector" not in rendered
    assert "bk-lite-monitor-config-secret" not in rendered
