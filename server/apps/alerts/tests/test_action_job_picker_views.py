import pytest
from unittest.mock import patch
from rest_framework.test import APIClient
from apps.base.models import User


@pytest.fixture
def superuser_client(db):
    user = User.objects.create_user(username="admin3", password="x", domain="domain.com",
                                    group_list=[{"id": 1, "name": "T"}], roles=["admin"])
    user.is_superuser = True
    user.save()
    client = APIClient()
    client.force_authenticate(user=user)
    return client


@pytest.mark.django_db
@patch("apps.alerts.views.action.JobMgmt")
def test_job_script_list_proxy(mock_job, superuser_client):
    mock_job.return_value.list_scripts.return_value = {"count": 1, "items": [
        {"id": 42, "name": "重启nginx", "script_type": "shell"}]}
    superuser_client.cookies["current_team"] = "1"
    resp = superuser_client.get("/api/v1/alerts/api/action_job/scripts/?name=nginx")
    assert resp.status_code == 200
    body = resp.json()
    data = body.get("data", body)
    assert data["items"][0]["id"] == 42


@pytest.mark.django_db
@patch("apps.alerts.views.action.JobMgmt")
def test_job_script_list_passes_current_team_as_group_id(mock_job, superuser_client):
    """脚本列表按登陆者当前组织(current_team)过滤 —— 以 group_id 关键字下传。"""
    mock_job.return_value.list_scripts.return_value = {"count": 0, "items": []}
    superuser_client.cookies["current_team"] = "7"
    resp = superuser_client.get("/api/v1/alerts/api/action_job/scripts/")
    assert resp.status_code == 200
    mock_job.return_value.list_scripts.assert_called_once_with(group_id=7, team=[7])


@pytest.mark.django_db
@patch("apps.alerts.views.action.JobMgmt")
def test_job_script_params_proxy(mock_job, superuser_client):
    mock_job.return_value.get_script.return_value = {"id": 42, "name": "重启nginx",
        "params": [{"name": "service", "default": ""}]}
    superuser_client.cookies["current_team"] = "7"
    resp = superuser_client.get("/api/v1/alerts/api/action_job/scripts/42/")
    assert resp.status_code == 200
    body = resp.json()
    data = body.get("data", body)
    assert data["params"][0]["name"] == "service"
    mock_job.return_value.get_script.assert_called_once_with(42, team=[7])


@pytest.mark.django_db
@pytest.mark.parametrize("path", [
    "/api/v1/alerts/api/action_job/scripts/",
    "/api/v1/alerts/api/action_job/scripts/42/",
])
def test_job_script_proxy_requires_action_rule_view_permission(path, superuser_client):
    superuser_client.handler._force_user.is_superuser = False
    superuser_client.handler._force_user.permission = {}
    superuser_client.cookies["current_team"] = "1"

    response = superuser_client.get(path)

    assert response.status_code == 403
