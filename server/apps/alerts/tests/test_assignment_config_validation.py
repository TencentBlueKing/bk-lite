import pytest

from apps.alerts.serializers.assignment_shield import AlertAssignmentModelSerializer


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
