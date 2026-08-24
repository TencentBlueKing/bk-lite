from types import SimpleNamespace

import pytest

from apps.alerts.open_api.auth import AlertsOpenAPIContext
from apps.alerts.open_api.errors import AlertsOpenAPIError


def _request(*, api_pass=True, groups=None, permissions=None, is_superuser=False):
    user = SimpleNamespace(
        username="api-user",
        group_list=groups if groups is not None else [{"id": 7}],
        permission={"alarm": set(permissions or [])},
        is_superuser=is_superuser,
        locale="zh-CN",
    )
    return SimpleNamespace(api_pass=api_pass, user=user)


def test_context_rejects_non_api_secret():
    with pytest.raises(AlertsOpenAPIError) as exc:
        AlertsOpenAPIContext.from_request(_request(api_pass=False))
    assert exc.value.code == "alerts.auth.api_secret_required"
    assert exc.value.status_code == 403


def test_context_rejects_non_single_team():
    with pytest.raises(AlertsOpenAPIError) as exc:
        AlertsOpenAPIContext.from_request(_request(groups=[{"id": 1}, {"id": 2}]))
    assert exc.value.code == "alerts.auth.invalid_team"


def test_context_parses_single_team():
    ctx = AlertsOpenAPIContext.from_request(_request(groups=[{"id": 7}]))
    assert ctx.team_id == 7
    assert ctx.username == "api-user"


def test_require_feature_checks_alarm_permission_key():
    ctx = AlertsOpenAPIContext.from_request(_request(permissions={"Alarms-View"}))
    ctx.require_feature("Alarms-View")
    with pytest.raises(AlertsOpenAPIError) as exc:
        ctx.require_feature("Alarms-Edit")
    assert exc.value.code == "alerts.permission.denied"


def test_require_feature_superuser_bypass():
    ctx = AlertsOpenAPIContext.from_request(_request(permissions=set(), is_superuser=True))
    ctx.require_feature("Alarms-Edit")
