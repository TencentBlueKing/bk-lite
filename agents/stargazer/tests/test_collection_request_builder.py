import pytest
from core.collection.request_builder import build_collection_request


def test_request_rejects_target_count_above_configured_limit(monkeypatch):
    monkeypatch.setenv("MAX_TARGETS_PER_RUN", "2")
    with pytest.raises(ValueError, match="exceeds MAX_TARGETS_PER_RUN"):
        build_collection_request(
            task_id="too-many",
            params={
                "model_id": "mysql",
                "targets": ["10.0.0.1", "10.0.0.2", "10.0.0.3"],
            },
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


def test_builder_normalizes_empty_credential_scope_fields():
    request = build_collection_request(
        task_id="credential-scope",
        params={
            "model_id": "mysql",
            "host": "10.10.24.1",
            "scope_id": "",
            "collect_task_id": "131",
            "credential_set_version": "",
        },
    )

    assert request.params["scope_id"] == "131"
    assert request.params["credential_set_version"] == "default"


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


def test_vmware_legacy_hostname_header_becomes_the_network_target():
    request = build_collection_request(
        task_id="vmware-hostname-header",
        params={
            "model_id": "vmware_vc",
            "plugin_name": "vmware_info",
            "executor_type": "protocol",
            "hostname": "10.10.16.254",
            "port": "443",
            "ssl": "false",
            "username": "readonly",
            "password": "secret",
            "tags": {"instance_id": "cmdb_6"},
        },
    )

    assert request.targets == ("10.10.16.254",)
    assert request.params["target_is_logical"] is False
    assert request.params["hostname"] == "10.10.16.254"
    assert request.credentials[0]["username"] == "readonly"
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


def test_builder_strips_internal_yaml_policy_trust_markers():
    request = build_collection_request(
        task_id="untrusted-policy-marker",
        params={
            "model_id": "mysql",
            "host": "10.10.24.1",
            "target_policy_mode": "cloud_endpoint",
            "trusted_endpoint_domains": ["example.com"],
            "_yaml_target_policy_verified": True,
            "_validated_connect_host": "127.0.0.1",
        },
    )

    assert "target_policy_mode" not in request.params
    assert "trusted_endpoint_domains" not in request.params
    assert "_yaml_target_policy_verified" not in request.params
    assert "_validated_connect_host" not in request.params


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


def test_network_builder_defaults_to_snmp_preflight():
    request = build_collection_request(
        task_id="network-preflight",
        params={
            "model_id": "network",
            "executor_type": "protocol",
            "host": "10.10.69.245",
        },
    )
    assert request.params["preflight_kind"] == "snmp"
    assert int(request.params["port"]) == 161


def test_network_config_file_builder_defaults_to_remote():
    request = build_collection_request(
        task_id="ncf-preflight",
        params={
            "model_id": "network_config_file",
            "executor_type": "protocol",
            "host": "10.10.69.10",
        },
    )
    assert request.params["preflight_kind"] == "remote"
    assert int(request.params["port"]) == 22


def test_pc_windows_builder_dials_winrm_port():
    request = build_collection_request(
        task_id="pc-win-preflight",
        params={
            "model_id": "pc",
            "executor_type": "job",
            "host": "10.10.24.50",
            "os_type": "windows",
            "winrm_scheme": "https",
        },
    )
    assert request.params["preflight_kind"] == "tcp"
    assert int(request.params["port"]) == 5986


def test_pc_macos_builder_dials_ssh():
    request = build_collection_request(
        task_id="pc-mac-preflight",
        params={
            "model_id": "pc",
            "executor_type": "job",
            "host": "10.10.24.51",
            "os_type": "macos",
        },
    )
    assert request.params["preflight_kind"] == "remote"
    assert int(request.params["port"]) == 22


def test_request_digest_changes_when_credential_target_binding_changes():
    first = build_collection_request(
        task_id="credential-binding-digest",
        params={
            "model_id": "network",
            "host": "10.10.69.245",
            "credentials_pool": [
                {
                    "credential_id": "snmp-credential",
                    "target_host": "10.10.69.245",
                    "community": "secret-community",
                }
            ],
        },
    )
    second = build_collection_request(
        task_id="credential-binding-digest",
        params={
            "model_id": "network",
            "host": "10.10.69.245",
            "credentials_pool": [
                {
                    "credential_id": "snmp-credential",
                    "target_host": "10.10.69.246",
                    "community": "secret-community",
                }
            ],
        },
    )

    assert first.digest != second.digest
    assert "secret-community" not in first.digest
