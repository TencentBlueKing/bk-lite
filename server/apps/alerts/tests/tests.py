import json
from io import StringIO
from datetime import datetime, timedelta
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.contrib.auth.hashers import make_password
from django.core.management import call_command
from django.db import DEFAULT_DB_ALIAS, connections
from django.test import Client
from django.test import TestCase
from django.utils import timezone
from django.utils import translation
from rest_framework.test import APIRequestFactory, force_authenticate

from apps.alerts.aggregation.builder.synthetic_alert_builder import (
    SyntheticAlertBuilder,
)
from apps.alerts.aggregation.processor.aggregation_processor import AggregationProcessor
from apps.alerts.aggregation.window.factory import WindowFactory
from apps.alerts.aggregation.strategy.matcher import StrategyMatcher
from apps.alerts.aggregation.recovery.recovery_handler import RecoveryHandler
from apps.alerts.common.assignment import AlertAssignmentOperator
from apps.alerts.common.source_adapter.base import AlertSourceAdapterFactory
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
from apps.alerts.constants.constants import (
    AlertAssignmentMatchType,
    IncidentStatus,
    LogAction,
    LogTargetType,
    SessionStatus,
)
from apps.alerts.utils.util import str_to_md5
from apps.alerts.models import Alert, AlertSource, AlarmStrategy, Event, Level, OperatorLog
from apps.alerts.models.alert_operator import AlertAssignment
from apps.alerts.models.models import Incident
from apps.alerts.serializers.event import EventModelSerializer
from apps.alerts.serializers.incident import IncidentModelSerializer
from apps.alerts.serializers.alert_source import AlertSourceModelSerializer
from apps.alerts.serializers.strategy import AlarmStrategySerializer
from apps.alerts.utils.util import MAX_AGGREGATION_WINDOW_SIZE_MINUTES
from apps.alerts.utils.rule_matcher import RuleMatcher
from apps.alerts.views.alert import AlertModelViewSet
from apps.alerts.views.alert_source import AlertSourceModelViewSet
from apps.alerts.views.event import EventModelViewSet
from apps.alerts.views.incident import IncidentModelViewSet
from apps.alerts.views.operator_log import SystemLogModelViewSet
from apps.alerts.views.strategy import AlarmStrategyModelViewSet
from apps.system_mgmt.models.user import Group, User


def build_permission_test_user(username, group_list, permissions_by_app=None):
    user = User.objects.create(
        username=username,
        display_name=username,
        email=f"{username}@example.com",
        password=make_password("password123"),
        domain="domain.com",
        group_list=group_list,
    )
    user.permission = permissions_by_app or {}
    user.is_superuser = False
    user.is_authenticated = True
    return user


