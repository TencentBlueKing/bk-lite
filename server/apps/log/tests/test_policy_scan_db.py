"""apps/log/tasks/services/policy_scan.py 真实 DB 行为测试。

外部边界 mock：
- VictoriaMetricsAPI 查询（vlogs_api.query）—— 返回真实形态假数据
- SystemMgmtUtils.send_msg_with_channel —— 通知通道
- S3JSONField._upload_to_s3 —— MinIO 上传，返回假路径

DB（Policy/Alert/Event/AlertSnapshot）走真实，断言落库副作用。
"""
from concurrent.futures import ThreadPoolExecutor
from copy import deepcopy
from itertools import count
from threading import Barrier
from threading import Event as ThreadEvent
from threading import Lock

import pytest
from django.db import close_old_connections, connection
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
                [{"total_count": "7"}],
                [{"_msg": "error A"}, {"_msg": "error B"}],
            ],
        )
        events = scan.keyword_alert_detection()
        assert len(events) == 1
        ev = events[0]
        assert ev["source_id"] == f"policy_{policy.id}"
        assert ev["value"] == 7
        assert ev["level"] == "warning"
        assert "7 条匹配日志" in ev["content"]
        assert ev["raw_data"] == [{"message": "error A"}, {"message": "error B"}]

    def test_empty_query_returns_no_events(self):
        policy = _make_policy(alert_condition={"query": ""})
        events = LogPolicyScan(policy).keyword_alert_detection()
        assert events == []

    def test_no_logs_returns_empty(self, mocker):
        policy = _make_policy()
        scan = LogPolicyScan(policy)
        mocker.patch.object(scan.vlogs_api, "query", return_value=[])
        assert scan.keyword_alert_detection() == []

    def test_count_zero_does_not_fall_back_to_sample_length(self, mocker):
        policy = _make_policy()
        scan = LogPolicyScan(policy)
        mocker.patch.object(
            scan.vlogs_api,
            "query",
            side_effect=[[{"total_count": "0"}], [{"_msg": "x"}]],
        )
        assert scan.keyword_alert_detection() == []

    def test_keyword_snapshot_freezes_jump_query(self, mocker):
        policy = _make_policy(alert_condition={"query": "error", "limit": 3})
        scan = LogPolicyScan(policy, window_start=100, window_end=400)
        mocker.patch.object(
            scan.vlogs_api,
            "query",
            side_effect=[[{"total_count": "2"}], [{"_msg": "error A"}]],
        )
        _install_memory_json_storage(mocker)
        events = scan.keyword_alert_detection()
        persisted = scan.create_events(events)[0]
        snapshot = AlertSnapshot.objects.get(alert=persisted.alert)
        event_snapshot = next(item for item in snapshot.snapshots if item.get("event_id") == persisted.id)
        assert events[0]["jump_query"]["query"] == "error"
        assert events[0]["jump_query"]["window_start"] == 100
        assert events[0]["jump_query"]["window_end"] == 400
        assert event_snapshot["jump_query"] == events[0]["jump_query"]

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
    def test_group_source_id_stays_within_storage_limit(self, mocker):
        policy = _make_policy(
            alert_type="aggregate",
            alert_name="${url} 聚合",
            alert_condition={
                "query": "*",
                "group_by": ["url"],
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
            return_value=[{"url": f"https://example.com/{'x' * 200}", "count__msg": "9"}],
        )

        event = scan.aggregate_alert_detection()[0]

        assert len(event["source_id"]) <= 100
        assert event["source_id"].startswith(f"policy_{policy.id}_g2_")
        assert "source_id_aliases" not in event

        persisted_event = scan.create_events([event])[0]
        assert persisted_event.source_id == event["source_id"]
        assert persisted_event.alert.source_id == event["source_id"]
        assert AlertSnapshot.objects.get(alert=persisted_event.alert).source_id == event["source_id"]

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
        assert events[0]["source_id"].startswith(f"policy_{policy.id}_g2_")
        assert events[0]["source_id_aliases"] == [f"policy_{policy.id}_host=h1"]

    def test_ambiguous_legacy_group_keys_have_distinct_source_ids(self, mocker):
        policy = _make_policy(
            alert_type="aggregate",
            alert_name="歧义分组",
            alert_condition={
                "query": "*",
                "group_by": ["a", "b"],
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
            return_value=[
                {"a": "x, b=y", "b": "z", "count__msg": "9"},
                {"a": "x", "b": "y, b=z", "count__msg": "8"},
            ],
        )

        events = scan.aggregate_alert_detection()

        assert events[0]["source_id"] != events[1]["source_id"]
        assert events[0]["source_id_aliases"] == events[1]["source_id_aliases"]

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

    def test_aggregate_samples_capped_and_snapshot_has_jump_query(self, mocker):
        policy = _make_policy(
            alert_type="aggregate",
            alert_name="聚合",
            alert_condition={
                "query": "level:error",
                "group_by": ["service"],
                "limit": 50,
                "rule": {
                    "mode": "and",
                    "conditions": [{"func": "count", "field": "_msg", "op": ">", "value": 1}],
                },
            },
        )
        scan = LogPolicyScan(policy, window_start=100, window_end=400)
        mocker.patch.object(
            scan.vlogs_api,
            "query",
            side_effect=[
                [{"service": "order", "count__msg": "12"}],
                [{"_msg": f"line-{index}"} for index in range(12)],
            ],
        )
        _install_memory_json_storage(mocker)
        events = scan.aggregate_alert_detection()
        samples = events[0]["raw_data"]["samples"]
        assert len(samples) == 10
        assert samples[0]["message"] == "line-0"
        assert events[0]["jump_query"] == {
            "query": 'level:error AND service:="order"',
            "window_start": 100,
            "window_end": 400,
        }
        persisted = scan.create_events(events)[0]
        snapshot = AlertSnapshot.objects.get(alert=persisted.alert)
        event_snapshot = next(item for item in snapshot.snapshots if item.get("event_id") == persisted.id)
        assert event_snapshot["jump_query"] == events[0]["jump_query"]
        assert len(event_snapshot["raw_data"]["samples"]) == 10

    def test_aggregate_event_persists_condition_results(self, mocker):
        policy = _make_policy(
            alert_type="aggregate",
            alert_name="条件",
            alert_condition={
                "query": "level:error",
                "group_by": [],
                "rule": {
                    "mode": "and",
                    "conditions": [{"func": "count", "field": "_msg", "op": ">", "value": 1}],
                },
            },
        )
        scan = LogPolicyScan(policy, window_start=100, window_end=400)
        mocker.patch.object(scan.vlogs_api, "query", return_value=[{"count__msg": "9"}])
        _install_memory_json_storage(mocker)
        events = scan.aggregate_alert_detection()
        matched = events[0]["raw_data"]["aggregate_result"]["conditions"][0]
        assert matched["func"] == "count"
        assert matched["matched"] is True
        assert matched["current"] == 9
        persisted = scan.create_events(events)[0]
        raw = EventRawData.objects.get(event=persisted)
        assert raw.data["aggregate_result"]["conditions"][0]["matched"] is True

    def test_count_below_one_persists_normal_event_and_ignores_no_data(self, mocker):
        policy = _make_policy(
            alert_type="aggregate",
            alert_level="warning",
            alert_name="断流",
            alert_condition={
                "query": "*",
                "group_by": [],
                "no_data": {"enabled": True, "level": "error"},
                "rule": {
                    "mode": "and",
                    "conditions": [{"func": "count", "field": "_msg", "op": "<", "value": 1}],
                },
            },
        )
        scan = LogPolicyScan(policy, window_start=100, window_end=400)

        def fake_query(query, start, end, limit=10):
            if "stats" in query:
                return [{"count__msg": "0"}]
            return []

        mocker.patch.object(scan.vlogs_api, "query", side_effect=fake_query)
        _install_memory_json_storage(mocker)
        events = scan.aggregate_alert_detection()
        assert len(events) == 1
        persisted = scan.create_events(events)[0]
        assert persisted.level == "warning"
        assert persisted.value == 0
        assert persisted.content == "断流"
        assert not persisted.source_id.endswith(":no_data")
        assert persisted.alert.source_id == persisted.source_id
        raw = EventRawData.objects.get(event=persisted)
        assert raw.data["aggregate_result"].get("no_data") is not True
        assert raw.data["aggregate_result"]["count"] == 0

    def test_no_data_switch_off_persists_nothing(self, mocker):
        policy = _make_policy(
            alert_type="aggregate",
            alert_name="断流",
            alert_condition={
                "query": "*",
                "group_by": [],
                "no_data": {"enabled": False},
                "rule": {
                    "mode": "and",
                    "conditions": [{"func": "count", "field": "_msg", "op": ">", "value": 1}],
                },
            },
        )
        scan = LogPolicyScan(policy, window_start=100, window_end=400)
        starts = []

        def fake_query(query, start, end, limit=10):
            starts.append(start)
            return []

        mocker.patch.object(scan.vlogs_api, "query", side_effect=fake_query)
        assert scan.aggregate_alert_detection() == []
        assert starts == [100]
        assert Alert.objects.filter(policy=policy).count() == 0


def _install_memory_json_storage(mocker):
    """覆盖 autouse 的空回读，让快照条目可以按写入内容断言。"""
    object_store = {}
    object_counter = count()

    def configure(field, prefix):
        def upload(instance, value):
            path = f"{prefix}-{next(object_counter)}.json.gz"
            object_store[path] = deepcopy(value)
            return path

        def load(path):
            return deepcopy(object_store[path])

        mocker.patch.object(field, "_upload_to_s3", side_effect=upload)
        mocker.patch.object(field, "_load_from_s3", side_effect=load)
        mocker.patch.object(field, "_minio_storage", mocker.MagicMock())

    configure(EventRawData._meta.get_field("data"), "raw")
    configure(AlertSnapshot._meta.get_field("snapshots"), "snapshot")


class TestCreateEvents:
    def test_group_identity_upgrade_reuses_legacy_active_alert(self, mocker):
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
        legacy_source_id = f"policy_{policy.id}_host=h1"
        legacy_alert = Alert.objects.create(
            id="legacy-group-alert",
            policy=policy,
            source_id=legacy_source_id,
            level="warning",
            value=1,
            content="旧告警",
            status=AlertConstants.STATUS_NEW,
            start_event_time=timezone.now(),
            end_event_time=timezone.now(),
        )
        scan = LogPolicyScan(policy)
        mocker.patch.object(scan.vlogs_api, "query", return_value=[{"host": "h1", "count__msg": "9"}])
        event = scan.aggregate_alert_detection()[0]

        created_events = scan.create_events([event])

        assert Alert.objects.filter(policy=policy).count() == 1
        assert created_events[0].alert_id == legacy_alert.id
        legacy_alert.refresh_from_db()
        assert legacy_alert.source_id == legacy_source_id

    def test_new_safe_group_keeps_legacy_alert_identity_for_rollback_handoff(self, mocker):
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
        scan_time = timezone.now()
        new_scan = LogPolicyScan(policy, scan_time=scan_time, execution_key="new-worker")
        mocker.patch.object(new_scan.vlogs_api, "query", return_value=[{"host": "h1", "count__msg": "9"}])
        new_event = new_scan.create_events(new_scan.aggregate_alert_detection())[0]
        legacy_source_id = f"policy_{policy.id}_host=h1"

        assert new_event.source_id.startswith(f"policy_{policy.id}_g2_")
        assert new_event.alert.source_id == legacy_source_id
        assert AlertSnapshot.objects.get(alert=new_event.alert).source_id == legacy_source_id

        old_scan = LogPolicyScan(
            policy,
            scan_time=scan_time + timezone.timedelta(minutes=1),
            execution_key="old-worker",
        )
        old_event = old_scan.create_events(
            [{"source_id": legacy_source_id, "level": "warning", "content": "旧 worker 命中", "value": 10, "raw_data": []}]
        )[0]

        assert old_event.alert_id == new_event.alert_id
        assert Alert.objects.filter(policy=policy).count() == 1

    def test_grouped_alias_claim_uses_policy_row_lock(self, mocker):
        policy = _make_policy(alert_type="aggregate")
        lock = mocker.spy(Policy.objects, "select_for_update")
        source_id = f"policy_{policy.id}_g2_deadbeef"

        LogPolicyScan(policy).create_events(
            [
                {
                    "source_id": source_id,
                    "source_id_aliases": [f"policy_{policy.id}_host=h1"],
                    "level": "warning",
                    "content": "命中",
                    "value": 1,
                    "raw_data": [],
                }
            ]
        )

        lock.assert_called_once_with()

    def test_ambiguous_legacy_alias_is_claimed_by_only_one_new_group(self, mocker):
        policy = _make_policy(
            alert_type="aggregate",
            alert_name="歧义分组",
            alert_condition={
                "query": "*",
                "group_by": ["a", "b"],
                "rule": {
                    "mode": "and",
                    "conditions": [{"func": "count", "field": "_msg", "op": ">", "value": 2}],
                },
            },
        )
        legacy_source_id = f"policy_{policy.id}_a=x, b=y, b=z"
        legacy_alert = Alert.objects.create(
            id="ambiguous-legacy-alert",
            policy=policy,
            source_id=legacy_source_id,
            level="warning",
            value=1,
            content="旧告警",
            status=AlertConstants.STATUS_NEW,
            start_event_time=timezone.now(),
            end_event_time=timezone.now(),
        )
        scan = LogPolicyScan(policy)
        mocker.patch.object(
            scan.vlogs_api,
            "query",
            return_value=[
                {"a": "x, b=y", "b": "z", "count__msg": "9"},
                {"a": "x", "b": "y, b=z", "count__msg": "8"},
            ],
        )

        created_events = scan.create_events(scan.aggregate_alert_detection())

        assert Alert.objects.filter(policy=policy).count() == 2
        assert len({event.alert_id for event in created_events}) == 2
        assert legacy_alert.id in {event.alert_id for event in created_events}
        assert len({event.source_id for event in created_events}) == 2
        assert Alert.objects.filter(policy=policy, source_id=legacy_source_id).count() == 1

    def test_legacy_alias_claim_persists_across_scans(self, mocker):
        policy = _make_policy(
            alert_type="aggregate",
            alert_name="歧义分组",
            alert_condition={
                "query": "*",
                "group_by": ["a", "b"],
                "rule": {
                    "mode": "and",
                    "conditions": [{"func": "count", "field": "_msg", "op": ">", "value": 2}],
                },
            },
        )
        first_scan_time = timezone.now()
        legacy_source_id = f"policy_{policy.id}_a=x, b=y, b=z"
        legacy_alert = Alert.objects.create(
            id="persisted-legacy-claim",
            policy=policy,
            source_id=legacy_source_id,
            level="warning",
            value=1,
            content="旧告警",
            status=AlertConstants.STATUS_NEW,
            start_event_time=first_scan_time - timezone.timedelta(minutes=1),
            end_event_time=first_scan_time - timezone.timedelta(minutes=1),
        )
        legacy_event = Event.objects.create(
            id="persisted-legacy-event",
            policy=policy,
            source_id=legacy_source_id,
            alert=legacy_alert,
            event_time=first_scan_time - timezone.timedelta(minutes=1),
            value=1,
            level="warning",
            content="旧事件",
        )
        first_scan = LogPolicyScan(policy, scan_time=first_scan_time, execution_key="first-scan")
        mocker.patch.object(first_scan.vlogs_api, "query", return_value=[{"a": "x, b=y", "b": "z", "count__msg": "9"}])
        first_event = first_scan.create_events(first_scan.aggregate_alert_detection())[0]
        assert first_event.alert_id == legacy_alert.id
        assert first_event.id != legacy_event.id
        assert first_event.source_id.startswith(f"policy_{policy.id}_g2_")
        legacy_event.refresh_from_db()
        assert legacy_event.source_id == legacy_source_id

        second_scan = LogPolicyScan(
            policy,
            scan_time=first_scan.scan_time + timezone.timedelta(minutes=1),
            execution_key="second-scan",
        )
        mocker.patch.object(second_scan.vlogs_api, "query", return_value=[{"a": "x", "b": "y, b=z", "count__msg": "8"}])

        second_event = second_scan.create_events(second_scan.aggregate_alert_detection())[0]

        assert Alert.objects.filter(policy=policy).count() == 2
        assert second_event.alert_id != legacy_alert.id

    def test_snapshot_failure_keeps_legacy_event_discoverable_for_rollback(self, mocker):
        policy = _make_policy(alert_type="aggregate")
        scan_time = timezone.now()
        legacy_source_id = f"policy_{policy.id}_host=h1"
        legacy_alert = Alert.objects.create(
            id="rollback-legacy-alert",
            policy=policy,
            source_id=legacy_source_id,
            level="warning",
            value=1,
            content="旧告警",
            status=AlertConstants.STATUS_NEW,
            start_event_time=scan_time - timezone.timedelta(minutes=1),
            end_event_time=scan_time - timezone.timedelta(minutes=1),
        )
        legacy_event = Event.objects.create(
            id="rollback-legacy-event",
            policy=policy,
            source_id=legacy_source_id,
            alert=legacy_alert,
            event_time=scan_time - timezone.timedelta(minutes=1),
            value=1,
            level="warning",
            content="旧事件",
        )
        new_scan = LogPolicyScan(policy, scan_time=scan_time, execution_key="upgrade-scan")
        mocker.patch.object(new_scan, "_create_snapshots_for_alerts", side_effect=RuntimeError("snapshot down"))

        with pytest.raises(RuntimeError, match="snapshot down"):
            new_scan.create_events(
                [
                    {
                        "source_id": f"policy_{policy.id}_g2_deadbeef",
                        "source_id_aliases": [legacy_source_id],
                        "level": "warning",
                        "content": "新版本命中",
                        "value": 2,
                        "raw_data": [],
                    }
                ]
            )

        legacy_event.refresh_from_db()
        assert legacy_event.source_id == legacy_source_id
        assert Event.objects.filter(policy=policy).count() == 2

        rollback_event = LogPolicyScan(
            policy,
            scan_time=scan_time + timezone.timedelta(minutes=1),
            execution_key="rollback-scan",
        ).create_events(
            [
                {
                    "source_id": legacy_source_id,
                    "level": "warning",
                    "content": "回滚版本命中",
                    "value": 3,
                    "raw_data": [],
                }
            ]
        )[0]

        assert rollback_event.id == legacy_event.id
        assert rollback_event.alert_id == legacy_alert.id
        assert Event.objects.filter(policy=policy).count() == 2

    def test_primary_identity_reuses_alert_when_group_field_order_changes(self, mocker):
        policy = _make_policy(
            alert_type="aggregate",
            alert_name="字段顺序调整",
            alert_condition={
                "query": "*",
                "group_by": ["a", "b"],
                "rule": {
                    "mode": "and",
                    "conditions": [{"func": "count", "field": "_msg", "op": ">", "value": 2}],
                },
            },
        )
        first_scan_time = timezone.now()
        first_scan = LogPolicyScan(policy, scan_time=first_scan_time, execution_key="first-order")
        mocker.patch.object(first_scan.vlogs_api, "query", return_value=[{"a": "x", "b": "y", "count__msg": "9"}])
        first_event = first_scan.create_events(first_scan.aggregate_alert_detection())[0]
        Event.objects.bulk_create(
            [
                Event(
                    id=f"group-order-history-{index}",
                    policy=policy,
                    source_id=first_event.source_id,
                    alert=first_event.alert,
                    event_time=first_scan_time - timezone.timedelta(days=index + 1),
                    value=index,
                    level="warning",
                    content="历史事件",
                )
                for index in range(3)
            ]
        )

        policy.alert_condition = {**policy.alert_condition, "group_by": ["b", "a"]}
        second_scan = LogPolicyScan(
            policy,
            scan_time=first_scan.scan_time + timezone.timedelta(minutes=1),
            execution_key="second-order",
            cursor_time=first_scan_time,
        )
        mocker.patch.object(second_scan.vlogs_api, "query", return_value=[{"a": "x", "b": "y", "count__msg": "8"}])

        second_event = second_scan.create_events(second_scan.aggregate_alert_detection())[0]

        assert second_event.source_id == first_event.source_id
        assert second_event.alert_id == first_event.alert_id
        assert Alert.objects.filter(policy=policy).count() == 1

    @pytest.mark.skipif(not connection.features.has_select_for_update, reason="测试数据库不支持行锁")
    @pytest.mark.django_db(transaction=True)
    def test_concurrent_new_groups_claim_same_legacy_alias_only_once(self):
        policy = _make_policy(alert_type="aggregate")
        legacy_source_id = f"policy_{policy.id}_a=x, b=y, b=z"
        ready = Barrier(2)

        def create_once(suffix):
            close_old_connections()
            try:
                ready.wait(timeout=5)
                return LogPolicyScan(
                    Policy.objects.get(id=policy.id),
                    execution_key=f"claim-{suffix}",
                ).create_events(
                    [
                        {
                            "source_id": f"policy_{policy.id}_g2_{suffix}",
                            "source_id_aliases": [legacy_source_id],
                            "level": "warning",
                            "content": f"分组 {suffix}",
                            "value": 1,
                            "raw_data": [],
                        }
                    ]
                )[0]
            finally:
                close_old_connections()

        with ThreadPoolExecutor(max_workers=2) as executor:
            created_events = list(executor.map(create_once, ["first", "second"]))

        assert len({event.alert_id for event in created_events}) == 2
        assert Alert.objects.filter(policy=policy).count() == 2
        assert Alert.objects.filter(policy=policy, source_id=legacy_source_id).count() == 1

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

    def test_new_alert_snapshots_freeze_query_clue_not_live_policy(self, mocker):
        scan_time = timezone.datetime(2026, 9, 15, 8, 0, tzinfo=timezone.utc)
        policy = _make_policy(
            name="frozen-clue",
            alert_condition={"query": "error AND host:web-1"},
            log_groups=["group-a"],
            last_run_time=scan_time,
        )
        raw_field = EventRawData._meta.get_field("data")
        snapshot_field = AlertSnapshot._meta.get_field("snapshots")
        object_store = {}
        object_counter = count()

        def configure_memory_storage(field, prefix):
            def upload(instance, value):
                path = f"{prefix}-{next(object_counter)}.json.gz"
                object_store[path] = deepcopy(value)
                return path

            def load(path):
                return deepcopy(object_store[path])

            mocker.patch.object(field, "_upload_to_s3", side_effect=upload)
            mocker.patch.object(field, "_load_from_s3", side_effect=load)
            mocker.patch.object(field, "_minio_storage", mocker.MagicMock())

        configure_memory_storage(raw_field, "raw")
        configure_memory_storage(snapshot_field, "snapshot")

        scan = LogPolicyScan(policy, scan_time=scan_time)
        event_objs = scan.create_events(
            [
                {
                    "source_id": f"policy_{policy.id}",
                    "level": "warning",
                    "content": "命中",
                    "value": 5,
                    "raw_data": [{"_msg": "error on web-1"}],
                }
            ]
        )
        policy.alert_condition = {"query": "error AND host:web-2"}
        policy.log_groups = ["group-b"]
        policy.save(update_fields=["alert_condition", "log_groups"])

        snapshot = AlertSnapshot.objects.get(alert=event_objs[0].alert)
        event_snapshot = next(item for item in snapshot.snapshots if item.get("event_id") == event_objs[0].id)
        clue = event_snapshot["query_clue"]
        assert clue["policy_id"] == policy.id
        assert clue["policy_name"] == "frozen-clue"
        assert clue["log_groups"] == ["group-a"]
        assert clue["alert_condition"] == {"query": "error AND host:web-1"}
        assert clue["alert_type"] == "keyword"
        assert clue["period"] == {"type": "min", "value": 5}
        assert clue["window_end"] == int(scan_time.timestamp())
        assert event_snapshot["raw_data"] == [{"_msg": "error on web-1"}]
        assert "jump_query" not in event_snapshot

    def test_snapshot_lifts_jump_query_from_event(self, mocker):
        scan_time = timezone.datetime(2026, 9, 15, 8, 0, tzinfo=timezone.utc)
        policy = _make_policy(name="jump-snapshot", last_run_time=scan_time)
        snapshot_field = AlertSnapshot._meta.get_field("snapshots")
        raw_field = EventRawData._meta.get_field("data")
        object_store = {}
        object_counter = count()

        def configure_memory_storage(field, prefix):
            def upload(instance, value):
                path = f"{prefix}-{next(object_counter)}.json.gz"
                object_store[path] = deepcopy(value)
                return path

            def load(path):
                return deepcopy(object_store[path])

            mocker.patch.object(field, "_upload_to_s3", side_effect=upload)
            mocker.patch.object(field, "_load_from_s3", side_effect=load)
            mocker.patch.object(field, "_minio_storage", mocker.MagicMock())

        configure_memory_storage(raw_field, "raw")
        configure_memory_storage(snapshot_field, "snapshot")
        jump_query = {"query": 'level:error AND service:="order"', "window_start": 100, "window_end": 400}
        scan = LogPolicyScan(policy, scan_time=scan_time, window_start=100, window_end=400)
        event_objs = scan.create_events(
            [
                {
                    "source_id": f"policy_{policy.id}",
                    "level": "warning",
                    "content": "命中",
                    "value": 5,
                    "raw_data": [{"message": "order exploded"}],
                    "jump_query": jump_query,
                }
            ]
        )
        snapshot = AlertSnapshot.objects.get(alert=event_objs[0].alert)
        event_snapshot = next(item for item in snapshot.snapshots if item.get("event_id") == event_objs[0].id)
        assert event_snapshot["jump_query"] == jump_query
        assert event_snapshot["raw_data"] == [{"message": "order exploded"}]

    def test_new_alert_snapshots_policy_handlers(self):
        policy = _make_policy(handlers=[7, 8])
        first_scan = LogPolicyScan(policy)
        first_scan.create_events(
            [
                {
                    "source_id": f"policy_{policy.id}",
                    "level": "warning",
                    "content": "命中",
                    "value": 5,
                    "raw_data": [{"_msg": "x"}],
                }
            ]
        )
        alert = Alert.objects.get(policy=policy)
        policy.handlers = [9]
        policy.save(update_fields=["handlers"])
        LogPolicyScan(policy).create_events(
            [
                {
                    "source_id": f"policy_{policy.id}",
                    "level": "warning",
                    "content": "再次命中",
                    "value": 6,
                    "raw_data": [{"_msg": "y"}],
                }
            ]
        )
        alert.refresh_from_db()

        assert alert.handlers == [7, 8]
        assert Alert.objects.filter(policy=policy).count() == 1

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

    def test_active_alert_level_only_rises_across_windows(self):
        policy = _make_policy()
        source_id = f"policy_{policy.id}"
        base = timezone.datetime(2026, 10, 29, tzinfo=timezone.utc)

        def hit(minute, level, value, cursor):
            scan = LogPolicyScan(
                policy,
                scan_time=base + timezone.timedelta(minutes=minute),
                cursor_time=cursor,
            )
            event = scan.create_events(
                [
                    {
                        "source_id": source_id,
                        "level": level,
                        "content": level,
                        "value": value,
                        "raw_data": [],
                    }
                ]
            )[0]
            event.refresh_from_db()
            event.alert.refresh_from_db()
            return event

        first = hit(0, "warning", 12, base - timezone.timedelta(minutes=5))
        assert first.level == "warning"
        assert first.alert.level == "warning"
        Alert.objects.filter(id=first.alert_id).update(notice=True)

        second = hit(5, "error", 60, base)
        assert second.id != first.id
        assert second.level == "error"
        assert second.alert_id == first.alert_id
        assert second.alert.level == "error"
        assert second.alert.notice is False
        Alert.objects.filter(id=second.alert_id).update(notice=True)

        third = hit(10, "critical", 300, base + timezone.timedelta(minutes=5))
        assert third.level == "critical"
        assert third.alert.level == "critical"
        assert third.alert.notice is False
        Alert.objects.filter(id=third.alert_id).update(notice=True)

        fourth = hit(15, "error", 60, base + timezone.timedelta(minutes=10))
        assert fourth.level == "error"
        assert fourth.alert.level == "critical"
        assert fourth.alert.notice is True
        assert fourth.alert.value == 60
        assert fourth.alert.content == "error"
        assert Alert.objects.filter(policy=policy).count() == 1
        assert Event.objects.filter(policy=policy).count() == 4

    def test_same_execution_downgrade_keeps_alert_level_and_notice(self):
        scan_time = timezone.datetime(2026, 10, 29, tzinfo=timezone.utc)
        policy = _make_policy(notice=True, notice_users=["u1"])
        source_id = f"policy_{policy.id}"
        first_scan = LogPolicyScan(policy, scan_time=scan_time, execution_key="same-window")
        first_event = first_scan.create_events([{"source_id": source_id, "level": "critical", "content": "高", "value": 300, "raw_data": []}])[0]
        Event.objects.filter(id=first_event.id).update(
            notified=True,
            notice_result=[{"result": True}],
            notice_retry_count=1,
        )
        Alert.objects.filter(id=first_event.alert_id).update(notice=True)

        retry_scan = LogPolicyScan(
            policy,
            scan_time=scan_time + timezone.timedelta(minutes=1),
            execution_key="same-window",
        )
        retry_event = retry_scan.create_events([{"source_id": source_id, "level": "warning", "content": "回落", "value": 12, "raw_data": []}])[0]
        retry_event.refresh_from_db()
        retry_event.alert.refresh_from_db()
        assert retry_event.id == first_event.id
        assert retry_event.level == "warning"
        assert retry_event.notified is True
        assert retry_event.notice_result == [{"result": True}]
        assert retry_event.notice_retry_count == 1
        assert retry_event.content == "回落"
        assert retry_event.alert.level == "critical"
        assert retry_event.alert.notice is True
        assert retry_event.alert.value == 12

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

    def test_event_and_alert_locks_do_not_require_for_update_of(self, mocker):
        scan_time = timezone.datetime(2026, 7, 24, tzinfo=timezone.utc)
        policy = _make_policy(notice=True, notice_users=["u1"])
        source_id = f"policy_{policy.id}"
        first_scan = LogPolicyScan(policy, scan_time=scan_time, execution_key="same-execution")
        event = first_scan.create_events([{"source_id": source_id, "level": "warning", "content": "first", "value": 1, "raw_data": []}])[0]
        mocker.patch.object(connection.features, "has_select_for_update_of", False)

        retry_scan = LogPolicyScan(
            policy,
            scan_time=scan_time + timezone.timedelta(minutes=1),
            execution_key="same-execution",
        )
        retry_event = retry_scan.create_events([{"source_id": source_id, "level": "warning", "content": "retry", "value": 2, "raw_data": []}])[0]
        send = mocker.patch.object(LogPolicyScan, "send_notice", return_value=(True, {"result": True}))

        retry_scan.notice([retry_event])

        send.assert_called_once()
        event.refresh_from_db()
        assert event.event_time == retry_scan.scan_time
        assert event.notified is True

    def test_late_same_execution_cannot_overwrite_newer_event(self, mocker):
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

        newer_scan.create_events([{"source_id": source_id, "level": "warning", "content": "newer", "value": 4, "raw_data": [{"version": 4}]}])
        snapshot_update = mocker.spy(older_scan, "_create_snapshots_for_alerts")
        older_result = older_scan.create_events(
            [{"source_id": source_id, "level": "warning", "content": "older", "value": 3, "raw_data": [{"version": 3}]}]
        )

        event = Event.objects.get(policy=policy)
        event.alert.refresh_from_db()
        assert older_result == []
        assert snapshot_update.call_args.args[0] == []
        assert event.event_time == newer_scan.scan_time
        assert event.content == "newer"
        assert event.value == 4
        assert event.alert.end_event_time == newer_scan.scan_time
        assert event.alert.content == "newer"
        assert event.alert.value == 4

    def test_same_execution_retry_does_not_modify_closed_alert(self, mocker):
        scan_time = timezone.datetime(2026, 7, 24, tzinfo=timezone.utc)
        policy = _make_policy()
        source_id = f"policy_{policy.id}"
        first_scan = LogPolicyScan(policy, scan_time=scan_time, execution_key="same-execution")
        event = first_scan.create_events([{"source_id": source_id, "level": "warning", "content": "first", "value": 1, "raw_data": []}])[0]
        closed_at = scan_time + timezone.timedelta(minutes=2)
        Alert.objects.filter(id=event.alert_id).update(
            status=AlertConstants.STATUS_CLOSED,
            end_event_time=closed_at,
            content="closed",
            notice=True,
        )

        retry_scan = LogPolicyScan(
            policy,
            scan_time=scan_time + timezone.timedelta(minutes=3),
            execution_key="same-execution",
        )
        snapshot_update = mocker.spy(retry_scan, "_create_snapshots_for_alerts")
        retry_result = retry_scan.create_events([{"source_id": source_id, "level": "critical", "content": "retry", "value": 2, "raw_data": []}])

        event.alert.refresh_from_db()
        assert retry_result == []
        assert snapshot_update.call_args.args[0] == []
        assert event.alert.status == AlertConstants.STATUS_CLOSED
        assert event.alert.end_event_time == closed_at
        assert event.alert.content == "closed"
        assert event.alert.level == "warning"
        assert event.alert.notice is True

    @pytest.mark.django_db(transaction=True)
    def test_same_execution_raw_data_update_deletes_previous_s3_object(self, mocker):
        scan_time = timezone.datetime(2026, 7, 24, tzinfo=timezone.utc)
        policy = _make_policy()
        source_id = f"policy_{policy.id}"
        raw_paths = iter(["raw-v1.json.gz", "raw-v2.json.gz"])

        def upload(instance, data):
            if isinstance(instance, EventRawData):
                return next(raw_paths)
            return f"snapshot-{instance.pk}.json.gz"

        mocker.patch("apps.core.fields.s3_json_field.S3JSONField._upload_to_s3", side_effect=upload)
        raw_field = EventRawData._meta.get_field("data")
        snapshot_field = AlertSnapshot._meta.get_field("snapshots")
        raw_storage = mocker.MagicMock()
        snapshot_storage = mocker.MagicMock()
        mocker.patch.object(raw_field, "_minio_storage", raw_storage)
        mocker.patch.object(snapshot_field, "_minio_storage", snapshot_storage)

        first_scan = LogPolicyScan(policy, scan_time=scan_time, execution_key="same-execution")
        retry_scan = LogPolicyScan(
            policy,
            scan_time=scan_time + timezone.timedelta(minutes=1),
            execution_key="same-execution",
        )
        first_scan.create_events([{"source_id": source_id, "level": "warning", "content": "first", "value": 1, "raw_data": [{"version": 1}]}])
        retry_scan.create_events([{"source_id": source_id, "level": "warning", "content": "retry", "value": 2, "raw_data": [{"version": 2}]}])

        raw_storage.delete.assert_called_once_with("raw-v1.json.gz")

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

    @pytest.mark.django_db(transaction=True)
    def test_concurrent_existing_event_cannot_be_overwritten_by_late_worker(self):
        cursor = timezone.datetime(2026, 7, 24, tzinfo=timezone.utc)
        policy = _make_policy(last_run_time=cursor)
        source_id = f"policy_{policy.id}"
        initial_scan = LogPolicyScan(
            policy,
            scan_time=cursor + timezone.timedelta(minutes=1),
            execution_key="same-execution",
            cursor_time=cursor,
        )
        initial_scan.create_events([{"source_id": source_id, "level": "warning", "content": "initial", "value": 1, "raw_data": []}])
        barrier = Barrier(2)

        class CoordinatedScan(LogPolicyScan):
            def _find_existing_events(self, event_ids, source_ids):
                existing = super()._find_existing_events(event_ids, source_ids)
                barrier.wait(timeout=5)
                return existing

        def update_once(scan_time, content, value):
            close_old_connections()
            try:
                return CoordinatedScan(
                    Policy.objects.get(id=policy.id),
                    scan_time=scan_time,
                    execution_key="same-execution",
                    cursor_time=cursor,
                ).create_events([{"source_id": source_id, "level": "warning", "content": content, "value": value, "raw_data": []}])
            finally:
                close_old_connections()

        with ThreadPoolExecutor(max_workers=2) as executor:
            futures = [
                executor.submit(update_once, cursor + timezone.timedelta(minutes=3), "older", 3),
                executor.submit(update_once, cursor + timezone.timedelta(minutes=4), "newer", 4),
            ]
            [future.result() for future in futures]

        event = Event.objects.get(policy=policy)
        event.alert.refresh_from_db()
        assert event.event_time == cursor + timezone.timedelta(minutes=4)
        assert event.content == "newer"
        assert event.value == 4
        assert event.alert.end_event_time == cursor + timezone.timedelta(minutes=4)
        assert event.alert.content == "newer"
        assert event.alert.value == 4

    @pytest.mark.django_db(transaction=True)
    def test_late_worker_cannot_regress_raw_data_or_snapshot_after_newer_commit(self, mocker):
        cursor = timezone.datetime(2026, 7, 24, tzinfo=timezone.utc)
        policy = _make_policy(last_run_time=cursor)
        source_id = f"policy_{policy.id}"
        raw_field = EventRawData._meta.get_field("data")
        snapshot_field = AlertSnapshot._meta.get_field("snapshots")
        object_store = {}
        object_counter = count()
        object_lock = Lock()

        def configure_memory_storage(field, prefix):
            def upload(instance, value):
                with object_lock:
                    path = f"{prefix}-{next(object_counter)}.json.gz"
                    object_store[path] = deepcopy(value)
                    return path

            def load(path):
                with object_lock:
                    return deepcopy(object_store[path])

            mocker.patch.object(field, "_upload_to_s3", side_effect=upload)
            mocker.patch.object(field, "_load_from_s3", side_effect=load)
            mocker.patch.object(field, "_minio_storage", mocker.MagicMock())

        configure_memory_storage(raw_field, "raw")
        configure_memory_storage(snapshot_field, "snapshot")

        initial_scan = LogPolicyScan(
            policy,
            scan_time=cursor + timezone.timedelta(minutes=1),
            execution_key="same-execution",
            cursor_time=cursor,
        )
        initial_scan.create_events(
            [
                {
                    "source_id": source_id,
                    "level": "warning",
                    "content": "initial",
                    "value": 1,
                    "raw_data": [{"version": 1}],
                }
            ]
        )

        older_snapshot_ready = ThreadEvent()
        release_older_snapshot = ThreadEvent()

        class CoordinatedScan(LogPolicyScan):
            def _create_snapshots_for_alerts(self, *args, **kwargs):
                if self.scan_time == cursor + timezone.timedelta(minutes=3):
                    older_snapshot_ready.set()
                    assert release_older_snapshot.wait(timeout=5)
                return super()._create_snapshots_for_alerts(*args, **kwargs)

        def update_older():
            close_old_connections()
            try:
                return CoordinatedScan(
                    Policy.objects.get(id=policy.id),
                    scan_time=cursor + timezone.timedelta(minutes=3),
                    execution_key="same-execution",
                    cursor_time=cursor,
                ).create_events(
                    [
                        {
                            "source_id": source_id,
                            "level": "warning",
                            "content": "older",
                            "value": 3,
                            "raw_data": [{"version": 3}],
                        }
                    ]
                )
            finally:
                close_old_connections()

        with ThreadPoolExecutor(max_workers=1) as executor:
            older_future = executor.submit(update_older)
            assert older_snapshot_ready.wait(timeout=5)
            newer_scan = LogPolicyScan(
                Policy.objects.get(id=policy.id),
                scan_time=cursor + timezone.timedelta(minutes=4),
                execution_key="same-execution",
                cursor_time=cursor,
            )
            newer_scan.create_events(
                [
                    {
                        "source_id": source_id,
                        "level": "warning",
                        "content": "newer",
                        "value": 4,
                        "raw_data": [{"version": 4}],
                    }
                ]
            )
            release_older_snapshot.set()
            older_future.result()

        event = Event.objects.get(policy=policy)
        raw_data = EventRawData.objects.get(event=event)
        snapshot = AlertSnapshot.objects.get(alert=event.alert)
        event_snapshot = next(item for item in snapshot.snapshots if item.get("event_id") == event.id)
        assert event.event_time == cursor + timezone.timedelta(minutes=4)
        assert event.content == "newer"
        assert raw_data.data == [{"version": 4}]
        assert event_snapshot["event_time"] == event.event_time.isoformat()
        assert event_snapshot["raw_data"] == [{"version": 4}]

    def test_stale_create_events_does_not_reset_successful_notification(self, mocker):
        scan_time = timezone.datetime(2026, 7, 24, tzinfo=timezone.utc)
        policy = _make_policy(notice=True, notice_users=["u1"])
        source_id = f"policy_{policy.id}"
        scan = LogPolicyScan(policy, scan_time=scan_time, execution_key="same-execution")
        event = scan.create_events([{"source_id": source_id, "level": "warning", "content": "first", "value": 1, "raw_data": []}])[0]
        stale_existing = scan._find_existing_events([event.id], [source_id])
        send = mocker.patch.object(LogPolicyScan, "send_notice", return_value=(True, {"result": True}))
        scan.notice([event])

        retry_scan = LogPolicyScan(
            policy,
            scan_time=scan_time + timezone.timedelta(minutes=1),
            execution_key="same-execution",
        )
        mocker.patch.object(retry_scan, "_find_existing_events", return_value=stale_existing)
        retry_event = retry_scan.create_events([{"source_id": source_id, "level": "warning", "content": "retry", "value": 2, "raw_data": []}])[0]
        retry_scan.notice([retry_event])

        retry_event.refresh_from_db()
        assert retry_event.notified is True
        send.assert_called_once()


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

    def test_create_notice_keeps_policy_notice_users_not_handlers(self, mocker):
        policy = _make_policy(notice_users=["u1"], notice_type_id=2, handlers=[99])
        scan = LogPolicyScan(policy)
        send = mocker.patch(
            "apps.log.tasks.services.policy_scan.SystemMgmtUtils.send_msg_with_channel",
            return_value={"result": True},
        )
        event = Event(id="e1", policy=policy, source_id="s", event_time=timezone.now(), level="warning", content="c")

        ok, _ = scan.send_notice(event)

        assert ok is True
        assert send.call_args.args[3] == ["u1"]
        assert 99 not in send.call_args.args[3]
        assert "99" not in send.call_args.args[3]

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
                [{"total_count": "2"}],
                [{"_msg": "err"}],
                [{"total_count": "2"}],
                [{"_msg": "err"}],
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
                side_effect=[[{"total_count": "2"}], [{"_msg": "err"}]],
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
            side_effect=[[{"total_count": "2"}], [{"_msg": "err"}]],
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
            side_effect=[[{"total_count": "2"}], [{"_msg": "err"}]],
        )

        scan.run()

        assert list(Event.objects.filter(policy=policy).values_list("id", flat=True)) == [legacy_event.id]

    def test_keyword_run_full_flow(self, mocker):
        policy = _make_policy(notice=False)
        scan = LogPolicyScan(policy)
        mocker.patch.object(
            scan.vlogs_api,
            "query",
            side_effect=[[{"total_count": "2"}], [{"_msg": "err"}]],
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
            side_effect=[[{"total_count": "2"}], [{"_msg": "err"}]],
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


def _aggregate_policy(**overrides):
    condition = {
        "query": "*",
        "group_by": ["host"],
        "rule": {
            "mode": "and",
            "conditions": [{"func": "count", "field": "_msg", "op": ">", "value": 2}],
            "recover_after": 2,
        },
    }
    data = dict(
        name="recover-policy",
        alert_type="aggregate",
        alert_name="${host} 聚合",
        alert_condition=condition,
        notice=False,
    )
    data.update(overrides)
    if "alert_condition" in overrides:
        data["alert_condition"] = overrides["alert_condition"]
    return _make_policy(**data)


def _run_aggregate(policy, mocker, scan_time, rows, execution_key, callbacks=None):
    scan = LogPolicyScan(policy, scan_time=scan_time, execution_key=execution_key)
    mocker.patch.object(scan, "_fetch_aggregate_samples", return_value={})
    mocker.patch.object(scan.vlogs_api, "query", return_value=rows)
    if callbacks is None:
        scan.run()
    else:
        with callbacks(execute=True):
            scan.run()
    return scan


class TestAggregateRecovery:
    def test_consecutive_misses_recover_then_retrigger_opens_a_new_alert(self, mocker, django_capture_on_commit_callbacks):
        channel = Channel.objects.create(
            name="告警中心",
            channel_type="nats",
            config={"method_name": "receive_alert_events"},
            description="",
        )
        policy = _aggregate_policy(notice=True, notice_type_id=channel.id, notice_type="nats")
        send = mocker.patch(
            "apps.log.services.alert_lifecycle_notify.SystemMgmtUtils.send_msg_with_channel",
            return_value={"result": True},
        )
        mocker.patch.object(LogPolicyScan, "notice", return_value=None)
        base = timezone.datetime(2026, 10, 29, 1, 0, tzinfo=timezone.utc)
        hit = [{"host": "a", "count__msg": "9"}]
        miss = [{"host": "a", "count__msg": "1"}]

        _run_aggregate(policy, mocker, base, hit, "w1", django_capture_on_commit_callbacks)
        alert = Alert.objects.get(policy=policy)
        assert alert.status == AlertConstants.STATUS_NEW
        assert alert.info_event_count == 0

        _run_aggregate(policy, mocker, base + timezone.timedelta(minutes=5), miss, "w2", django_capture_on_commit_callbacks)
        alert.refresh_from_db()
        assert alert.status == AlertConstants.STATUS_NEW
        assert alert.info_event_count == 1

        recovering = _run_aggregate(
            policy,
            mocker,
            base + timezone.timedelta(minutes=10),
            miss,
            "w3",
            django_capture_on_commit_callbacks,
        )
        alert.refresh_from_db()
        assert alert.status == AlertConstants.STATUS_RECOVERED
        assert alert.operator == ""
        assert alert.end_event_time == recovering.scan_time
        recovered_events = list(Event.objects.filter(alert=alert, action=Event.Action.RECOVERED))
        assert len(recovered_events) == 1
        assert recovered_events[0].value is None
        assert recovered_events[0].content == alert.content
        assert recovered_events[0].level == alert.level
        assert send.call_count == 1
        assert send.call_args.args[2]["events"][0]["action"] == "recovered"

        _run_aggregate(
            policy,
            mocker,
            base + timezone.timedelta(minutes=10),
            miss,
            "w3",
            django_capture_on_commit_callbacks,
        )
        alert.refresh_from_db()
        assert alert.status == AlertConstants.STATUS_RECOVERED
        assert Event.objects.filter(alert=alert, action=Event.Action.RECOVERED).count() == 1
        assert send.call_count == 1

        _run_aggregate(policy, mocker, base + timezone.timedelta(minutes=15), hit, "w4", django_capture_on_commit_callbacks)
        assert Alert.objects.filter(policy=policy, status=AlertConstants.STATUS_NEW).count() == 1
        assert Alert.objects.filter(policy=policy, status=AlertConstants.STATUS_RECOVERED).count() == 1
        assert Alert.objects.get(policy=policy, status=AlertConstants.STATUS_NEW).id != alert.id

    def test_failed_window_does_not_change_recovery_count(self, mocker):
        policy = _aggregate_policy()
        base = timezone.datetime(2026, 10, 29, 2, 0, tzinfo=timezone.utc)
        _run_aggregate(policy, mocker, base, [{"host": "a", "count__msg": "9"}], "ok")
        alert = Alert.objects.get(policy=policy)
        Alert.objects.filter(id=alert.id).update(info_event_count=1)

        scan = LogPolicyScan(policy, scan_time=base + timezone.timedelta(minutes=5), execution_key="fail")
        mocker.patch.object(scan.vlogs_api, "query", side_effect=RuntimeError("vm down"))
        with pytest.raises(RuntimeError):
            scan.run()
        alert.refresh_from_db()
        assert alert.info_event_count == 1
        assert alert.status == AlertConstants.STATUS_NEW

        frozen = LogPolicyScan(policy, scan_time=base + timezone.timedelta(minutes=10), execution_key="frozen")
        frozen.window_observed = True
        frozen.recovery_frozen = True
        frozen.last_detection_rows = [{"reason": "window_failed", "triggered": False}]
        frozen.reconcile_recoveries([])
        alert.refresh_from_db()
        assert alert.info_event_count == 1
        assert alert.status == AlertConstants.STATUS_NEW

    def test_missing_group_counts_as_a_miss(self, mocker, django_capture_on_commit_callbacks):
        policy = _aggregate_policy()
        base = timezone.datetime(2026, 10, 29, 3, 0, tzinfo=timezone.utc)
        _run_aggregate(policy, mocker, base, [{"host": "a", "count__msg": "9"}], "hit", django_capture_on_commit_callbacks)
        _run_aggregate(policy, mocker, base + timezone.timedelta(minutes=5), [], "gone", django_capture_on_commit_callbacks)
        alert = Alert.objects.get(policy=policy)
        assert alert.status == AlertConstants.STATUS_NEW
        assert alert.info_event_count == 1

    def test_policy_without_recover_after_never_recovers(self, mocker, django_capture_on_commit_callbacks):
        condition = {
            "query": "*",
            "group_by": ["host"],
            "rule": {
                "mode": "and",
                "conditions": [{"func": "count", "field": "_msg", "op": ">", "value": 2}],
            },
        }
        policy = _aggregate_policy(name="legacy-aggregate", alert_condition=condition)
        base = timezone.datetime(2026, 10, 29, 4, 0, tzinfo=timezone.utc)
        _run_aggregate(policy, mocker, base, [{"host": "a", "count__msg": "9"}], "hit", django_capture_on_commit_callbacks)
        _run_aggregate(policy, mocker, base + timezone.timedelta(minutes=5), [], "miss-1", django_capture_on_commit_callbacks)
        _run_aggregate(policy, mocker, base + timezone.timedelta(minutes=10), [], "miss-2", django_capture_on_commit_callbacks)
        alert = Alert.objects.get(policy=policy)
        assert alert.status == AlertConstants.STATUS_NEW
        assert alert.info_event_count == 0
        assert Event.objects.filter(policy=policy, action=Event.Action.RECOVERED).count() == 0

    def test_keyword_scan_does_not_reconcile_recovery(self, mocker):
        policy = _make_policy(
            name="keyword-no-recover",
            alert_condition={"query": "error", "rule": {"recover_after": 1, "min_hits": 1}},
        )
        alert = Alert.objects.create(
            id="keyword-active",
            policy=policy,
            source_id=f"policy_{policy.id}",
            level="warning",
            status=AlertConstants.STATUS_NEW,
            info_event_count=4,
            start_event_time=timezone.now(),
        )
        scan = LogPolicyScan(policy, execution_key="keyword-miss")
        mocker.patch.object(scan.vlogs_api, "query", return_value=[])
        scan.run()
        alert.refresh_from_db()
        assert alert.status == AlertConstants.STATUS_NEW
        assert alert.info_event_count == 4

    def test_avg_alert_value_is_the_computed_average(self, mocker):
        policy = _make_policy(
            name="avg-value",
            alert_type="aggregate",
            alert_name="耗时",
            alert_condition={
                "query": "*",
                "group_by": [],
                "rule": {
                    "mode": "and",
                    "conditions": [{"func": "avg", "field": "duration", "op": ">", "value": "500"}],
                },
            },
        )
        scan = LogPolicyScan(policy, execution_key="avg")
        mocker.patch.object(scan, "_fetch_aggregate_samples", return_value={})
        mocker.patch.object(scan.vlogs_api, "query", return_value=[{"avg_duration": "800.5"}])
        scan.run()
        alert = Alert.objects.get(policy=policy)
        assert alert.value == pytest.approx(800.5)
        assert alert.value != 0
