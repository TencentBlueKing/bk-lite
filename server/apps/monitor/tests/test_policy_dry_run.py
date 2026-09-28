"""策略预检：草稿/已保存、越权过滤、判定、零副作用、连续 N 文案、失败日志。"""

import logging
import traceback
from datetime import datetime, timezone
from types import SimpleNamespace

import pytest
from rest_framework.exceptions import ValidationError

from apps.core.exceptions.base_app_exception import BaseAppException, UnauthorizedException
from apps.monitor.models import (
    MonitorAlert,
    MonitorAlertMetricSnapshot,
    MonitorEvent,
    MonitorInstance,
    PolicyOrganization,
)
from apps.monitor.models.monitor_metrics import Metric, MetricGroup
from apps.monitor.models.monitor_object import MonitorObject
from apps.monitor.models.plugin import MonitorPlugin
from apps.monitor.models.monitor_policy import MonitorPolicy
from apps.monitor.services.policy_dry_run import (
    DRY_RUN_FAIL_TEMPLATE,
    HIT_COUNT_REASON,
    PolicyDryRunService,
)
from apps.monitor.views.monitor_policy import MonitorPolicyViewSet

pytestmark = pytest.mark.django_db

_ACTOR = {"username": "tester", "is_superuser": False}
_TEAM = 7


def _visible_actor(team=_TEAM, **overrides):
    actor = {
        "username": "tester",
        "is_superuser": False,
        "data_scope": SimpleNamespace(data_team_ids=[team]),
    }
    actor.update(overrides)
    return actor


def _attach_org(policy, team=_TEAM):
    PolicyOrganization.objects.create(policy=policy, organization=team)
    return policy


@pytest.fixture
def metric_ctx():
    obj = MonitorObject.objects.create(
        name="DryRunObj",
        level="base",
        instance_id_keys=["instance_id"],
    )
    plugin = MonitorPlugin.objects.create(name="DryRunPlugin")
    group = MetricGroup.objects.create(
        monitor_object=obj, monitor_plugin=plugin, name="g"
    )
    metric = Metric.objects.create(
        monitor_object=obj,
        monitor_plugin=plugin,
        metric_group=group,
        name="cpu",
        query="cpu{__$labels__}",
        instance_id_keys=["instance_id"],
        data_type="Number",
        unit="percent",
    )
    return {"obj": obj, "metric": metric}


def _instance(obj, instance_id, name):
    return MonitorInstance.objects.create(
        id=instance_id, name=name, monitor_object=obj
    )


def _payload(metric_ctx, **overrides):
    metric = metric_ctx["metric"]
    data = {
        "name": "dry-run",
        "alert_name": "$instance_name 超阈值 $value",
        "monitor_object": metric.monitor_object_id,
        "query_condition": {
            "type": "metric",
            "metric_id": metric.id,
            "filter": [],
        },
        "source": {"type": "instance", "values": ["('h1',)"]},
        "schedule": {"type": "min", "value": 5},
        "period": {"type": "min", "value": 5},
        "group_algorithm": "avg",
        "algorithm": "avg_over_time",
        "group_by": ["instance_id"],
        "enable_alerts": ["threshold"],
        "threshold": [{"level": "critical", "method": ">", "value": 80}],
        "metric_unit": "percent",
        "calculation_unit": "percent",
        "threshold_unit": "percent",
        "trigger_count": 1,
        "recovery_condition": 1,
        "compare_mode": "absolute",
    }
    data.update(overrides)
    return data


def _vm(*series):
    return {"status": "success", "data": {"result": list(series)}}


def _series(instance_id, *values):
    points = [[index + 1, str(value)] for index, value in enumerate(values)]
    return {"metric": {"instance_id": instance_id}, "values": points}


def _queue_vm(mocker, *responses):
    queue = list(responses)
    return mocker.patch(
        "apps.monitor.tasks.services.policy_scan.metric_query.VictoriaMetricsAPI.query_range",
        side_effect=lambda *args, **kwargs: queue.pop(0) if queue else _vm(),
    )


