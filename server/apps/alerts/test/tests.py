import json
from datetime import datetime, timedelta
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.test import Client
from django.test import TestCase
from django.utils import timezone

from apps.alerts.aggregation.builder.synthetic_alert_builder import (
    SyntheticAlertBuilder,
)
from apps.alerts.aggregation.processor.aggregation_processor import AggregationProcessor
from apps.alerts.aggregation.recovery.recovery_handler import RecoveryHandler
from apps.alerts.nats.nats import receive_alert_events
from apps.alerts.constants import (
    AlertStatus,
    AlarmStrategyType,
    AlertsSourceTypes,
    EventAction,
    EventType,
    HeartbeatActivationMode,
    HeartbeatCheckMode,
    HeartbeatStatus,
    LevelType,
)
from apps.alerts.models import Alert, AlertSource, AlarmStrategy, Event, Level
from apps.alerts.serializers.alert_source import AlertSourceModelSerializer
from apps.alerts.serializers.strategy import AlarmStrategySerializer


class AlarmStrategySerializerTestCase(TestCase):
    def test_missing_detection_serializer_strips_runtime_fields(self):
        serializer = AlarmStrategySerializer(
            data={
                "name": "heartbeat-rule",
                "strategy_type": AlarmStrategyType.MISSING_DETECTION,
                "team": [1],
                "dispatch_team": [1],
                "match_rules": [[{"key": "service", "operator": "eq", "value": "backup"}]],
                "params": {
                    "check_mode": HeartbeatCheckMode.CRON,
                    "cron_expr": "*/5 * * * *",
                    "grace_period": 2,
                    "activation_mode": HeartbeatActivationMode.IMMEDIATE,
                    "auto_recovery": True,
                    "heartbeat_status": HeartbeatStatus.ALERTING,
                    "last_heartbeat_time": "2026-03-20T00:00:00+08:00",
                    "last_heartbeat_context": {"service": "x"},
                    "alert_template": {
                        "title": "{{service}} missing",
                        "level": "1",
                        "description": "heartbeat lost",
                    },
                },
                "auto_close": False,
                "close_minutes": 120,
            }
        )

        self.assertTrue(serializer.is_valid(), serializer.errors)
        params = serializer.validated_data["params"]
        self.assertEqual(params["heartbeat_status"], HeartbeatStatus.WAITING)
        self.assertIsNone(params["last_heartbeat_time"])
        self.assertIsNone(params["last_heartbeat_context"])

    def test_missing_detection_serializer_rejects_invalid_config(self):
        serializer = AlarmStrategySerializer(
            data={
                "name": "heartbeat-rule",
                "strategy_type": AlarmStrategyType.MISSING_DETECTION,
                "team": [1],
                "dispatch_team": [1],
                "match_rules": [],
                "params": {
                    "check_mode": HeartbeatCheckMode.CRON,
                    "interval_value": 5,
                    "interval_unit": "minutes",
                    "cron_expr": "bad cron",
                    "grace_period": 0,
                    "alert_template": {"title": "", "level": "", "description": ""},
                },
            }
        )

        self.assertFalse(serializer.is_valid())
        self.assertIn("match_rules", serializer.errors)

    def test_missing_detection_serializer_rejects_non_cron_mode(self):
        serializer = AlarmStrategySerializer(
            data={
                "name": "heartbeat-rule",
                "strategy_type": AlarmStrategyType.MISSING_DETECTION,
                "team": [1],
                "dispatch_team": [1],
                "match_rules": [[{"key": "service", "operator": "eq", "value": "backup"}]],
                "params": {
                    "check_mode": "interval",
                    "cron_expr": "*/5 * * * *",
                    "grace_period": 1,
                    "activation_mode": HeartbeatActivationMode.IMMEDIATE,
                    "auto_recovery": True,
                    "alert_template": {
                        "title": "{{service}} missing",
                        "level": "1",
                        "description": "heartbeat lost",
                    },
                },
            }
        )

        self.assertFalse(serializer.is_valid())
        self.assertEqual(
            serializer.errors["params"]["check_mode"][0],
            "缺失检查仅支持 cron 模式。",
        )

    def test_missing_detection_serializer_rejects_interval_fields(self):
        serializer = AlarmStrategySerializer(
            data={
                "name": "heartbeat-rule",
                "strategy_type": AlarmStrategyType.MISSING_DETECTION,
                "team": [1],
                "dispatch_team": [1],
                "match_rules": [[{"key": "service", "operator": "eq", "value": "backup"}]],
                "params": {
                    "check_mode": HeartbeatCheckMode.CRON,
                    "cron_expr": "*/5 * * * *",
                    "interval_value": 5,
                    "interval_unit": "minutes",
                    "grace_period": 1,
                    "activation_mode": HeartbeatActivationMode.IMMEDIATE,
                    "auto_recovery": True,
                    "alert_template": {
                        "title": "{{service}} missing",
                        "level": "1",
                        "description": "heartbeat lost",
                    },
                },
            }
        )

        self.assertFalse(serializer.is_valid())
        self.assertEqual(
            serializer.errors["params"]["interval_value"][0],
            "缺失检查不再支持固定间隔数值。",
        )
        self.assertEqual(
            serializer.errors["params"]["interval_unit"][0],
            "缺失检查不再支持固定间隔单位。",
        )


