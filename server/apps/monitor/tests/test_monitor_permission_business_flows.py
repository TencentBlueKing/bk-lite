from uuid import uuid4

import pytest
from django_celery_beat.models import CrontabSchedule, PeriodicTask

from apps.monitor.models import MonitorAlert
from apps.monitor.models.monitor_condition import MonitorCondition, MonitorConditionOrganization
from apps.monitor.models.monitor_metrics import Metric, MetricGroup
from apps.monitor.models.monitor_object import MonitorInstance, MonitorInstanceOrganization, MonitorObject
from apps.monitor.models.monitor_policy import MonitorPolicy, PolicyOrganization
from apps.monitor.models.plugin import MonitorPlugin

pytestmark = pytest.mark.django_db

BASE = "/api/v1/monitor"


@pytest.fixture(autouse=True)
def disable_error_log_async(mocker):
    return mocker.patch("apps.system_mgmt.middleware.error_log_middleware.write_error_log_async")


def _name(prefix):
    return f"{prefix}-{uuid4().hex[:8]}"


def _response_data(resp):
    body = resp.json()
    return body.get("data", body)


def _monitor_object(prefix="BizObj"):
    return MonitorObject.objects.create(name=_name(prefix), level="base", instance_id_keys=["instance_id"])


def _policy_payload(monitor_object, *, name=None, organizations=None, schedule=None):
    return {
        "name": name or _name("policy"),
        "monitor_object": monitor_object.id,
        "organizations": organizations or [1],
        "algorithm": "max_over_time",
        "group_algorithm": "max",
        "query_condition": {"type": "pmq", "query": "up"},
        "source": {},
        "schedule": schedule or {"type": "min", "value": 5},
        "period": {"type": "min", "value": 5},
        "group_by": [],
        "threshold": [],
        "trigger_count": 1,
        "recovery_condition": 1,
        "enable_alerts": ["threshold"],
        "enable": True,
    }


def _policy(monitor_object, *, org=1, name=None):
    policy = MonitorPolicy.objects.create(
        monitor_object=monitor_object,
        name=name or _name("policy"),
        algorithm="max_over_time",
        group_algorithm="max",
        query_condition={"type": "pmq", "query": "up"},
        source={},
        schedule={"type": "min", "value": 5},
        period={"type": "min", "value": 5},
        group_by=[],
        trigger_count=1,
        recovery_condition=1,
        enable_alerts=["threshold"],
    )
    PolicyOrganization.objects.create(policy=policy, organization=org)
    return policy


def _patch_policy_business_permissions(mocker, *, teams=None, instances=None):
    permission = {"team": teams or [], "instance": instances or []}
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
    mocker.patch(
        "apps.monitor.services.node_mgmt.get_permission_rules",
        return_value=permission,
    )
    mocker.patch(
        "apps.monitor.views.monitor_policy.InstanceConfigService._get_actor_scope_groups",
        return_value=teams or [],
    )


def _patch_condition_business_permissions(mocker, *, teams=None, instances=None):
    mocker.patch(
        "apps.core.utils.current_team_scope.SystemMgmt.get_authorized_groups_scoped",
        return_value={"result": True, "data": [1]},
    )
    mocker.patch(
        "apps.core.utils.current_team_scope.SystemMgmt.get_assignable_groups",
        return_value={"result": True, "data": [1]},
    )
    mocker.patch(
        "apps.monitor.views.monitor_condition.get_permission_rules",
        return_value={"team": teams or [], "instance": instances or []},
    )


