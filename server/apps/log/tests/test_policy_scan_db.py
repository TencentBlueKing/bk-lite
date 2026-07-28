"""apps/log/tasks/services/policy_scan.py 真实 DB 行为测试。

外部边界 mock：
- VictoriaMetricsAPI 查询（vlogs_api.query）—— 返回真实形态假数据
- SystemMgmtUtils.send_msg_with_channel —— 通知通道
- S3JSONField._upload_to_s3 —— MinIO 上传，返回假路径

DB（Policy/Alert/Event/AlertSnapshot）走真实，断言落库副作用。
"""
from concurrent.futures import ThreadPoolExecutor
from threading import Barrier

import pytest
from django.db import close_old_connections
from django.utils import timezone

from apps.log.constants.alert_policy import AlertConstants
from apps.log.models.policy import Alert, AlertSnapshot, Event, EventRawData, Policy
from apps.log.services.alert_lifecycle_notify import LogAlertLifecycleNotifier
from apps.log.tasks.services.policy_scan import LogPolicyScan
from apps.system_mgmt.models.channel import Channel

pytestmark = pytest.mark.django_db


@pytest.fixture(autouse=True)
def _stub_s3_upload(mocker):
    """拦截 MinIO 边界：上传返回确定性假路径，回读返回空列表。

    生产环境 snapshots/raw_data 通过 MinIO 持久化；测试环境无对象存储，
    回读会落到 "文件不存在" 分支返回 None，破坏 snapshots 列表语义。
    因此把读边界 stub 成空列表，模拟首次创建后尚无历史快照的真实形态。
    """
    mocker.patch(
        "apps.core.fields.s3_json_field.S3JSONField._upload_to_s3",
        return_value="2026/01/01/fake_path.json.gz",
    )
    mocker.patch(
        "apps.core.fields.s3_json_field.S3JSONField._load_from_s3",
        return_value=[],
    )


def _make_policy(**overrides):
    data = dict(
        name=overrides.pop("name", "p-scan"),
        alert_type="keyword",
        alert_name="${host} 报错",
        alert_level="warning",
        alert_condition={"query": "error", "limit": 3},
        schedule={"type": "min", "value": 5},
        period={"type": "min", "value": 5},
        notice=False,
        notice_users=[],
        last_run_time=timezone.now(),
    )
    data.update(overrides)
    return Policy.objects.create(**data)


class TestKeywordAlertDetection:
    def test_returns_event_with_total_count(self, mocker):
        policy = _make_policy(alert_name="关键字命中")
        scan = LogPolicyScan(policy)
        # 第一次 query 返回样本日志，第二次返回 count
        mocker.patch.object(
            scan.vlogs_api,
            "query",
            side_effect=[
                [{"_msg": "error A"}, {"_msg": "error B"}],  # 样本
                [{"total_count": "7"}],  # count
            ],
        )
        events = scan.keyword_alert_detection()
        assert len(events) == 1
        ev = events[0]
        assert ev["source_id"] == f"policy_{policy.id}"
        assert ev["value"] == 7
        assert ev["level"] == "warning"
        assert "7 条匹配日志" in ev["content"]
        assert ev["raw_data"] == [{"_msg": "error A"}, {"_msg": "error B"}]

    def test_empty_query_returns_no_events(self):
        policy = _make_policy(alert_condition={"query": ""})
        events = LogPolicyScan(policy).keyword_alert_detection()
        assert events == []

    def test_no_logs_returns_empty(self, mocker):
        policy = _make_policy()
        scan = LogPolicyScan(policy)
        mocker.patch.object(scan.vlogs_api, "query", return_value=[])
        assert scan.keyword_alert_detection() == []

    def test_count_zero_falls_back_to_logs_length(self, mocker):
        policy = _make_policy()
        scan = LogPolicyScan(policy)
        mocker.patch.object(
            scan.vlogs_api,
            "query",
            side_effect=[[{"_msg": "x"}], [{"total_count": "0"}]],
        )
        events = scan.keyword_alert_detection()
        assert events[0]["value"] == 1

    def test_grouped_detection(self, mocker):
        policy = _make_policy(alert_condition={"query": "error", "group_by": ["host"], "limit": 2})
        scan = LogPolicyScan(policy)

        def fake_query(query, **kwargs):
            if "stats by" in query:
                return [
                    {"host": "h1", "total_count": "5"},
                    {"host": "h2", "total_count": "0"},  # 过滤掉
                    {"host": "", "total_count": "3"},  # 无完整分组值，跳过
                ]
            return [{"_msg": "sample"}]

        mocker.patch.object(scan.vlogs_api, "query", side_effect=fake_query)
        events = scan.keyword_alert_detection()
        assert len(events) == 1
        assert events[0]["value"] == 5
        assert events[0]["content"] == "h1 报错"

    def test_query_exception_propagates(self, mocker):
        policy = _make_policy()
        scan = LogPolicyScan(policy)
        mocker.patch.object(scan.vlogs_api, "query", side_effect=RuntimeError("vm down"))
        with pytest.raises(RuntimeError):
            scan.keyword_alert_detection()


