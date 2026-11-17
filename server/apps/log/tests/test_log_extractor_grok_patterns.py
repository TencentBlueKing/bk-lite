import re

import pytest

from apps.log.services.log_extractor.grok import expand_grok
from apps.log.services.log_extractor.grok_library import GROK_CATEGORIES, GROK_PATTERNS, grok_catalog
from apps.log.services.log_extractor.semantics import (
    PROTECTED_FIELDS,
    _ensure_vector_regex_compatible,
    _execute_rules_inline,
    execute_rules,
    normalize_rule,
)


def _draft(pattern):
    return {
        "extractor_type": "grok",
        "source_field": "message",
        "condition": {},
        "config": {"pattern": pattern},
        "delete_source": False,
    }


def _with_output(event, path, value):
    current = event
    segments = path.split(".")
    for segment in segments[:-1]:
        current = current.setdefault(segment, {})
    current[segments[-1]] = value
    return event


@pytest.mark.unit
def test_grok_catalog_shape_follows_request_language():
    english = grok_catalog("en")
    chinese = grok_catalog("zh-Hans")

    assert [item["name"] for item in english] == [pattern.name for pattern in GROK_PATTERNS]
    assert {item["category"] for item in english} <= set(GROK_CATEGORIES)
    ip = next(item for item in english if item["name"] == "IP")
    assert ip == {
        "name": "IP",
        "category": "network",
        "description": "An IPv4 or IPv6 address",
        "example": "192.168.1.10",
        "composite": False,
        "outputs": [],
    }
    combined = next(item for item in english if item["name"] == "COMBINEDAPACHELOG")
    assert combined["composite"] is True
    assert combined["outputs"] == [
        "source.address",
        "user.name",
        "log_time",
        "http.request.method",
        "url.original",
        "http.version",
        "http.response.status_code",
        "http.response.body.bytes",
        "http.request.referrer",
        "user_agent.original",
    ]
    assert "Nginx" in combined["description"]
    assert next(item for item in chinese if item["name"] == "IP")["description"] == "IPv4 或 IPv6 地址"
    assert "grok_pattern" not in "".join(item["description"] for item in english + chinese)


@pytest.mark.unit
@pytest.mark.parametrize("pattern", GROK_PATTERNS, ids=lambda pattern: pattern.name)
def test_grok_pattern_example_matches_itself_and_definition_is_vector_compatible(pattern):
    if pattern.composite:
        source = f"%{{{pattern.name}}}"
        expected = {"message": pattern.example}
        for path, value in pattern.example_outputs:
            _with_output(expected, path, value)
        assert [path for path, _value in pattern.example_outputs] == list(pattern.outputs)
    else:
        source = f"^%{{{pattern.name}:value}}$"
        expected = {"message": pattern.example, "value": pattern.example}

    expanded, mapping = expand_grok(source)
    re.compile(expanded)
    _ensure_vector_regex_compatible(expanded)
    result = execute_rules({"message": pattern.example}, [normalize_rule(_draft(source))])

    assert result.results[0].status == "success"
    assert result.event == expected
    if not pattern.composite:
        unanchored = f"%{{{pattern.name}:value}}"
        unanchored_result = _execute_rules_inline({"message": pattern.example}, [normalize_rule(_draft(unanchored))])
        if pattern.name == "DATA":
            assert unanchored_result.results[0].status == "failed"
            assert unanchored_result.results[0].error == "regex_no_match"
            assert unanchored_result.event == {"message": pattern.example}
        else:
            assert unanchored_result.results[0].status == "success"
            assert unanchored_result.event["value"] == pattern.example
    assert list(mapping.values()) == (list(pattern.outputs) if pattern.composite else ["value"])
    for output in mapping.values():
        root = output.split(".", 1)[0]
        assert root not in PROTECTED_FIELDS
        assert root != "message"
        assert output != "message"


@pytest.mark.unit
@pytest.mark.parametrize(
    "address",
    [
        "2001:db8::1",
        "2001:db8::1:2",
        "fe80::1",
        "2001:db8:85a3::8a2e:370:7334",
        "::1",
        "2001:db8::",
        "1:2:3:4:5:6:7:8",
    ],
)
def test_unanchored_ipv6_keeps_the_longer_address(address):
    result = _execute_rules_inline(
        {"message": f"src {address} done"},
        [normalize_rule(_draft("%{IPV6:client.ip}"))],
    )

    assert result.results[0].status == "success"
    assert result.event["client"]["ip"] == address


@pytest.mark.unit
@pytest.mark.parametrize("level", ["INF", "WRN", "DBG", "TRC", "ERR", "ERROR"])
def test_loglevel_matches_bracketed_abbreviations_and_words(level):
    result = _execute_rules_inline(
        {"message": f"ready [{level}] now"},
        [normalize_rule(_draft(r"\[%{LOGLEVEL:log.level}\]"))],
    )

    assert result.results[0].status == "success"
    assert result.event["log"]["level"] == level