def _authorize(mocker, allowed_ids=None):
    def _fake(actor_context, object_id, require_operate=False):
        qs = MonitorInstance.objects.filter(
            monitor_object_id=object_id, is_deleted=False
        )
        if allowed_ids is not None:
            qs = qs.filter(id__in=allowed_ids)
        return qs

    return mocker.patch(
        "apps.monitor.services.policy_dry_run.InstanceConfigService._get_authorized_monitor_instances",
        side_effect=_fake,
    )


def _run(payload, mocker, *vm_responses, allowed_ids=None, actor=None):
    _authorize(mocker, allowed_ids)
    _queue_vm(mocker, *vm_responses)
    return PolicyDryRunService(payload, actor or _ACTOR).run()


def _verdicts(result):
    return {item["instance_id"]: item["verdict"] for item in result["items"]}


def test_draft_would_trigger(metric_ctx, mocker):
    _instance(metric_ctx["obj"], "('h1',)", "主机1")
    result = _run(
        _payload(metric_ctx),
        mocker,
        _vm(_series("h1", 90)),
        _vm(_series("h1", 90)),
    )
    item = result["items"][0]
    assert item["verdict"] == "would_trigger"
    assert item["compared_value"] == 90
    assert item["current_value"] == 90
    assert item["matched_threshold"]["level"] == "critical"
    assert item["reason"] == ""


def test_saved_policy_uses_id_without_writing(metric_ctx, mocker):
    _instance(metric_ctx["obj"], "('h1',)", "主机1")
    last_run_time = datetime(2026, 1, 1, tzinfo=timezone.utc)
    policy = MonitorPolicy.objects.create(
        monitor_object=metric_ctx["obj"],
        name="saved",
        algorithm="avg_over_time",
        query_condition={"type": "metric", "metric_id": metric_ctx["metric"].id},
        source={"type": "instance", "values": ["('h1',)"]},
        group_by=["instance_id"],
        last_run_time=last_run_time,
    )
    result = _run(
        _payload(metric_ctx, id=policy.id),
        mocker,
        _vm(_series("h1", 10)),
        _vm(_series("h1", 10)),
    )
    policy.refresh_from_db()
    assert result["items"][0]["verdict"] == "ok"
    assert policy.last_run_time == last_run_time


def test_unauthorized_source_instances_are_filtered(metric_ctx, mocker):
    _instance(metric_ctx["obj"], "('h1',)", "主机1")
    _instance(metric_ctx["obj"], "('h2',)", "主机2")
    result = _run(
        _payload(
            metric_ctx,
            source={"type": "instance", "values": ["('h1',)", "('h2',)"]},
        ),
        mocker,
        _vm(_series("h1", 90), _series("h2", 90)),
        _vm(_series("h1", 90), _series("h2", 90)),
        allowed_ids=["('h1',)"],
    )
    assert list(_verdicts(result)) == ["('h1',)"]


def test_unauthorized_preview_instance_is_rejected(metric_ctx, mocker):
    _instance(metric_ctx["obj"], "('h1',)", "主机1")
    _instance(metric_ctx["obj"], "('h2',)", "主机2")
    _authorize(mocker, allowed_ids=["('h1',)"])
    with pytest.raises(UnauthorizedException):
        PolicyDryRunService(
            _payload(metric_ctx, preview={"instance_id": "('h2',)"}),
            _ACTOR,
        ).run()


def test_preview_instance_id_values_rewritten_to_authorized_identity(metric_ctx, mocker):
    _instance(metric_ctx["obj"], "('h1',)", "主机1")
    _authorize(mocker, allowed_ids=["('h1',)"])
    payload = _payload(
        metric_ctx,
        preview={
            "instance_id": "('h1',)",
            "instance_id_values": ["other-host"],
        },
    )
    PolicyDryRunService.authorize_preview_payload(payload, _ACTOR)
    assert payload["preview"]["instance_id_values"] == ["h1"]


