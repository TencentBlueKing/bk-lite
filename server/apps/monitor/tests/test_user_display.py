import pytest

from apps.monitor.utils.user_display import (
    build_user_display_map,
    enrich_alerts_notice_users_display,
    format_notice_users,
    resolve_alert_notice_users,
)
from apps.system_mgmt.models import User

pytestmark = pytest.mark.django_db


def _create_user(**overrides):
    values = {
        "username": "u1",
        "display_name": "用户一",
        "email": "u1@example.com",
        "password": "x",
    }
    values.update(overrides)
    return User.objects.create(**values)


def test_build_user_display_map_by_id_and_username():
    user = _create_user(username="alice", display_name="爱丽丝")

    user_map = build_user_display_map([user.id, "alice", 99999])

    assert user_map[str(user.id)] == "爱丽丝(alice)"
    assert user_map["alice"] == "爱丽丝(alice)"
    assert "99999" not in user_map


def test_format_notice_users_falls_back_to_raw_identifier():
    user = _create_user(username="bob", display_name="")

    assert format_notice_users([user.id, "missing"]) == ["bob", "missing"]


def test_resolve_alert_notice_users_prefers_alert_then_policy():
    assert resolve_alert_notice_users({"notice_users": [1], "policy": {"notice_users": [2]}}) == [1]
    assert resolve_alert_notice_users({"notice_users": [], "policy": {"notice_users": [2, 3]}}) == [2, 3]
    assert resolve_alert_notice_users({"notice_users": [], "policy": None}) == []


def test_enrich_alerts_notice_users_display_in_place():
    user_a = _create_user(username="a", display_name="甲")
    user_b = _create_user(username="b", display_name="乙", email="b@example.com")
    alerts = [
        {
            "notice_users": [user_a.id],
            "policy": {"notice_users": [user_b.id]},
        },
        {
            "notice_users": [],
            "policy": {"notice_users": [user_b.id, "gone"]},
        },
    ]

    enrich_alerts_notice_users_display(alerts)

    assert alerts[0]["notice_users_display"] == ["甲(a)"]
    assert alerts[1]["notice_users_display"] == ["乙(b)", "gone"]