class TestAggregateAlertDetection:
    def test_emits_event_when_condition_met(self, mocker):
        policy = _make_policy(
            alert_type="aggregate",
            alert_name="${host} 聚合",
            alert_condition={
                "query": "*",
                "group_by": ["host"],
                "rule": {
                    "mode": "and",
                    "conditions": [{"func": "count", "field": "_msg", "op": ">", "value": 2}],
                },
            },
        )
        scan = LogPolicyScan(policy)
        mocker.patch.object(
            scan.vlogs_api,
            "query",
            return_value=[{"host": "h1", "count__msg": "9"}],
        )
        events = scan.aggregate_alert_detection()
        assert len(events) == 1
        assert events[0]["value"] == 9
        assert events[0]["content"] == "h1 聚合"
        assert events[0]["source_id"].startswith(f"policy_{policy.id}_host=h1")

    def test_no_rule_conditions_returns_empty(self):
        policy = _make_policy(alert_type="aggregate", alert_condition={"query": "*", "rule": {}})
        assert LogPolicyScan(policy).aggregate_alert_detection() == []

    def test_no_results_returns_empty(self, mocker):
        policy = _make_policy(
            alert_type="aggregate",
            alert_condition={"query": "*", "group_by": [], "rule": {"conditions": [{"func": "count", "field": "_msg", "op": ">", "value": 1}]}},
        )
        scan = LogPolicyScan(policy)
        mocker.patch.object(scan.vlogs_api, "query", return_value=[])
        assert scan.aggregate_alert_detection() == []

    def test_condition_not_met_no_event(self, mocker):
        policy = _make_policy(
            alert_type="aggregate",
            alert_condition={"query": "*", "group_by": [], "rule": {"conditions": [{"func": "count", "field": "_msg", "op": ">", "value": 100}]}},
        )
        scan = LogPolicyScan(policy)
        mocker.patch.object(scan.vlogs_api, "query", return_value=[{"total_count": "3"}])
        assert scan.aggregate_alert_detection() == []


