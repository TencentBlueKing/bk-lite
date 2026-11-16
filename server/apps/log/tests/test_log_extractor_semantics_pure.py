import re

import pytest

from apps.log.services.log_extractor.semantics import RuleValidationError, execute_rules, format_path, normalize_rule, parse_path


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
def test_collect_timestamp_cannot_be_overwritten_or_deleted():
    with pytest.raises(RuleValidationError, match="保护字段"):
        normalize_rule(
            {
                "extractor_type": "copy",
                "source_field": "message",
                "target_field": "collect_timestamp",
                "condition": {},
                "config": {},
                "delete_source": False,
            }
        )

    with pytest.raises(RuleValidationError, match="保护字段"):
        normalize_rule(
            {
                "extractor_type": "regex_replace",
                "source_field": "collect_timestamp",
                "condition": {},
                "config": {"pattern": ".+", "replacement": "masked"},
                "delete_source": False,
            }
        )


@pytest.mark.unit
@pytest.mark.parametrize("target", ["_msg", "log_message", "raw_message", "trap_message"])
def test_legacy_message_aliases_cannot_be_reintroduced(target):
    with pytest.raises(RuleValidationError, match="保护字段"):
        normalize_rule(
            {
                "extractor_type": "copy",
                "source_field": "message",
                "target_field": target,
                "condition": {},
                "config": {},
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


@pytest.mark.unit
@pytest.mark.parametrize(
    ("raw", "segments"),
    [
        ("@timestamp", ("@timestamp",)),
        ("@metadata.beat", ("@metadata", "beat")),
        ('["@metadata"].beat', ("@metadata", "beat")),
    ],
)
def test_parse_path_accepts_filebeat_at_fields(raw, segments):
    assert parse_path(raw) == segments
    assert parse_path(format_path(segments)) == segments


@pytest.mark.unit
def test_copy_preview_reads_restored_filebeat_metadata_path():
    rule = normalize_rule(
        {
            "extractor_type": "copy",
            "source_field": "@metadata.beat",
            "target_field": "beat_name",
            "condition": {},
            "config": {},
            "delete_source": False,
        }
    )

    result = execute_rules({"@metadata": {"beat": "filebeat"}, "@timestamp": "2026-09-15T02:51:41.979Z"}, [rule])

    assert [item.status for item in result.results] == ["success"]
    assert result.event["beat_name"] == "filebeat"


@pytest.mark.unit
def test_empty_or_condition_runs_like_empty_and_and_compiler_true():
    base = {
        "extractor_type": "copy",
        "source_field": "message",
        "config": {},
        "delete_source": False,
    }
    empty_or = normalize_rule(
        {
            **base,
            "target_field": "copied.or",
            "condition": {"mode": "OR", "conditions": []},
        }
    )
    empty_and = normalize_rule(
        {
            **base,
            "target_field": "copied.and",
            "condition": {"mode": "AND", "conditions": []},
        }
    )
    matching_or = normalize_rule(
        {
            **base,
            "target_field": "copied.match",
            "condition": {
                "mode": "OR",
                "conditions": [
                    {"field": "message", "op": "==", "value": "other"},
                    {"field": "message", "op": "==", "value": "hello"},
                ],
            },
        }
    )
    missing_or = normalize_rule(
        {
            **base,
            "target_field": "copied.miss",
            "condition": {
                "mode": "OR",
                "conditions": [
                    {"field": "message", "op": "==", "value": "other"},
                    {"field": "level", "op": "==", "value": "debug"},
                ],
            },
        }
    )

    result = execute_rules({"message": "hello"}, [empty_or, empty_and, matching_or, missing_or])

    assert [item.status for item in result.results] == ["success", "success", "success", "not_matched"]
    assert result.event["copied"]["or"] == "hello"
    assert result.event["copied"]["and"] == "hello"
    assert result.event["copied"]["match"] == "hello"
    assert "miss" not in result.event["copied"]


@pytest.mark.unit
@pytest.mark.parametrize(
    ("pattern", "replacement", "payload", "expected"),
    [
        (r"(a)", "${1}", "a", "a"),
        (r"user=(?P<user>\w+)", "user=${user}-masked", "user=alice", "user=alice-masked"),
        (r"(a)", "$$", "a", "$"),
        (r"(a)?(b)", "${1}${2}", "b", "b"),
    ],
    ids=["numbered", "named", "literal-dollar", "unmatched-optional"],
)
def test_regex_replace_expands_capture_references(pattern, replacement, payload, expected):
    rule = normalize_rule(
        {
            "extractor_type": "regex_replace",
            "source_field": "payload",
            "target_field": "result",
            "condition": {},
            "config": {"pattern": pattern, "replacement": replacement},
            "delete_source": False,
        }
    )

    result = execute_rules({"payload": payload}, [rule])

    assert result.results[0].status == "success"
    assert result.event == {"payload": payload, "result": expected}


@pytest.mark.unit
def test_regex_replace_rejects_missing_numbered_group():
    with pytest.raises(RuleValidationError, match="不存在的捕获组"):
        normalize_rule(
            {
                "extractor_type": "regex_replace",
                "source_field": "payload",
                "target_field": "result",
                "condition": {},
                "config": {"pattern": r"(a)", "replacement": "${2}"},
                "delete_source": False,
            }
        )


def _grok(pattern, **overrides):
    draft = {
        "extractor_type": "grok",
        "source_field": "message",
        "condition": {},
        "config": {"pattern": pattern},
        "delete_source": False,
    }
    draft.update(overrides)
    return draft


@pytest.mark.unit
@pytest.mark.parametrize(
    ("pattern", "message"),
    [
        ("%{NOPE:client}", "引用 1 的模式 NOPE 不存在"),
        ("%{WORD:client} %{NOPE:host}", "引用 2 的模式 NOPE 不存在"),
        ("%{NUMBER:bytes:int}", "引用 1（NUMBER）Grok 只写出字符串，如需数值比较请在查询中转换"),
        ("%{COMBINEDAPACHELOG:client}", "引用 1 不能给复合模式 COMBINEDAPACHELOG 命名"),
        ("%{WORD:http} %{WORD:http.method}", "写出路径重叠: http 与 http.method"),
        ("%{WORD:client} %{NOTSPACE:client}", "写出路径重复: client"),
        ("%{WORD:timestamp}", "不能覆盖系统保护字段 timestamp"),
        ("%{WORD:message}", "不能写出 message"),
        ("(?P<name>[A-Z]+)%{WORD:value}", "Grok 字面量不能包含命名捕获组"),
        ("(?=end)%{WORD:value}", "Vector 0.48"),
        ("[%{WORD:value}", "pattern 不是有效正则"),
        ("", "pattern 长度必须为 1 到 2000"),
        ("a" * 2001, "pattern 长度必须为 1 到 2000"),
        ("%{WORD}", "Grok 模式没有写出字段"),
        ("%{WORD:client", "引用 1 语法无效"),
        ("%{WORD:http-status}", "属性路径无效"),
    ],
)
def test_grok_rule_rejections_name_the_reference(pattern, message):
    with pytest.raises(RuleValidationError, match=re.escape(message)):
        normalize_rule(_grok(pattern))


@pytest.mark.unit
def test_grok_rejects_more_than_64_references_and_oversized_expansion():
    too_many = " ".join(f"%{{WORD:f{index}}}" for index in range(65))
    with pytest.raises(RuleValidationError, match="引用数上限 64"):
        normalize_rule(_grok(too_many))

    too_long = " ".join(f"%{{IPV6:f{index:02d}}}" for index in range(40))
    with pytest.raises(RuleValidationError, match="16384"):
        normalize_rule(_grok(too_long))


@pytest.mark.unit
def test_grok_rejects_target_field_unknown_config_and_source_overlap():
    with pytest.raises(RuleValidationError, match="不接受单一目标属性"):
        normalize_rule(_grok("%{WORD:event.action}", target_field="event.action"))
    with pytest.raises(RuleValidationError, match="未声明字段"):
        normalize_rule(_grok("%{WORD:event.action}", config={"pattern": "%{WORD:event.action}", "group_mapping": {}}))
    with pytest.raises(RuleValidationError, match="输出路径与源路径重叠"):
        normalize_rule(_grok("%{WORD:http}", source_field="http.method", delete_source=True))
