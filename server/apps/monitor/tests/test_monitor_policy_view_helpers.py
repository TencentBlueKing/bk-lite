"""MonitorPolicyViewSet 业务方法规格测试（直接实例化 ViewSet 调方法）。

聚焦基准状态计算、配置变更原因、告警关闭、组织/定时任务维护。
AlertLifecycleNotifier / PolicyBaselineService 等外部边界 mock。
"""

from types import SimpleNamespace

import pytest

from apps.core.exceptions.base_app_exception import BaseAppException
from apps.monitor.models import MonitorAlert
from apps.monitor.models.monitor_object import MonitorObject
from apps.monitor.models.monitor_policy import (
    MonitorPolicy,
    PolicyOrganization,
)
from apps.monitor.views.monitor_policy import MonitorPolicyViewSet

pytestmark = pytest.mark.django_db


def _vs():
    return MonitorPolicyViewSet()


def _policy_obj(**kwargs):
    base = dict(
        enable_alerts=["threshold"],
        source={"type": "instance", "values": ["b", "a"]},
        group_by=["instance_id"],
        query_condition={"type": "pmq", "query": "up"},
        monitor_object_id=1,
        collect_type="snmp",
    )
    base.update(kwargs)
    return SimpleNamespace(**base)


class TestIsNoDataAlertEnabled:
    def test_true(self):
        assert _vs().is_no_data_alert_enabled(_policy_obj(enable_alerts=["no_data"])) is True

    def test_false(self):
        assert _vs().is_no_data_alert_enabled(_policy_obj(enable_alerts=["threshold"])) is False

    def test_none_policy(self):
        assert _vs().is_no_data_alert_enabled(None) is False


class TestNormalizeBaselineSource:
    def test_sorts_values(self):
        out = _vs()._normalize_baseline_source({"type": "instance", "values": ["b", "a", "c"]})
        assert out["values"] == ["a", "b", "c"]

    def test_empty_source(self):
        assert _vs()._normalize_baseline_source(None) == {}

    def test_non_dict_passthrough(self):
        assert _vs()._normalize_baseline_source("x") == "x"


class TestBaselineState:
    def test_get_state_normalizes_source(self):
        state = _vs().get_baseline_state(_policy_obj())
        assert state["source"]["values"] == ["a", "b"]
        assert state["monitor_object"] == 1

    def test_none_policy(self):
        assert _vs().get_baseline_state(None) == {}

    def test_state_changed(self):
        vs = _vs()
        old = vs.get_baseline_state(_policy_obj())
        changed = _policy_obj(group_by=["instance_id", "device"])
        assert vs.baseline_state_changed(old, changed) is True
        assert vs.baseline_state_changed(old, _policy_obj()) is False

    def test_state_changed_empty_inputs(self):
        assert _vs().baseline_state_changed({}, _policy_obj()) is False


class TestShouldUpdateBaselines:
    def test_both_disabled_false(self):
        vs = _vs()
        old = _policy_obj(enable_alerts=["threshold"])
        new = _policy_obj(enable_alerts=["threshold"])
        assert vs.should_update_policy_baselines(old, vs.get_baseline_state(old), new) is False

    def test_toggle_enables_update(self):
        vs = _vs()
        old = _policy_obj(enable_alerts=["threshold"])
        new = _policy_obj(enable_alerts=["no_data"])
        assert vs.should_update_policy_baselines(old, vs.get_baseline_state(old), new) is True

    def test_state_change_when_both_enabled(self):
        vs = _vs()
        old = _policy_obj(enable_alerts=["no_data"])
        new = _policy_obj(enable_alerts=["no_data"], group_by=["x"])
        assert vs.should_update_policy_baselines(old, vs.get_baseline_state(old), new) is True