class TestCreateEvents:
    def test_creates_alert_event_and_snapshot(self, mocker):
        policy = _make_policy()
        scan = LogPolicyScan(policy)
        events = [
            {
                "source_id": f"policy_{policy.id}",
                "level": "warning",
                "content": "命中",
                "value": 5,
                "raw_data": [{"_msg": "x"}],
            }
        ]
        event_objs = scan.create_events(events)
        assert len(event_objs) == 1
        # 新告警落库
        alert = Alert.objects.get(policy=policy)
        assert alert.status == AlertConstants.STATUS_NEW
        assert alert.content == "命中"
        assert alert.value == 5
        # 事件落库
        assert Event.objects.filter(policy=policy).count() == 1
        # 原始数据落库
        assert EventRawData.objects.filter(event=event_objs[0]).count() == 1
        # 快照创建
        snap = AlertSnapshot.objects.get(alert=alert)
        assert snap.policy_id == policy.id

    def test_empty_events_returns_empty(self):
        policy = _make_policy()
        assert LogPolicyScan(policy).create_events([]) == []

    def test_existing_active_alert_is_updated_not_duplicated(self):
        policy = _make_policy()
        scan = LogPolicyScan(policy)
        existing = Alert.objects.create(
            id="alert-exist",
            policy=policy,
            source_id=f"policy_{policy.id}",
            collect_type=None,
            level="warning",
            value=1,
            content="老内容",
            status=AlertConstants.STATUS_NEW,
            start_event_time=timezone.now(),
            end_event_time=timezone.now(),
        )
        events = [
            {
                "source_id": f"policy_{policy.id}",
                "level": "critical",
                "content": "新内容",
                "value": 9,
                "raw_data": [],
            }
        ]
        scan.create_events(events)
        existing.refresh_from_db()
        assert existing.content == "新内容"
        assert existing.level == "critical"
        assert existing.value == 9
        # 级别变化导致 notice 重置为 False
        assert existing.notice is False
        # 没有创建新告警
        assert Alert.objects.filter(policy=policy).count() == 1

    def test_same_execution_level_change_resets_event_notification(self, mocker):
        scan_time = timezone.datetime(2026, 7, 24, tzinfo=timezone.utc)
        policy = _make_policy(notice=True, notice_users=["u1"])
        first_scan = LogPolicyScan(policy, scan_time=scan_time, execution_key="same-execution")
        first_event = first_scan.create_events(
            [
                {
                    "source_id": f"policy_{policy.id}",
                    "level": "warning",
                    "content": "首次命中",
                    "value": 1,
                    "raw_data": [],
                }
            ]
        )[0]
        Event.objects.filter(id=first_event.id).update(notified=True)
        Alert.objects.filter(id=first_event.alert_id).update(notice=True)

        retry_scan = LogPolicyScan(
            policy,
            scan_time=scan_time + timezone.timedelta(minutes=1),
            execution_key="same-execution",
        )
        retry_event = retry_scan.create_events(
            [
                {
                    "source_id": f"policy_{policy.id}",
                    "level": "critical",
                    "content": "升级命中",
                    "value": 2,
                    "raw_data": [],
                }
            ]
        )[0]

        retry_event.refresh_from_db()
        retry_event.alert.refresh_from_db()
        assert retry_event.id == first_event.id
        assert retry_event.notified is False
        assert retry_event.alert.notice is False

        send = mocker.patch.object(LogPolicyScan, "send_notice", return_value=(True, {"result": True}))
        retry_scan.notice([retry_event])

        send.assert_called_once()
        retry_event.refresh_from_db()
        assert retry_event.notified is True

    def test_late_same_execution_cannot_overwrite_newer_event(self):
        cursor = timezone.datetime(2026, 7, 24, tzinfo=timezone.utc)
        policy = _make_policy(last_run_time=cursor)
        source_id = f"policy_{policy.id}"
        newer_scan = LogPolicyScan(
            policy,
            scan_time=cursor + timezone.timedelta(minutes=4),
            execution_key="same-execution",
            cursor_time=cursor,
        )
        older_scan = LogPolicyScan(
            policy,
            scan_time=cursor + timezone.timedelta(minutes=3),
            execution_key="same-execution",
            cursor_time=cursor,
        )

        newer_scan.create_events(
            [{"source_id": source_id, "level": "warning", "content": "newer", "value": 4, "raw_data": []}]
        )
        older_scan.create_events(
            [{"source_id": source_id, "level": "warning", "content": "older", "value": 3, "raw_data": []}]
        )

        event = Event.objects.get(policy=policy)
        event.alert.refresh_from_db()
        assert event.event_time == newer_scan.scan_time
        assert event.content == "newer"
        assert event.value == 4
        assert event.alert.end_event_time == newer_scan.scan_time
        assert event.alert.content == "newer"
        assert event.alert.value == 4

    @pytest.mark.django_db(transaction=True)
    def test_concurrent_same_execution_recovers_event_conflict(self):
        policy = _make_policy()
        events = [
            {
                "source_id": f"policy_{policy.id}",
                "level": "warning",
                "content": "并发命中",
                "value": 1,
                "raw_data": [],
            }
        ]
        barrier = Barrier(2)

        class CoordinatedScan(LogPolicyScan):
            def _find_existing_events(self, event_ids, source_ids):
                existing = super()._find_existing_events(event_ids, source_ids)
                barrier.wait(timeout=5)
                return existing

        def create_once():
            close_old_connections()
            try:
                return CoordinatedScan(
                    Policy.objects.get(id=policy.id),
                    execution_key="same-execution",
                ).create_events(events)
            finally:
                close_old_connections()

        with ThreadPoolExecutor(max_workers=2) as executor:
            results = list(executor.map(lambda _: create_once(), range(2)))

        assert [len(result) for result in results] == [1, 1]
        assert Event.objects.filter(policy=policy).count() == 1
        assert Alert.objects.filter(policy=policy).count() == 1

    @pytest.mark.django_db(transaction=True)
    def test_concurrent_different_windows_force_loser_to_retry(self):
        policy = _make_policy()
        events = [
            {
                "source_id": f"policy_{policy.id}",
                "level": "warning",
                "content": "并发命中",
                "value": 1,
                "raw_data": [],
            }
        ]
        barrier = Barrier(2)
        scan_times = [
            timezone.datetime(2026, 7, 24, 0, 2, tzinfo=timezone.utc),
            timezone.datetime(2026, 7, 24, 0, 3, tzinfo=timezone.utc),
        ]

        class CoordinatedScan(LogPolicyScan):
            def _find_existing_events(self, event_ids, source_ids):
                existing = super()._find_existing_events(event_ids, source_ids)
                barrier.wait(timeout=5)
                return existing

        def create_once(scan_time):
            close_old_connections()
            try:
                return CoordinatedScan(
                    Policy.objects.get(id=policy.id),
                    scan_time=scan_time,
                    execution_key="same-execution",
                ).create_events(events)
            finally:
                close_old_connections()

        with ThreadPoolExecutor(max_workers=2) as executor:
            futures = [executor.submit(create_once, scan_time) for scan_time in scan_times]
            outcomes = []
            for future in futures:
                try:
                    outcomes.append(("success", future.result()))
                except RuntimeError as exc:
                    outcomes.append(("retry", str(exc)))

        assert [outcome[0] for outcome in outcomes].count("success") == 1
        assert [outcome[0] for outcome in outcomes].count("retry") == 1
        assert Event.objects.filter(policy=policy).count() == 1
        assert Alert.objects.filter(policy=policy).count() == 1


