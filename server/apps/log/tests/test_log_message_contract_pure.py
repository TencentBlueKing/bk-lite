import json
from pathlib import Path

import pytest
import yaml

from apps.log.services.log_event_contract import (
    to_logical_event,
    to_logical_field,
    to_logical_json_line,
    to_storage_field,
    to_storage_query,
)
from apps.log.services.log_extractor.compiler import compile_system_vector_config


REPOSITORY_ROOT = Path(__file__).resolve().parents[4]
PLUGIN_ROOT = REPOSITORY_ROOT / "server/apps/log/support-files/plugins"
LEGACY_MESSAGE_FIELDS = {"_msg", "log_message", "raw_message", "trap_message"}


@pytest.mark.unit
def test_all_builtin_collect_types_declare_one_canonical_message_field():
    collect_type_files = sorted(PLUGIN_ROOT.glob("*/*/collect_type.json"))

    assert len(collect_type_files) == 18
    for path in collect_type_files:
        attrs = json.loads(path.read_text())["attrs"]
        assert attrs.count("message") == 1, path
        assert LEGACY_MESSAGE_FIELDS.isdisjoint(attrs), path


@pytest.mark.unit
def test_builtin_collectors_do_not_emit_legacy_full_message_copies():
    paths = [
        REPOSITORY_ROOT / "agents/webhookd/bk-lite-log-collector.yaml",
        REPOSITORY_ROOT / "deploy/dist/bk-lite-kubernetes-collector/bk-lite-log-collector.yaml",
        REPOSITORY_ROOT / "server/apps/node_mgmt/support-files/collectors/Auditbeat.json",
        REPOSITORY_ROOT / "server/apps/node_mgmt/support-files/collectors/Packetbeat.json",
        REPOSITORY_ROOT / "server/apps/node_mgmt/support-files/collectors/Vector.json",
        REPOSITORY_ROOT / "server/apps/node_mgmt/support-files/collectors/Winlogbeat.json",
        *PLUGIN_ROOT.glob("*/*/*.j2"),
    ]
    forbidden_snippets = (
        ".log_message = .message",
        ".trap_message =",
        "event.Put('_msg'",
        "JSON.stringify(evt)",
        "_msg: \"\"",
    )

    for path in paths:
        content = path.read_text()
        for snippet in forbidden_snippets:
            assert snippet not in content, f"{path}: {snippet}"


@pytest.mark.unit
def test_system_vector_moves_message_at_the_victoria_logs_adapter_seam():
    config = yaml.safe_load(compile_system_vector_config([]))

    assert list(config["transforms"]) == ["normalize_event", "log_extractors", "prepare_victoria_logs"]
    assert config["transforms"]["log_extractors"]["inputs"] == ["normalize_event"]
    assert config["transforms"]["prepare_victoria_logs"]["inputs"] == ["log_extractors"]
    assert "._msg = del(.message)" in config["transforms"]["prepare_victoria_logs"]["source"]
    assert config["sinks"]["victoria_logs"]["inputs"] == ["prepare_victoria_logs"]


@pytest.mark.unit
def test_system_vector_normalizer_supports_mixed_collector_versions_without_retaining_aliases():
    config = yaml.safe_load(compile_system_vector_config([]))
    source = config["transforms"]["normalize_event"]["source"]

    assert ".message = del(._msg)" in source
    assert ".message = del(.trap_message)" in source
    for field in LEGACY_MESSAGE_FIELDS:
        assert f"del(.{field})" in source
    assert "encode_json(.)" not in source


@pytest.mark.unit
def test_victoria_logs_adapter_hides_physical_message_field_without_copying_it():
    assert to_storage_field("message") == "_msg"
    assert to_storage_field("host") == "host"
    assert to_logical_field("_msg") == "message"
    assert to_logical_event({"_msg": "hello", "host": "node-1"}) == {"message": "hello", "host": "node-1"}


@pytest.mark.unit
def test_logical_message_wins_during_read_compatibility():
    assert to_logical_event({"message": "canonical", "_msg": "legacy", "log_message": "canonical"}) == {"message": "canonical"}
    assert to_logical_event({"message": None, "_msg": "legacy"}) == {"message": "legacy"}
    assert to_logical_event({"collect_type": "snmp_trap", "message": "raw", "trap_message": "parsed"}) == {
        "collect_type": "snmp_trap",
        "message": "parsed",
    }


@pytest.mark.unit
def test_tail_line_exposes_logical_message_and_preserves_non_json_lines():
    assert json.loads(to_logical_json_line('{"_msg":"hello","host":"node-1"}')) == {"message": "hello", "host": "node-1"}
    assert to_logical_json_line("not-json") == "not-json"


@pytest.mark.unit
def test_query_adapter_maps_only_top_level_logical_message_field_filters():
    query = (
        'message:"error" AND nginx.error.message:* AND note:"message:value" '
        '| extract "<value>" from message | fields _time, message, nginx.error.message'
    )

    assert to_storage_query(query) == (
        '_msg:"error" AND nginx.error.message:* AND note:"message:value" '
        '| extract "<value>" from _msg | fields _time, _msg, nginx.error.message'
    )
    assert to_storage_query("message error") == "message error"
