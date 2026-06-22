from types import SimpleNamespace
from apps.alerts.aggregation.builder.alert_builder import AlertBuilder


def _ev(enrichment):
    return SimpleNamespace(enrichment=enrichment)


def test_merge_enrichment_consistent_namespace():
    events = [_ev({"cmdb": {"owner": "alice"}}), _ev({"cmdb": {"owner": "alice"}})]
    assert AlertBuilder._merge_enrichment(events) == {"cmdb": {"owner": "alice"}}


def test_merge_enrichment_takes_first_on_conflict():
    events = [_ev({"cmdb": {"owner": "alice"}}), _ev({"cmdb": {"owner": "bob"}})]
    assert AlertBuilder._merge_enrichment(events) == {"cmdb": {"owner": "alice"}}


def test_merge_enrichment_empty():
    assert AlertBuilder._merge_enrichment([_ev({}), _ev({})]) == {}