class TestSendNotice:
    def test_no_notice_users_returns_false(self):
        policy = _make_policy(notice_users=[])
        scan = LogPolicyScan(policy)
        event = Event(id="e1", policy=policy, source_id="s", event_time=timezone.now(), level="warning", content="c")
        ok, result = scan.send_notice(event)
        assert ok is False
        assert result == []

    def test_success_first_attempt(self, mocker):
        policy = _make_policy(notice_users=["u1"], notice_type_id=2)
        scan = LogPolicyScan(policy)
        send = mocker.patch(
            "apps.log.tasks.services.policy_scan.SystemMgmtUtils.send_msg_with_channel",
            return_value={"result": True},
        )
        event = Event(id="e1", policy=policy, source_id="s", event_time=timezone.now(), level="warning", content="c")
        ok, result = scan.send_notice(event)
        assert ok is True
        assert result == {"result": True}
        send.assert_called_once()

    def test_failure_then_returns_last_result(self, mocker):
        policy = _make_policy(notice_users=["u1"])
        scan = LogPolicyScan(policy)
        mocker.patch(
            "apps.log.tasks.services.policy_scan.SystemMgmtUtils.send_msg_with_channel",
            return_value={"result": False, "message": "channel down"},
        )
        mocker.patch("apps.log.tasks.services.policy_scan.time.sleep")
        event = Event(id="e1", policy=policy, source_id="s", event_time=timezone.now(), level="warning", content="c")
        ok, result = scan.send_notice(event, max_attempts=2)
        assert ok is False
        assert result["message"] == "channel down"

    def test_exception_during_send_recorded(self, mocker):
        policy = _make_policy(notice_users=["u1"])
        scan = LogPolicyScan(policy)
        mocker.patch(
            "apps.log.tasks.services.policy_scan.SystemMgmtUtils.send_msg_with_channel",
            side_effect=RuntimeError("boom"),
        )
        event = Event(id="e1", policy=policy, source_id="s", event_time=timezone.now(), level="warning", content="c")
        ok, result = scan.send_notice(event, max_attempts=1)
        assert ok is False
        assert result["result"] is False

    def test_alert_center_notice_without_users_sends_created_event(self, mocker):
        channel = Channel.objects.create(
            name="告警中心",
            channel_type="nats",
            config={"method_name": "receive_alert_events"},
            description="",
        )
        policy = _make_policy(
            notice=True,
            notice_type="nats",
            notice_type_id=channel.id,
            notice_users=[],
        )
        alert = Alert.objects.create(
            id="a-nats-no-users",
            policy=policy,
            source_id="s",
            level="warning",
            status="new",
            start_event_time=timezone.now(),
        )
        event = Event.objects.create(
            id="e-nats-no-users",
            policy=policy,
            alert=alert,
            source_id="s",
            event_time=timezone.now(),
            level="warning",
            content="c",
        )
        notify = mocker.patch.object(
            LogAlertLifecycleNotifier,
            "notify_created",
            return_value=(True, {"result": True}),
        )

        ok, result = LogPolicyScan(policy).send_notice(event)

        assert ok is True
        assert result == {"result": True}
        notify.assert_called_once_with(event, max_attempts=None)

    def test_created_success_replays_closed_when_alert_closed_during_send(self, mocker):
        channel = Channel.objects.create(
            name="告警中心并发关闭",
            channel_type="nats",
            config={"method_name": "receive_alert_events"},
            description="",
        )
        policy = _make_policy(
            notice=True,
            notice_type="nats",
            notice_type_id=channel.id,
            notice_users=[],
        )
        alert = Alert.objects.create(
            id="a-created-closed-race",
            policy=policy,
            source_id="s",
            level="warning",
            status="new",
            start_event_time=timezone.now(),
        )
        event = Event.objects.create(
            id="e-created-closed-race",
            policy=policy,
            alert=alert,
            source_id="s",
            event_time=timezone.now(),
            level="warning",
            content="c",
        )
        closed_at = timezone.now()

        def close_during_created(*args, **kwargs):
            Alert.objects.filter(id=alert.id).update(
                status=AlertConstants.STATUS_CLOSED,
                end_event_time=closed_at,
                notice=True,
            )
            return True, {"result": True}

        mocker.patch.object(
            LogAlertLifecycleNotifier,
            "notify_created",
            side_effect=close_during_created,
        )
        notify_closed = mocker.patch.object(
            LogAlertLifecycleNotifier,
            "notify_closed",
            return_value=(True, {"result": True}),
        )

        ok, _ = LogPolicyScan(policy).send_notice(event, max_attempts=1)

        assert ok is True
        replayed_alert = notify_closed.call_args.args[0]
        assert replayed_alert.status == AlertConstants.STATUS_CLOSED
        assert replayed_alert.end_event_time == closed_at
        notify_closed.assert_called_once_with(replayed_alert, max_attempts=1)

    def test_failed_closed_replay_restores_pending_notice(self, mocker):
        channel = Channel.objects.create(
            name="告警中心关闭重放失败",
            channel_type="nats",
            config={"method_name": "receive_alert_events"},
            description="",
        )
        policy = _make_policy(
            notice=True,
            notice_type="nats",
            notice_type_id=channel.id,
            notice_users=[],
        )
        alert = Alert.objects.create(
            id="a-closed-replay-fail",
            policy=policy,
            source_id="s",
            level="warning",
            status="new",
            start_event_time=timezone.now(),
        )
        event = Event.objects.create(
            id="e-closed-replay-fail",
            policy=policy,
            alert=alert,
            source_id="s",
            event_time=timezone.now(),
            level="warning",
            content="c",
        )
        closed_at = timezone.now()

        def close_during_created(*args, **kwargs):
            Alert.objects.filter(id=alert.id).update(
                status=AlertConstants.STATUS_CLOSED,
                end_event_time=closed_at,
                notice=True,
            )
            return True, {"result": True}

        mocker.patch.object(
            LogAlertLifecycleNotifier,
            "notify_created",
            side_effect=close_during_created,
        )
        mocker.patch.object(
            LogAlertLifecycleNotifier,
            "notify_closed",
            return_value=(False, {"result": False, "message": "down"}),
        )

        ok, _ = LogPolicyScan(policy).send_notice(event, max_attempts=1)

        assert ok is True
        alert.refresh_from_db()
        assert alert.status == AlertConstants.STATUS_CLOSED
        assert alert.end_event_time == closed_at
        assert alert.notice is False