class TestMonitorPolicyBusinessFlow:
    def test_authorized_user_can_manage_policy_lifecycle(self, api_client, mocker):
        api_client.cookies["current_team"] = "1"
        _patch_policy_business_permissions(mocker, teams=[1])
        monitor_object = _monitor_object("PolicyLifecycleObj")

        create_resp = api_client.post(
            f"{BASE}/api/monitor_policy/",
            _policy_payload(monitor_object, name=_name("policy-lifecycle"), organizations=[1]),
            format="json",
        )
        assert create_resp.status_code == 201
        policy_id = _response_data(create_resp)["id"]
        assert PolicyOrganization.objects.filter(policy_id=policy_id, organization=1).exists()
        assert PeriodicTask.objects.filter(name=f"scan_policy_task_{policy_id}").exists()

        list_resp = api_client.get(f"{BASE}/api/monitor_policy/?monitor_object_id={monitor_object.id}")
        assert list_resp.status_code == 200
        assert any(item["id"] == policy_id for item in list_resp.json()["data"]["items"])

        patch_resp = api_client.patch(
            f"{BASE}/api/monitor_policy/{policy_id}/",
            {"schedule": {"type": "min", "value": 10}, "organizations": [1]},
            format="json",
        )
        assert patch_resp.status_code == 200
        task = PeriodicTask.objects.get(name=f"scan_policy_task_{policy_id}")
        assert task.crontab.minute == "*/10"
        assert set(PolicyOrganization.objects.filter(policy_id=policy_id).values_list("organization", flat=True)) == {1}

        delete_resp = api_client.delete(f"{BASE}/api/monitor_policy/{policy_id}/")
        assert delete_resp.status_code in (200, 204)
        assert not MonitorPolicy.objects.filter(id=policy_id).exists()
        assert not PolicyOrganization.objects.filter(policy_id=policy_id).exists()
        assert not PeriodicTask.objects.filter(name=f"scan_policy_task_{policy_id}").exists()

    def test_unauthorized_delete_policy_does_not_trigger_side_effects(self, api_client, mocker):
        api_client.cookies["current_team"] = "1"
        _patch_policy_business_permissions(mocker, teams=[1])
        monitor_object = _monitor_object("PolicyBlockedObj")
        blocked = _policy(monitor_object, org=2, name=_name("blocked-policy"))
        schedule = CrontabSchedule.objects.create(
            minute="*/5",
            hour="*",
            day_of_week="*",
            day_of_month="*",
            month_of_year="*",
        )
        PeriodicTask.objects.create(
            name=f"scan_policy_task_{blocked.id}",
            task="apps.monitor.tasks.monitor_policy.scan_policy_task",
            args=f"[{blocked.id}]",
            crontab=schedule,
        )
        MonitorAlert.objects.create(policy_id=blocked.id, monitor_instance_id="h1", status="new")

        delete_resp = api_client.delete(f"{BASE}/api/monitor_policy/{blocked.id}/")
        assert delete_resp.status_code == 404
        assert MonitorPolicy.objects.filter(id=blocked.id).exists()
        assert PolicyOrganization.objects.filter(policy_id=blocked.id, organization=2).exists()
        assert PeriodicTask.objects.filter(name=f"scan_policy_task_{blocked.id}").exists()
        assert MonitorAlert.objects.filter(policy_id=blocked.id, status="new").exists()


class TestMonitorConditionBusinessFlow:
    def test_authorized_user_can_manage_condition_lifecycle(self, api_client, mocker):
        api_client.cookies["current_team"] = "1"
        _patch_condition_business_permissions(mocker, teams=[1])

        create_resp = api_client.post(
            f"{BASE}/api/monitor_condition/",
            {"name": _name("condition-lifecycle"), "condition": {"level": "critical"}, "organizations": [1]},
            format="json",
        )
        assert create_resp.status_code == 201
        condition_id = _response_data(create_resp)["id"]
        assert MonitorConditionOrganization.objects.filter(monitor_condition_id=condition_id, organization=1).exists()

        list_resp = api_client.get(f"{BASE}/api/monitor_condition/")
        assert list_resp.status_code == 200
        assert any(item["id"] == condition_id for item in list_resp.json()["data"]["items"])

        patch_resp = api_client.patch(
            f"{BASE}/api/monitor_condition/{condition_id}/",
            {"description": "updated", "organizations": [1]},
            format="json",
        )
        assert patch_resp.status_code == 200
        assert MonitorCondition.objects.get(id=condition_id).description == "updated"

        delete_resp = api_client.delete(f"{BASE}/api/monitor_condition/{condition_id}/")
        assert delete_resp.status_code in (200, 204)
        assert not MonitorCondition.objects.filter(id=condition_id).exists()
        assert not MonitorConditionOrganization.objects.filter(monitor_condition_id=condition_id).exists()

    def test_unauthorized_delete_condition_does_not_clean_organizations(self, api_client, mocker):
        api_client.cookies["current_team"] = "1"
        _patch_condition_business_permissions(mocker, teams=[1])
        blocked = MonitorCondition.objects.create(name=_name("blocked-condition"), condition={})
        MonitorConditionOrganization.objects.create(monitor_condition=blocked, organization=2)

        delete_resp = api_client.delete(f"{BASE}/api/monitor_condition/{blocked.id}/")
        assert delete_resp.status_code == 404
        assert MonitorCondition.objects.filter(id=blocked.id).exists()
        assert MonitorConditionOrganization.objects.filter(monitor_condition=blocked, organization=2).exists()