class MissingDetectionProcessorTestCase(TestCase):
    def setUp(self):
        self.source = AlertSource.objects.create(
            name="test-source",
            source_id="source-1",
            source_type=AlertsSourceTypes.WEBHOOK,
        )
        Level.objects.create(
            level_id=1,
            level_name="warning",
            level_display_name="预警",
            color="#FAAD14",
            icon="",
            description="",
            level_type=LevelType.ALERT,
        )
        self.processor = AggregationProcessor()

    def create_strategy(self, **overrides):
        params = {
            "check_mode": HeartbeatCheckMode.CRON,
            "cron_expr": "*/5 * * * *",
            "grace_period": 1,
            "activation_mode": HeartbeatActivationMode.IMMEDIATE,
            "auto_recovery": True,
            "heartbeat_status": HeartbeatStatus.WAITING,
            "last_heartbeat_time": None,
            "last_heartbeat_context": None,
            "alert_template": {
                "title": "{{service}} 心跳缺失",
                "level": "1",
                "description": "期望事件未按时到达",
            },
        }
        params.update(overrides.pop("params", {}))
        return AlarmStrategy.objects.create(
            name=overrides.pop("name", "strategy-%s" % timezone.now().timestamp()),
            strategy_type=overrides.pop("strategy_type", AlarmStrategyType.MISSING_DETECTION),
            team=[1],
            dispatch_team=[1],
            match_rules=overrides.pop(
                "match_rules",
                [[{"key": "service", "operator": "eq", "value": "backup"}]],
            ),
            params=params,
            auto_close=False,
            close_minutes=120,
            **overrides,
        )

    def create_event(self, received_at, **overrides):
        event = Event.objects.create(
            source=self.source,
            raw_data={},
            title=overrides.pop("title", "heartbeat"),
            description=overrides.pop("description", "heartbeat ok"),
            level=overrides.pop("level", "1"),
            service=overrides.pop("service", "backup"),
            event_type=overrides.pop("event_type", EventType.ALERT),
            tags=overrides.pop("tags", {}),
            location=overrides.pop("location", "gz"),
            external_id=overrides.pop("external_id", "hb-1"),
            start_time=overrides.pop("start_time", received_at),
            end_time=overrides.pop("end_time", None),
            labels=overrides.pop("labels", {}),
            action=overrides.pop("action", EventAction.CREATED),
            rule_id=overrides.pop("rule_id", None),
            event_id=overrides.pop("event_id", "EVENT-%s" % timezone.now().timestamp()),
            item=overrides.pop("item", "job"),
            resource_id=overrides.pop("resource_id", "r-1"),
            resource_type=overrides.pop("resource_type", "task"),
            resource_name=overrides.pop("resource_name", "backup-job"),
            status=overrides.pop("status", "received"),
            assignee=overrides.pop("assignee", []),
            value=overrides.pop("value", None),
        )
        Event.objects.filter(pk=event.pk).update(received_at=received_at)
        event.refresh_from_db()
        return event

    def test_process_strategy_dispatches_by_strategy_type(self):
        smart_strategy = self.create_strategy(
            name="smart-rule",
            strategy_type=AlarmStrategyType.SMART_DENOISE,
            params={"group_by": ["service"], "window_size": 5, "time_out": False},
        )
        missing_strategy = self.create_strategy(name="missing-rule")
        now = timezone.now()

        with (
            patch.object(self.processor, "_process_missing_detection_strategy") as missing_mock,
            patch.object(self.processor, "get_events_for_strategy") as events_mock,
        ):
            events_mock.return_value.exists.return_value = False
            self.processor._process_strategy(smart_strategy, now)
            self.processor._process_strategy(missing_strategy, now)

        events_mock.assert_called_once_with(smart_strategy)
        missing_mock.assert_called_once_with(missing_strategy, now)

    def test_first_heartbeat_mode_waits_for_first_event(self):
        now = timezone.make_aware(datetime(2026, 3, 20, 10, 0, 0))
        strategy = self.create_strategy(
            params={
                "activation_mode": HeartbeatActivationMode.FIRST_HEARTBEAT,
                "heartbeat_status": HeartbeatStatus.WAITING,
            }
        )
        AlarmStrategy.objects.filter(pk=strategy.pk).update(created_at=now - timedelta(minutes=10))
        strategy.refresh_from_db()

        self.processor._process_missing_detection_strategy(strategy, now)
        strategy.refresh_from_db()

        self.assertEqual(strategy.params["heartbeat_status"], HeartbeatStatus.WAITING)
        self.assertEqual(Alert.objects.count(), 0)
        self.assertEqual(strategy.last_execute_time, now)

    def test_first_heartbeat_mode_enters_monitoring_after_first_event(self):
        now = timezone.make_aware(datetime(2026, 3, 20, 10, 0, 0))
        strategy = self.create_strategy(
            params={
                "activation_mode": HeartbeatActivationMode.FIRST_HEARTBEAT,
                "heartbeat_status": HeartbeatStatus.WAITING,
            }
        )
        self.create_event(now - timedelta(minutes=1), event_id="EVENT-FIRST")

        self.processor._process_missing_detection_strategy(strategy, now)
        strategy.refresh_from_db()

        self.assertEqual(strategy.params["heartbeat_status"], HeartbeatStatus.MONITORING)
        self.assertEqual(strategy.params["last_heartbeat_context"]["service"], "backup")

    def test_immediate_mode_triggers_single_missing_alert(self):
        now = timezone.make_aware(datetime(2026, 3, 20, 10, 10, 0))
        strategy = self.create_strategy(
            params={
                "activation_mode": HeartbeatActivationMode.IMMEDIATE,
                "heartbeat_status": HeartbeatStatus.WAITING,
                "cron_expr": "*/5 * * * *",
                "grace_period": 1,
            }
        )
        AlarmStrategy.objects.filter(pk=strategy.pk).update(created_at=now - timedelta(minutes=7))
        strategy.refresh_from_db()

        self.processor._process_missing_detection_strategy(strategy, now)
        self.processor._process_missing_detection_strategy(strategy, now + timedelta(minutes=1))
        strategy.refresh_from_db()

        self.assertEqual(Alert.objects.count(), 1)
        self.assertEqual(strategy.params["heartbeat_status"], HeartbeatStatus.ALERTING)
        self.assertEqual(strategy.last_execute_time, now + timedelta(minutes=1))

    def test_cron_mode_uses_recent_expected_slot(self):
        now = timezone.make_aware(datetime(2026, 3, 20, 10, 7, 0))
        strategy = self.create_strategy(
            params={
                "check_mode": HeartbeatCheckMode.CRON,
                "cron_expr": "*/5 * * * *",
                "grace_period": 1,
                "heartbeat_status": HeartbeatStatus.MONITORING,
                "last_heartbeat_time": (now - timedelta(minutes=10)).isoformat(),
            }
        )

        self.processor._process_missing_detection_strategy(strategy, now)
        self.assertEqual(Alert.objects.count(), 1)

    def test_business_timezone_cron_is_converted_before_comparison(self):
        now = timezone.make_aware(datetime(2026, 3, 20, 8, 35, 0))
        strategy = self.create_strategy(
            params={
                "check_mode": HeartbeatCheckMode.CRON,
                "cron_expr": "30 16 * * *",
                "grace_period": 20,
                "heartbeat_status": HeartbeatStatus.MONITORING,
                "last_heartbeat_time": None,
            }
        )
        AlarmStrategy.objects.filter(pk=strategy.pk).update(created_at=timezone.make_aware(datetime(2026, 3, 20, 0, 0, 0)))
        strategy.refresh_from_db()

        deadline = self.processor._calculate_deadline(strategy, strategy.params, now)

        self.assertEqual(deadline.isoformat(), "2026-03-20T08:50:00+00:00")

    def test_immediate_mode_waits_until_first_expected_slot_after_creation(self):
        now = timezone.make_aware(datetime(2026, 3, 20, 10, 2, 0))
        strategy = self.create_strategy(
            params={
                "activation_mode": HeartbeatActivationMode.IMMEDIATE,
                "heartbeat_status": HeartbeatStatus.WAITING,
                "cron_expr": "*/5 * * * *",
                "grace_period": 1,
            }
        )
        AlarmStrategy.objects.filter(pk=strategy.pk).update(created_at=now - timedelta(minutes=1))
        strategy.refresh_from_db()

        self.processor._process_missing_detection_strategy(strategy, now)
        strategy.refresh_from_db()

        self.assertEqual(Alert.objects.count(), 0)
        self.assertEqual(strategy.params["heartbeat_status"], HeartbeatStatus.MONITORING)

    def test_immediate_mode_alerts_after_first_expected_slot_passes(self):
        now = timezone.make_aware(datetime(2026, 3, 20, 10, 7, 0))
        strategy = self.create_strategy(
            params={
                "activation_mode": HeartbeatActivationMode.IMMEDIATE,
                "heartbeat_status": HeartbeatStatus.WAITING,
                "cron_expr": "*/5 * * * *",
                "grace_period": 1,
            }
        )
        AlarmStrategy.objects.filter(pk=strategy.pk).update(created_at=now - timedelta(minutes=8))
        strategy.refresh_from_db()

        self.processor._process_missing_detection_strategy(strategy, now)
        strategy.refresh_from_db()

        self.assertEqual(Alert.objects.count(), 1)
        self.assertEqual(strategy.params["heartbeat_status"], HeartbeatStatus.ALERTING)

    def test_auto_recovery_marks_alert_closed_and_returns_monitoring(self):
        now = timezone.make_aware(datetime(2026, 3, 20, 10, 10, 0))
        strategy = self.create_strategy(
            params={
                "heartbeat_status": HeartbeatStatus.ALERTING,
                "last_heartbeat_time": (now - timedelta(minutes=10)).isoformat(),
                "last_heartbeat_context": {"service": "backup"},
            }
        )
        alert = SyntheticAlertBuilder.create_alert(strategy, strategy.params, now - timedelta(minutes=1))
        self.create_event(now, event_id="EVENT-RECOVERY")
        AlarmStrategy.objects.filter(pk=strategy.pk).update(last_execute_time=now - timedelta(minutes=2))
        strategy.refresh_from_db()

        self.processor._process_missing_detection_strategy(strategy, now + timedelta(minutes=1))
        strategy.refresh_from_db()
        alert.refresh_from_db()

        self.assertEqual(alert.status, AlertStatus.AUTO_RECOVERY)
        self.assertEqual(strategy.params["heartbeat_status"], HeartbeatStatus.MONITORING)
        self.assertEqual(
            strategy.params["last_heartbeat_time"],
            Event.objects.get(event_id="EVENT-RECOVERY").received_at.isoformat(),
        )


