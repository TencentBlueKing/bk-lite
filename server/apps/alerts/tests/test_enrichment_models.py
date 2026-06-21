import pytest
from apps.alerts.models.models import Event, Alert


def test_event_enrichment_defaults_to_empty_dict():
    field = Event._meta.get_field("enrichment")
    assert field.get_default() == {}


def test_alert_enrichment_defaults_to_empty_dict():
    field = Alert._meta.get_field("enrichment")
    assert field.get_default() == {}


def test_enrichment_rule_field_defaults():
    from apps.alerts.models.enrichment import EnrichmentRule
    assert EnrichmentRule._meta.get_field("provider_type").get_default() == "cmdb"
    assert EnrichmentRule._meta.get_field("on_multiple").get_default() == "first"
    assert EnrichmentRule._meta.get_field("input_binding").get_default() == {}
    assert EnrichmentRule._meta.get_field("output_projection").get_default() == []
    assert EnrichmentRule._meta.get_field("is_active").get_default() is True


def test_enrichment_rule_resolved_namespace_falls_back_to_provider_type():
    from apps.alerts.models.enrichment import EnrichmentRule
    rule = EnrichmentRule(name="r", provider_type="cmdb", namespace="")
    assert rule.resolved_namespace == "cmdb"
    rule2 = EnrichmentRule(name="r2", provider_type="cmdb", namespace="biz")
    assert rule2.resolved_namespace == "biz"
