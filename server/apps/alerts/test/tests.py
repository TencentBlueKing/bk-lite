from datetime import datetime, timedelta
from unittest.mock import patch

from django.test import TestCase
from django.utils import timezone

from apps.alerts.aggregation.builder.synthetic_alert_builder import (
    SyntheticAlertBuilder,
)
from apps.alerts.aggregation.processor.aggregation_processor import AggregationProcessor
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
from apps.alerts.serializers.strategy import AlarmStrategySerializer


class AlarmStrategySerializerTestCase(TestCase):
    def test_missing_detection_serializer_strips_runtime_fields(self):
        serializer = AlarmStrategySerializer(
            data={
                "name": "heartbeat-rule",
                "strategy_type": AlarmStrategyType.MISSING_DETECTION,
                "team": [1],
                "dispatch_team": [1],
                "match_rules": [
                    [{"key": "service", "operator": "eq", "value": "backup"}]
                ],
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
                "match_rules": [
                    [{"key": "service", "operator": "eq", "value": "backup"}]
                ],
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
                "match_rules": [
                    [{"key": "service", "operator": "eq", "value": "backup"}]
                ],
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
            strategy_type=overrides.pop(
                "strategy_type", AlarmStrategyType.MISSING_DETECTION
            ),
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

        with patch.object(
            self.processor, "_process_missing_detection_strategy"
        ) as missing_mock, \
            patch.object(self.processor, "get_events_for_strategy") as events_mock:
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
        AlarmStrategy.objects.filter(pk=strategy.pk).update(
            created_at=now - timedelta(minutes=10)
        )
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

        self.assertEqual(
            strategy.params["heartbeat_status"], HeartbeatStatus.MONITORING
        )
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
        AlarmStrategy.objects.filter(pk=strategy.pk).update(
            created_at=now - timedelta(minutes=7)
        )
        strategy.refresh_from_db()

        self.processor._process_missing_detection_strategy(strategy, now)
        self.processor._process_missing_detection_strategy(
            strategy, now + timedelta(minutes=1)
        )
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
        AlarmStrategy.objects.filter(pk=strategy.pk).update(
            created_at=timezone.make_aware(datetime(2026, 3, 20, 0, 0, 0))
        )
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
        AlarmStrategy.objects.filter(pk=strategy.pk).update(
            created_at=now - timedelta(minutes=1)
        )
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
        AlarmStrategy.objects.filter(pk=strategy.pk).update(
            created_at=now - timedelta(minutes=8)
        )
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
        alert = SyntheticAlertBuilder.create_alert(
            strategy, strategy.params, now - timedelta(minutes=1)
        )
        self.create_event(now, event_id="EVENT-RECOVERY")
        AlarmStrategy.objects.filter(pk=strategy.pk).update(
            last_execute_time=now - timedelta(minutes=2)
        )
        strategy.refresh_from_db()

        self.processor._process_missing_detection_strategy(
            strategy, now + timedelta(minutes=1)
        )
        strategy.refresh_from_db()
        alert.refresh_from_db()

        self.assertEqual(alert.status, AlertStatus.AUTO_RECOVERY)
        self.assertEqual(
            strategy.params["heartbeat_status"], HeartbeatStatus.MONITORING
        )
        self.assertEqual(
            strategy.params["last_heartbeat_time"],
            Event.objects.get(event_id="EVENT-RECOVERY").received_at.isoformat(),
        )
