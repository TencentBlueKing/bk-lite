"""告警 OpenAPI：屏蔽策略创建、启停、修改与删除。"""

from types import SimpleNamespace

import pytest

from apps.alerts.models.alert_operator import AlertShield
from apps.alerts.open_api.auth import AlertsOpenAPIContext
from apps.alerts.open_api.errors import AlertsOpenAPIError
from apps.alerts.open_api.services import AlertsOpenAPIService


def _context(*, team_id=1, username="api-user", is_superuser=True, permissions=None, domain="default"):
    alarm_perms = {"shield_strategy-Add", "shield_strategy-Edit", "shield_strategy-Delete"} if permissions is None else permissions
    user = SimpleNamespace(
        username=username,
        group_list=[{"id": team_id}],
        permission={"alarm": set(alarm_perms)},
        is_superuser=is_superuser,
        locale="zh-CN",
        domain=domain,
    )
    return AlertsOpenAPIContext(user=user, team_id=team_id)


def _service(**kwargs):
    return AlertsOpenAPIService(_context(**kwargs))


@pytest.mark.django_db
def test_create_shield_writes_owner_and_log():
    result = _service(username="alice").create_shield(
        {
            "name": "周末维护",
            "match_type": "all",
            "match_rules": [],
            "suppression_time": {"type": "day", "start_time": "00:00:00", "end_time": "23:59:59"},
        }
    )

    assert result["name"] == "周末维护"
    assert result["is_active"] is True
    shield = AlertShield.objects.get(name="周末维护")
    assert shield.created_by == "alice"
    assert shield.match_type == "all"


@pytest.mark.django_db
def test_create_shield_rejects_invalid_filter_rules():
    with pytest.raises(AlertsOpenAPIError) as exc:
        _service().create_shield(
            {
                "name": "bad-shield",
                "match_type": "filter",
                "match_rules": [[{"key": "not_a_field", "operator": "eq", "value": "x"}]],
            }
        )

    assert exc.value.code == "alerts.validation.failed"
    assert not AlertShield.objects.filter(name="bad-shield").exists()


@pytest.mark.django_db
def test_operate_and_update_shield_only_own_record():
    own = AlertShield.objects.create(name="own-shield", match_type="all", created_by="api-user", is_active=True)
    other = AlertShield.objects.create(name="other-shield", match_type="all", created_by="other-user", is_active=True)

    operated = _service().operate_shield("own-shield", False)
    assert operated["is_active"] is False
    own.refresh_from_db()
    assert own.is_active is False

    updated = _service().update_shield(
        {
            "name": "own-shield",
            "match_type": "filter",
            "match_rules": [[{"key": "title", "operator": "eq", "value": "cpu"}]],
            "suppression_time": {},
        }
    )
    assert updated["match_type"] == "filter"
    own.refresh_from_db()
    assert own.match_type == "filter"

    with pytest.raises(AlertsOpenAPIError) as exc:
        _service().operate_shield("other-shield", False)
    assert exc.value.code == "alerts.shield.not_found"
    other.refresh_from_db()
    assert other.is_active is True


@pytest.mark.django_db
def test_delete_shield_only_removes_own_record():
    own = AlertShield.objects.create(name="own-shield", match_type="all", created_by="api-user")
    other = AlertShield.objects.create(name="other-shield", match_type="all", created_by="other-user")

    result = _service().delete_shield("own-shield")

    assert result["name"] == "own-shield"
    assert not AlertShield.objects.filter(id=own.id).exists()
    assert AlertShield.objects.filter(id=other.id).exists()

    with pytest.raises(AlertsOpenAPIError) as exc:
        _service().delete_shield("other-shield")
    assert exc.value.code == "alerts.shield.not_found"
    assert AlertShield.objects.filter(id=other.id).exists()
