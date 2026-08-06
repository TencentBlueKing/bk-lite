import pytest

from core.collection_request_builder import build_collection_request


def test_request_rejects_target_count_above_configured_limit(monkeypatch):
    monkeypatch.setenv("MAX_TARGETS_PER_RUN", "2")
    with pytest.raises(ValueError, match="exceeds MAX_TARGETS_PER_RUN"):
        build_collection_request(
            task_id="too-many",
            params={"model_id": "mysql", "targets": ["10.0.0.1", "10.0.0.2", "10.0.0.3"]},
        )


def test_request_rejects_credential_pool_above_configured_limit(monkeypatch):
    monkeypatch.setenv("MAX_CREDENTIALS_PER_RUN", "2")

    with pytest.raises(ValueError, match="exceeds MAX_CREDENTIALS_PER_RUN=2"):
        build_collection_request(
            task_id="too-many-credentials",
            params={
                "model_id": "mysql",
                "host": "10.0.0.1",
                "credentials_pool": [
                    {"credential_id": "c1"},
                    {"credential_id": "c2"},
                    {"credential_id": "c3"},
                ],
            },
        )


def test_builder_keeps_one_run_for_many_ips_and_moves_secrets_to_credentials():
    request = build_collection_request(
        task_id="network-scan-001",
        params={
            "model_id": "mysql",
            "plugin_name": "mysql_info",
            "executor_type": "protocol",
            "hosts": ["10.10.24.1", "10.10.24.2"],
            "credentials_pool": [
                {
                    "credential_id": "credential-1",
                    "username": "root",
                    "password": "secret-1",
                },
                {
                    "credential_id": "credential-2",
                    "username": "readonly",
                    "password": "secret-2",
                },
            ],
        },
    )

    assert request.targets == ("10.10.24.1", "10.10.24.2")
    assert len(request.credentials) == 2
    assert request.params["plugin_family"] == "configuration"
    assert request.params["preflight_kind"] == "tcp"
    assert request.params["port"] == 3306
    assert "password" not in request.params
    assert "credentials_pool" not in request.params
    assert "secret-1" not in request.digest


def test_builder_requires_stable_caller_task_id():
    with pytest.raises(ValueError, match="task_id is required"):
        build_collection_request(
            task_id="",
            params={"model_id": "mysql", "host": "10.10.24.1"},
        )


def test_monitor_builder_uses_the_same_request_contract():
    request = build_collection_request(
        task_id="monitor-001",
        params={
            "monitor_type": "windows_wmi",
            "host": "10.10.24.3",
            "username": "administrator",
            "password": "secret",
        },
    )

    assert request.plugin_ref == "windows_wmi.monitor"
    assert request.params["plugin_family"] == "monitor"
    assert request.targets == ("10.10.24.3",)
    assert request.credentials[0]["username"] == "administrator"
    assert "password" not in request.params


def test_builder_deduplicates_targets_without_changing_order():
    request = build_collection_request(
        task_id="network-scan-duplicates",
        params={
            "model_id": "mysql",
            "hosts": ["10.10.24.2", "10.10.24.1", "10.10.24.2"],
        },
    )

    assert request.targets == ("10.10.24.2", "10.10.24.1")


def test_job_plugin_uses_ssh_preflight_before_collection():
    request = build_collection_request(
        task_id="job-preflight",
        params={
            "model_id": "apache",
            "executor_type": "job",
            "host": "10.10.24.20",
        },
    )

    assert request.params["preflight_kind"] == "remote"