class TestConfigChangeReason:
    def test_scope_changed(self):
        vs = _vs()
        old = vs.get_baseline_state(_policy_obj())
        new = _policy_obj(source={"type": "instance", "values": ["z"]})
        assert vs.get_policy_config_change_reason(old, new) == "policy_scope_changed"

    def test_group_by_changed(self):
        vs = _vs()
        old = vs.get_baseline_state(_policy_obj())
        new = _policy_obj(group_by=["x"])
        assert vs.get_policy_config_change_reason(old, new) == "policy_group_by_changed"

    def test_query_condition_changed(self):
        vs = _vs()
        old = vs.get_baseline_state(_policy_obj())
        new = _policy_obj(query_condition={"type": "pmq", "query": "down"})
        assert vs.get_policy_config_change_reason(old, new) == "policy_query_condition_changed"

    def test_monitor_target_changed(self):
        vs = _vs()
        old = vs.get_baseline_state(_policy_obj())
        new = _policy_obj(collect_type="trap")
        assert vs.get_policy_config_change_reason(old, new) == "policy_monitor_target_changed"

    def test_no_change(self):
        vs = _vs()
        old = vs.get_baseline_state(_policy_obj())
        assert vs.get_policy_config_change_reason(old, _policy_obj()) == ""


class TestFormatCrontab:
    def test_min(self):
        cron = _vs().format_crontab({"type": "min", "value": 5})
        assert cron.minute == "*/5"

    def test_hour(self):
        cron = _vs().format_crontab({"type": "hour", "value": 2})
        assert cron.hour == "*/2"

    def test_day(self):
        cron = _vs().format_crontab({"type": "day", "value": 1})
        assert cron.day_of_month == "*/1"

    def test_invalid_raises(self):
        with pytest.raises(BaseAppException):
            _vs().format_crontab({"type": "week", "value": 1})


class TestCloseAlerts:
    def test_no_alerts_noop(self, mocker):
        notifier = mocker.patch("apps.monitor.views.monitor_policy.AlertLifecycleNotifier")
        _vs().close_alerts(_policy_obj(), [], "system", "reason")
        notifier.assert_not_called()

    def test_closes_and_notifies(self, mocker):
        notifier = mocker.patch("apps.monitor.views.monitor_policy.AlertLifecycleNotifier")
        obj = MonitorObject.objects.create(name="CAObj", level="base")
        policy = MonitorPolicy.objects.create(
            monitor_object=obj, name="p", algorithm="max",
            query_condition={}, source={}, group_by=[],
        )
        alert = MonitorAlert.objects.create(
            policy_id=policy.id, monitor_instance_id="h1", status="new",
        )
        _vs().close_alerts(policy, [alert], "admin", "manual")
        alert.refresh_from_db()
        assert alert.status == "closed"
        assert alert.operator == "admin"
        assert alert.alert_center_notified is False
        notifier.return_value.notify_alerts.assert_called_once()


class TestHandlePolicyEnableChange:
    def test_no_change_noop(self, mocker):
        spy = mocker.patch.object(MonitorPolicy.objects, "filter")
        _vs().handle_policy_enable_change(1, True, True)
        spy.assert_not_called()

    def test_disable_closes_alerts(self, mocker):
        mocker.patch("apps.monitor.views.monitor_policy.AlertLifecycleNotifier")
        obj = MonitorObject.objects.create(name="HPECObj", level="base")
        policy = MonitorPolicy.objects.create(
            monitor_object=obj, name="p", algorithm="max",
            query_condition={}, source={}, group_by=[],
        )
        alert = MonitorAlert.objects.create(policy_id=policy.id, monitor_instance_id="h1", status="new")
        _vs().handle_policy_enable_change(policy.id, True, False)
        alert.refresh_from_db()
        assert alert.status == "closed"

    def test_enable_sets_last_run_time(self):
        obj = MonitorObject.objects.create(name="HPECObj2", level="base")
        policy = MonitorPolicy.objects.create(
            monitor_object=obj, name="p", algorithm="max",
            query_condition={}, source={}, group_by=[], last_run_time=None,
        )
        _vs().handle_policy_enable_change(policy.id, False, True)
        policy.refresh_from_db()
        assert policy.last_run_time is not None