def test_verdict_no_data(metric_ctx, mocker):
    _instance(metric_ctx["obj"], "('h1',)", "主机1")
    result = _run(_payload(metric_ctx), mocker, _vm(), _vm())
    assert result["items"][0]["verdict"] == "no_data"
    assert result["items"][0]["reason"] == "无数据"


def test_verdict_missing_baseline(metric_ctx, mocker):
    _instance(metric_ctx["obj"], "('h1',)", "主机1")
    result = _run(
        _payload(metric_ctx),
        mocker,
        _vm(_series("h1", 12)),
        _vm(),
    )
    assert result["items"][0]["verdict"] == "missing_baseline"
    assert "对照缺失" in result["items"][0]["reason"]


def test_verdict_insufficient_samples(metric_ctx, mocker):
    _instance(metric_ctx["obj"], "('h1',)", "主机1")
    result = _run(
        _payload(metric_ctx, trigger_count=3),
        mocker,
        _vm(_series("h1", 90)),
        _vm(_series("h1", 90)),
    )
    item = result["items"][0]
    assert item["verdict"] == "insufficient_samples"
    assert "样本不足" in item["reason"]
    assert HIT_COUNT_REASON.format(hit=1, total=3) in item["reason"]


def test_trigger_count_copy_when_not_firing(metric_ctx, mocker):
    _instance(metric_ctx["obj"], "('h1',)", "主机1")
    result = _run(
        _payload(metric_ctx, trigger_count=2),
        mocker,
        _vm(_series("h1", 10, 90)),
        _vm(_series("h1", 10, 90)),
    )
    item = result["items"][0]
    assert item["verdict"] == "ok"
    assert item["reason"] == HIT_COUNT_REASON.format(hit=1, total=2)


def test_draft_does_not_evaluate_recovery(metric_ctx, mocker):
    _instance(metric_ctx["obj"], "('h1',)", "主机1")
    MonitorAlert.objects.create(
        policy_id=999,
        monitor_instance_id="('h1',)",
        metric_instance_id="('h1',)",
        alert_type="alert",
        status="new",
        info_event_count=0,
    )
    result = _run(
        _payload(metric_ctx),
        mocker,
        _vm(_series("h1", 10)),
        _vm(_series("h1", 10)),
    )
    assert result["items"][0]["verdict"] == "ok"


def test_saved_active_alert_would_recover(metric_ctx, mocker):
    _instance(metric_ctx["obj"], "('h1',)", "主机1")
    policy = MonitorPolicy.objects.create(
        monitor_object=metric_ctx["obj"],
        name="saved-recover",
        algorithm="avg_over_time",
        query_condition={"type": "metric", "metric_id": metric_ctx["metric"].id},
        source={"type": "instance", "values": ["('h1',)"]},
        group_by=["instance_id"],
        recovery_condition=1,
    )
    _attach_org(policy)
    alert = MonitorAlert.objects.create(
        policy_id=policy.id,
        monitor_instance_id="('h1',)",
        metric_instance_id="('h1',)",
        alert_type="alert",
        status="new",
        info_event_count=0,
    )
    result = _run(
        _payload(metric_ctx, id=policy.id, recovery_condition=1),
        mocker,
        _vm(_series("h1", 10)),
        _vm(_series("h1", 10)),
        actor=_visible_actor(),
    )
    alert.refresh_from_db()
    assert result["items"][0]["verdict"] == "would_recover"
    assert alert.status == "new"
    assert alert.info_event_count == 0