class AlertSourceIngressTestCase(TestCase):
    def setUp(self):
        self.client = Client()
        self.user = get_user_model().objects.create_user(
            username="alerts-admin",
            password="test-pass-123",
            domain="default.local",
        )
        self.client.force_login(self.user)
        Level.objects.create(
            level_id=3,
            level_name="info",
            level_display_name="提醒",
            color="#1677FF",
            icon="",
            description="",
            level_type=LevelType.EVENT,
        )

    def test_prometheus_serializer_populates_default_config(self):
        serializer = AlertSourceModelSerializer(
            data={
                "name": "Prometheus Prod",
                "source_id": "prometheus-prod",
                "source_type": AlertsSourceTypes.PROMETHEUS,
                "config": {},
            }
        )

        self.assertTrue(serializer.is_valid(), serializer.errors)
        config = serializer.validated_data["config"]
        self.assertTrue(config["accept_default_payload"])
        self.assertTrue(config["accept_custom_payload"])
        self.assertTrue(config["send_resolved_required"])
        self.assertTrue(config["url"].endswith("/api/v1/alerts/api/source/{source_id}/webhook/"))
        self.assertNotIn("external_id_labels", config)
        self.assertNotIn("severity_mapping", config)
        self.assertIn("event_fields_mapping", config)

    def test_prometheus_webhook_accepts_events_for_matching_source_type(self):
        source = AlertSource.objects.create(
            name="Prometheus Prod",
            source_id="prometheus-prod",
            source_type=AlertsSourceTypes.PROMETHEUS,
            secret="prom-secret",
            config={
                "event_fields_mapping": {
                    "title": "title",
                    "description": "description",
                    "level": "level",
                    "item": "item",
                    "start_time": "start_time",
                    "labels": "labels",
                    "external_id": "external_id",
                    "resource_name": "resource_name",
                    "action": "action",
                }
            },
        )
        payload = {
            "events": [
                {
                    "title": "HighCPUUsage",
                    "description": "cpu > 90%",
                    "level": "3",
                    "item": "cpu_usage",
                    "start_time": str(int(timezone.now().timestamp())),
                    "labels": {"alertname": "HighCPUUsage", "instance": "node-1"},
                    "external_id": "prom-node-1-highcpu",
                    "resource_name": "node-1",
                    "action": "created",
                }
            ]
        }

        response = self.client.post(
            f"/api/v1/alerts/api/source/{source.source_id}/webhook/",
            data=json.dumps(payload),
            content_type="application/json",
            HTTP_SECRET="prom-secret",
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["status"], "success")
        self.assertEqual(Event.objects.count(), 1)
        self.assertEqual(Event.objects.first().source.source_id, source.source_id)

    def test_zabbix_webhook_normalizes_single_event_payload(self):
        source = AlertSource.objects.create(
            name="Zabbix Prod",
            source_id="zabbix-prod",
            source_type=AlertsSourceTypes.ZABBIX,
            secret="zbx-secret",
            config={
                "event_fields_mapping": {
                    "title": "title",
                    "description": "description",
                    "level": "level",
                    "item": "item",
                    "start_time": "start_time",
                    "labels": "labels",
                    "rule_id": "rule_id",
                    "external_id": "external_id",
                    "resource_id": "resource_id",
                    "resource_name": "resource_name",
                    "resource_type": "resource_type",
                    "action": "action",
                    "service": "service",
                    "tags": "tags",
                    "location": "location",
                }
            },
        )
        payload = {
            "event": {
                "title": "Zabbix CPU High",
                "description": "cpu usage > 90%",
                "level": "3",
                "item": "system.cpu.util",
                "start_time": str(int(timezone.now().timestamp())),
                "labels": {"problem_id": "10001", "event_id": "20001"},
                "rule_id": "30001",
                "resource_id": "40001",
                "resource_name": "host-1",
                "action": "created",
            }
        }

        response = self.client.post(
            f"/api/v1/alerts/api/source/{source.source_id}/webhook/",
            data=json.dumps(payload),
            content_type="application/json",
            HTTP_SECRET="zbx-secret",
        )

        self.assertEqual(response.status_code, 200)
        event = Event.objects.get(source=source)
        self.assertEqual(event.external_id, "10001")
        self.assertEqual(event.resource_name, "host-1")
        self.assertEqual(event.action, EventAction.CREATED)

    def test_zabbix_webhook_builds_event_from_official_template_fields(self):
        source = AlertSource.objects.create(
            name="Zabbix Prod",
            source_id="zabbix-prod",
            source_type=AlertsSourceTypes.ZABBIX,
            secret="zbx-secret",
            config={
                "event_fields_mapping": {
                    "title": "title",
                    "description": "description",
                    "level": "level",
                    "item": "item",
                    "start_time": "start_time",
                    "labels": "labels",
                    "rule_id": "rule_id",
                    "external_id": "external_id",
                    "resource_id": "resource_id",
                    "resource_name": "resource_name",
                    "resource_type": "resource_type",
                    "action": "action",
                    "service": "service",
                    "tags": "tags",
                    "location": "location",
                }
            },
        )

        response = self.client.post(
            f"/api/v1/alerts/api/source/{source.source_id}/webhook/",
            data=json.dumps(
                {
                    "Subject": "Zabbix CPU High",
                    "Message": "cpu usage > 90%",
                    "Severity": "3",
                    "TriggerName": "system.cpu.util",
                    "ProblemId": "10002",
                    "EventId": "20002",
                    "TriggerId": "30002",
                    "HostId": "40002",
                    "HostName": "host-2",
                    "EventValue": "0",
                }
            ),
            content_type="application/json",
            HTTP_SECRET="zbx-secret",
        )

        self.assertEqual(response.status_code, 200)
        event = Event.objects.get(source=source)
        self.assertEqual(event.external_id, "10002")
        self.assertEqual(event.action, EventAction.RECOVERY)
        self.assertEqual(event.resource_name, "host-2")

    def test_prometheus_webhook_normalizes_default_alertmanager_payload(self):
        source = AlertSource.objects.create(
            name="Prometheus Prod",
            source_id="prometheus-prod",
            source_type=AlertsSourceTypes.PROMETHEUS,
            secret="prom-secret",
            config={
                "event_fields_mapping": {
                    "title": "title",
                    "description": "description",
                    "level": "level",
                    "item": "item",
                    "start_time": "start_time",
                    "end_time": "end_time",
                    "labels": "labels",
                    "rule_id": "rule_id",
                    "external_id": "external_id",
                    "push_source_id": "push_source_id",
                    "resource_id": "resource_id",
                    "resource_name": "resource_name",
                    "resource_type": "resource_type",
                    "action": "action",
                    "service": "service",
                    "tags": "tags",
                    "location": "location",
                },
            },
        )
        payload = {
            "receiver": "bk-lite-prometheus",
            "status": "firing",
            "commonLabels": {"alertname": "HighCPUUsage", "severity": "critical"},
            "commonAnnotations": {"summary": "CPU too high"},
            "alerts": [
                {
                    "status": "firing",
                    "labels": {"instance": "node-1", "job": "node-exporter"},
                    "annotations": {"description": "node-1 cpu usage > 90%"},
                    "startsAt": "2026-04-22T08:00:00Z",
                    "endsAt": "2026-04-22T09:00:00Z",
                }
            ],
        }

        response = self.client.post(
            f"/api/v1/alerts/api/source/{source.source_id}/webhook/",
            data=json.dumps(payload),
            content_type="application/json",
            HTTP_SECRET="prom-secret",
        )

        self.assertEqual(response.status_code, 200)
        event = Event.objects.get(source=source)
        self.assertEqual(event.action, EventAction.CREATED)
        self.assertEqual(event.item, "HighCPUUsage")
        self.assertEqual(event.resource_name, "node-1")
        self.assertEqual(event.service, "node-exporter")
        self.assertEqual(event.raw_data["push_source_id"], "bk-lite-prometheus")
        self.assertTrue(event.external_id)

    def test_prometheus_webhook_uses_same_external_id_for_firing_and_resolved(self):
        source = AlertSource.objects.create(
            name="Prometheus Prod",
            source_id="prometheus-prod",
            source_type=AlertsSourceTypes.PROMETHEUS,
            secret="prom-secret",
            config={
                "event_fields_mapping": {
                    "title": "title",
                    "description": "description",
                    "level": "level",
                    "item": "item",
                    "start_time": "start_time",
                    "end_time": "end_time",
                    "labels": "labels",
                    "rule_id": "rule_id",
                    "external_id": "external_id",
                    "push_source_id": "push_source_id",
                    "resource_id": "resource_id",
                    "resource_name": "resource_name",
                    "resource_type": "resource_type",
                    "action": "action",
                    "service": "service",
                    "tags": "tags",
                    "location": "location",
                },
            },
        )

        def send_payload(status):
            return self.client.post(
                f"/api/v1/alerts/api/source/{source.source_id}/webhook/",
                data=json.dumps(
                    {
                        "receiver": "bk-lite-prometheus",
                        "status": status,
                        "commonLabels": {"alertname": "HighCPUUsage"},
                        "alerts": [
                            {
                                "status": status,
                                "labels": {"instance": "node-1"},
                                "annotations": {"summary": "CPU too high"},
                                "startsAt": "2026-04-22T08:00:00Z",
                                "endsAt": "2026-04-22T09:00:00Z",
                            }
                        ],
                    }
                ),
                content_type="application/json",
                HTTP_SECRET="prom-secret",
            )

        firing_response = send_payload("firing")
        resolved_response = send_payload("resolved")

        self.assertEqual(firing_response.status_code, 200)
        self.assertEqual(resolved_response.status_code, 200)

        events = list(Event.objects.filter(source=source).order_by("received_at"))
        self.assertEqual(len(events), 2)
        self.assertEqual(events[0].external_id, events[1].external_id)
        self.assertEqual(events[0].action, EventAction.CREATED)
        self.assertEqual(events[1].action, EventAction.RECOVERY)

    def test_receiver_rejects_inactive_source(self):
        source = AlertSource.objects.create(
            name="RESTful Disabled",
            source_id="rest-disabled",
            source_type=AlertsSourceTypes.RESTFUL,
            secret="rest-secret",
            is_active=False,
            config={
                "event_fields_mapping": {
                    "title": "title",
                    "level": "level",
                    "start_time": "start_time",
                }
            },
        )

        response = self.client.post(
            f"/api/v1/alerts/api/source/{source.source_id}/webhook/",
            data=json.dumps(
                {
                    "events": [
                        {
                            "title": "disabled-source-event",
                            "level": "3",
                            "start_time": str(int(timezone.now().timestamp())),
                        }
                    ]
                }
            ),
            content_type="application/json",
            HTTP_SECRET="rest-secret",
        )

        self.assertEqual(response.status_code, 400)
        self.assertEqual(Event.objects.count(), 0)

    def test_default_external_id_distinguishes_resource_identity(self):
        source = AlertSource.objects.create(
            name="RESTful Source",
            source_id="rest-source",
            source_type=AlertsSourceTypes.RESTFUL,
            secret="rest-secret",
            config={
                "event_fields_mapping": {
                    "title": "title",
                    "description": "description",
                    "level": "level",
                    "item": "item",
                    "start_time": "start_time",
                    "resource_id": "resource_id",
                    "resource_name": "resource_name",
                    "resource_type": "resource_type",
                    "action": "action",
                }
            },
        )

        payload = {
            "events": [
                {
                    "title": "cpu high",
                    "description": "cpu > 90%",
                    "level": "3",
                    "item": "cpu_usage",
                    "start_time": str(int(timezone.now().timestamp())),
                    "resource_id": 1,
                    "resource_name": "shared-name",
                    "resource_type": "service",
                    "action": "created",
                },
                {
                    "title": "cpu high",
                    "description": "cpu > 90%",
                    "level": "3",
                    "item": "cpu_usage",
                    "start_time": str(int(timezone.now().timestamp())),
                    "resource_id": "2",
                    "resource_name": "shared-name",
                    "resource_type": "service",
                    "action": "created",
                },
            ]
        }

        response = self.client.post(
            f"/api/v1/alerts/api/source/{source.source_id}/webhook/",
            data=json.dumps(payload),
            content_type="application/json",
            HTTP_SECRET="rest-secret",
        )

        self.assertEqual(response.status_code, 200)
        events = list(Event.objects.filter(source=source).order_by("resource_id"))
        self.assertEqual(len(events), 2)
        self.assertNotEqual(events[0].external_id, events[1].external_id)

    def test_nats_ingress_rejects_non_nats_source(self):
        source = AlertSource.objects.create(
            name="Prometheus Source",
            source_id="prometheus-prod",
            source_type=AlertsSourceTypes.PROMETHEUS,
            secret="prom-secret",
            config={},
        )

        result = receive_alert_events(
            source_id=source.source_id,
            pusher="lite-monitor",
            events=[
                {
                    "title": "forged",
                    "description": "forged",
                    "level": "3",
                    "item": "cpu_usage",
                    "start_time": str(int(timezone.now().timestamp())),
                    "action": "created",
                }
            ],
        )

        self.assertFalse(result["result"])
        self.assertEqual(Event.objects.count(), 0)

    def test_nats_ingress_rejects_inactive_or_ineffective_nats_source(self):
        inactive_source = AlertSource.objects.create(
            name="NATS Inactive",
            source_id="nats-inactive",
            source_type=AlertsSourceTypes.NATS,
            secret="nats-secret",
            is_active=False,
            config={},
        )
        ineffective_source = AlertSource.objects.create(
            name="NATS Ineffective",
            source_id="nats-ineffective",
            source_type=AlertsSourceTypes.NATS,
            secret="nats-secret",
            is_effective=False,
            config={},
        )

        inactive_result = receive_alert_events(
            source_id=inactive_source.source_id,
            pusher="lite-monitor",
            events=[
                {
                    "title": "inactive",
                    "description": "inactive",
                    "level": "3",
                    "item": "cpu_usage",
                    "start_time": str(int(timezone.now().timestamp())),
                    "action": "created",
                }
            ],
        )
        ineffective_result = receive_alert_events(
            source_id=ineffective_source.source_id,
            pusher="lite-monitor",
            events=[
                {
                    "title": "ineffective",
                    "description": "ineffective",
                    "level": "3",
                    "item": "cpu_usage",
                    "start_time": str(int(timezone.now().timestamp())),
                    "action": "created",
                }
            ],
        )

        self.assertFalse(inactive_result["result"])
        self.assertFalse(ineffective_result["result"])
        self.assertEqual(Event.objects.count(), 0)


