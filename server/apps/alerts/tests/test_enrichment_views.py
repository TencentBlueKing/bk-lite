# -- coding: utf-8 --
"""告警丰富规则 L1.5 视图集与序列化器测试。"""

import pytest


# ============================================================
# Task 1: EnrichmentRuleModelSerializer
# ============================================================

@pytest.mark.django_db
def test_serializer_roundtrips_all_rule_fields():
    from apps.alerts.serializers.enrichment import EnrichmentRuleModelSerializer
    payload = {
        "name": "测试规则",
        "is_active": True,
        "match_rules": [],
        "provider_type": "cmdb",
        "input_binding": {"model_id": "resource_type", "_id": "resource_id"},
        "provider_config": {},
        "output_projection": [{"source": "responsible_person", "as": "owner"}],
        "on_multiple": "first",
        "namespace": "cmdb",
    }
    s = EnrichmentRuleModelSerializer(data=payload)
    assert s.is_valid(), s.errors
    obj = s.save()
    assert obj.input_binding == {"model_id": "resource_type", "_id": "resource_id"}
    assert obj.output_projection == [{"source": "responsible_person", "as": "owner"}]


@pytest.mark.django_db
def test_serializer_rejects_bad_on_multiple():
    from apps.alerts.serializers.enrichment import EnrichmentRuleModelSerializer
    s = EnrichmentRuleModelSerializer(data={"name": "x", "on_multiple": "nonsense"})
    assert not s.is_valid()
    assert "on_multiple" in s.errors
