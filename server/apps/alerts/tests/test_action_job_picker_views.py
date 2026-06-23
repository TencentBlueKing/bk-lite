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
    resp = superuser_client.get("/api/v1/alerts/api/action_job/scripts/?name=nginx")
    assert resp.status_code == 200
    body = resp.json()
    data = body.get("data", body)
    assert data["items"][0]["id"] == 42


@pytest.mark.django_db
@patch("apps.alerts.views.action.JobMgmt")
def test_job_script_params_proxy(mock_job, superuser_client):
    mock_job.return_value.get_script.return_value = {"id": 42, "name": "重启nginx",
        "params": [{"name": "service", "default": ""}]}
    resp = superuser_client.get("/api/v1/alerts/api/action_job/scripts/42/")
    assert resp.status_code == 200
    body = resp.json()
    data = body.get("data", body)
    assert data["params"][0]["name"] == "service"
