"""作业异步回调幂等：同组织回放、跨组织不得泄露 execution_id。"""

from unittest.mock import MagicMock, patch

import pytest

from apps.job_mgmt.models import JobExecution, Target
from apps.job_mgmt.nats_api import _run_script_execute
from apps.system_mgmt.models import Group

pytestmark = [pytest.mark.django_db]


CALLBACK_CONTEXT = {
    "callback_url": "https://example.com/openapi/v1/itsm/openapi/v1/action_components/callback/",
    "callback_token": "tok-async-replay",
    "operator": "system",
    "timeout": 3600,
}


def _payload(team_id, target, **overrides):
    payload = {
        "name": "补丁安装",
        "target_source": "manual",
        "target_list": [{"target_id": target.id, "name": target.name, "ip": target.ip}],
        "script_type": "shell",
        "script_content": "echo hello",
        "team": [team_id],
        "async_callback_context": dict(CALLBACK_CONTEXT),
    }
    payload.update(overrides)
    return payload


@pytest.fixture
def teams():
    own = Group.objects.create(name="job-replay-a")
    other = Group.objects.create(name="job-replay-b")
    own_target = Target.objects.create(name="web-01", ip="10.0.0.1", team=[own.id])
    other_target = Target.objects.create(name="db-01", ip="10.0.0.2", team=[other.id])
    return own, other, own_target, other_target


def test_async_script_execute_same_token_is_idempotent(teams):
    own, _other, own_target, _other_target = teams
    with patch("apps.job_mgmt.nats_api.DangerousChecker.check_command") as mock_check, patch(
        "apps.job_mgmt.nats_api.execute_script_task.delay"
    ) as mock_delay, patch("apps.job_mgmt.nats_api.SSRFValidator.validate_callback"):
        mock_check.return_value = MagicMock(can_execute=True, forbidden=[])
        mock_delay.return_value.id = "celery-async-replay"
        first = _run_script_execute(_payload(own.id, own_target))
        second = _run_script_execute(_payload(own.id, own_target))

    assert first["result"] is True
    assert second["result"] is True
    assert first["data"]["execution_id"] == second["data"]["execution_id"]
    assert JobExecution.objects.filter(async_callback_key__isnull=False).count() == 1
    mock_delay.assert_called_once()


def test_async_script_execute_other_tenant_cannot_replay_callback_token(teams):
    own, other, own_target, other_target = teams
    with patch("apps.job_mgmt.nats_api.DangerousChecker.check_command") as mock_check, patch(
        "apps.job_mgmt.nats_api.execute_script_task.delay"
    ) as mock_delay, patch("apps.job_mgmt.nats_api.SSRFValidator.validate_callback"):
        mock_check.return_value = MagicMock(can_execute=True, forbidden=[])
        mock_delay.return_value.id = "celery-async-owner"
        owner = _run_script_execute(_payload(own.id, own_target))
        replay = _run_script_execute(_payload(other.id, other_target))

    assert owner["result"] is True
    assert replay["result"] is False
    assert "execution_id" not in (replay.get("data") or {})
    assert owner["data"]["execution_id"] not in str(replay)
    assert JobExecution.objects.filter(async_callback_key__isnull=False).count() == 1
    mock_delay.assert_called_once()