class AlarmStrategySerializerTestCase(TestCase):
    def test_smart_denoise_serializer_rejects_non_positive_window_size(self):
        serializer = AlarmStrategySerializer(
            data={
                "name": "smart-rule",
                "strategy_type": AlarmStrategyType.SMART_DENOISE,
                "team": [1],
                "dispatch_team": [1],
                "match_rules": [[{"key": "service", "operator": "eq", "value": "backup"}]],
                "params": {
                    "group_by": ["service"],
                    "window_size": 0,
                    "time_out": False,
                },
                "auto_close": False,
                "close_minutes": 120,
            }
        )

        self.assertFalse(serializer.is_valid())
        self.assertEqual(
            serializer.errors["params"]["window_size"],
            "窗口大小必须为大于 0 的整数分钟。",
        )

    def test_smart_denoise_serializer_rejects_oversized_window_size(self):
        serializer = AlarmStrategySerializer(
            data={
                "name": "smart-rule",
                "strategy_type": AlarmStrategyType.SMART_DENOISE,
                "team": [1],
                "dispatch_team": [1],
                "match_rules": [[{"key": "service", "operator": "eq", "value": "backup"}]],
                "params": {
                    "group_by": ["service"],
                    "window_size": MAX_AGGREGATION_WINDOW_SIZE_MINUTES + 1,
                    "time_out": False,
                },
                "auto_close": False,
                "close_minutes": 120,
            }
        )

        self.assertFalse(serializer.is_valid())
        self.assertEqual(
            serializer.errors["params"]["window_size"],
            f"窗口大小不能超过 {MAX_AGGREGATION_WINDOW_SIZE_MINUTES} 分钟。",
        )

    def test_smart_denoise_serializer_accepts_valid_window_size(self):
        serializer = AlarmStrategySerializer(
            data={
                "name": "smart-rule",
                "strategy_type": AlarmStrategyType.SMART_DENOISE,
                "team": [1],
                "dispatch_team": [1],
                "match_rules": [[{"key": "service", "operator": "eq", "value": "backup"}]],
                "params": {
                    "group_by": ["service"],
                    "window_size": 5,
                    "time_out": False,
                },
                "auto_close": False,
                "close_minutes": 120,
            }
        )

        self.assertTrue(serializer.is_valid(), serializer.errors)
        self.assertEqual(serializer.validated_data["params"]["window_size"], 5)

    def test_smart_denoise_serializer_partial_update_preserves_existing_params(self):
        strategy = AlarmStrategy.objects.create(
            name="smart-rule-existing",
            strategy_type=AlarmStrategyType.SMART_DENOISE,
            team=[1],
            dispatch_team=[1],
            match_rules=[[{"key": "service", "operator": "eq", "value": "backup"}]],
            params={"group_by": ["service"], "window_size": 30, "time_out": True, "time_minutes": 15},
            auto_close=False,
            close_minutes=120,
        )

        serializer = AlarmStrategySerializer(
            strategy,
            data={"description": "patched-description"},
            partial=True,
        )

        self.assertTrue(serializer.is_valid(), serializer.errors)
        self.assertEqual(
            serializer.validated_data["params"],
            strategy.params,
        )

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
            serializer.errors["params"]["check_mode"],
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
            serializer.errors["params"]["interval_value"],
            "缺失检查不再支持固定间隔数值。",
        )
        self.assertEqual(
            serializer.errors["params"]["interval_unit"],
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
            team=overrides.pop("team", [1]),
            dispatch_team=overrides.pop("dispatch_team", [1]),
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
            source=overrides.pop("source", self.source),
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
            team=overrides.pop("team", [1]),
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
        ) as missing_mock, patch.object(
            self.processor, "get_events_for_strategy"
        ) as events_mock:
            events_mock.return_value.exists.return_value = False
            self.processor._process_strategy(smart_strategy, now)
            self.processor._process_strategy(missing_strategy, now)

        events_mock.assert_called_once_with(smart_strategy, now)
        missing_mock.assert_called_once_with(missing_strategy, now)

    def test_get_events_for_strategy_clamps_oversized_window_size(self):
        now = timezone.now()
        strategy = self.create_strategy(
            name="smart-window-clamp",
            strategy_type=AlarmStrategyType.SMART_DENOISE,
            params={"group_by": ["service"], "window_size": MAX_AGGREGATION_WINDOW_SIZE_MINUTES + 60, "time_out": False},
        )
        old_event = self.create_event(
            now - timedelta(minutes=MAX_AGGREGATION_WINDOW_SIZE_MINUTES + 30),
            event_id="EVENT-OLD-WINDOW",
        )
        recent_event = self.create_event(
            now - timedelta(minutes=5),
            event_id="EVENT-RECENT-WINDOW",
        )

        events = self.processor.get_events_for_strategy(strategy, now)

        self.assertQuerySetEqual(
            events.order_by("event_id").values_list("event_id", flat=True),
            [recent_event.event_id],
            transform=lambda value: value,
        )
        self.assertFalse(events.filter(pk=old_event.pk).exists())

    def test_get_events_for_strategy_scopes_events_by_strategy_team(self):
        now = timezone.now()
        strategy = self.create_strategy(
            name="smart-team-scope",
            strategy_type=AlarmStrategyType.SMART_DENOISE,
            team=[1],
            dispatch_team=[1],
            params={"group_by": ["service"], "window_size": 5, "time_out": False},
        )
        scoped_event = self.create_event(
            now - timedelta(minutes=1),
            event_id="EVENT-TEAM-SCOPED",
            team=[1],
            external_id="team-scoped-1",
        )
        self.create_event(
            now - timedelta(minutes=1),
            event_id="EVENT-TEAM-OUTSIDE",
            team=[2],
            external_id="team-outside-2",
        )

        events = self.processor.get_events_for_strategy(strategy, now)

        self.assertQuerySetEqual(
            events.order_by("event_id").values_list("event_id", flat=True),
            [scoped_event.event_id],
            transform=lambda value: value,
        )

    def test_query_candidate_events_scopes_events_by_strategy_team(self):
        strategy = self.create_strategy(
            name="missing-team-scope",
            strategy_type=AlarmStrategyType.MISSING_DETECTION,
            team=[1],
            dispatch_team=[1],
        )
        now = timezone.now()
        scoped_event = self.create_event(
            now,
            event_id="EVENT-MISSING-SCOPED",
            team=[1],
            action=EventAction.CREATED,
            external_id="missing-scoped-1",
        )
        self.create_event(
            now,
            event_id="EVENT-MISSING-OUTSIDE",
            team=[2],
            action=EventAction.CREATED,
            external_id="missing-outside-2",
        )

        events = self.processor._query_candidate_events(strategy, now)

        self.assertQuerySetEqual(
            events.order_by("event_id").values_list("event_id", flat=True),
            [scoped_event.event_id],
            transform=lambda value: value,
        )

    def test_window_factory_clamps_oversized_window_size(self):
        strategy = self.create_strategy(
            name="smart-window-config",
            strategy_type=AlarmStrategyType.SMART_DENOISE,
            params={"group_by": ["service"], "window_size": MAX_AGGREGATION_WINDOW_SIZE_MINUTES + 60, "time_out": False},
        )

        window_config = WindowFactory.create_from_strategy(strategy)

        self.assertEqual(
            window_config.window_size_minutes,
            MAX_AGGREGATION_WINDOW_SIZE_MINUTES,
        )
        self.assertEqual(window_config.session_timeout_minutes, 0)

    def test_sliding_window_alert_is_not_marked_observing(self):
        now = timezone.now()
        strategy = self.create_strategy(
            name="smart-sliding-direct-alert",
            strategy_type=AlarmStrategyType.SMART_DENOISE,
            params={"group_by": ["service"], "window_size": 5, "time_out": False},
        )
        event = self.create_event(
            now - timedelta(minutes=1),
            event_id="EVENT-SLIDING-DIRECT-1",
            external_id="sliding-direct-1",
            service="backup",
        )

        with patch.object(self.processor, "_schedule_auto_assignment"):
            success = self.processor._aggregate_for_dimensions(
                strategy,
                Event.objects.filter(pk=event.pk),
                ["service"],
                now,
            )

        self.assertTrue(success)
        alert = Alert.objects.get()
        self.assertFalse(alert.is_session_alert)
        self.assertIsNone(alert.session_status)
        self.assertIsNone(alert.session_end_time)

    def test_normalize_fingerprint_preserves_full_multi_dimension_combination(self):
        alert_levels = [{"level_id": 1, "level_name": "warning", "level_display_name": "预警"}]
        beijing_result = {
            "fingerprint": "42|service=api|location=beijing",
            "alert_level": 1,
            "event_count": 1,
            "first_event_description": "api beijing error",
            "alert_description": "api-beijing",
        }
        shanghai_result = {
            "fingerprint": "42|service=api|location=shanghai",
            "alert_level": 1,
            "event_count": 1,
            "first_event_description": "api shanghai error",
            "alert_description": "api-shanghai",
        }

        AggregationProcessor._normalize_fingerprint(beijing_result, alert_levels)
        AggregationProcessor._normalize_fingerprint(shanghai_result, alert_levels)

        self.assertNotEqual(beijing_result["fingerprint"], shanghai_result["fingerprint"])

    def test_normalize_fingerprint_uses_macro_filtered_title(self):
        alert_levels = [{"level_id": 1, "level_name": "warning", "level_display_name": "预警"}]
        result = {
            "fingerprint": "42|resource_name=172.18.0.19|item=snmp_trap:unknown_trap",
            "alert_level": 1,
            "event_count": 2,
            "first_event_description": "",
            "alert_description": "172.18.0.19",
        }

        AggregationProcessor._normalize_fingerprint(result, alert_levels)

        self.assertEqual(
            result["alert_title"],
            "resource_name=172.18.0.19|item=snmp_trap:unknown_trap 检测到异常",
        )
        self.assertEqual(result["alert_description"], "影响范围：172.18.0.19")
        self.assertEqual(
            result["fingerprint"],
            str_to_md5("resource_name=172.18.0.19|item=snmp_trap:unknown_trap"),
        )

    def test_multi_dimension_group_by_creates_distinct_alerts(self):
        now = timezone.now()
        strategy = self.create_strategy(
            name="smart-multi-dimension-rule",
            strategy_type=AlarmStrategyType.SMART_DENOISE,
            params={"group_by": ["service", "location"], "window_size": 5, "time_out": False},
        )
        first_event = self.create_event(
            now - timedelta(minutes=1),
            event_id="EVENT-MULTI-DIMENSION-1",
            external_id="multi-dimension-1",
            service="api",
            location="beijing",
            resource_name="api-beijing",
        )
        second_event = self.create_event(
            now - timedelta(minutes=1),
            event_id="EVENT-MULTI-DIMENSION-2",
            external_id="multi-dimension-2",
            service="api",
            location="shanghai",
            resource_name="api-shanghai",
        )

        with patch.object(self.processor, "_schedule_auto_assignment"):
            success = self.processor._aggregate_for_dimensions(
                strategy,
                Event.objects.filter(pk__in=[first_event.pk, second_event.pk]),
                ["service", "location"],
                now,
            )

        self.assertTrue(success)
        self.assertEqual(Alert.objects.count(), 2)
        self.assertEqual(
            Alert.objects.values_list("fingerprint", flat=True).distinct().count(),
            2,
        )

    def test_smart_denoise_alert_inherits_unique_standard_fields(self):
        now = timezone.now()
        strategy = self.create_strategy(
            name="smart-unique-standard-fields",
            strategy_type=AlarmStrategyType.SMART_DENOISE,
            params={"group_by": ["service"], "window_size": 5, "time_out": False},
        )
        first_event = self.create_event(
            now - timedelta(minutes=1),
            event_id="EVENT-STANDARD-FIELDS-1",
            external_id="standard-fields-1",
            service="backup",
            item="cpu_usage",
            resource_id="node-1",
            resource_name="node-1",
            resource_type="host",
            labels={"env": "prod"},
        )
        second_event = self.create_event(
            now - timedelta(seconds=30),
            event_id="EVENT-STANDARD-FIELDS-2",
            external_id="standard-fields-2",
            service="backup",
            item="cpu_usage",
            resource_id="node-1",
            resource_name="node-1",
            resource_type="host",
            labels={"env": "prod"},
        )

        with patch.object(self.processor, "_schedule_auto_assignment"):
            success = self.processor._aggregate_for_dimensions(
                strategy,
                Event.objects.filter(pk__in=[first_event.pk, second_event.pk]),
                ["service"],
                now,
            )

        self.assertTrue(success)
        alert = Alert.objects.get()
        self.assertEqual(alert.source_name, self.source.name)
        self.assertEqual(alert.resource_id, "node-1")
        self.assertEqual(alert.resource_name, "node-1")
        self.assertEqual(alert.resource_type, "host")
        self.assertEqual(alert.item, "cpu_usage")
        self.assertEqual(alert.labels, {"env": "prod"})

    def test_smart_denoise_alert_clears_non_unique_standard_fields_on_update(self):
        now = timezone.now()
        strategy = self.create_strategy(
            name="smart-clear-standard-fields",
            strategy_type=AlarmStrategyType.SMART_DENOISE,
            params={"group_by": ["service"], "window_size": 5, "time_out": False},
        )
        first_event = self.create_event(
            now - timedelta(minutes=1),
            event_id="EVENT-CLEAR-FIELDS-1",
            external_id="clear-fields-1",
            service="backup",
            item="cpu_usage",
            resource_id="node-1",
            resource_name="node-1",
            resource_type="host",
            labels={"env": "prod"},
        )

        with patch.object(self.processor, "_schedule_auto_assignment"):
            self.processor._aggregate_for_dimensions(
                strategy,
                Event.objects.filter(pk=first_event.pk),
                ["service"],
                now,
            )

        second_source = AlertSource.objects.create(
            name="other-source",
            source_id="source-2",
            source_type=AlertsSourceTypes.WEBHOOK,
        )
        second_event = self.create_event(
            now - timedelta(seconds=20),
            source=second_source,
            event_id="EVENT-CLEAR-FIELDS-2",
            external_id="clear-fields-2",
            service="backup",
            item="memory_usage",
            resource_id="node-2",
            resource_name="node-2",
            resource_type="service",
            labels={"env": "staging"},
        )

        with patch.object(self.processor, "_schedule_auto_assignment"):
            self.processor._aggregate_for_dimensions(
                strategy,
                Event.objects.filter(pk__in=[first_event.pk, second_event.pk]),
                ["service"],
                now,
            )

        alert = Alert.objects.get()
        self.assertIsNone(alert.source_name)
        self.assertIsNone(alert.resource_id)
        self.assertIsNone(alert.resource_name)
        self.assertIsNone(alert.resource_type)
        self.assertIsNone(alert.item)
        self.assertEqual(alert.labels, {})

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
        AlarmStrategy.objects.filter(pk=strategy.pk).update(created_at=now - timedelta(minutes=10))
        strategy.refresh_from_db()
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

    def test_auto_recovery_marks_alert_closed_and_returns_monitoring_on_created_event(self):
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

    def test_auto_recovery_ignores_recovery_event_for_missing_detection(self):
        now = timezone.make_aware(datetime(2026, 3, 20, 10, 10, 0))
        previous_heartbeat_time = (now - timedelta(minutes=10)).isoformat()
        strategy = self.create_strategy(
            params={
                "heartbeat_status": HeartbeatStatus.ALERTING,
                "last_heartbeat_time": previous_heartbeat_time,
                "last_heartbeat_context": {"service": "backup"},
            }
        )
        alert = SyntheticAlertBuilder.create_alert(strategy, strategy.params, now - timedelta(minutes=1))
        self.create_event(now, event_id="EVENT-ONLY-RECOVERY", action=EventAction.RECOVERY)
        AlarmStrategy.objects.filter(pk=strategy.pk).update(last_execute_time=now - timedelta(minutes=2))
        strategy.refresh_from_db()

        self.processor._process_missing_detection_strategy(strategy, now + timedelta(minutes=1))
        strategy.refresh_from_db()
        alert.refresh_from_db()

        self.assertNotEqual(alert.status, AlertStatus.AUTO_RECOVERY)
        self.assertEqual(strategy.params["heartbeat_status"], HeartbeatStatus.ALERTING)
        self.assertEqual(strategy.params["last_heartbeat_time"], previous_heartbeat_time)


