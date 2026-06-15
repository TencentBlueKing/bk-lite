import pytest
from apps.alerts.serializers.assignment_shield import AlertAssignmentModelSerializer


def _payload(escalation):
    return {
        "name": "r1", "match_type": "all",
        "notify_channels": [{"id": 1, "channel_type": "email", "name": "邮件"}],
        "personnel": ["u1"],
        "config": {"escalation": escalation},
    }


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