class TestMonitorPolicyBulkBusinessFlow:
    def _metric_template_context(self):
        monitor_object = _monitor_object("PolicyBulkObj")
        plugin = MonitorPlugin.objects.create(name=_name("bulk-plugin"))
        group = MetricGroup.objects.create(monitor_object=monitor_object, monitor_plugin=plugin, name=_name("bulk-group"))
        metric = Metric.objects.create(
            monitor_object=monitor_object,
            monitor_plugin=plugin,
            metric_group=group,
            name=_name("cpu_usage"),
            unit="percent",
        )
        return monitor_object, metric

    def test_bulk_template_create_rejects_cross_team_asset_before_creating_policy(self, api_client, mocker, disable_error_log_async):
        api_client.cookies["current_team"] = "1"
        _patch_policy_business_permissions(mocker, teams=[1])
        monitor_object, metric = self._metric_template_context()
        inst = MonitorInstance.objects.create(id=f"('{_name('host-blocked')}',)", name="host-blocked", monitor_object=monitor_object)
        MonitorInstanceOrganization.objects.create(monitor_instance=inst, organization=2)
        before_task_names = set(PeriodicTask.objects.values_list("name", flat=True))

        resp = api_client.post(
            f"{BASE}/api/monitor_policy/bulk_create_from_templates/",
            {
                "monitor_object": monitor_object.id,
                "asset_ids": [inst.id],
                "templates": [{"name": "CPU high", "metric_name": metric.name, "algorithm": "max"}],
                "config": {
                    "schedule": {"type": "min", "value": 5},
                    "period": {"type": "min", "value": 5},
                    "enable_alerts": ["threshold"],
                },
            },
            format="json",
        )

        assert resp.status_code == 401
        assert resp.json()["message"].startswith("无权限访问指定监控资产")
        disable_error_log_async.delay.assert_not_called()
        assert MonitorPolicy.objects.filter(monitor_object=monitor_object).count() == 0
        assert set(PeriodicTask.objects.values_list("name", flat=True)) == before_task_names

    def test_bulk_template_create_authorized_asset_creates_policy_and_task(self, api_client, mocker):
        api_client.cookies["current_team"] = "1"
        _patch_policy_business_permissions(mocker, teams=[1])
        monitor_object, metric = self._metric_template_context()
        inst = MonitorInstance.objects.create(id=f"('{_name('host-allowed')}',)", name="host-allowed", monitor_object=monitor_object)
        MonitorInstanceOrganization.objects.create(monitor_instance=inst, organization=1)

        resp = api_client.post(
            f"{BASE}/api/monitor_policy/bulk_create_from_templates/",
            {
                "monitor_object": monitor_object.id,
                "asset_ids": [inst.id],
                "templates": [
                    {
                        "name": "CPU high",
                        "metric_name": metric.name,
                        "metric_unit": "percent",
                        "algorithm": "max",
                        "threshold": [{"level": "critical", "method": ">", "value": 90}],
                    }
                ],
                "config": {
                    "name_prefix": "biz",
                    "schedule": {"type": "min", "value": 5},
                    "period": {"type": "min", "value": 5},
                    "enable_alerts": ["threshold"],
                    "group_by": ["instance_id"],
                },
            },
            format="json",
        )

        assert resp.status_code == 200
        body = resp.json()["data"]
        assert body["created_count"] == 1
        policy_id = body["policy_ids"][0]
        policy = MonitorPolicy.objects.get(id=policy_id)
        assert policy.source == {"type": "instance", "values": [inst.id]}
        assert PolicyOrganization.objects.filter(policy_id=policy_id, organization=1).exists()
        assert PeriodicTask.objects.filter(name=f"scan_policy_task_{policy_id}").exists()
