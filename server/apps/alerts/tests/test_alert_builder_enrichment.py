from types import SimpleNamespace

from apps.alerts.aggregation.builder.alert_builder import AlertBuilder
from apps.alerts.enrichment.merge import normalize_enrichment_document
from apps.alerts.utils.enrichment import flatten_enrichment, resolve_data_path


def _ev(enrichment):
    return SimpleNamespace(enrichment=enrichment)


def test_merge_enrichment_consistent_namespace():
    events = [_ev({"cmdb": {"owner": "alice"}}), _ev({"cmdb": {"owner": "alice"}})]
    assert AlertBuilder._merge_enrichment(events) == {"cmdb": {"owner": "alice"}}


def test_merge_enrichment_preserves_conflict_as_distinct_payloads():
    events = [_ev({"cmdb": {"owner": "alice"}}), _ev({"cmdb": {"owner": "bob"}})]
    assert AlertBuilder._merge_enrichment(events) == {
        "cmdb": {
            "owner": "alice",
            "_meta": {
                "schema_version": 1,
                "status": "conflict",
                "conflicts": {"owner": ["bob"]},
            },
        }
    }


def test_merge_enrichment_empty():
    assert AlertBuilder._merge_enrichment([_ev({}), _ev({})]) == {}


def test_legacy_namespace_array_is_read_as_stable_object_and_meta_is_hidden():
    data = {"enrichment": {"cmdb": [{"owner": "alice"}, {"owner": "bob"}]}}
    merged = AlertBuilder._merge_enrichment([_ev(data["enrichment"])])

    assert resolve_data_path(data, "enrichment.cmdb.owner") == "alice"
    assert merged["cmdb"]["owner"] == "alice"
    assert all("_meta" not in key for key, _ in flatten_enrichment(merged))


def test_historical_enrichment_normalization_is_idempotent():
    legacy = {"cmdb": [{"owner": "alice"}, {"owner": "bob"}]}

    normalized, changed = normalize_enrichment_document(legacy)
    second, changed_again = normalize_enrichment_document(normalized)

    assert changed is True
    assert changed_again is False
    assert second == normalized
