import pytest
from apps.alerts.models.action import ActionRule


@pytest.fixture
def superuser_client(authenticated_user):
    """api_client with is_superuser=True so HasPermission is bypassed."""
    from rest_framework.test import APIClient
    authenticated_user.is_superuser = True
    client = APIClient()
    client.force_authenticate(user=authenticated_user)
    return client


@pytest.mark.django_db
def test_create_and_list_rule(superuser_client):
    superuser_client.cookies["current_team"] = "1"
    payload = {"name": "磁盘清理", "team": [1], "trigger_events": ["created"],
               "match_rules": [[{"key": "level", "operator": "eq", "value": "1"}]],
               "action_type": "job",
               "action_config": {"script_id": 1, "target_binding": {"source": "node_mgmt",
                                  "host_field": "labels.ip"}, "param_bindings": []}}
    resp = superuser_client.post("/api/v1/alerts/api/action_rule/", data=payload, format="json")
    assert resp.status_code in (200, 201)
    assert ActionRule.objects.filter(name="磁盘清理").exists()
    lst = superuser_client.get("/api/v1/alerts/api/action_rule/")
    assert lst.status_code == 200


@pytest.mark.django_db
def test_patch_toggle_active(superuser_client):
    rule = ActionRule.objects.create(name="r", team=[1], is_active=True)
    superuser_client.cookies["current_team"] = "1"
    resp = superuser_client.patch(f"/api/v1/alerts/api/action_rule/{rule.id}/",
                            data={"is_active": False}, format="json")
    assert resp.status_code == 200
    rule.refresh_from_db()
    assert rule.is_active is False


@pytest.mark.django_db
def test_rule_list_is_scoped_to_current_team(superuser_client):
    ActionRule.objects.create(name="team-1", team=[1])
    ActionRule.objects.create(name="team-2", team=[2])
    superuser_client.cookies["current_team"] = "1"

    response = superuser_client.get("/api/v1/alerts/api/action_rule/")

    assert response.status_code == 200
    data = response.json().get("data", response.json())
    items = data.get("items", data) if isinstance(data, dict) else data
    assert {item["name"] for item in items} == {"team-1"}


@pytest.mark.django_db
def test_create_rule_rejects_team_outside_current_scope(superuser_client):
    superuser_client.cookies["current_team"] = "1"

    response = superuser_client.post(
        "/api/v1/alerts/api/action_rule/",
        data={"name": "cross-team", "team": [2], "action_type": "job"},
        format="json",
    )

    assert response.status_code == 400
    assert not ActionRule.objects.filter(name="cross-team").exists()
