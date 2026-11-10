import json

import pytest
from rest_framework.test import APIRequestFactory, force_authenticate

from apps.cmdb.services.change_record_retention import JOB_KEY, POLICY_KEY
from apps.cmdb.views.change_record_retention import ChangeRecordRetentionView
from apps.system_mgmt.models import SystemSettings

pytestmark = pytest.mark.django_db


@pytest.fixture(autouse=True)
def _clear_retention_settings():
    # Shared --reuse-db can leave policy and job rows from earlier tests.
    SystemSettings.objects.filter(key__in=(POLICY_KEY, JOB_KEY)).delete()


def _user(authenticated_user, perms, superuser=True):
    authenticated_user.is_superuser = superuser
    authenticated_user.permission = set(perms)
    return authenticated_user


def _req(method, user, data=None):
    factory = APIRequestFactory()
    fn = getattr(factory, method)
    request = fn("/cmdb/api/change_record_retention/", data=data or {}, format="json")
    force_authenticate(request, user=user)
    return request


def _body(response):
    if hasattr(response, "render"):
        response.render()
    return json.loads(response.content)


def test_get_returns_default_off(authenticated_user):
    user = _user(authenticated_user, {"model_management-View"})
    response = ChangeRecordRetentionView.as_view()(_req("get", user))
    assert response.status_code == 200
    data = _body(response)["data"]
    assert data["policy"]["mode"] == "off"
    assert data["job"]["status"] == "idle"


def test_put_off_does_not_enqueue(authenticated_user, monkeypatch):
    called = {}
    monkeypatch.setattr(
        "apps.cmdb.views.change_record_retention.cleanup_change_record_retention.delay",
        lambda **kw: called.setdefault("yes", kw),
    )
    user = _user(authenticated_user, {"model_management-View", "model_management-Edit Model"})
    response = ChangeRecordRetentionView.as_view()(_req("put", user, {"mode": "off"}))
    assert response.status_code == 200
    assert "yes" not in called


def test_put_by_days_enqueues(authenticated_user, monkeypatch):
    called = {}
    monkeypatch.setattr(
        "apps.cmdb.views.change_record_retention.cleanup_change_record_retention.delay",
        lambda **kw: called.setdefault("yes", kw),
    )
    user = _user(authenticated_user, {"model_management-View", "model_management-Edit Model"})
    response = ChangeRecordRetentionView.as_view()(_req("put", user, {"mode": "by_days", "days": 180}))
    assert response.status_code == 200
    assert called["yes"] == {"trigger": "save"}
    assert _body(response)["data"]["policy"]["days"] == 180


def test_put_rejects_when_running(authenticated_user):
    from django.utils.timezone import now

    from apps.cmdb.services.change_record_retention import read_job, write_job

    write_job({**read_job(), "status": "running", "started_at": now().isoformat()})
    user = _user(authenticated_user, {"model_management-View", "model_management-Edit Model"})
    response = ChangeRecordRetentionView.as_view()(_req("put", user, {"mode": "by_days", "days": 30}))
    assert response.status_code == 409


def test_get_presents_stale_running_job_as_idle(authenticated_user):
    from datetime import timedelta

    from django.utils.timezone import now

    from apps.cmdb.services.change_record_retention import LEASE_SECONDS, read_job, write_job

    started = (now() - timedelta(seconds=LEASE_SECONDS + 10)).isoformat()
    write_job({**read_job(), "status": "running", "started_at": started})
    user = _user(authenticated_user, {"model_management-View"})
    response = ChangeRecordRetentionView.as_view()(_req("get", user))
    assert response.status_code == 200
    assert _body(response)["data"]["job"]["status"] == "idle"


def test_put_invalid_mode_400(authenticated_user):
    user = _user(authenticated_user, {"model_management-View", "model_management-Edit Model"})
    response = ChangeRecordRetentionView.as_view()(_req("put", user, {"mode": "both"}))
    assert response.status_code == 400
