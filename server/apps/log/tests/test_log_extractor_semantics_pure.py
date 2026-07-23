import pytest

from apps.log.services.log_extractor.semantics import RuleValidationError, execute_rules, normalize_rule


@pytest.mark.unit
def test_copy_reads_nested_path_and_later_rule_reads_its_output():
    rules = [
        normalize_rule(
            {
                "extractor_type": "copy",
                "source_field": "http.status",
                "target_field": "parsed.status",
                "condition": {"conditions": [{"field": "http.method", "op": "==", "value": "GET"}]},
                "config": {},
                "delete_source": False,
            }
        ),
        normalize_rule(
            {
                "extractor_type": "copy",
                "source_field": "parsed.status",
                "target_field": "search.status",
                "condition": {},
                "config": {},
                "delete_source": False,
            }
        ),
    ]

    result = execute_rules({"http": {"method": "GET", "status": 200}}, rules)

    assert [item.status for item in result.results] == ["success", "success"]
    assert result.event["search"]["status"] == 200


@pytest.mark.unit
def test_failed_rule_preserves_event_and_allows_later_rule():
    rules = [
        normalize_rule(
            {
                "extractor_type": "json",
                "source_field": "payload",
                "target_field": "parsed",
                "condition": {},
                "config": {},
                "delete_source": True,
            }
        ),
        normalize_rule(
            {
                "extractor_type": "copy",
                "source_field": "payload",
                "target_field": "raw.copy",
                "condition": {},
                "config": {},
                "delete_source": False,
            }
        ),
    ]

    result = execute_rules({"payload": "not-json"}, rules)

    assert [item.status for item in result.results] == ["failed", "success"]
    assert result.event == {"payload": "not-json", "raw": {"copy": "not-json"}}


@pytest.mark.unit
@pytest.mark.parametrize("target", ["payload", "payload.value", "root"])
def test_delete_source_rejects_output_path_overlap(target):
    source = "payload" if target != "root" else "root.value"

    with pytest.raises(RuleValidationError, match="输出路径与源路径重叠"):
        normalize_rule(
            {
                "extractor_type": "copy",
                "source_field": source,
                "target_field": target,
                "condition": {},
                "config": {},
                "delete_source": True,
            }
        )


@pytest.mark.unit
def test_protected_fields_cannot_be_overwritten_or_deleted():
    with pytest.raises(RuleValidationError, match="保护字段"):
        normalize_rule(
            {
                "extractor_type": "copy",
                "source_field": "message",
                "target_field": "instance_id",
                "condition": {},
                "config": {},
                "delete_source": False,
            }
        )

    with pytest.raises(RuleValidationError, match="保护字段"):
        normalize_rule(
            {
                "extractor_type": "regex",
                "source_field": "message",
                "condition": {},
                "config": {"pattern": r"(?P<instance_id>.+)", "group_mapping": {}},
                "delete_source": False,
            }
        )

    with pytest.raises(RuleValidationError, match="保护字段"):
        normalize_rule(
            {
                "extractor_type": "regex_replace",
                "source_field": "timestamp",
                "condition": {},
                "config": {"pattern": ".+", "replacement": "masked"},
                "delete_source": False,
            }
        )


@pytest.mark.unit
@pytest.mark.parametrize("pattern", [r"value(?=end)", r"(?P<value>.+)-(?P=value)", r"(.)\1"])
def test_regex_rejects_python_constructs_unsupported_by_vector_048(pattern):
    with pytest.raises(RuleValidationError, match="Vector 0.48"):
        normalize_rule(
            {
                "extractor_type": "regex_replace",
                "source_field": "message",
                "target_field": "result",
                "condition": {},
                "config": {"pattern": pattern, "replacement": "masked"},
                "delete_source": False,
            }
        )


@pytest.mark.unit
@pytest.mark.parametrize(
    ("draft", "event", "expected"),
    [
        (
            {"extractor_type": "split", "source_field": "payload", "target_field": "parts.value", "config": {"delimiter": ":", "index": 1}},
            {"payload": "key:value"},
            {"payload": "key:value", "parts": {"value": "value"}},
        ),
        (
            {
                "extractor_type": "kv",
                "source_field": "payload",
                "config": {"key_value_delimiter": "=", "field_delimiter": " ", "field_mapping": {"user": "labels.user"}},
            },
            {"payload": "user=alice ignored=yes"},
            {"payload": "user=alice ignored=yes", "labels": {"user": "alice"}},
        ),
        (
            {
                "extractor_type": "regex",
                "source_field": "payload",
                "config": {"pattern": r"status=(?P<status>\d+)", "group_mapping": {"status": "http.status"}},
            },
            {"payload": "status=201"},
            {"payload": "status=201", "http": {"status": "201"}},
        ),
        (
            {
                "extractor_type": "regex_replace",
                "source_field": "payload",
                "target_field": "masked",
                "config": {"pattern": r"user=(?P<user>\w+)", "replacement": "user=${user}-masked"},
            },
            {"payload": "user=alice"},
            {"payload": "user=alice", "masked": "user=alice-masked"},
        ),
        (
            {"extractor_type": "json", "source_field": "payload", "target_field": "decoded", "config": {}},
            {"payload": '{"ok": true}'},
            {"payload": '{"ok": true}', "decoded": {"ok": True}},
        ),
    ],
)
def test_all_parsing_actions_share_success_contract(draft, event, expected):
    draft.setdefault("condition", {})
    draft.setdefault("delete_source", False)

    result = execute_rules(event, [normalize_rule(draft)])

    assert result.results[0].status == "success"
    assert result.event == expected


@pytest.mark.unit
def test_conditions_use_action_before_snapshot_with_and_or_semantics():
    base = {
        "extractor_type": "copy",
        "source_field": "payload",
        "target_field": "output",
        "config": {},
        "delete_source": False,
    }
    and_rule = normalize_rule(
        {
            **base,
            "condition": {
                "mode": "AND",
                "conditions": [
                    {"field": "level", "op": "==", "value": "error"},
                    {"field": "missing", "op": "!exists"},
                ],
            },
        }
    )
    or_rule = normalize_rule(
        {
            **base,
            "target_field": "fallback",
            "condition": {
                "mode": "OR",
                "conditions": [
                    {"field": "level", "op": "==", "value": "debug"},
                    {"field": "payload", "op": "contains", "value": "timeout"},
                ],
            },
        }
    )

    result = execute_rules({"level": "error", "payload": "request timeout"}, [and_rule, or_rule])

    assert [item.status for item in result.results] == ["success", "success"]

    with pytest.raises(RuleValidationError, match="保护字段"):
        normalize_rule(
            {
                "extractor_type": "copy",
                "source_field": "timestamp",
                "target_field": "parsed.timestamp",
                "condition": {},
                "config": {},
                "delete_source": True,
            }
        )
