import pytest

from apps.log.services.aggregate_group_identity import build_aggregate_group_identity

pytestmark = pytest.mark.unit


def test_ungrouped_identity_keeps_legacy_contract():
    identity = build_aggregate_group_identity(9, {"count": 3}, [])

    assert identity.source_id == "policy_9_"
    assert identity.legacy_source_ids == ()


def test_long_group_value_produces_bounded_identity_without_unstorable_alias():
    identity = build_aggregate_group_identity(9, {"url": f"https://example.com/{'x' * 200}"}, ["url"])

    assert identity.source_id.startswith("policy_9_g2_")
    assert len(identity.source_id) <= 100
    assert identity.legacy_source_ids == ()


def test_ambiguous_legacy_encoding_produces_distinct_primary_identities():
    first = build_aggregate_group_identity(9, {"a": "x, b=y", "b": "z"}, ["a", "b"])
    second = build_aggregate_group_identity(9, {"a": "x", "b": "y, b=z"}, ["a", "b"])

    assert first.source_id != second.source_id
    assert first.legacy_source_ids == second.legacy_source_ids == ("policy_9_a=x, b=y, b=z",)


def test_group_field_order_does_not_change_primary_identity():
    first = build_aggregate_group_identity(9, {"host": "h1", "level": "error"}, ["host", "level"])
    reordered = build_aggregate_group_identity(9, {"host": "h1", "level": "error"}, ["level", "host"])

    assert first.source_id == reordered.source_id


def test_nested_mapping_key_order_does_not_change_primary_identity():
    first = build_aggregate_group_identity(9, {"meta": {"a": 1, "b": 2}}, ["meta"])
    reordered = build_aggregate_group_identity(9, {"meta": {"b": 2, "a": 1}}, ["meta"])

    assert first.source_id == reordered.source_id


def test_missing_value_is_distinct_from_literal_legacy_placeholder():
    missing = build_aggregate_group_identity(9, {}, ["host"])
    literal = build_aggregate_group_identity(9, {"host": "unknown"}, ["host"])

    assert missing.source_id != literal.source_id
    assert missing.legacy_source_ids == literal.legacy_source_ids == ("policy_9_host=unknown",)


@pytest.mark.parametrize(
    ("result", "group_by", "legacy_source_id"),
    [
        ({"host": "h1"}, ["host"], "policy_9_host=h1"),
        ({"tags": ["a", "b"]}, ["tags"], "policy_9_tags=a,b"),
        ({"meta": {"x": 1}}, ["meta"], "policy_9_meta={'x': 1}"),
        ({"host": None}, ["host"], "policy_9_host=null"),
        ({}, ["host"], "policy_9_host=unknown"),
    ],
)
def test_storable_legacy_alias_matches_previous_encoding(result, group_by, legacy_source_id):
    identity = build_aggregate_group_identity(9, result, group_by)

    assert identity.legacy_source_ids == (legacy_source_id,)
