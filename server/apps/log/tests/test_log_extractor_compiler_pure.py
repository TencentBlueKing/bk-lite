from types import SimpleNamespace

import pytest
import yaml

from apps.log.services.log_extractor.compiler import compile_system_vector_config, get_system_vector_config_contract_version


@pytest.mark.unit
def test_complete_config_declares_platform_contract_version():
    content = compile_system_vector_config([])

    assert content.startswith("# bk-lite-system-vector-contract-version: 1\n")
    assert get_system_vector_config_contract_version(content) == 1


@pytest.mark.unit
@pytest.mark.parametrize(
    "content",
    [
        "sources: {}\n",
        "# bk-lite-system-vector-contract-version: invalid\nsources: {}\n",
        "# bk-lite-system-vector-contract-version: -1\nsources: {}\n",
    ],
)
def test_legacy_or_invalid_snapshot_has_contract_version_zero(content):
    assert get_system_vector_config_contract_version(content) == 0


@pytest.mark.unit
def test_no_rules_compile_to_complete_noop_topology():
    content = compile_system_vector_config([])
    config = yaml.safe_load(content)

    assert set(config) == {"sources", "transforms", "sinks"}
    assert config["transforms"]["log_extractors"]["source"] == ". = ."
    assert config["sinks"]["victoria_logs"]["inputs"] == ["prepare_victoria_logs"]
    assert config["sources"]["server_nats"]["url"] == "${VECTOR_NATS_SERVERS}"
    assert config["sources"]["server_nats"]["decoding"] == {"codec": "json"}
    assert config["sources"]["server_nats"]["log_namespace"] is True
    assert config["sources"]["server_nats"]["tls"] == {
        "enabled": "${VECTOR_NATS_TLS_ENABLED}",
        "ca_file": "${VECTOR_NATS_TLS_CA_FILE}",
        "verify_certificate": True,
    }
    assert "enabled: ${VECTOR_NATS_TLS_ENABLED}" in content
    assert "enabled: '${VECTOR_NATS_TLS_ENABLED}'" not in content
    assert config["sinks"]["victoria_logs"]["framing"] == {"method": "newline_delimited"}
    assert "_msg_field=_msg" in config["sinks"]["victoria_logs"]["uri"]
    assert "_time_field=timestamp" in config["sinks"]["victoria_logs"]["uri"]


@pytest.mark.unit
def test_rules_from_multiple_instances_share_one_stable_config():
    rules = [
        SimpleNamespace(
            id=2,
            collect_instance_id="region-b-instance",
            extractor_type="copy",
            source_field="message",
            target_field="parsed.message",
            condition={},
            config={},
            delete_source=False,
            sort_order=0,
        ),
        SimpleNamespace(
            id=1,
            collect_instance_id="region-a-instance",
            extractor_type="copy",
            source_field="message",
            target_field="parsed.message",
            condition={},
            config={},
            delete_source=False,
            sort_order=0,
        ),
    ]

    first = compile_system_vector_config(rules)
    second = compile_system_vector_config(list(reversed(rules)))

    assert first == second
    assert 'instance_id == "region-a-instance"' in first
    assert 'instance_id == "region-b-instance"' in first
    assert "cloud_region" not in first


@pytest.mark.unit
def test_user_strings_cannot_trigger_vector_environment_interpolation():
    rule = SimpleNamespace(
        id=1,
        collect_instance_id="instance-${HOME}",
        extractor_type="copy",
        source_field="message",
        target_field="parsed.message",
        condition={"conditions": [{"field": "message", "op": "contains", "value": "${HOME}"}]},
        config={},
        delete_source=False,
        sort_order=0,
    )

    content = compile_system_vector_config([rule])

    assert "instance-$${HOME}" in content
    assert 'contains(string!(.message), "$${HOME}")' in content


@pytest.mark.unit
def test_type_scoped_rules_match_collect_type_not_instance_id():
    rules = [
        SimpleNamespace(
            id=1,
            collect_instance_id=None,
            collect_type=SimpleNamespace(name="syslog"),
            extractor_type="copy",
            source_field="message",
            target_field="parsed.message",
            condition={},
            config={},
            delete_source=False,
            sort_order=0,
        ),
        SimpleNamespace(
            id=2,
            collect_instance_id="nginx-1",
            collect_type=None,
            extractor_type="copy",
            source_field="message",
            target_field="parsed.message",
            condition={},
            config={},
            delete_source=False,
            sort_order=0,
        ),
        SimpleNamespace(
            id=3,
            collect_instance_id=None,
            collect_type=SimpleNamespace(name="snmp_trap"),
            extractor_type="copy",
            source_field="message",
            target_field="parsed.trap",
            condition={},
            config={},
            delete_source=False,
            sort_order=0,
        ),
    ]

    content = compile_system_vector_config(rules)

    assert '.collect_type == "syslog"' in content
    assert '.collect_type == "snmp_trap"' in content
    assert 'instance_id == "nginx-1"' in content
    assert "instance_id == \"None\"" not in content
    assert ".instance_id == \"base\"" not in content