class TestNotice:
    def _persist_event(self, policy, alert, level="warning"):
        return Event.objects.create(
            id=f"ev-{level}",
            policy=policy,
            source_id="s",
            alert=alert,
            event_time=timezone.now(),
            level=level,
            content="c",
            notice_result=[],
        )

    def test_no_events_or_notice_disabled_noop(self):
        policy = _make_policy(notice=False)
        # 不抛异常即可
        LogPolicyScan(policy).notice([])

    def test_info_level_skipped(self, mocker):
        policy = _make_policy(notice=True, notice_users=["u1"])
        alert = Alert.objects.create(id="a-info", policy=policy, source_id="s", level="info", status="new", start_event_time=timezone.now())
        ev = self._persist_event(policy, alert, level="info")
        send = mocker.patch.object(LogPolicyScan, "send_notice")
        LogPolicyScan(policy).notice([ev])
        send.assert_not_called()

    def test_already_notified_alert_skipped(self, mocker):
        policy = _make_policy(notice=True, notice_users=["u1"])
        alert = Alert.objects.create(
            id="a-noticed", policy=policy, source_id="s", level="warning", status="new", start_event_time=timezone.now(), notice=True
        )
        ev = self._persist_event(policy, alert, level="warning")
        send = mocker.patch.object(LogPolicyScan, "send_notice")
        LogPolicyScan(policy).notice([ev])
        send.assert_not_called()
        ev.refresh_from_db()
        assert ev.notified is True

    def test_successful_notice_marks_alert(self, mocker):
        policy = _make_policy(notice=True, notice_users=["u1"])
        alert = Alert.objects.create(
            id="a-send", policy=policy, source_id="s", level="warning", status="new", start_event_time=timezone.now(), notice=False
        )
        ev = self._persist_event(policy, alert, level="warning")
        mocker.patch.object(LogPolicyScan, "send_notice", return_value=(True, {"result": True}))
        LogPolicyScan(policy).notice([ev])
        ev.refresh_from_db()
        alert.refresh_from_db()
        assert ev.notified is True
        assert alert.notice is True

    def test_late_created_success_does_not_mark_closed_alert_noticed(self, mocker):
        policy = _make_policy(notice=True, notice_users=["u1"])
        alert = Alert.objects.create(
            id="a-closed-race",
            policy=policy,
            source_id="s",
            level="warning",
            status=AlertConstants.STATUS_CLOSED,
            start_event_time=timezone.now(),
            end_event_time=timezone.now(),
            notice=False,
        )
        event = self._persist_event(policy, alert, level="warning")
        mocker.patch.object(LogPolicyScan, "send_notice", return_value=(True, {"result": True}))

        LogPolicyScan(policy).notice([event])

        event.refresh_from_db()
        alert.refresh_from_db()
        assert event.notified is True
        assert alert.notice is False

    def test_retry_does_not_resend_event_already_notified_before_alert_closed(self, mocker):
        policy = _make_policy(notice=True, notice_users=["u1"])
        alert = Alert.objects.create(
            id="a-notified-before-close",
            policy=policy,
            source_id="s",
            level="warning",
            status=AlertConstants.STATUS_NEW,
            start_event_time=timezone.now(),
            notice=False,
        )
        event = self._persist_event(policy, alert, level="warning")

        def send_then_close(*args, **kwargs):
            Alert.objects.filter(id=alert.id).update(
                status=AlertConstants.STATUS_CLOSED,
                notice=False,
            )
            return True, {"result": True}

        send = mocker.patch.object(LogPolicyScan, "send_notice", side_effect=send_then_close)
        scan = LogPolicyScan(policy)
        scan.notice([event])
        retry_event = Event.objects.select_related("alert").get(id=event.id)

        scan.notice([retry_event])

        send.assert_called_once()

    def test_stale_event_copy_does_not_resend_after_success(self, mocker):
        policy = _make_policy(notice=True, notice_users=["u1"])
        alert = Alert.objects.create(
            id="a-stale-notice",
            policy=policy,
            source_id="s",
            level="warning",
            status=AlertConstants.STATUS_NEW,
            start_event_time=timezone.now(),
            notice=False,
        )
        event = self._persist_event(policy, alert, level="warning")
        first_copy = Event.objects.select_related("alert").get(id=event.id)
        stale_copy = Event.objects.select_related("alert").get(id=event.id)
        send = mocker.patch.object(LogPolicyScan, "send_notice", return_value=(True, {"result": True}))
        scan = LogPolicyScan(policy)

        scan.notice([first_copy])
        scan.notice([stale_copy])

        send.assert_called_once()

    def test_retry_resends_event_whose_notice_failed(self, mocker):
        policy = _make_policy(notice=True, notice_users=["u1"])
        alert = Alert.objects.create(
            id="a-notice-retry",
            policy=policy,
            source_id="s",
            level="warning",
            status=AlertConstants.STATUS_NEW,
            start_event_time=timezone.now(),
            notice=False,
        )
        event = self._persist_event(policy, alert, level="warning")
        send = mocker.patch.object(
            LogPolicyScan,
            "send_notice",
            side_effect=[
                (False, {"result": False}),
                (True, {"result": True}),
            ],
        )
        scan = LogPolicyScan(policy)

        scan.notice([event])
        retry_event = Event.objects.select_related("alert").get(id=event.id)
        scan.notice([retry_event])

        assert send.call_count == 2
        retry_event.refresh_from_db()
        assert retry_event.notified is True