class StrategyMatcherTestCase(TestCase):
    def setUp(self):
        self.source = AlertSource.objects.create(
            name="matcher-source",
            source_id="matcher-source",
            source_type=AlertsSourceTypes.WEBHOOK,
        )
        self.event = Event.objects.create(
            source=self.source,
            raw_data={},
            title="cpu high",
            description="cpu high",
            level="1",
            start_time=timezone.now(),
            event_id="EVENT-strategy-matcher",
        )

    def test_invalid_in_rule_does_not_match_all_events(self):
        matched = StrategyMatcher.match_events_to_strategy(
            Event.objects.all(),
            [[{"key": "title", "operator": "in", "value": "cpu high"}]],
        )

        self.assertFalse(matched.exists())

    def test_invalid_regex_rule_does_not_match_all_events(self):
        matched = StrategyMatcher.match_events_to_strategy(
            Event.objects.all(),
            [[{"key": "title", "operator": "regex", "value": "["}]],
        )

        self.assertFalse(matched.exists())

    def test_partially_invalid_and_group_does_not_broaden_match_scope(self):
        matched = StrategyMatcher.match_events_to_strategy(
            Event.objects.all(),
            [
                [
                    {"key": "title", "operator": "eq", "value": "cpu high"},
                    {"key": "title", "operator": "regex", "value": "["},
                ]
            ],
        )

        self.assertFalse(matched.exists())

    def test_unknown_operator_does_not_fall_back_to_exact_match(self):
        matched = StrategyMatcher.match_events_to_strategy(
            Event.objects.all(),
            [[{"key": "title", "operator": "unknown", "value": "cpu high"}]],
        )

        self.assertFalse(matched.exists())

    def test_shared_rule_matcher_invalid_and_group_returns_empty_result(self):
        matcher = RuleMatcher({"title": "title"})

        matched_ids = matcher.filter_queryset(
            Event.objects.all(),
            [
                [
                    {"key": "title", "operator": "eq", "value": "cpu high"},
                    {"key": "title", "operator": "re", "value": "["},
                ]
            ],
        )

        self.assertEqual(matched_ids, [])

    def test_shared_rule_matcher_unknown_operator_returns_empty_result(self):
        matcher = RuleMatcher({"title": "title"})

        matched_ids = matcher.filter_queryset(
            Event.objects.all(),
            [[{"key": "title", "operator": "unknown", "value": "cpu high"}]],
        )

        self.assertEqual(matched_ids, [])


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
        self.assertTrue(config["url"].endswith("/api/v1/alerts/api/source/prometheus-prod/webhook/"))
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

    def test_receiver_rejects_ineffective_source(self):
        source = AlertSource.objects.create(
            name="RESTful Ineffective",
            source_id="rest-ineffective",
            source_type=AlertsSourceTypes.RESTFUL,
            secret="rest-secret",
            is_effective=False,
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
                            "title": "ineffective-source-event",
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

    def test_nats_ingress_sets_push_source_id_from_pusher(self):
        source = AlertSource.objects.create(
            name="NATS Source",
            source_id="nats",
            source_type=AlertsSourceTypes.NATS,
            secret="nats-secret",
            config={
                "event_fields_mapping": {
                    "title": "title",
                    "description": "description",
                    "level": "level",
                    "item": "item",
                    "start_time": "start_time",
                    "action": "action",
                    "resource_id": "resource_id",
                    "resource_name": "resource_name",
                    "resource_type": "resource_type",
                }
            },
        )

        result = receive_alert_events(
            source_id=source.source_id,
            pusher="lite-monitor",
            events=[
                {
                    "title": "cpu high",
                    "description": "cpu > 90%",
                    "level": "3",
                    "item": "cpu_usage",
                    "start_time": str(int(timezone.now().timestamp())),
                    "action": "created",
                    "resource_id": "gateway-01",
                    "resource_name": "API 网关",
                    "resource_type": "service",
                }
            ],
        )

        self.assertTrue(result["result"])
        event = Event.objects.get(source=source)
        self.assertEqual(event.push_source_id, "lite-monitor")
        self.assertEqual(event.raw_data["push_source_id"], "lite-monitor")

    def test_nats_ingress_preserves_event_push_source_id(self):
        source = AlertSource.objects.create(
            name="NATS Source",
            source_id="nats",
            source_type=AlertsSourceTypes.NATS,
            secret="nats-secret",
            config={
                "event_fields_mapping": {
                    "title": "title",
                    "description": "description",
                    "level": "level",
                    "item": "item",
                    "start_time": "start_time",
                    "action": "action",
                    "resource_id": "resource_id",
                    "resource_name": "resource_name",
                    "resource_type": "resource_type",
                    "push_source_id": "push_source_id",
                }
            },
        )

        result = receive_alert_events(
            source_id=source.source_id,
            pusher="lite-monitor",
            events=[
                {
                    "title": "cpu high",
                    "description": "cpu > 90%",
                    "level": "3",
                    "item": "cpu_usage",
                    "start_time": str(int(timezone.now().timestamp())),
                    "action": "created",
                    "resource_id": "gateway-01",
                    "resource_name": "API 网关",
                    "resource_type": "service",
                    "push_source_id": "custom-upstream",
                }
            ],
        )

        self.assertTrue(result["result"])
        event = Event.objects.get(source=source)
        self.assertEqual(event.push_source_id, "custom-upstream")
        self.assertEqual(event.raw_data["push_source_id"], "custom-upstream")


class TestAlarmStrategySessionDisable(TestCase):
    def setUp(self):
        self.factory = APIRequestFactory()
        self.user = get_user_model().objects.create_user(
            username="strategy-admin",
            password="test-pass-123",
            domain="default.local",
        )
        self.user.is_superuser = True
        self.user.save(update_fields=["is_superuser"])

    def test_update_disabling_session_window_triggers_auto_assignment_for_confirmed_alerts(self):
        strategy = AlarmStrategy.objects.create(
            name="session-strategy",
            strategy_type=AlarmStrategyType.SMART_DENOISE,
            team=[1],
            dispatch_team=[1],
            match_rules=[[{"key": "title", "operator": "eq", "value": "cpu high"}]],
            params={"group_by": ["service"], "window_size": 10, "time_out": True, "time_minutes": 10},
            auto_close=False,
            close_minutes=120,
        )
        alert = Alert.objects.create(
            alert_id="ALERT-SESSION-DISABLE-1",
            status=AlertStatus.UNASSIGNED,
            level="1",
            title="cpu high",
            content="cpu > 90%",
            labels={},
            first_event_time=timezone.now(),
            last_event_time=timezone.now(),
            fingerprint="service:backup",
            group_by_field="service",
            rule_id=str(strategy.id),
            is_session_alert=True,
            session_status=SessionStatus.OBSERVING,
            session_end_time=timezone.now() + timedelta(minutes=10),
            team=[1],
        )

        request = self.factory.put(
            f"/api/v1/alerts/strategy/{strategy.id}/",
            data={
                "name": strategy.name,
                "strategy_type": strategy.strategy_type,
                "description": strategy.description,
                "team": strategy.team,
                "dispatch_team": strategy.dispatch_team,
                "match_rules": strategy.match_rules,
                "params": {"group_by": ["service"], "window_size": 10, "time_out": False, "time_minutes": 0},
                "auto_close": strategy.auto_close,
                "close_minutes": strategy.close_minutes,
                "is_active": strategy.is_active,
            },
            format="json",
        )
        force_authenticate(request, user=self.user)
        view = AlarmStrategyModelViewSet.as_view({"put": "update"})

        with patch("apps.alerts.tasks.async_auto_assignment_for_alerts.delay") as assignment_delay:
            with self.captureOnCommitCallbacks(execute=True):
                response = view(request, pk=str(strategy.id))

        self.assertEqual(response.status_code, 200)
        alert.refresh_from_db()
        self.assertEqual(alert.session_status, SessionStatus.CONFIRMED)
        assignment_delay.assert_called_once_with([alert.alert_id])

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


class AutoAssignmentTaskTestCase(TestCase):
    def test_async_auto_assignment_for_alerts_deduplicates_before_execution(self):
        from apps.alerts.tasks.tasks import async_auto_assignment_for_alerts

        with patch(
            "apps.alerts.common.assignment.execute_auto_assignment_for_alerts"
        ) as execute_assignment:
            execute_assignment.return_value = {
                "total_alerts": 2,
                "assigned_alerts": 1,
                "failed_alerts": 0,
                "assignment_results": [],
            }

            result = async_auto_assignment_for_alerts(["ALERT-1", "ALERT-1", "ALERT-2"])

        self.assertFalse(result.get("chunked", False))
        execute_assignment.assert_called_once_with(["ALERT-1", "ALERT-2"])

    def test_async_auto_assignment_for_alerts_chunks_large_batches(self):
        from apps.alerts.tasks.tasks import (
            AUTO_ASSIGNMENT_CHUNK_SIZE,
            async_auto_assignment_for_alerts,
        )

        alert_ids = [f"ALERT-{i}" for i in range(AUTO_ASSIGNMENT_CHUNK_SIZE + 3)]

        with patch(
            "apps.alerts.tasks.tasks.async_auto_assignment_for_alerts.delay"
        ) as delay_mock, patch(
            "apps.alerts.common.assignment.execute_auto_assignment_for_alerts"
        ) as execute_assignment:
            result = async_auto_assignment_for_alerts(alert_ids)

        self.assertTrue(result["chunked"])
        self.assertEqual(result["chunk_count"], 2)
        self.assertEqual(delay_mock.call_count, 2)
        self.assertEqual(len(delay_mock.call_args_list[0].args[0]), AUTO_ASSIGNMENT_CHUNK_SIZE)
        self.assertEqual(len(delay_mock.call_args_list[1].args[0]), 3)
        execute_assignment.assert_not_called()


class AlertAssignmentOperatorTestCase(TestCase):
    def setUp(self):
        self.source = AlertSource.objects.create(
            name="Assignment Source",
            source_id="assignment-source",
            source_type=AlertsSourceTypes.RESTFUL,
            secret="assignment-secret",
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

    def create_event(self, event_id, title, resource_id):
        return Event.objects.create(
            source=self.source,
            raw_data={},
            title=title,
            description="desc",
            level="3",
            service=None,
            event_type=EventType.ALERT,
            tags={},
            location=None,
            external_id=f"ext-{event_id}",
            start_time=timezone.now(),
            end_time=None,
            labels={},
            action=EventAction.CREATED,
            rule_id=None,
            event_id=event_id,
            item="cpu_usage",
            resource_id=resource_id,
            resource_type="host",
            resource_name=resource_id,
            status="received",
            assignee=[],
            value=None,
        )

    def create_alert(self, alert_id, title, resource_id):
        event = self.create_event(f"EVENT-{alert_id}", title, resource_id)
        alert = Alert.objects.create(
            alert_id=alert_id,
            status=AlertStatus.UNASSIGNED,
            level="3",
            title=title,
            content="content",
            labels={},
            first_event_time=event.received_at,
            last_event_time=event.received_at,
            item=event.item,
            resource_id=event.resource_id,
            resource_name=event.resource_name,
            resource_type=event.resource_type,
            operator=[],
            source_name=self.source.name,
            fingerprint=f"fp-{alert_id}",
        )
        alert.events.add(event)
        return alert

    def test_execute_auto_assignment_excludes_alerts_assigned_by_previous_rule(self):
        first_alert = self.create_alert("ALERT-FIRST", "cpu high", "node-1")
        second_alert = self.create_alert("ALERT-SECOND", "disk high", "node-2")

        first_assignment = AlertAssignment.objects.create(
            name="assignment-first",
            match_type=AlertAssignmentMatchType.ALL,
            match_rules=[],
            personnel=["alice"],
            notify_channels=[],
            notification_scenario=[],
            config={},
            is_active=True,
        )
        second_assignment = AlertAssignment.objects.create(
            name="assignment-second",
            match_type=AlertAssignmentMatchType.ALL,
            match_rules=[],
            personnel=["bob"],
            notify_channels=[],
            notification_scenario=[],
            config={},
            is_active=True,
        )

        operator = AlertAssignmentOperator([first_alert.alert_id, second_alert.alert_id])

        with patch.object(
            AlertAssignmentOperator,
            "_batch_execute_assignment",
            side_effect=[
                [
                    {
                        "alert_id": first_alert.alert_id,
                        "alert_pk": first_alert.id,
                        "success": True,
                        "assignment_id": first_assignment.id,
                        "assigned_to": ["alice"],
                    }
                ],
                [
                    {
                        "alert_id": second_alert.alert_id,
                        "alert_pk": second_alert.id,
                        "success": True,
                        "assignment_id": second_assignment.id,
                        "assigned_to": ["bob"],
                    }
                ],
            ],
        ) as execute_mock, patch.object(
            AlertAssignmentOperator, "_batch_create_log"
        ):
            result = operator.execute_auto_assignment()

        self.assertEqual(result["assigned_alerts"], 2)
        self.assertEqual(execute_mock.call_count, 2)
        self.assertEqual(execute_mock.call_args_list[0].args[0], [first_alert.id, second_alert.id])
        self.assertEqual(execute_mock.call_args_list[1].args[0], [second_alert.id])


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
        self.adapter_class = AlertSourceAdapterFactory.get_adapter(self.source)

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

    def _run_pending_on_commit_callbacks(self):
        connection = connections[DEFAULT_DB_ALIAS]
        while connection.run_on_commit:
            _, callback, robust = connection.run_on_commit.pop(0)
            if robust:
                try:
                    callback()
                except Exception:
                    pass
            else:
                callback()

    def build_unsaved_event(self, action, start_time, external_id=None, **kwargs):
        event = Event(
            title=kwargs.pop("title", "cpu high"),
            description=kwargs.pop("description", "cpu > 90%"),
            level=kwargs.pop("level", "3"),
            start_time=start_time,
            action=action,
            item=kwargs.pop("item", "cpu_usage"),
            resource_id=kwargs.pop("resource_id", "node-1"),
            resource_type=kwargs.pop("resource_type", "host"),
            resource_name=kwargs.pop("resource_name", "node-1"),
            service=kwargs.pop("service", None),
            event_type=kwargs.pop("event_type", EventType.ALERT),
            tags=kwargs.pop("tags", {}),
            location=kwargs.pop("location", None),
            end_time=kwargs.pop("end_time", None),
            labels=kwargs.pop("labels", {}),
            rule_id=kwargs.pop("rule_id", None),
            status=kwargs.pop("status", "received"),
            assignee=kwargs.pop("assignee", []),
            value=kwargs.pop("value", None),
        )
        if external_id is not None:
            event.external_id = external_id
        return event

    def save_ingress_event(self, event, payload=None):
        adapter = self.adapter_class(alert_source=self.source)
        adapter.add_base_fields(event, payload or {"action": event.action})
        return adapter.bulk_save_events([event])

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
        self._run_pending_on_commit_callbacks()
        alert.refresh_from_db()

        self.assertTrue(alert.events.filter(event_id="EVENT-RECOVERY-1").exists())
        self.assertEqual(alert.status, AlertStatus.UNASSIGNED)

    def test_duplicate_created_ingress_event_is_deduplicated_before_persistence(self):
        start_time = timezone.now()

        first_event = self.build_unsaved_event(
            EventAction.CREATED,
            start_time,
            external_id="dup-created-ext",
            resource_id="node-dup-1",
            resource_type="host",
            resource_name="node-dup-1",
        )
        second_event = self.build_unsaved_event(
            EventAction.CREATED,
            start_time,
            external_id="dup-created-ext",
            resource_id="node-dup-1",
            resource_type="host",
            resource_name="node-dup-1",
        )

        self.save_ingress_event(first_event, {"action": "created", "external_id": "dup-created-ext"})
        self.save_ingress_event(second_event, {"action": "created", "external_id": "dup-created-ext"})

        events = Event.objects.filter(
            source=self.source,
            external_id="dup-created-ext",
            action=EventAction.CREATED,
            start_time=start_time,
        )
        self.assertEqual(events.count(), 1)
        self.assertTrue(events.first().ingest_key)

    def test_duplicate_recovery_ingress_event_is_deduplicated_before_persistence(self):
        start_time = timezone.now()

        first_event = self.build_unsaved_event(
            EventAction.RECOVERY,
            start_time,
            external_id="dup-recovery-ext",
            resource_id="node-dup-2",
            resource_type="host",
            resource_name="node-dup-2",
            description="cpu recovered",
        )
        second_event = self.build_unsaved_event(
            EventAction.RECOVERY,
            start_time,
            external_id="dup-recovery-ext",
            resource_id="node-dup-2",
            resource_type="host",
            resource_name="node-dup-2",
            description="cpu recovered",
        )

        self.save_ingress_event(first_event, {"action": "recovery", "external_id": "dup-recovery-ext"})
        self.save_ingress_event(second_event, {"action": "recovery", "external_id": "dup-recovery-ext"})

        events = Event.objects.filter(
            source=self.source,
            external_id="dup-recovery-ext",
            action=EventAction.RECOVERY,
            start_time=start_time,
        )
        self.assertEqual(events.count(), 1)
        self.assertTrue(events.first().ingest_key)

    def test_ingest_key_distinguishes_created_and_recovery_events(self):
        created_at = timezone.now()
        recovery_at = created_at + timedelta(minutes=1)

        created_event = self.build_unsaved_event(
            EventAction.CREATED,
            created_at,
            external_id="shared-ext-id",
            resource_id="node-ingest-1",
            resource_type="host",
            resource_name="node-ingest-1",
        )
        recovery_event = self.build_unsaved_event(
            EventAction.RECOVERY,
            recovery_at,
            external_id="shared-ext-id",
            resource_id="node-ingest-1",
            resource_type="host",
            resource_name="node-ingest-1",
        )

        self.save_ingress_event(created_event, {"action": "created", "external_id": "shared-ext-id"})
        self.save_ingress_event(recovery_event, {"action": "recovery", "external_id": "shared-ext-id"})

        created_record = Event.objects.get(source=self.source, external_id="shared-ext-id", action=EventAction.CREATED)
        recovery_record = Event.objects.get(source=self.source, external_id="shared-ext-id", action=EventAction.RECOVERY)

        self.assertNotEqual(created_record.ingest_key, recovery_record.ingest_key)

    def test_recovery_event_reuses_created_external_id_when_legacy_match_is_unique(self):
        created_at = timezone.now() - timedelta(minutes=1)
        created_event = self.create_event(
            "EVENT-CREATED-COMPAT-1",
            EventAction.CREATED,
            "legacy-created-id",
            created_at,
            item="cpu_usage",
            resource_id="service-1",
            resource_type="service",
            resource_name="shared-name",
        )
        alert = self.create_alert("ALERT-COMPAT-1", AlertStatus.UNASSIGNED, created_event)

        adapter = self.adapter_class(alert_source=self.source)
        recovery_event = Event(
            title="cpu high",
            description="cpu recovered",
            level="3",
            start_time=timezone.now(),
            action=EventAction.RECOVERY,
            item="cpu_usage",
            resource_name="shared-name",
        )

        adapter.add_base_fields(recovery_event, {"action": "recovery"})
        self.assertEqual(recovery_event.external_id, "legacy-created-id")

        recovery_event.save()
        RecoveryHandler.handle_recovery_events([recovery_event])
        self._run_pending_on_commit_callbacks()
        alert.refresh_from_db()

        self.assertTrue(alert.events.filter(event_id=recovery_event.event_id).exists())
        self.assertEqual(alert.status, AlertStatus.AUTO_RECOVERY)

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
        self._run_pending_on_commit_callbacks()

        self.assertFalse(alert_one.events.filter(event_id="EVENT-RECOVERY-2").exists())
        self.assertFalse(alert_two.events.filter(event_id="EVENT-RECOVERY-2").exists())
        alert_one.refresh_from_db()
        alert_two.refresh_from_db()
        self.assertEqual(alert_one.status, AlertStatus.UNASSIGNED)
        self.assertEqual(alert_two.status, AlertStatus.PROCESSING)

    def test_recovery_event_does_not_resolve_external_id_when_legacy_match_is_ambiguous(self):
        created_at = timezone.now() - timedelta(minutes=2)
        created_event_one = self.create_event(
            "EVENT-CREATED-COMPAT-2A",
            EventAction.CREATED,
            "legacy-created-id-a",
            created_at,
            item="cpu_usage",
            resource_id="service-1",
            resource_type="service",
            resource_name="shared-name",
        )
        created_event_two = self.create_event(
            "EVENT-CREATED-COMPAT-2B",
            EventAction.CREATED,
            "legacy-created-id-b",
            created_at + timedelta(seconds=1),
            item="cpu_usage",
            resource_id="service-2",
            resource_type="service",
            resource_name="shared-name",
        )
        self.create_alert("ALERT-COMPAT-2A", AlertStatus.UNASSIGNED, created_event_one)
        self.create_alert("ALERT-COMPAT-2B", AlertStatus.PROCESSING, created_event_two)

        adapter = self.adapter_class(alert_source=self.source)
        recovery_event = Event(
            title="cpu high",
            description="cpu recovered",
            level="3",
            start_time=timezone.now(),
            action=EventAction.RECOVERY,
            item="cpu_usage",
            resource_name="shared-name",
        )

        adapter.add_base_fields(recovery_event, {"action": "recovery"})

        self.assertNotIn(recovery_event.external_id, {"legacy-created-id-a", "legacy-created-id-b"})

    def test_recovery_event_keeps_explicit_external_id(self):
        created_at = timezone.now() - timedelta(minutes=1)
        created_event = self.create_event(
            "EVENT-CREATED-COMPAT-3",
            EventAction.CREATED,
            "explicit-id",
            created_at,
            item="cpu_usage",
            resource_id="service-1",
            resource_type="service",
            resource_name="shared-name",
        )
        alert = self.create_alert("ALERT-COMPAT-3", AlertStatus.UNASSIGNED, created_event)
        recovery_event = self.create_event(
            "EVENT-RECOVERY-COMPAT-3",
            EventAction.RECOVERY,
            "explicit-id",
            timezone.now(),
            item="cpu_usage",
            resource_name="shared-name",
            raw_data={"action": "recovery"},
        )

        RecoveryHandler.handle_recovery_events([recovery_event])
        self._run_pending_on_commit_callbacks()
        alert.refresh_from_db()

        self.assertTrue(alert.events.filter(event_id="EVENT-RECOVERY-COMPAT-3").exists())
        self.assertEqual(alert.status, AlertStatus.AUTO_RECOVERY)

    def test_mapping_fields_to_event_keeps_missing_end_time_empty(self):
        self.source.config = {
            "event_fields_mapping": {
                "title": "title",
                "description": "description",
                "level": "level",
                "start_time": "start_time",
                "end_time": "end_time",
                "action": "action",
            }
        }
        self.source.save(update_fields=["config"])

        adapter = self.adapter_class(alert_source=self.source)
        payload = {
            "title": "cpu high",
            "description": "cpu recovered",
            "level": "3",
            "start_time": str(int(timezone.now().timestamp())),
            "end_time": "",
            "action": "recovery",
        }

        mapped = adapter.mapping_fields_to_event(payload)

        self.assertIn("start_time", mapped)
        self.assertNotIn("end_time", mapped)

    def test_closed_event_immediately_recovers_active_alert(self):
        created_at = timezone.now() - timedelta(minutes=5)
        created_event = self.create_event(
            "EVENT-CREATED-CLOSED-1",
            EventAction.CREATED,
            "ext-closed-1",
            created_at,
            item="cpu_usage",
            resource_id="node-1",
            resource_type="host",
            resource_name="node-1",
        )
        alert = self.create_alert("ALERT-CLOSED-1", AlertStatus.UNASSIGNED, created_event)
        closed_event = self.create_event(
            "EVENT-CLOSED-1",
            EventAction.CLOSED,
            "ext-closed-1",
            timezone.now(),
            item="cpu_usage",
            resource_id="node-1",
            resource_type="host",
            resource_name="node-1",
            description="cpu closed",
        )

        RecoveryHandler.handle_recovery_events([closed_event])
        self._run_pending_on_commit_callbacks()
        alert.refresh_from_db()

        self.assertTrue(alert.events.filter(event_id="EVENT-CLOSED-1").exists())
        self.assertEqual(alert.status, AlertStatus.AUTO_RECOVERY)

    def test_alert_recovers_only_after_all_created_events_are_recovered(self):
        created_at = timezone.now() - timedelta(minutes=5)
        created_event_one = self.create_event(
            "EVENT-CREATED-MULTI-1",
            EventAction.CREATED,
            "ext-multi-1",
            created_at,
            item="cpu_usage",
            resource_id="node-1",
            resource_type="host",
            resource_name="node-1",
        )
        created_event_two = self.create_event(
            "EVENT-CREATED-MULTI-2",
            EventAction.CREATED,
            "ext-multi-2",
            created_at + timedelta(seconds=1),
            item="cpu_usage",
            resource_id="node-1",
            resource_type="host",
            resource_name="node-1",
        )
        alert = self.create_alert("ALERT-MULTI-1", AlertStatus.UNASSIGNED, created_event_one, created_event_two)

        first_recovery = self.create_event(
            "EVENT-RECOVERY-MULTI-1",
            EventAction.RECOVERY,
            "ext-multi-1",
            timezone.now(),
            item="cpu_usage",
            resource_id="node-1",
            resource_type="host",
            resource_name="node-1",
        )

        RecoveryHandler.handle_recovery_events([first_recovery])
        self._run_pending_on_commit_callbacks()
        alert.refresh_from_db()
        self.assertEqual(alert.status, AlertStatus.UNASSIGNED)

        second_recovery = self.create_event(
            "EVENT-RECOVERY-MULTI-2",
            EventAction.RECOVERY,
            "ext-multi-2",
            timezone.now() + timedelta(seconds=1),
            item="cpu_usage",
            resource_id="node-1",
            resource_type="host",
            resource_name="node-1",
        )

        RecoveryHandler.handle_recovery_events([second_recovery])
        self._run_pending_on_commit_callbacks()
        alert.refresh_from_db()
        self.assertEqual(alert.status, AlertStatus.AUTO_RECOVERY)

    def test_duplicate_recovery_event_rechecks_existing_relation_and_recovers_alert(self):
        created_at = timezone.now() - timedelta(minutes=5)
        created_event = self.create_event(
            "EVENT-CREATED-DUP-1",
            EventAction.CREATED,
            "ext-dup-1",
            created_at,
            item="cpu_usage",
            resource_id="node-1",
            resource_type="host",
            resource_name="node-1",
        )
        recovery_event = self.create_event(
            "EVENT-RECOVERY-DUP-1",
            EventAction.RECOVERY,
            "ext-dup-1",
            timezone.now(),
            item="cpu_usage",
            resource_id="node-1",
            resource_type="host",
            resource_name="node-1",
        )
        alert = self.create_alert("ALERT-DUP-1", AlertStatus.UNASSIGNED, created_event, recovery_event)

        RecoveryHandler.handle_recovery_events([recovery_event])
        self._run_pending_on_commit_callbacks()
        alert.refresh_from_db()

        self.assertEqual(alert.status, AlertStatus.AUTO_RECOVERY)

    def test_out_of_order_recovery_event_does_not_recover_active_alert(self):
        created_at = timezone.now()
        created_event = self.create_event(
            "EVENT-CREATED-OUT-OF-ORDER-1",
            EventAction.CREATED,
            "ext-out-of-order-1",
            created_at,
            start_time=created_at,
            item="cpu_usage",
            resource_id="node-1",
            resource_type="host",
            resource_name="node-1",
        )
        alert = self.create_alert("ALERT-OUT-OF-ORDER-1", AlertStatus.UNASSIGNED, created_event)
        recovery_event = self.create_event(
            "EVENT-RECOVERY-OUT-OF-ORDER-1",
            EventAction.RECOVERY,
            "ext-out-of-order-1",
            created_at + timedelta(minutes=10),
            start_time=created_at - timedelta(minutes=10),
            end_time=created_at - timedelta(minutes=5),
            item="cpu_usage",
            resource_id="node-1",
            resource_type="host",
            resource_name="node-1",
        )

        RecoveryHandler.handle_recovery_events([recovery_event])
        self._run_pending_on_commit_callbacks()
        alert.refresh_from_db()

        self.assertTrue(alert.events.filter(event_id="EVENT-RECOVERY-OUT-OF-ORDER-1").exists())
        self.assertEqual(alert.status, AlertStatus.UNASSIGNED)

    def test_integration_guide_returns_prometheus_template(self):
        source = AlertSource.objects.create(
            name="Prometheus Prod",
            source_id="prometheus-prod",
            source_type=AlertsSourceTypes.PROMETHEUS,
            secret="prom-secret",
            config={},
        )
        user = build_permission_test_user("integration-reader-prom", [1], {"alarm": {"Integration-View"}})

        request = APIRequestFactory().get(f"/api/v1/alerts/api/alert_source/{source.id}/integration-guide/")
        force_authenticate(request, user=user)
        response = AlertSourceModelViewSet.as_view({"get": "integration_guide"})(request, pk=source.pk)

        self.assertEqual(response.status_code, 200)
        payload = response.data
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
        user = build_permission_test_user("integration-reader-zbx", [1], {"alarm": {"Integration-View"}})

        request = APIRequestFactory().get(f"/api/v1/alerts/api/alert_source/{source.id}/integration-guide/")
        force_authenticate(request, user=user)
        response = AlertSourceModelViewSet.as_view({"get": "integration_guide"})(request, pk=source.pk)

        self.assertEqual(response.status_code, 200)
        payload = response.data
        self.assertEqual(payload["source_type"], AlertsSourceTypes.ZABBIX)
        self.assertIn(f"/api/v1/alerts/api/source/{source.source_id}/webhook/", payload["webhook_url"])
        self.assertEqual(payload["headers"], {"SECRET": source.secret})
        self.assertIn("setup_steps", payload)
        self.assertEqual(len(payload["setup_steps"]), 2)
        self.assertEqual(payload["setup_steps"][0]["title"], "准备 BK-Lite 告警源")
        self.assertIn("parameter_guidance", payload)
        self.assertTrue(any(item["name"] == "ProblemId" and item["required"] for item in payload["parameter_guidance"]))
        self.assertIn("verification", payload)
        self.assertIn("curl_check", payload["verification"])
        self.assertIn("field_mappings", payload)
        self.assertTrue(any(item["bk_lite_field"] == "external_id" for item in payload["field_mappings"]))
        self.assertIn("troubleshooting", payload)
        self.assertTrue(any(item["symptom"] == "created 有，recovery 没有" for item in payload["troubleshooting"]))
        self.assertIn("key_reminders", payload)
        self.assertGreaterEqual(len(payload["key_reminders"]), 3)
        self.assertIn("script_template", payload)

    def test_integration_guide_returns_zabbix_template_in_english(self):
        source = AlertSource.objects.create(
            name="Zabbix Prod",
            source_id="zabbix-prod-en",
            source_type=AlertsSourceTypes.ZABBIX,
            secret="zbx-secret-en",
            config={},
        )
        user = build_permission_test_user("integration-reader-zbx-en", [1], {"alarm": {"Integration-View"}})

        request = APIRequestFactory().get(
            f"/api/v1/alerts/api/alert_source/{source.id}/integration-guide/",
            HTTP_ACCEPT_LANGUAGE="en-US,en;q=0.9",
        )
        request.LANGUAGE_CODE = "en-us"
        force_authenticate(request, user=user)

        with translation.override("en"):
            response = AlertSourceModelViewSet.as_view({"get": "integration_guide"})(request, pk=source.pk)

        self.assertEqual(response.status_code, 200)
        payload = response.data
        self.assertEqual(payload["source_type"], AlertsSourceTypes.ZABBIX)
        self.assertEqual(payload["setup_steps"][0]["title"], "1. Determine the three BK-Lite values first")
        self.assertEqual(payload["parameter_guidance"][0]["name"], "Interface requirements")
        self.assertEqual(payload["verification"]["curl_check"]["title"], "CURL connectivity check")
        self.assertEqual(payload["troubleshooting"][0]["symptom"], "Missing source_id returned")
        self.assertTrue(payload["key_reminders"][0].startswith("Confirm the interface requirements first"))


class IncidentQueryPathTestCase(TestCase):
    def setUp(self):
        self.source = AlertSource.objects.create(
            name="test-source",
            source_id="source-incident",
            source_type=AlertsSourceTypes.WEBHOOK,
        )
        self.user = User.objects.create(
            username="incident-operator",
            display_name="事故处理人",
            email="incident@example.com",
            password="pwd",
        )

    def create_event(self, event_id: str, title: str):
        now = timezone.now()
        return Event.objects.create(
            source=self.source,
            raw_data={},
            title=title,
            description=f"{title} description",
            level="1",
            service="svc",
            event_type=EventType.ALERT,
            tags={},
            location="gz",
            external_id=event_id,
            start_time=now,
            labels={},
            action=EventAction.CREATED,
            event_id=event_id,
            item="cpu",
            resource_id=f"res-{event_id}",
            resource_type="host",
            resource_name=f"host-{event_id}",
            status="received",
            assignee=[],
        )

    def create_alert(self, alert_id: str, events):
        alert = Alert.objects.create(
            alert_id=alert_id,
            status=AlertStatus.UNASSIGNED,
            level="1",
            title=f"title-{alert_id}",
            content=f"content-{alert_id}",
            labels={},
            first_event_time=timezone.now(),
            last_event_time=timezone.now(),
            fingerprint=f"fp-{alert_id}",
            operator=[self.user.username],
        )
        alert.events.add(*events)
        return alert

    def test_incident_serializer_uses_prefetched_alert_sources_and_operator_map(self):
        event_a = self.create_event("EVENT-A", "event-a")
        event_b = self.create_event("EVENT-B", "event-b")
        alert_1 = self.create_alert("ALERT-A", [event_a])
        alert_2 = self.create_alert("ALERT-B", [event_b])

        incident = Incident.objects.create(
            incident_id="INCIDENT-A",
            title="incident-a",
            content="content",
            labels={},
            operator=[self.user.username],
            level="1",
        )
        incident.alert.add(alert_1, alert_2)

        viewset = IncidentModelViewSet()
        queryset = list(viewset.get_queryset().filter(pk=incident.pk))
        serializer = IncidentModelSerializer(
            queryset,
            many=True,
            context={
                "operator_user_map": {
                    self.user.username: self.user.display_name,
                }
            },
        )

        with self.assertNumQueries(0):
            data = serializer.data

        self.assertEqual(data[0]["alert_count"], 2)
        self.assertEqual(data[0]["sources"], "test-source")
        self.assertEqual(data[0]["operator_users"], "事故处理人")

    def test_event_serializer_uses_select_related_source_from_viewset_queryset(self):
        event = self.create_event("EVENT-SOURCE", "event-source")

        viewset = EventModelViewSet()
        queryset = list(viewset.get_queryset().filter(pk=event.pk))

        with self.assertNumQueries(0):
            data = EventModelSerializer(queryset, many=True).data

        self.assertEqual(data[0]["source_name"], "test-source")


class AlertPermissionScopeTestCase(TestCase):
    def setUp(self):
        self.factory = APIRequestFactory()
        self._ensure_groups(1, 2)

    @staticmethod
    def _ensure_groups(*group_ids):
        for group_id in group_ids:
            Group.objects.get_or_create(
                id=group_id,
                defaults={"name": f"group-{group_id}", "parent_id": 0},
            )

    @staticmethod
    def _build_user(username, group_list, alarm_permissions):
        user = User.objects.create(
            username=username,
            display_name=username,
            email=f"{username}@example.com",
            password=make_password("password123"),
            domain="domain.com",
            group_list=group_list,
        )
        user.permission = {"alarm": set(alarm_permissions)}
        user.is_superuser = False
        user.is_authenticated = True
        return user

    @staticmethod
    def _build_alert(team, operator, suffix):
        source = AlertSource.objects.create(
            name=f"source-{suffix}",
            source_id=f"source-{suffix}",
            source_type=AlertsSourceTypes.WEBHOOK,
        )
        event = Event.objects.create(
            source=source,
            push_source_id="default",
            raw_data={},
            title=f"event-{suffix}",
            description="desc",
            level="warning",
            service="svc",
            event_type=EventType.ALERT,
            tags={},
            location="gz",
            external_id=f"external-{suffix}",
            start_time=timezone.now(),
            labels={},
            action=EventAction.CREATED,
            event_id=f"EVENT-{suffix}",
            item="cpu",
            resource_id=f"resource-{suffix}",
            resource_type="host",
            resource_name=f"host-{suffix}",
            status="received",
            assignee=[],
        )
        alert = Alert.objects.create(
            alert_id=f"ALERT-{suffix}",
            status=AlertStatus.UNASSIGNED,
            level="warning",
            title=f"alert-{suffix}",
            content="content",
            labels={},
            first_event_time=timezone.now(),
            last_event_time=timezone.now(),
            item="cpu",
            resource_id=f"resource-{suffix}",
            resource_name=f"host-{suffix}",
            resource_type="host",
            operate=None,
            operator=operator,
            source_name=source.name,
            fingerprint=f"fp-{suffix}",
            group_by_field="service",
            dimensions={"service": "svc"},
            rule_id=f"rule-{suffix}",
            team=team,
        )
        alert.events.add(event)
        return alert

    def test_alert_list_is_scoped_by_operator_and_authorized_team(self):
        user = self._build_user("alert-owner", [1], ["Alarms-View"])
        team_alert = self._build_alert([1], [], "team")
        assigned_alert = self._build_alert([2], ["alert-owner"], "assigned")
        hidden_alert = self._build_alert([2], ["someone-else"], "hidden")

        request = self.factory.get("/api/alert")
        request.COOKIES["current_team"] = "1"
        force_authenticate(request, user=user)

        response = AlertModelViewSet.as_view({"get": "list"})(request)
        payload = json.loads(response.content)
        returned_alert_ids = {item["alert_id"] for item in payload["data"]}

        self.assertIn(team_alert.alert_id, returned_alert_ids)
        self.assertIn(assigned_alert.alert_id, returned_alert_ids)
        self.assertNotIn(hidden_alert.alert_id, returned_alert_ids)

    def test_incident_retrieve_rejects_cross_team_access(self):
        user = self._build_user("incident-reader", [1], ["Incidents-View"])
        foreign_alert = self._build_alert([2], ["someone-else"], "foreign")
        incident = Incident.objects.create(
            incident_id="INCIDENT-foreign",
            status=IncidentStatus.PENDING,
            level="warning",
            title="foreign-incident",
            content="content",
            note="",
            labels={},
            operator=[],
            fingerprint="incident-fp",
            created_by="system",
            updated_by="system",
            domain="domain.com",
            updated_by_domain="domain.com",
        )
        incident.alert.add(foreign_alert)

        request = self.factory.get(f"/api/incident/{incident.pk}/")
        request.COOKIES["current_team"] = "1"
        force_authenticate(request, user=user)

        response = IncidentModelViewSet.as_view({"get": "retrieve"})(request, pk=incident.pk)

        self.assertEqual(response.status_code, 404)

    def test_incident_create_rejects_unscoped_alert_ids(self):
        user = self._build_user("incident-editor", [1], ["Alarms-Edit"])
        hidden_alert = self._build_alert([2], ["someone-else"], "hidden-create")

        request = self.factory.post(
            "/api/incident",
            {
                "title": "new-incident",
                "level": "warning",
                "content": "content",
                "note": "",
                "labels": {},
                "operator": [],
                "alert": [hidden_alert.pk],
            },
            format="json",
        )
        request.COOKIES["current_team"] = "1"
        force_authenticate(request, user=user)

        response = IncidentModelViewSet.as_view({"post": "create"})(request)

        self.assertEqual(response.status_code, 400)
        self.assertEqual(Incident.objects.count(), 0)

    def test_incident_create_rejects_null_alert_payload(self):
        user = self._build_user("incident-editor-null", [1], ["Alarms-Edit"])

        request = self.factory.post(
            "/api/incident",
            {
                "title": "new-incident",
                "level": "warning",
                "content": "content",
                "note": "",
                "labels": {},
                "operator": [],
                "alert": None,
            },
            format="json",
        )
        request.COOKIES["current_team"] = "1"
        force_authenticate(request, user=user)

        response = IncidentModelViewSet.as_view({"post": "create"})(request)

        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.data["detail"], "alert must be a list of ids.")

    def test_incident_patch_rejects_null_alert_payload(self):
        user = self._build_user(
            "incident-editor-patch",
            [1],
            ["Incidents-Edit", "Alarms-Edit"],
        )
        visible_alert = self._build_alert([1], ["incident-editor-patch"], "visible-patch")
        incident = Incident.objects.create(
            incident_id="INCIDENT-visible",
            status=IncidentStatus.PENDING,
            level="warning",
            title="visible-incident",
            content="content",
            note="",
            labels={},
            operator=["incident-editor-patch"],
            fingerprint="incident-visible-fp",
            created_by="system",
            updated_by="system",
            domain="domain.com",
            updated_by_domain="domain.com",
        )
        incident.alert.add(visible_alert)

        request = self.factory.patch(
            f"/api/incident/{incident.pk}/",
            {"alert": None},
            format="json",
        )
        request.COOKIES["current_team"] = "1"
        force_authenticate(request, user=user)

        response = IncidentModelViewSet.as_view({"patch": "partial_update"})(request, pk=incident.pk)

        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.data["detail"], "alert must be a list of ids.")

    def test_alert_operator_rejects_unscoped_alert_ids(self):
        user = self._build_user("alert-editor", [1], ["Alarms-Edit"])
        hidden_alert = self._build_alert([2], ["someone-else"], "hidden-operator")

        request = self.factory.post(
            "/api/alert/operator/assign/",
            {"alert_id": [hidden_alert.alert_id], "assignee": ["alert-editor"]},
            format="json",
        )
        request.COOKIES["current_team"] = "1"
        force_authenticate(request, user=user)

        response = AlertModelViewSet.as_view({"post": "operator"})(request, operator_action="assign")
        payload = json.loads(response.content)
        hidden_alert.refresh_from_db()

        self.assertEqual(response.status_code, 500)
        self.assertFalse(payload["result"])
        self.assertEqual(
            payload["data"][hidden_alert.alert_id]["message"],
            "您没有权限操作此告警",
        )
        self.assertEqual(hidden_alert.status, AlertStatus.UNASSIGNED)

    def test_alert_operator_rejects_assignee_outside_alert_team_scope(self):
        user = self._build_user("alert-editor-scope", [1], ["Alarms-Edit"])
        self._build_user("foreign-alert-operator", [2], [])
        visible_alert = self._build_alert([1], [], "visible-operator-scope")

        request = self.factory.post(
            "/api/alert/operator/assign/",
            {
                "alert_id": [visible_alert.alert_id],
                "assignee": ["foreign-alert-operator"],
            },
            format="json",
        )
        request.COOKIES["current_team"] = "1"
        force_authenticate(request, user=user)

        response = AlertModelViewSet.as_view({"post": "operator"})(request, operator_action="assign")
        payload = json.loads(response.content)
        visible_alert.refresh_from_db()

        self.assertEqual(response.status_code, 500)
        self.assertFalse(payload["result"])
        self.assertEqual(
            payload["data"][visible_alert.alert_id]["message"],
            "以下处理人不在告警所属组织范围内: foreign-alert-operator",
        )
        self.assertEqual(visible_alert.status, AlertStatus.UNASSIGNED)
        self.assertEqual(visible_alert.operator, [])

    @patch("apps.alerts.service.alter_operator.AlertOperator.format_notify_data", return_value={})
    def test_alert_operator_accepts_assignee_within_alert_team_scope(self, _format_notify_data):
        user = self._build_user("alert-editor-valid", [1], ["Alarms-Edit"])
        self._build_user("team-alert-operator", [1], [])
        visible_alert = self._build_alert([1], [], "visible-operator-valid")

        request = self.factory.post(
            "/api/alert/operator/assign/",
            {
                "alert_id": [visible_alert.alert_id],
                "assignee": ["team-alert-operator"],
            },
            format="json",
        )
        request.COOKIES["current_team"] = "1"
        force_authenticate(request, user=user)

        response = AlertModelViewSet.as_view({"post": "operator"})(request, operator_action="assign")
        visible_alert.refresh_from_db()

        self.assertEqual(response.status_code, 200)
        self.assertEqual(visible_alert.status, AlertStatus.PENDING)
        self.assertEqual(visible_alert.operator, ["team-alert-operator"])

    def test_incident_create_rejects_operator_outside_alert_team_scope(self):
        user = self._build_user("incident-editor-scope", [1], ["Alarms-Edit"])
        self._build_user("foreign-incident-operator", [2], [])
        visible_alert = self._build_alert([1], [], "visible-incident-scope")

        request = self.factory.post(
            "/api/incident",
            {
                "title": "new-incident-scope",
                "level": "warning",
                "content": "content",
                "note": "",
                "labels": {},
                "operator": ["foreign-incident-operator"],
                "alert": [visible_alert.pk],
            },
            format="json",
        )
        request.COOKIES["current_team"] = "1"
        force_authenticate(request, user=user)

        response = IncidentModelViewSet.as_view({"post": "create"})(request)

        self.assertEqual(response.status_code, 400)
        self.assertEqual(
            response.data["operator"][0],
            "以下处理人不在事故关联告警组织范围内: foreign-incident-operator",
        )
        self.assertEqual(Incident.objects.count(), 0)

    def test_incident_patch_rejects_operator_outside_alert_team_scope(self):
        user = self._build_user(
            "incident-editor-scope-patch",
            [1],
            ["Incidents-Edit", "Alarms-Edit"],
        )
        self._build_user("foreign-incident-patch-operator", [2], [])
        visible_alert = self._build_alert([1], ["incident-editor-scope-patch"], "visible-incident-patch-scope")
        incident = Incident.objects.create(
            incident_id="INCIDENT-scope-patch",
            status=IncidentStatus.PENDING,
            level="warning",
            title="scope-patch-incident",
            content="content",
            note="",
            labels={},
            operator=["incident-editor-scope-patch"],
            fingerprint="incident-scope-patch-fp",
            created_by="system",
            updated_by="system",
            domain="domain.com",
            updated_by_domain="domain.com",
        )
        incident.alert.add(visible_alert)

        request = self.factory.patch(
            f"/api/incident/{incident.pk}/",
            {"operator": ["foreign-incident-patch-operator"]},
            format="json",
        )
        request.COOKIES["current_team"] = "1"
        force_authenticate(request, user=user)

        response = IncidentModelViewSet.as_view({"patch": "partial_update"})(request, pk=incident.pk)
        incident.refresh_from_db()

        self.assertEqual(response.status_code, 400)
        self.assertEqual(
            response.data["operator"][0],
            "以下处理人不在事故关联告警组织范围内: foreign-incident-patch-operator",
        )
        self.assertEqual(incident.operator, ["incident-editor-scope-patch"])

    def test_alert_operator_rejects_nonexistent_assignee(self):
        user = self._build_user("alert-editor-missing", [1], ["Alarms-Edit"])
        visible_alert = self._build_alert([1], [], "visible-operator-missing")

        request = self.factory.post(
            "/api/alert/operator/assign/",
            {"alert_id": [visible_alert.alert_id], "assignee": ["ghost-user"]},
            format="json",
        )
        request.COOKIES["current_team"] = "1"
        force_authenticate(request, user=user)

        response = AlertModelViewSet.as_view({"post": "operator"})(request, operator_action="assign")
        payload = json.loads(response.content)
        visible_alert.refresh_from_db()

        self.assertEqual(response.status_code, 500)
        self.assertFalse(payload["result"])
        self.assertEqual(
            payload["data"][visible_alert.alert_id]["message"],
            "以下处理人不存在: ghost-user",
        )
        self.assertEqual(visible_alert.operator, [])

    def test_incident_create_rejects_nonexistent_operator(self):
        user = self._build_user("incident-editor-missing", [1], ["Alarms-Edit"])
        visible_alert = self._build_alert([1], [], "visible-incident-missing")

        request = self.factory.post(
            "/api/incident",
            {
                "title": "new-incident-missing",
                "level": "warning",
                "content": "content",
                "note": "",
                "labels": {},
                "operator": ["ghost-incident-user"],
                "alert": [visible_alert.pk],
            },
            format="json",
        )
        request.COOKIES["current_team"] = "1"
        force_authenticate(request, user=user)

        response = IncidentModelViewSet.as_view({"post": "create"})(request)

        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.data["operator"][0], "以下处理人不存在: ghost-incident-user")
        self.assertEqual(Incident.objects.count(), 0)

    def test_event_retrieve_rejects_cross_team_access(self):
        user = self._build_user("event-reader", [1], ["Alarms-View"])
        hidden_alert = self._build_alert([2], ["someone-else"], "hidden-event")
        hidden_event = hidden_alert.events.first()

        request = self.factory.get(f"/api/events/{hidden_event.pk}/")
        request.COOKIES["current_team"] = "1"
        force_authenticate(request, user=user)

        response = EventModelViewSet.as_view({"get": "retrieve"})(request, pk=hidden_event.pk)

        self.assertEqual(response.status_code, 404)

    def test_operator_log_list_hides_cross_team_alert_history(self):
        user = self._build_user("log-reader", [1], ["operation_log-View"])
        visible_alert = self._build_alert([1], [], "visible-log")
        hidden_alert = self._build_alert([2], ["someone-else"], "hidden-log")
        OperatorLog.objects.create(
            operator="system",
            action=LogAction.MODIFY,
            target_type=LogTargetType.ALERT,
            operator_object="告警处理-关闭",
            target_id=visible_alert.alert_id,
            overview="visible log",
        )
        OperatorLog.objects.create(
            operator="system",
            action=LogAction.MODIFY,
            target_type=LogTargetType.ALERT,
            operator_object="告警处理-关闭",
            target_id=hidden_alert.alert_id,
            overview="hidden log",
        )

        request = self.factory.get("/api/log/")
        request.COOKIES["current_team"] = "1"
        force_authenticate(request, user=user)

        response = SystemLogModelViewSet.as_view({"get": "list"})(request)
        payload = response.data
        rows = payload["data"] if isinstance(payload, dict) else payload
        returned_overviews = {item["overview"] for item in rows}

        self.assertIn("visible log", returned_overviews)
        self.assertNotIn("hidden log", returned_overviews)

    def test_incident_queryset_keeps_distinct_alert_count_after_scope_filtering(self):
        user = self._build_user("incident-count-reader", [1], ["Incidents-View"])
        alert_one = self._build_alert([1], [], "count-one")
        alert_two = self._build_alert([1], [], "count-two")
        incident = Incident.objects.create(
            incident_id="INCIDENT-count",
            status=IncidentStatus.PENDING,
            level="warning",
            title="count-incident",
            content="content",
            note="",
            labels={},
            operator=[],
            fingerprint="incident-count-fp",
            created_by="system",
            updated_by="system",
            domain="domain.com",
            updated_by_domain="domain.com",
        )
        incident.alert.add(alert_one, alert_two)

        request = self.factory.get("/api/incident")
        request.COOKIES["current_team"] = "1"
        force_authenticate(request, user=user)

        response = IncidentModelViewSet.as_view({"get": "list"})(request)
        payload = json.loads(response.content)

        self.assertEqual(response.status_code, 200)
        self.assertEqual(payload["data"][0]["alert_count"], 2)


