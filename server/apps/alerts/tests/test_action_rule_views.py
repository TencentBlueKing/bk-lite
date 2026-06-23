import pytest
from apps.alerts.models.action import ActionRule


@pytest.mark.django_db
def test_create_and_list_rule(api_client):
    payload = {"name": "磁盘清理", "team": [1], "trigger_events": ["created"],
               "match_rules": [[{"key": "level", "operator": "eq", "value": "1"}]],
               "action_type": "job",
               "action_config": {"script_id": 1, "target_binding": {"source": "node_mgmt",
                                  "host_field": "labels.ip"}, "param_bindings": []}}
    resp = api_client.post("/api/v1/alerts/api/action_rule/", data=payload, format="json")
    assert resp.status_code in (200, 201)
    assert ActionRule.objects.filter(name="磁盘清理").exists()
    lst = api_client.get("/api/v1/alerts/api/action_rule/")
    assert lst.status_code == 200


@pytest.mark.django_db
def test_patch_toggle_active(api_client):
    rule = ActionRule.objects.create(name="r", team=[1], is_active=True)
    resp = api_client.patch(f"/api/v1/alerts/api/action_rule/{rule.id}/",
                            data={"is_active": False}, format="json")
    assert resp.status_code == 200
    rule.refresh_from_db()
    assert rule.is_active is False
