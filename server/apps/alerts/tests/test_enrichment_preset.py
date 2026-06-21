import pytest
from apps.alerts.constants.init_data import BUILTIN_ENRICHMENT_RULES


def test_builtin_cmdb_preset_shape():
    rule = next(r for r in BUILTIN_ENRICHMENT_RULES if r["provider_type"] == "cmdb")
    assert rule["input_binding"] == {"model_id": "resource_type", "_id": "resource_id"}
    assert rule["on_multiple"] == "first"
    assert rule["is_active"] is True


@pytest.mark.django_db
def test_init_enrichment_rules_upsert_idempotent():
    from apps.alerts.constants.init_data import init_enrichment_rules
    from apps.alerts.models.enrichment import EnrichmentRule
    init_enrichment_rules()
    init_enrichment_rules()  # second call must not duplicate
    assert EnrichmentRule.objects.filter(name="内置-CMDB资源丰富").count() == 1
