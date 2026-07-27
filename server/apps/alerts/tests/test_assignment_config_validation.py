from types import SimpleNamespace

import pytest

from apps.alerts.serializers.assignment_shield import AlertAssignmentModelSerializer
from apps.system_mgmt.models import Group, User


def _payload(escalation, **overrides):
    payload = {
        "name": "r1",
        "match_type": "all",
        "notify_channels": [{"id": 1, "channel_type": "email", "name": "邮件"}],
        "personnel": ["u1"],
        "config": {"escalation": escalation},
    }
    payload.update(overrides)
    return payload


@pytest.mark.django_db
def test_assignment_rejects_empty_level_value_list():
    serializer = AlertAssignmentModelSerializer(
        data=_payload(
            {"enabled": False},
            match_type="filter",
            match_rules=[[{"key": "level", "operator": "eq", "value": []}]],
        )
    )
    assert not serializer.is_valid()
    assert serializer.errors["match_rules"][0] == "级别至少选择一个值"


@pytest.mark.django_db
def test_assignment_accepts_non_empty_level_value_list():
    serializer = AlertAssignmentModelSerializer(
        data=_payload(
            {"enabled": False},
            match_type="filter",
            match_rules=[[{"key": "level", "operator": "ne", "value": ["0", "1"]}]],
        )
    )
    assert serializer.is_valid(), serializer.errors


@pytest.mark.django_db
def test_valid_escalation_passes():
    ser = AlertAssignmentModelSerializer(data=_payload({
        "enabled": True, "mode": "append",
        "layers": [{"personnel": ["u1"], "wait_minutes": 10, "notify_channels": []}],
    }))
    assert ser.is_valid(), ser.errors


@pytest.mark.django_db
def test_disabled_escalation_skips_validation():
    ser = AlertAssignmentModelSerializer(data=_payload({"enabled": False}))
    assert ser.is_valid(), ser.errors


@pytest.mark.django_db
@pytest.mark.parametrize("bad", [
    {"enabled": True, "mode": "bogus", "layers": [{"personnel": ["u1"], "wait_minutes": 10}]},
    {"enabled": True, "mode": "append", "layers": []},
    {"enabled": True, "mode": "append", "layers": [{"personnel": [], "wait_minutes": 10}]},
    {"enabled": True, "mode": "append", "layers": [{"personnel": ["u1"], "wait_minutes": 0}]},
])
def test_invalid_escalation_rejected(bad):
    ser = AlertAssignmentModelSerializer(data=_payload(bad))
    assert not ser.is_valid()
    assert "config" in ser.errors


@pytest.mark.django_db
def test_organization_target_is_normalized_and_clears_legacy_personnel():
    group = Group.objects.create(name="运维中心")
    serializer = AlertAssignmentModelSerializer(
        data=_payload(
            {"enabled": False},
            personnel=["legacy-user"],
            config={
                "escalation": {"enabled": False},
                "notification_target": {
                    "type": "organization",
                    "organization_ids": [str(group.id), group.id],
                    "include_children": True,
                },
            },
        )
    )

    assert serializer.is_valid(), serializer.errors
    assert serializer.validated_data["personnel"] == []
    assert serializer.validated_data["config"]["notification_target"] == {
        "type": "organization",
        "usernames": [],
        "organization_ids": [group.id],
        "include_children": True,
    }


@pytest.mark.django_db
def test_escalation_layer_accepts_organization_target_without_personnel():
    group = Group.objects.create(name="二线支持")
    serializer = AlertAssignmentModelSerializer(
        data=_payload(
            {
                "enabled": True,
                "mode": "append",
                "layers": [
                    {
                        "personnel": [],
                        "wait_minutes": 10,
                        "notify_channels": [],
                        "notification_target": {
                            "type": "organization",
                            "organization_ids": [group.id],
                            "include_children": False,
                        },
                    }
                ],
            }
        )
    )

    assert serializer.is_valid(), serializer.errors
    layer = serializer.validated_data["config"]["escalation"]["layers"][0]
    assert layer["personnel"] == []
    assert layer["notification_target"]["organization_ids"] == [group.id]


@pytest.mark.django_db
@pytest.mark.parametrize(
    "target",
    [
        {
            "type": "user",
            "usernames": ["u1"],
            "organization_ids": [1],
            "include_children": False,
        },
        {
            "type": "organization",
            "organization_ids": [1],
            "usernames": ["u1"],
            "include_children": False,
        },
        {
            "type": "organization",
            "organization_ids": [1],
            "usernames": [],
            "include_children": "yes",
        },
    ],
)
def test_notification_target_rejects_mixed_or_invalid_fields(target):
    Group.objects.get_or_create(id=1, defaults={"name": "运维中心"})
    serializer = AlertAssignmentModelSerializer(
        data=_payload(
            {"enabled": False},
            config={
                "escalation": {"enabled": False},
                "notification_target": target,
            },
        )
    )

    assert not serializer.is_valid()
    assert "config" in serializer.errors


@pytest.mark.django_db
@pytest.mark.parametrize("disabled", [False, True])
def test_user_target_rejects_missing_or_disabled_user(disabled):
    if disabled:
        User.objects.create(
            username="u1",
            display_name="U1",
            email="u1@example.com",
            password="x",
            disabled=True,
        )
    serializer = AlertAssignmentModelSerializer(
        data=_payload(
            {"enabled": False},
            config={
                "escalation": {"enabled": False},
                "notification_target": {
                    "type": "user",
                    "usernames": ["u1"],
                    "organization_ids": [],
                    "include_children": False,
                },
            },
        )
    )

    assert not serializer.is_valid()
    assert "不存在或已禁用" in str(serializer.errors["config"])


@pytest.mark.django_db
def test_user_target_accepts_active_user():
    User.objects.create(
        username="u1",
        display_name="U1",
        email="u1@example.com",
        password="x",
    )
    serializer = AlertAssignmentModelSerializer(
        data=_payload(
            {"enabled": False},
            config={
                "escalation": {"enabled": False},
                "notification_target": {
                    "type": "user",
                    "usernames": ["u1"],
                    "organization_ids": [],
                    "include_children": False,
                },
            },
        )
    )

    assert serializer.is_valid(), serializer.errors


@pytest.mark.django_db
def test_organization_target_rejects_group_outside_request_scope():
    group = Group.objects.create(name="无权组织")
    serializer = AlertAssignmentModelSerializer(
        data=_payload(
            {"enabled": False},
            config={
                "escalation": {"enabled": False},
                "notification_target": {
                    "type": "organization",
                    "organization_ids": [group.id],
                    "include_children": False,
                },
            },
        ),
        context={
            "request": SimpleNamespace(
                user=SimpleNamespace(is_superuser=False, group_list=[])
            )
        },
    )

    assert not serializer.is_valid()
    assert "无权选择" in str(serializer.errors["config"])


@pytest.mark.django_db
def test_organization_target_allows_superuser_scope_bypass():
    group = Group.objects.create(name="任意组织")
    serializer = AlertAssignmentModelSerializer(
        data=_payload(
            {"enabled": False},
            config={
                "escalation": {"enabled": False},
                "notification_target": {
                    "type": "organization",
                    "organization_ids": [group.id],
                    "include_children": False,
                },
            },
        ),
        context={
            "request": SimpleNamespace(
                user=SimpleNamespace(is_superuser=True, group_list=[])
            )
        },
    )

    assert serializer.is_valid(), serializer.errors