class TestGetBulkPolicyAssets:
    def test_empty_ids(self):
        assert _vs().get_bulk_policy_assets(1, []) == []

    def test_missing_asset_raises(self):
        obj = MonitorObject.objects.create(name="BulkObj", level="base")
        with pytest.raises(BaseAppException):
            _vs().get_bulk_policy_assets(obj.id, ["('missing',)"])

    def test_returns_assets_with_orgs(self):
        from apps.monitor.models import MonitorInstance, MonitorInstanceOrganization
        obj = MonitorObject.objects.create(name="BulkObj2", level="base")
        inst = MonitorInstance.objects.create(id="('h1',)", name="h1", monitor_object=obj)
        MonitorInstanceOrganization.objects.create(monitor_instance=inst, organization=7)
        assets = _vs().get_bulk_policy_assets(obj.id, ["('h1',)"])
        assert len(assets) == 1
        assert assets[0]["instance_id"] == "('h1',)"
        assert assets[0]["organizations"] == [7]


class TestEnrichBulkPolicyTemplates:
    def test_missing_metric_name_raises(self):
        obj = MonitorObject.objects.create(name="EnrichObj", level="base")
        with pytest.raises(BaseAppException):
            _vs().enrich_bulk_policy_templates(obj.id, [{}])

    def test_metric_not_found_raises(self):
        obj = MonitorObject.objects.create(name="EnrichObj2", level="base")
        with pytest.raises(BaseAppException):
            _vs().enrich_bulk_policy_templates(obj.id, [{"metric_name": "nope"}])

    def test_enriches_with_metric_id_and_unit(self):
        from apps.monitor.models.monitor_metrics import Metric, MetricGroup
        from apps.monitor.models.plugin import MonitorPlugin
        obj = MonitorObject.objects.create(name="EnrichObj3", level="base")
        plugin = MonitorPlugin.objects.create(name="EnrichPlugin")
        group = MetricGroup.objects.create(monitor_object=obj, monitor_plugin=plugin, name="g")
        metric = Metric.objects.create(
            monitor_object=obj, monitor_plugin=plugin, metric_group=group,
            name="cpu", unit="percent",
        )
        out = _vs().enrich_bulk_policy_templates(obj.id, [{"metric_name": "cpu"}])
        assert out[0]["metric_id"] == metric.id
        assert out[0]["metric_unit"] == "percent"

    def test_none_unit_normalized_to_empty(self):
        from apps.monitor.models.monitor_metrics import Metric, MetricGroup
        from apps.monitor.models.plugin import MonitorPlugin
        obj = MonitorObject.objects.create(name="EnrichObj4", level="base")
        plugin = MonitorPlugin.objects.create(name="EnrichPlugin4")
        group = MetricGroup.objects.create(monitor_object=obj, monitor_plugin=plugin, name="g")
        Metric.objects.create(
            monitor_object=obj, monitor_plugin=plugin, metric_group=group,
            name="cnt", unit="none",
        )
        out = _vs().enrich_bulk_policy_templates(obj.id, [{"metric_name": "cnt"}])
        assert out[0]["metric_unit"] == ""


class TestUpdatePolicyOrganizations:
    def test_syncs_org_diff(self):
        obj = MonitorObject.objects.create(name="UPOObj", level="base")
        policy = MonitorPolicy.objects.create(
            monitor_object=obj, name="p", algorithm="max",
            query_condition={}, source={}, group_by=[],
        )
        PolicyOrganization.objects.create(policy=policy, organization=1)
        PolicyOrganization.objects.create(policy=policy, organization=2)
        _vs().update_policy_organizations(policy.id, [2, 3])
        orgs = set(
            PolicyOrganization.objects.filter(policy_id=policy.id).values_list("organization", flat=True)
        )
        assert orgs == {2, 3}
