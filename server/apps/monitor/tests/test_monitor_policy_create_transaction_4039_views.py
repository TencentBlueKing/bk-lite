"""Issue #4039: 新建监控策略的多步写入必须保持原子性。"""

from uuid import uuid4

import pytest
from django.db import IntegrityError
from django_celery_beat.models import CrontabSchedule, PeriodicTask

from apps.monitor.models.monitor_object import MonitorObject
from apps.monitor.models.monitor_policy import MonitorPolicy, PolicyOrganization
from apps.monitor.views.monitor_policy import MonitorPolicyViewSet

pytestmark = [pytest.mark.integration, pytest.mark.django_db]

BASE = "/api/v1/monitor"


@pytest.fixture(autouse=True)
def disable_error_log_async(mocker):
    return mocker.patch(
        "apps.system_mgmt.middleware.error_log_middleware.write_error_log_async"
    )


def _patch_policy_permissions(mocker):
    permission = {"team": [1], "instance": []}
    mocker.patch(
        "apps.core.utils.current_team_scope.SystemMgmt.get_authorized_groups_scoped",
        return_value={"result": True, "data": [1]},
    )
    mocker.patch(
        "apps.core.utils.current_team_scope.SystemMgmt.get_assignable_groups",
        return_value={"result": True, "data": [1]},
    )
    mocker.patch(
        "apps.monitor.views.monitor_policy.get_permission_rules",
        return_value=permission,
    )


def _policy_payload(monitor_object, name):
    return {
        "name": name,
        "monitor_object": monitor_object.id,
        "organizations": [1],
        "algorithm": "max_over_time",
        "group_algorithm": "max",
        "query_condition": {"type": "pmq", "query": "up"},
        "source": {},
        "schedule": {"type": "min", "value": 5},
        "period": {"type": "min", "value": 5},
        "group_by": [],
        "threshold": [],
        "trigger_count": 1,
        "recovery_condition": 1,
        "enable_alerts": ["threshold"],
        "enable": True,
    }


class TestMonitorPolicyCreateTransaction:
    @pytest.mark.parametrize(
        ("failing_method", "enable_alerts"),
        [
            ("update_policy_organizations", ["threshold"]),
            ("update_policy_baselines", ["no_data"]),
        ],
    )
    def test_late_write_failure_rolls_back_all_create_side_effects(
        self, api_client, mocker, failing_method, enable_alerts
    ):
        api_client.cookies["current_team"] = "1"
        _patch_policy_permissions(mocker)
        monitor_object = MonitorObject.objects.create(
            name=f"PolicyCreateTx-{uuid4().hex[:8]}",
            level="base",
            instance_id_keys=["instance_id"],
        )
        policy_name = f"policy-create-tx-{uuid4().hex[:8]}"
        before_task_ids = set(PeriodicTask.objects.values_list("id", flat=True))
        before_schedule_ids = set(CrontabSchedule.objects.values_list("id", flat=True))
        failing_write = mocker.patch.object(
            MonitorPolicyViewSet,
            failing_method,
            side_effect=IntegrityError("simulated create side-effect failure"),
        )
        payload = _policy_payload(monitor_object, policy_name)
        payload["enable_alerts"] = enable_alerts

        response = api_client.post(
            f"{BASE}/api/monitor_policy/",
            payload,
            format="json",
        )

        assert response.status_code == 500
        failing_write.assert_called_once()
        assert not MonitorPolicy.objects.filter(name=policy_name).exists()
        assert set(PeriodicTask.objects.values_list("id", flat=True)) == before_task_ids
        assert set(CrontabSchedule.objects.values_list("id", flat=True)) == before_schedule_ids
        assert not PolicyOrganization.objects.filter(
            policy__name=policy_name
        ).exists()