class RecoveryFallbackTestCase(TestCase):
    def setUp(self):
        self.source = AlertSource.objects.create(
            name="RESTful Source",
            source_id="rest-source",
            source_type=AlertsSourceTypes.RESTFUL,
            secret="rest-secret",
            config={},
        )
        Level.objects.create(
            level_id=3,
            level_name="info",
            level_display_name="提醒",
            color="#1677FF",
            icon="",
            description="",
            level_type=LevelType.EVENT,
        )

    def create_event(self, event_id, action, external_id, received_at, **kwargs):
        event = Event.objects.create(
            source=self.source,
            raw_data=kwargs.pop("raw_data", {}),
            title=kwargs.pop("title", "cpu high"),
            description=kwargs.pop("description", "cpu > 90%"),
            level=kwargs.pop("level", "3"),
            service=kwargs.pop("service", None),
            event_type=kwargs.pop("event_type", EventType.ALERT),
            tags=kwargs.pop("tags", {}),
            location=kwargs.pop("location", None),
            external_id=external_id,
            start_time=kwargs.pop("start_time", received_at),
            end_time=kwargs.pop("end_time", None),
            labels=kwargs.pop("labels", {}),
            action=action,
            rule_id=kwargs.pop("rule_id", None),
            event_id=event_id,
            item=kwargs.pop("item", "cpu_usage"),
            resource_id=kwargs.pop("resource_id", None),
            resource_type=kwargs.pop("resource_type", None),
            resource_name=kwargs.pop("resource_name", "shared-name"),
            status=kwargs.pop("status", "received"),
            assignee=kwargs.pop("assignee", []),
            value=kwargs.pop("value", None),
        )
        Event.objects.filter(pk=event.pk).update(received_at=received_at)
        event.refresh_from_db()
        return event

    def create_alert(self, alert_id, status, *events):
        alert = Alert.objects.create(
            alert_id=alert_id,
            status=status,
            level="3",
            title=f"Alert {alert_id}",
            content="content",
            labels={},
            first_event_time=events[0].received_at,
            last_event_time=events[-1].received_at,
            item=events[0].item,
            resource_id=events[0].resource_id,
            resource_name=events[0].resource_name,
            resource_type=events[0].resource_type,
            operator=[],
            source_name=self.source.name,
            fingerprint=f"fp-{alert_id}",
        )
        alert.events.add(*events)
        return alert

    def test_recovery_fallback_recovers_when_candidate_is_unique(self):
        created_at = timezone.now() - timedelta(minutes=1)
        created_event = self.create_event(
            "EVENT-CREATED-1",
            EventAction.CREATED,
            "strict-created-id",
            created_at,
            item="cpu_usage",
            resource_id="service-1",
            resource_type="service",
            resource_name="shared-name",
        )
        alert = self.create_alert("ALERT-1", AlertStatus.UNASSIGNED, created_event)
        recovery_event = self.create_event(
            "EVENT-RECOVERY-1",
            EventAction.RECOVERY,
            "strict-recovery-id",
            timezone.now(),
            item="cpu_usage",
            resource_name="shared-name",
            raw_data={"action": "recovery"},
        )

        RecoveryHandler.handle_recovery_events([recovery_event])
        alert.refresh_from_db()

        self.assertTrue(alert.events.filter(event_id="EVENT-RECOVERY-1").exists())

    def test_recovery_fallback_skips_ambiguous_candidates(self):
        created_at = timezone.now() - timedelta(minutes=2)
        created_event_one = self.create_event(
            "EVENT-CREATED-2A",
            EventAction.CREATED,
            "strict-created-id-a",
            created_at,
            item="cpu_usage",
            resource_id="service-1",
            resource_type="service",
            resource_name="shared-name",
        )
        created_event_two = self.create_event(
            "EVENT-CREATED-2B",
            EventAction.CREATED,
            "strict-created-id-b",
            created_at + timedelta(seconds=1),
            item="cpu_usage",
            resource_id="service-2",
            resource_type="service",
            resource_name="shared-name",
        )
        alert_one = self.create_alert("ALERT-2A", AlertStatus.UNASSIGNED, created_event_one)
        alert_two = self.create_alert("ALERT-2B", AlertStatus.PROCESSING, created_event_two)
        recovery_event = self.create_event(
            "EVENT-RECOVERY-2",
            EventAction.RECOVERY,
            "strict-recovery-id-2",
            timezone.now(),
            item="cpu_usage",
            resource_name="shared-name",
            raw_data={"action": "recovery"},
        )

        RecoveryHandler.handle_recovery_events([recovery_event])

        self.assertFalse(alert_one.events.filter(event_id="EVENT-RECOVERY-2").exists())
        self.assertFalse(alert_two.events.filter(event_id="EVENT-RECOVERY-2").exists())

    def test_integration_guide_returns_prometheus_template(self):
        source = AlertSource.objects.create(
            name="Prometheus Prod",
            source_id="prometheus-prod",
            source_type=AlertsSourceTypes.PROMETHEUS,
            secret="prom-secret",
            config={},
        )

        response = self.client.get(f"/api/v1/alerts/api/alert_source/{source.id}/integration-guide/")

        self.assertEqual(response.status_code, 200)
        payload = response.json()["data"]
        self.assertEqual(payload["source_type"], AlertsSourceTypes.PROMETHEUS)
        self.assertIn(f"/api/v1/alerts/api/source/{source.source_id}/webhook/", payload["webhook_url"])
        self.assertIn("alertmanager_default_config", payload)

    def test_integration_guide_returns_zabbix_template(self):
        source = AlertSource.objects.create(
            name="Zabbix Prod",
            source_id="zabbix-prod",
            source_type=AlertsSourceTypes.ZABBIX,
            secret="zbx-secret",
            config={},
        )

        response = self.client.get(f"/api/v1/alerts/api/alert_source/{source.id}/integration-guide/")

        self.assertEqual(response.status_code, 200)
        payload = response.json()["data"]
        self.assertEqual(payload["source_type"], AlertsSourceTypes.ZABBIX)
        self.assertIn(f"/api/v1/alerts/api/source/{source.source_id}/webhook/", payload["webhook_url"])
        self.assertIn("script_template", payload)