def test_saved_active_alert_hold_in_hysteresis_band(metric_ctx, mocker):
    _instance(metric_ctx["obj"], "('h1',)", "主机1")
    policy = MonitorPolicy.objects.create(
        monitor_object=metric_ctx["obj"],
        name="saved-hold",
        algorithm="avg_over_time",
        query_condition={"type": "metric", "metric_id": metric_ctx["metric"].id},
        source={"type": "instance", "values": ["('h1',)"]},
        group_by=["instance_id"],
        recovery_condition=1,
        recovery_threshold={"method": "<", "value": 70},
        threshold=[{"level": "critical", "method": ">", "value": 80}],
    )
    _attach_org(policy)
    alert = MonitorAlert.objects.create(
        policy_id=policy.id,
        monitor_instance_id="('h1',)",
        metric_instance_id="('h1',)",
        alert_type="alert",
        status="new",
        info_event_count=3,
    )
    result = _run(
        _payload(
            metric_ctx,
            id=policy.id,
            recovery_condition=1,
            recovery_threshold={"method": "<", "value": 70},
        ),
        mocker,
        _vm(_series("h1", 75)),
        _vm(_series("h1", 75)),
        actor=_visible_actor(),
    )
    alert.refresh_from_db()
    assert result["items"][0]["verdict"] == "hold"
    assert alert.status == "new"
    assert alert.info_event_count == 3


def test_foreign_saved_id_does_not_evaluate_recovery(metric_ctx, mocker):
    _instance(metric_ctx["obj"], "('h1',)", "主机1")
    policy = MonitorPolicy.objects.create(
        monitor_object=metric_ctx["obj"],
        name="foreign-policy",
        algorithm="avg_over_time",
        query_condition={"type": "metric", "metric_id": metric_ctx["metric"].id},
        source={"type": "instance", "values": ["('h1',)"]},
        group_by=["instance_id"],
        recovery_condition=1,
    )
    _attach_org(policy, team=99)
    MonitorAlert.objects.create(
        policy_id=policy.id,
        monitor_instance_id="('h1',)",
        metric_instance_id="('h1',)",
        alert_type="alert",
        status="new",
        info_event_count=0,
    )
    result = _run(
        _payload(metric_ctx, id=policy.id, recovery_condition=1),
        mocker,
        _vm(_series("h1", 10)),
        _vm(_series("h1", 10)),
        actor=_visible_actor(team=_TEAM),
    )
    assert result["items"][0]["verdict"] == "ok"


def test_draft_hysteresis_band_is_ok(metric_ctx, mocker):
    _instance(metric_ctx["obj"], "('h1',)", "主机1")
    result = _run(
        _payload(metric_ctx, recovery_threshold={"method": "<", "value": 70}),
        mocker,
        _vm(_series("h1", 75)),
        _vm(_series("h1", 75)),
    )
    assert result["items"][0]["verdict"] == "ok"


def test_zero_side_effects(metric_ctx, mocker):
    _instance(metric_ctx["obj"], "('h1',)", "主机1")
    policy = MonitorPolicy.objects.create(
        monitor_object=metric_ctx["obj"],
        name="saved-side-effect",
        algorithm="avg_over_time",
        query_condition={"type": "metric", "metric_id": metric_ctx["metric"].id},
        source={"type": "instance", "values": ["('h1',)"]},
        group_by=["instance_id"],
        last_run_time=datetime(2026, 1, 1, tzinfo=timezone.utc),
    )
    alert = MonitorAlert.objects.create(
        policy_id=policy.id,
        monitor_instance_id="('h1',)",
        metric_instance_id="('h1',)",
        alert_type="alert",
        status="new",
    )
    MonitorEvent.objects.create(
        id="dry-run-evt",
        alert=alert,
        policy_id=policy.id,
        monitor_instance_id="('h1',)",
        level="critical",
        content="seed",
    )
    event_manager = mocker.patch(
        "apps.monitor.tasks.services.policy_scan.event_alert_manager.EventAlertManager"
    )
    notifier = mocker.patch(
        "apps.monitor.services.alert_lifecycle_notify.AlertLifecycleNotifier"
    )
    detector_notifier = mocker.patch(
        "apps.monitor.tasks.services.policy_scan.alert_detector.AlertLifecycleNotifier"
    )
    before = (
        MonitorAlert.objects.count(),
        MonitorEvent.objects.count(),
        MonitorAlertMetricSnapshot.objects.count(),
        policy.last_run_time,
    )
    _run(
        _payload(metric_ctx, id=policy.id),
        mocker,
        _vm(_series("h1", 90)),
        _vm(_series("h1", 90)),
    )
    policy.refresh_from_db()
    assert (
        MonitorAlert.objects.count(),
        MonitorEvent.objects.count(),
        MonitorAlertMetricSnapshot.objects.count(),
        policy.last_run_time,
    ) == before
    event_manager.assert_not_called()
    notifier.assert_not_called()
    detector_notifier.assert_not_called()