class RelatedAlertsFeatureTestCase(TestCase):
    def setUp(self):
        self.factory = APIRequestFactory()
        Group.objects.get_or_create(id=1, defaults={"name": "group-1", "parent_id": 0})
        self.source = AlertSource.objects.create(
            name="related-source",
            source_id="related-source",
            source_type=AlertsSourceTypes.WEBHOOK,
        )
        self.user = User.objects.create(
            username="related-reader",
            display_name="related-reader",
            email="related-reader@example.com",
            password=make_password("password123"),
            domain="domain.com",
            group_list=[{"id": 1, "name": "group-1"}],
        )
        self.user.permission = {"alarm": {"Alarms-View"}}
        self.user.is_superuser = False
        self.user.is_authenticated = True

    def _build_alert(self, suffix, *, service="svc-a", location="gz", resource_name=None, item="cpu", minutes_ago=5):
        occurred_at = timezone.now() - timedelta(minutes=minutes_ago)
        resource_name = resource_name or f"host-{suffix}"
        event = Event.objects.create(
            source=self.source,
            push_source_id="default",
            raw_data={},
            title=f"event-{suffix}",
            description="desc",
            level="warning",
            service=service,
            event_type=EventType.ALERT,
            tags={},
            location=location,
            external_id=f"external-{suffix}",
            start_time=occurred_at,
            labels={},
            action=EventAction.CREATED,
            event_id=f"EVENT-{suffix}",
            item=item,
            resource_id=f"resource-{suffix}",
            resource_type="host",
            resource_name=resource_name,
            status="received",
            assignee=[],
            team=[1],
        )
        Event.objects.filter(pk=event.pk).update(received_at=occurred_at)
        event.refresh_from_db()

        alert = Alert.objects.create(
            alert_id=f"ALERT-{suffix}",
            status=AlertStatus.UNASSIGNED,
            level="warning",
            title=f"alert-{suffix}",
            content="content",
            labels={},
            first_event_time=occurred_at,
            last_event_time=occurred_at,
            item=item,
            resource_id=f"resource-{suffix}",
            resource_name=resource_name,
            resource_type="host",
            operate=None,
            operator=[],
            source_name=self.source.name,
            fingerprint=f"fp-{suffix}",
            group_by_field="service,location,resource_name,item",
            dimensions={
                "service": service,
                "location": location,
                "resource_name": resource_name,
                "item": item,
            },
            rule_id=f"rule-{suffix}",
            team=[1],
        )
        Alert.objects.filter(pk=alert.pk).update(created_at=occurred_at, updated_at=occurred_at)
        alert.refresh_from_db()
        alert.events.add(event)
        return alert

    def test_related_alert_endpoint_returns_ranked_candidates_within_one_hour(self):
        current_alert = self._build_alert("current", resource_name="host-current")
        close_match = self._build_alert(
            "close-match",
            resource_name="host-current",
            minutes_ago=3,
        )
        low_match = self._build_alert(
            "low-match",
            service="svc-a",
            location="bj",
            resource_name="host-other",
            item="mem",
            minutes_ago=10,
        )
        self._build_alert(
            "out-window",
            resource_name="host-current",
            minutes_ago=120,
        )

        request = self.factory.get(f"/api/alerts/{current_alert.pk}/related/", {"time_window": 60, "limit": 10})
        request.COOKIES["current_team"] = "1"
        force_authenticate(request, user=self.user)

        response = AlertModelViewSet.as_view({"get": "related"})(request, pk=current_alert.pk)

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["related_count"], 1)
        self.assertEqual(response.data["maybe_related_count"], 1)
        self.assertEqual(response.data["items"][0]["id"], close_match.id)
        self.assertGreater(response.data["items"][0]["similarity_score"], response.data["items"][1]["similarity_score"])
        self.assertEqual(response.data["items"][1]["id"], low_match.id)

    def test_related_alert_endpoint_returns_multiple_incidents_and_respects_team_scope(self):
        current_alert = self._build_alert("current-multi", resource_name="host-multi")
        visible_match = self._build_alert(
            "visible-match",
            resource_name="host-multi",
            minutes_ago=3,
        )
        hidden_match = self._build_alert(
            "hidden-match",
            resource_name="host-multi",
            minutes_ago=2,
        )
        hidden_match.team = [2]
        hidden_match.save(update_fields=["team"])

        incident_a = Incident.objects.create(
            incident_id="INCIDENT-A",
            status=IncidentStatus.PENDING,
            level="warning",
            title="incident-a",
            content="content",
            note="",
            labels={},
            operator=[],
            fingerprint="incident-a",
            team=[1],
        )
        incident_b = Incident.objects.create(
            incident_id="INCIDENT-B",
            status=IncidentStatus.PENDING,
            level="warning",
            title="incident-b",
            content="content",
            note="",
            labels={},
            operator=[],
            fingerprint="incident-b",
            team=[1],
        )
        incident_c = Incident.objects.create(
            incident_id="INCIDENT-C",
            status=IncidentStatus.PENDING,
            level="warning",
            title="incident-c",
            content="content",
            note="",
            labels={},
            operator=[],
            fingerprint="incident-c",
            team=[2],
        )
        incident_a.alert.add(current_alert)
        incident_b.alert.add(current_alert)
        incident_a.alert.add(visible_match)
        incident_b.alert.add(visible_match)
        incident_c.alert.add(hidden_match)

        request = self.factory.get(f"/api/alerts/{current_alert.pk}/related/", {"time_window": 60, "limit": 10})
        request.COOKIES["current_team"] = "1"
        force_authenticate(request, user=self.user)

        response = AlertModelViewSet.as_view({"get": "related"})(request, pk=current_alert.pk)

        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            [incident["title"] for incident in response.data["current_incidents"]],
            ["incident-b", "incident-a"],
        )
        self.assertEqual(len(response.data["items"]), 1)
        self.assertEqual(response.data["items"][0]["id"], visible_match.id)
        self.assertEqual(
            [incident["title"] for incident in response.data["items"][0]["incidents"]],
            ["incident-b", "incident-a"],
        )

    def test_add_alerts_allows_alerts_in_multiple_incidents(self):
        incident_one = Incident.objects.create(
            incident_id="INCIDENT-ONE",
            status=IncidentStatus.PENDING,
            level="warning",
            title="incident-one",
            content="content",
            note="",
            labels={},
            operator=[],
            fingerprint="incident-one",
            team=[1],
        )
        incident_two = Incident.objects.create(
            incident_id="INCIDENT-TWO",
            status=IncidentStatus.PENDING,
            level="warning",
            title="incident-two",
            content="content",
            note="",
            labels={},
            operator=[],
            fingerprint="incident-two",
            team=[1],
        )
        alert = self._build_alert("multi-incident-add", resource_name="host-add")
        incident_one.alert.add(alert)

        request = self.factory.post(
            f"/api/incident/{incident_two.pk}/alerts/add/",
            {"alert": [alert.id]},
            format="json",
        )
        request.COOKIES["current_team"] = "1"
        editor = build_permission_test_user(
            "incident-editor",
            [{"id": 1, "name": "group-1"}],
            {"alarm": {"Incidents-Edit"}},
        )
        force_authenticate(request, user=editor)

        response = IncidentModelViewSet.as_view({"post": "add_alerts"})(request, pk=incident_two.pk)

        self.assertEqual(response.status_code, 200)
        self.assertEqual(set(alert.incident_set.values_list("id", flat=True)), {incident_one.id, incident_two.id})

    def test_backfill_alert_dimensions_command_populates_empty_dimensions(self):
        occurred_at = timezone.now() - timedelta(minutes=5)
        event = Event.objects.create(
            source=self.source,
            push_source_id="default",
            raw_data={},
            title="event-backfill",
            description="desc",
            level="warning",
            service="svc-backfill",
            event_type=EventType.ALERT,
            tags={},
            location="gz",
            external_id="external-backfill",
            start_time=occurred_at,
            labels={},
            action=EventAction.CREATED,
            event_id="EVENT-backfill",
            item="cpu",
            resource_id="resource-backfill",
            resource_type="host",
            resource_name="host-backfill",
            status="received",
            assignee=[],
            team=[1],
        )
        Event.objects.filter(pk=event.pk).update(received_at=occurred_at)
        alert = Alert.objects.create(
            alert_id="ALERT-backfill",
            status=AlertStatus.UNASSIGNED,
            level="warning",
            title="alert-backfill",
            content="content",
            labels={},
            first_event_time=occurred_at,
            last_event_time=occurred_at,
            item="cpu",
            resource_id="resource-backfill",
            resource_name="host-backfill",
            resource_type="host",
            operate=None,
            operator=[],
            source_name=self.source.name,
            fingerprint="fp-backfill",
            group_by_field="service,location,resource_name,item",
            dimensions={},
            rule_id="rule-backfill",
            team=[1],
        )
        alert.events.add(event)

        out = StringIO()
        call_command("backfill_alert_dimensions", stdout=out)
        alert.refresh_from_db()

        self.assertEqual(
            alert.dimensions,
            {
                "service": "svc-backfill",
                "location": "gz",
                "resource_name": "host-backfill",
                "item": "cpu",
            },
        )
        self.assertIn("updated=1", out.getvalue())