class TestRun:
    def test_retrying_same_scan_does_not_duplicate_event(self, mocker):
        scan_time = timezone.datetime(2026, 7, 24, tzinfo=timezone.utc)
        policy = _make_policy(last_run_time=scan_time)
        scan = LogPolicyScan(policy, scan_time=scan_time)
        mocker.patch.object(
            scan.vlogs_api,
            "query",
            side_effect=[
                [{"_msg": "err"}],
                [{"total_count": "2"}],
                [{"_msg": "err"}],
                [{"total_count": "2"}],
            ],
        )

        scan.run()
        first_event_id = Event.objects.get(policy=policy).id

        scan.run()

        assert list(Event.objects.filter(policy=policy).values_list("id", flat=True)) == [first_event_id]

    def test_retrying_from_same_cursor_is_idempotent_when_safe_time_moves(self, mocker):
        cursor = timezone.datetime(2026, 7, 24, tzinfo=timezone.utc)
        policy = _make_policy(last_run_time=cursor)
        first_scan = LogPolicyScan(
            policy,
            scan_time=cursor + timezone.timedelta(minutes=2),
            window_start=int(cursor.timestamp()) - 180,
            window_end=int(cursor.timestamp()) + 120,
            execution_key=cursor.isoformat(),
        )
        retry_scan = LogPolicyScan(
            policy,
            scan_time=cursor + timezone.timedelta(minutes=3),
            window_start=int(cursor.timestamp()) - 120,
            window_end=int(cursor.timestamp()) + 180,
            execution_key=cursor.isoformat(),
        )
        for scan in (first_scan, retry_scan):
            mocker.patch.object(
                scan.vlogs_api,
                "query",
                side_effect=[[{"_msg": "err"}], [{"total_count": "2"}]],
            )

        first_scan.run()
        retry_scan.run()

        assert Event.objects.filter(policy=policy).count() == 1
        event = Event.objects.get(policy=policy)
        assert event.event_time == retry_scan.scan_time
        assert event.value == 2
        assert event.content == "报错: 检测到 2 条匹配日志"

    def test_retry_reuses_legacy_uuid_event_created_before_upgrade(self, mocker):
        cursor = timezone.datetime(2026, 7, 24, tzinfo=timezone.utc)
        scan_time = cursor + timezone.timedelta(minutes=5)
        policy = _make_policy(last_run_time=cursor)
        alert = Alert.objects.create(
            id="legacy-alert",
            policy=policy,
            source_id=f"policy_{policy.id}",
            level="warning",
            status=AlertConstants.STATUS_NEW,
            start_event_time=scan_time,
        )
        legacy_event = Event.objects.create(
            id="legacy-random-uuid",
            policy=policy,
            alert=alert,
            source_id=f"policy_{policy.id}",
            event_time=scan_time,
            level="warning",
            content="旧版本已提交",
        )
        scan = LogPolicyScan(
            policy,
            scan_time=scan_time,
            window_start=int(cursor.timestamp()),
            window_end=int(scan_time.timestamp()),
            execution_key="new-version-execution",
            cursor_time=cursor,
        )
        mocker.patch.object(
            scan.vlogs_api,
            "query",
            side_effect=[[{"_msg": "err"}], [{"total_count": "2"}]],
        )

        scan.run()

        assert list(Event.objects.filter(policy=policy).values_list("id", flat=True)) == [legacy_event.id]

    def test_first_retry_reuses_legacy_uuid_event_when_safe_time_moves(self, mocker):
        first_scan_time = timezone.datetime(2026, 7, 24, tzinfo=timezone.utc)
        retry_scan_time = first_scan_time + timezone.timedelta(minutes=1)
        policy = _make_policy(last_run_time=None)
        alert = Alert.objects.create(
            id="legacy-first-alert",
            policy=policy,
            source_id=f"policy_{policy.id}",
            level="warning",
            status=AlertConstants.STATUS_NEW,
            start_event_time=first_scan_time,
        )
        legacy_event = Event.objects.create(
            id="legacy-first-random-uuid",
            policy=policy,
            alert=alert,
            source_id=f"policy_{policy.id}",
            event_time=first_scan_time,
            level="warning",
            content="旧版本首次扫描已提交",
        )
        scan = LogPolicyScan(
            policy,
            scan_time=retry_scan_time,
            execution_key="new-version-first-execution",
            cursor_time=None,
        )
        mocker.patch.object(
            scan.vlogs_api,
            "query",
            side_effect=[[{"_msg": "err"}], [{"total_count": "2"}]],
        )

        scan.run()

        assert list(Event.objects.filter(policy=policy).values_list("id", flat=True)) == [legacy_event.id]

    def test_keyword_run_full_flow(self, mocker):
        policy = _make_policy(notice=False)
        scan = LogPolicyScan(policy)
        mocker.patch.object(
            scan.vlogs_api,
            "query",
            side_effect=[[{"_msg": "err"}], [{"total_count": "2"}]],
        )
        scan.run()
        assert Alert.objects.filter(policy=policy).count() == 1
        assert Event.objects.filter(policy=policy).count() == 1

    def test_unknown_alert_type_returns_without_events(self):
        policy = _make_policy(alert_type="weird")
        LogPolicyScan(policy).run()
        assert Alert.objects.filter(policy=policy).count() == 0

    def test_no_events_no_alerts(self, mocker):
        policy = _make_policy()
        scan = LogPolicyScan(policy)
        mocker.patch.object(scan.vlogs_api, "query", return_value=[])
        scan.run()
        assert Alert.objects.filter(policy=policy).count() == 0

    def test_run_with_notice_calls_notice(self, mocker):
        policy = _make_policy(notice=True, notice_users=["u1"])
        scan = LogPolicyScan(policy)
        mocker.patch.object(
            scan.vlogs_api,
            "query",
            side_effect=[[{"_msg": "err"}], [{"total_count": "2"}]],
        )
        notice = mocker.patch.object(scan, "notice")
        scan.run()
        notice.assert_called_once()

    def test_run_propagates_detection_error(self, mocker):
        policy = _make_policy()
        scan = LogPolicyScan(policy)
        mocker.patch.object(scan.vlogs_api, "query", side_effect=RuntimeError("vm"))
        with pytest.raises(RuntimeError):
            scan.run()
