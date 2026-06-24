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


# ============================================================
# Task 2: EnrichmentRuleModelFilter
# ============================================================

@pytest.mark.django_db
def test_filter_by_name_icontains():
    from apps.alerts.models.enrichment import EnrichmentRule
    from apps.alerts.filters.enrichment import EnrichmentRuleModelFilter
    EnrichmentRule.objects.create(name="CMDB资源丰富", provider_type="cmdb")
    EnrichmentRule.objects.create(name="其它规则", provider_type="cmdb")
    f = EnrichmentRuleModelFilter(
        data={"name": "cmdb"}, queryset=EnrichmentRule.objects.all()
    )
    assert f.qs.count() == 1
    assert f.qs.first().name == "CMDB资源丰富"


# ============================================================
# Task 3 + 4: EnrichmentRuleModelViewSet CRUD 集成测试
# ============================================================

@pytest.fixture
def superuser_client(authenticated_user):
    """api_client with is_superuser=True so HasPermission is bypassed."""
    from rest_framework.test import APIClient
    authenticated_user.is_superuser = True
    client = APIClient()
    client.force_authenticate(user=authenticated_user)
    return client


@pytest.mark.django_db
def test_viewset_list_create_delete(superuser_client):
    # 创建
    payload = {
        "name": "视图测试规则", "is_active": True, "match_rules": [],
        "provider_type": "cmdb",
        "input_binding": {"model_id": "resource_type", "_id": "resource_id"},
        "provider_config": {}, "output_projection": [], "on_multiple": "first",
        "namespace": "cmdb",
    }
    resp = superuser_client.post("/api/v1/alerts/api/enrichment/", payload, format="json")
    assert resp.status_code == 201, resp.content
    rule_id = resp.data["id"]

    # 列表 — CustomPageNumberPagination returns {"count": n, "items": [...]} under data key
    # when no page_size param, paginate_queryset returns None → no pagination wrapper
    resp = superuser_client.get("/api/v1/alerts/api/enrichment/")
    assert resp.status_code == 200
    data = resp.data
    # Without page_size, pagination is skipped; data is a list
    if isinstance(data, dict):
        names = [r["name"] for r in (data.get("items") or data.get("results") or [])]
    else:
        names = [r["name"] for r in data]
    assert "视图测试规则" in names

    # 删除 — renderer changes 204 DELETE → 200
    resp = superuser_client.delete(f"/api/v1/alerts/api/enrichment/{rule_id}/")
    assert resp.status_code in (200, 204), resp.content


# ============================================================
# Task 5: metrics action 采纳漏斗
# ============================================================

@pytest.mark.django_db
def test_metrics_reports_adoption_funnel(superuser_client):
    from apps.alerts.models.enrichment import EnrichmentRule
    EnrichmentRule.objects.create(name="内置-CMDB资源丰富", provider_type="cmdb", is_active=True)
    EnrichmentRule.objects.create(name="用户自建规则", provider_type="cmdb", is_active=False)

    resp = superuser_client.get("/api/v1/alerts/api/enrichment/metrics/")
    assert resp.status_code == 200
    data = resp.data
    assert data["total_rules"] == 2
    assert data["active_rules"] == 1
    assert data["user_created_rules"] == 1   # 排除"内置-"前缀
    assert "enriched_alert_ratio" in data
    assert 0.0 <= data["enriched_alert_ratio"] <= 1.0


# ============================================================
# Task 6: enrichment 字段在 Alert/Event API 可读
# ============================================================

@pytest.mark.django_db
def test_alert_serializer_exposes_enrichment_readable(authenticated_user):
    """钉死 enrichment 字段在 Alert 序列化器中可读（非 write_only）。"""
    from unittest.mock import patch, MagicMock
    from apps.alerts.serializers.alert import AlertModelSerializer
    from apps.alerts.models.models import Alert

    request = MagicMock()
    request.user = authenticated_user
    request.COOKIES = {"current_team": "0"}

    empty_rules = {"team": [], "instance": []}
    with patch("apps.core.utils.serializers.get_permission_rules", return_value=empty_rules):
        alert = Alert(enrichment={"cmdb": {"owner": "alice"}})
        data = AlertModelSerializer(alert, context={"request": request}).data
    assert data.get("enrichment") == {"cmdb": {"owner": "alice"}}


@pytest.mark.django_db
def test_event_serializer_exposes_enrichment_readable(authenticated_user):
    """钉死 enrichment 字段在 Event 序列化器中可读（非 write_only）。"""
    from unittest.mock import patch, MagicMock, PropertyMock
    from apps.alerts.serializers.event import EventModelSerializer
    from apps.alerts.models.models import Event

    request = MagicMock()
    request.user = authenticated_user
    request.COOKIES = {"current_team": "0"}

    empty_rules = {"team": [], "instance": []}
    # Mock source on an Event instance to avoid RelatedObjectDoesNotExist
    event = MagicMock(spec=Event)
    event.enrichment = {"cmdb": {"owner": "alice"}}
    event.source.name = "test-source"
    # Make it look like a model instance for the serializer
    event._state = MagicMock()
    event.pk = None

    with patch("apps.core.utils.serializers.get_permission_rules", return_value=empty_rules):
        data = EventModelSerializer(event, context={"request": request}).data
    assert data.get("enrichment") == {"cmdb": {"owner": "alice"}}