def test_truncated_keeps_preview_instance(metric_ctx, mocker):
    _instance(metric_ctx["obj"], "('h1',)", "主机1")
    _instance(metric_ctx["obj"], "('h2',)", "主机2")
    mocker.patch(
        "apps.monitor.services.policy_dry_run.DRY_RUN_INSTANCE_LIMIT",
        1,
    )
    result = _run(
        _payload(
            metric_ctx,
            source={"type": "instance", "values": ["('h1',)", "('h2',)"]},
            preview={"instance_id": "('h2',)"},
        ),
        mocker,
        _vm(_series("h2", 10)),
        _vm(_series("h2", 10)),
    )
    assert result["truncated"] is True
    assert [item["instance_id"] for item in result["items"]] == ["('h2',)"]
    assert "已截断" in result["warnings"][0]


def test_d4_rejection_does_not_log_engine_failure(metric_ctx, mocker, caplog):
    _instance(metric_ctx["obj"], "('h1',)", "主机1")
    _authorize(mocker)
    caplog.set_level(logging.DEBUG, logger="monitor")
    with pytest.raises(ValidationError):
        PolicyDryRunService(
            _payload(metric_ctx, compare_mode="offset_1h"),
            _ACTOR,
        ).run()
    assert not [
        record
        for record in caplog.records
        if record.msg == DRY_RUN_FAIL_TEMPLATE
    ]


def test_failure_logs_single_warning_without_query_or_payload(metric_ctx, mocker, caplog):
    _instance(metric_ctx["obj"], "('h1',)", "主机1")
    _authorize(mocker)
    sentinel = 'avg_over_time(cpu{job="secret"}[5m]) payload-BODY'
    mocker.patch(
        "apps.monitor.tasks.services.policy_scan.metric_query.VictoriaMetricsAPI.query_range",
        side_effect=RuntimeError("query failed"),
    )
    caplog.set_level(logging.DEBUG, logger="monitor")
    with pytest.raises(BaseAppException, match="预检失败"):
        PolicyDryRunService(
            _payload(metric_ctx, name=sentinel),
            _ACTOR,
        ).run()
    records = [
        record for record in caplog.records if record.msg == DRY_RUN_FAIL_TEMPLATE
    ]
    assert len(records) == 1
    record = records[0]
    assert record.levelno == logging.WARNING
    assert record.args == ("", "query_existence", "RuntimeError")
    assert record.exc_info is not None
    formatted = record.getMessage()
    assert formatted == (
        "event=monitor_policy_dry_run_failed policy_id= "
        "failed_stage=query_existence error_type=RuntimeError"
    )
    tb_text = "".join(traceback.format_exception(*record.exc_info))
    assert sentinel not in record.msg
    assert sentinel not in str(record.args)
    assert sentinel not in formatted
    assert sentinel not in tb_text
    assert all(sentinel not in (record.getMessage() or "") for record in caplog.records)


def test_preview_and_dry_run_accept_add_or_edit():
    from types import SimpleNamespace

    from rest_framework.test import APIRequestFactory, force_authenticate

    factory = APIRequestFactory()

    def _invoke(action, permissions):
        request = factory.post("/", {}, format="json")
        user = SimpleNamespace(
            username="permission-user",
            domain="domain.com",
            locale="en",
            is_superuser=False,
            is_authenticated=True,
            permission={"monitor": set(permissions)},
        )
        force_authenticate(request, user=user)
        view = MonitorPolicyViewSet.as_view({"post": action})
        try:
            response = view(request)
        except Exception:
            return None
        return response.status_code

    for action in ("preview", "dry_run"):
        assert _invoke(action, set()) == 403
        assert _invoke(action, {"strategy_list-Add"}) != 403
        assert _invoke(action, {"strategy_list-Edit"}) != 403
