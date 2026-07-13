"""cmdb.services.subscription_trigger.SubscriptionTriggerService 测试。

仅 mock 真实外部边界（ModelManage / InstanceManage），ChangeRecord/SubscriptionRule 用真实 DB。
覆盖：
- 纯静态：_normalize_relation_change_models / _resolve_attribute_inst_name /
  _get_changed_fields / _parse_to_date / _merge_attribute_summary / _emit_attribute_event；
- DB 流：_check_attribute_change（合并模式 + 过滤条件集合增减）、
  _check_expiration（去重键 + 范围判定）、_update_snapshot、
  _build_related_change_map（ChangeRecord 窗口 + 字段过滤）；
- process 编排：空实例直接更新快照返回 []。
"""
import pydantic.root_model  # noqa

from datetime import datetime, timedelta

import pytest
from django.utils import timezone

from apps.cmdb.constants.subscription import FilterType, TriggerType
from apps.cmdb.models.change_record import (
    CREATE_INST,
    UPDATE_INST,
    ChangeRecord,
)
from apps.cmdb.models.subscription_rule import SubscriptionRule
from apps.cmdb.services.subscription_trigger import (
    SubscriptionTriggerService,
    TriggerEvent,
)

pytestmark = pytest.mark.django_db


@pytest.fixture
def patch_model_info(mocker):
    mocker.patch(
        "apps.cmdb.services.subscription_trigger.ModelManage.search_model_info",
        return_value={"model_name": "主机"},
    )


def make_rule(**kw):
    defaults = dict(
        name=kw.pop("name", "rule"),
        organization=1,
        model_id="host",
        filter_type=FilterType.INSTANCES.value,
        instance_filter={},
        trigger_types=[],
        trigger_config={},
        recipients={},
        channel_ids=[],
        is_enabled=True,
        snapshot_data={},
    )
    defaults.update(kw)
    return SubscriptionRule.objects.create(**defaults)


def make_change_record(model_id, inst_id, before, after, created_at, type=UPDATE_INST):
    rec = ChangeRecord.objects.create(
        model_id=model_id,
        inst_id=inst_id,
        label="host",
        type=type,
        before_data=before,
        after_data=after,
    )
    # created_at 为 auto_now_add，需手动改写到窗口内
    ChangeRecord.objects.filter(id=rec.id).update(created_at=created_at)
    rec.refresh_from_db()
    return rec


class TestNormalizeRelationModels:
    pytestmark = pytest.mark.unit

    def test_列表形态去重(self):
        cfg = {
            "related_models": [
                {"related_model": "switch", "fields": ["a"]},
                {"related_model": "switch", "fields": ["b"]},  # 重复 -> 去重
                {"no_model": 1},  # 跳过
                {"related_model": "router", "fields": "bad"},  # fields 非 list -> []
            ]
        }
        out = SubscriptionTriggerService._normalize_relation_change_models(cfg)
        assert [m["related_model"] for m in out] == ["switch", "router"]
        assert out[1]["fields"] == []

    def test_单模型旧格式(self):
        out = SubscriptionTriggerService._normalize_relation_change_models(
            {"related_model": "switch", "fields": ["a"]}
        )
        assert out == [{"related_model": "switch", "fields": ["a"]}]

    def test_空配置(self):
        assert SubscriptionTriggerService._normalize_relation_change_models(None) == []
        assert SubscriptionTriggerService._normalize_relation_change_models({}) == []


class TestPureStatics:
    pytestmark = pytest.mark.unit

    def test_get_changed_fields(self):
        out = SubscriptionTriggerService._get_changed_fields(
            {"a": 1, "b": 2}, {"a": 1, "b": 3, "c": 4}
        )
        assert out == {"b", "c"}

    def test_parse_to_date(self):
        assert SubscriptionTriggerService._parse_to_date(
            datetime(2026, 1, 2, 3, 4)
        ) == datetime(2026, 1, 2).date()
        assert SubscriptionTriggerService._parse_to_date(
            "2026-06-30T00:00:00Z"
        ) == datetime(2026, 6, 30).date()
        assert SubscriptionTriggerService._parse_to_date("bad") is None
        assert SubscriptionTriggerService._parse_to_date(12345) is None

    def test_resolve_attribute_inst_name_优先级(self):
        # instance_map 命中 inst_name
        assert (
            SubscriptionTriggerService._resolve_attribute_inst_name(
                {5: {"inst_name": "主机5"}}, 5
            )
            == "主机5"
        )
        # 回退到 ip_addr
        assert (
            SubscriptionTriggerService._resolve_attribute_inst_name(
                {5: {"ip_addr": "1.1.1.1"}}, 5
            )
            == "1.1.1.1"
        )
        # 全空回退到 after_data
        assert (
            SubscriptionTriggerService._resolve_attribute_inst_name(
                {}, 5, after_data={"inst_name": "fromchange"}
            )
            == "fromchange"
        )
        # 最终回退 str(inst_id)
        assert (
            SubscriptionTriggerService._resolve_attribute_inst_name({}, 5) == "5"
        )


class TestMergeAndEmit:
    pytestmark = pytest.mark.unit

    def test_merge_attribute_summary_去重并补名(self, patch_model_info):
        svc = SubscriptionTriggerService(make_rule(name="merge_r"))
        m = {}
        svc._merge_attribute_summary(m, 1, "1", "字段变化: a")  # inst_name == str(id)
        svc._merge_attribute_summary(m, 1, "主机1", "字段变化: a")  # 重复 part + 补名
        svc._merge_attribute_summary(m, 1, "主机1", "字段变化: b")
        assert m[1]["inst_name"] == "主机1"
        assert m[1]["parts"] == ["字段变化: a", "字段变化: b"]

    def test_emit_attribute_event(self, patch_model_info):
        svc = SubscriptionTriggerService(make_rule(name="emit_r"))
        events = []
        svc._emit_attribute_event(events, 7, "主机7", "字段变化: x", "2026-06-24T00:00:00")
        assert len(events) == 1
        e = events[0]
        assert isinstance(e, TriggerEvent)
        assert e.trigger_type == TriggerType.ATTRIBUTE_CHANGE.value
        assert e.inst_id == 7
        assert e.model_name == "主机"


class TestProcessEmpty:
    def test_空实例_更新快照返回空(self, mocker, patch_model_info):
        rule = make_rule(name="empty_r", trigger_types=[TriggerType.ATTRIBUTE_CHANGE.value])
        mocker.patch.object(
            SubscriptionTriggerService, "_get_current_instances", return_value=[]
        )
        svc = SubscriptionTriggerService(rule)
        out = svc.process()
        assert out == []
        rule.refresh_from_db()
        assert rule.last_check_time is not None
        assert rule.snapshot_data["instances"] == []


class TestCheckAttributeChange:
    def test_合并模式_字段变化生成单事件(self, patch_model_info):
        now = timezone.now()
        rule = make_rule(
            name="attr_r",
            trigger_types=[TriggerType.ATTRIBUTE_CHANGE.value],
            trigger_config={"attribute_change": {"fields": ["cpu", "mem"]}},
            last_check_time=now - timedelta(hours=1),
            snapshot_data={"instances": [1]},
        )
        # 窗口内两条变更记录，合并为一条事件
        make_change_record(
            "host", 1, {"cpu": "2"}, {"cpu": "4", "inst_name": "主机1"}, now - timedelta(minutes=30)
        )
        make_change_record(
            "host", 1, {"mem": "8"}, {"mem": "16", "inst_name": "主机1"}, now - timedelta(minutes=20)
        )
        svc = SubscriptionTriggerService(rule)
        instances = [{"_id": 1, "inst_name": "主机1"}]
        events = svc._check_attribute_change(instances, now)
        assert len(events) == 1
        e = events[0]
        assert e.inst_id == 1
        assert "cpu" in e.change_summary
        assert "mem" in e.change_summary

    def test_无监听字段_跳过(self, patch_model_info):
        rule = make_rule(
            name="attr_nofields",
            trigger_config={"attribute_change": {"fields": []}},
        )
        svc = SubscriptionTriggerService(rule)
        assert svc._check_attribute_change([{"_id": 1}], timezone.now()) == []

    def test_过滤条件模式_检测集合增减(self, patch_model_info):
        now = timezone.now()
        rule = make_rule(
            name="attr_cond",
            filter_type=FilterType.CONDITION.value,
            trigger_types=[TriggerType.ATTRIBUTE_CHANGE.value],
            trigger_config={"attribute_change": {"fields": ["cpu"]}},
            last_check_time=now - timedelta(hours=1),
            snapshot_data={"instances": [1, 2]},  # 旧集合
        )
        # 合并模式下，集合增减事件与字段变更事件统一在窗口扫描后 flush；
        # 需窗口内存在至少一条变更记录，flush 才会执行（否则提前返回）。
        make_change_record(
            "host", 3, {"cpu": "1"}, {"cpu": "2", "inst_name": "主机3"}, now - timedelta(minutes=5)
        )
        svc = SubscriptionTriggerService(rule)
        # 当前实例集合 {2,3} -> 新增 3，删除 1
        instances = [{"_id": 2, "inst_name": "主机2"}, {"_id": 3, "inst_name": "主机3"}]
        events = svc._check_attribute_change(instances, now)
        ids = {e.inst_id for e in events}
        assert 3 in ids  # 进入范围
        assert 1 in ids  # 离开范围
        added_event = next(e for e in events if e.inst_id == 3)
        assert "进入订阅范围" in added_event.change_summary


class TestCheckExpiration:
    def test_范围内首次通知_去重键写入(self, patch_model_info):
        rule = make_rule(
            name="exp_r",
            trigger_config={"expiration": {"time_field": "expire_at", "days_before": 7}},
            snapshot_data={"expiration_notified": {}},
        )
        svc = SubscriptionTriggerService(rule)
        target = (timezone.localdate() + timedelta(days=3)).isoformat()
        snapshot = {}
        instances = [{"_id": 1, "inst_name": "主机1", "expire_at": target}]
        events = svc._check_expiration(instances, snapshot)
        assert len(events) == 1
        assert events[0].trigger_type == TriggerType.EXPIRATION.value
        assert "3 天后到期" in events[0].change_summary
        # 去重键已写入快照
        assert len(snapshot["expiration_notified"]) == 1

    def test_已通知_跳过(self, patch_model_info):
        expire_date = (timezone.localdate() + timedelta(days=3)).isoformat()
        dedup_key = f"1:expire_at:{expire_date}"
        rule = make_rule(
            name="exp_dup",
            trigger_config={"expiration": {"time_field": "expire_at", "days_before": 7}},
            snapshot_data={"expiration_notified": {dedup_key: "x"}},
        )
        svc = SubscriptionTriggerService(rule)
        snapshot = {}
        instances = [{"_id": 1, "inst_name": "主机1", "expire_at": expire_date}]
        events = svc._check_expiration(instances, snapshot)
        assert events == []
        # 仍然写回当前去重键
        assert dedup_key in snapshot["expiration_notified"]

    def test_配置无效_跳过(self, patch_model_info):
        rule = make_rule(
            name="exp_bad",
            trigger_config={"expiration": {"time_field": "", "days_before": 0}},
        )
        svc = SubscriptionTriggerService(rule)
        assert svc._check_expiration([{"_id": 1}], {}) == []

    def test_超出范围_不通知(self, patch_model_info):
        rule = make_rule(
            name="exp_far",
            trigger_config={"expiration": {"time_field": "expire_at", "days_before": 7}},
            snapshot_data={"expiration_notified": {}},
        )
        svc = SubscriptionTriggerService(rule)
        far = (timezone.localdate() + timedelta(days=30)).isoformat()
        events = svc._check_expiration([{"_id": 1, "expire_at": far}], {})
        assert events == []


class TestBuildRelatedChangeMap:
    def test_窗口内字段变化_命中监听字段(self, patch_model_info):
        now = timezone.now()
        rule = make_rule(
            name="rel_r",
            last_check_time=now - timedelta(hours=1),
        )
        make_change_record(
            "switch", 100, {"port": "1"}, {"port": "2"}, now - timedelta(minutes=10)
        )
        svc = SubscriptionTriggerService(rule)
        change_map, count = svc._build_related_change_map(
            related_model="switch",
            related_instance_ids=[100],
            watch_fields={"port"},
            checkpoint=now,
        )
        assert count == 1
        assert 100 in change_map
        assert "port" in change_map[100][0]

    def test_空关联_返回空(self, patch_model_info):
        rule = make_rule(name="rel_empty")
        svc = SubscriptionTriggerService(rule)
        assert svc._build_related_change_map(
            related_model="switch",
            related_instance_ids=[],
            watch_fields=set(),
            checkpoint=timezone.now(),
        ) == ({}, 0)


class TestBuildRelatedInstNameMap:
    def test_查询并构建名称映射(self, mocker, patch_model_info):
        rule = make_rule(name="relname_r")
        svc = SubscriptionTriggerService(rule)
        mocker.patch(
            "apps.cmdb.services.subscription_trigger.InstanceManage.instance_list",
            return_value=(
                [
                    {"_id": 10, "inst_name": "交换机10"},
                    {"_id": 11, "ip_addr": "2.2.2.2"},
                    {"inst_name": "无id"},  # 跳过
                ],
                3,
            ),
        )
        previous = {"1": {"switch": [10]}}
        current = {"1": {"switch": [11]}}
        out = svc._build_related_inst_name_map("switch", previous, current)
        assert out == {10: "交换机10", 11: "2.2.2.2"}

    def test_无关联id返回空(self, patch_model_info):
        rule = make_rule(name="relname_empty")
        svc = SubscriptionTriggerService(rule)
        assert svc._build_related_inst_name_map("switch", {}, {}) == {}

    def test_查询异常返回空(self, mocker, patch_model_info):
        rule = make_rule(name="relname_exc")
        svc = SubscriptionTriggerService(rule)
        mocker.patch(
            "apps.cmdb.services.subscription_trigger.InstanceManage.instance_list",
            side_effect=RuntimeError("db down"),
        )
        out = svc._build_related_inst_name_map("switch", {"1": {"switch": [10]}}, {})
        assert out == {}


class TestCheckRelationChange:
    def test_新增删除关联生成事件(self, mocker, patch_model_info):
        rule = make_rule(
            name="rel_change_r",
            trigger_types=[TriggerType.RELATION_CHANGE.value],
            trigger_config={
                "relation_change": {"related_models": [{"related_model": "switch", "fields": []}]}
            },
            snapshot_data={"relations": {"1": {"switch": [10]}}},
        )
        # related inst name map -> 走 InstanceManage（mock 返回空即可，事件 summary 用 id）
        mocker.patch(
            "apps.cmdb.services.subscription_trigger.InstanceManage.instance_list",
            return_value=([], 0),
        )
        svc = SubscriptionTriggerService(rule)
        current_snapshot = {"relations": {"1": {"switch": [11]}}}  # 10删除, 11新增
        instances = [{"_id": 1, "inst_name": "主机1"}]
        events = svc._check_relation_change(current_snapshot, instances, timezone.now())
        assert len(events) == 1
        e = events[0]
        assert e.trigger_type == TriggerType.RELATION_CHANGE.value
        assert "新增关联: [11]" in e.change_summary
        assert "删除关联: [10]" in e.change_summary

    def test_未配置关联模型_跳过(self, patch_model_info):
        rule = make_rule(name="rel_none", trigger_config={"relation_change": {}})
        svc = SubscriptionTriggerService(rule)
        assert svc._check_relation_change({"relations": {}}, [], timezone.now()) == []


class TestCheckConfigFile:
    def test_非host模型跳过(self, patch_model_info):
        rule = make_rule(
            name="cf_nonhost",
            model_id="switch",
            trigger_types=[TriggerType.CONFIG_FILE.value],
        )
        svc = SubscriptionTriggerService(rule)
        assert svc._check_config_file([{"_id": 1}], {}, timezone.now()) == []

    def test_无实例跳过(self, patch_model_info):
        rule = make_rule(name="cf_noinst", model_id="host")
        svc = SubscriptionTriggerService(rule)
        assert svc._check_config_file([], {}, timezone.now()) == []

    def test_窗口无版本跳过(self, patch_model_info):
        now = timezone.now()
        rule = make_rule(
            name="cf_nover", model_id="host", last_check_time=now - timedelta(hours=1)
        )
        svc = SubscriptionTriggerService(rule)
        out = svc._check_config_file([{"_id": 1, "inst_name": "h1"}], {}, now)
        assert out == []


class TestUpdateSnapshot:
    def test_有事件写入触发时间(self, patch_model_info):
        rule = make_rule(name="snap_r")
        svc = SubscriptionTriggerService(rule)
        svc.events = [
            TriggerEvent(
                rule_id=rule.id, rule_name="r", model_id="host", model_name="主机",
                trigger_type=TriggerType.ATTRIBUTE_CHANGE.value, inst_id=1,
                inst_name="h", change_summary="s", triggered_at="t",
            )
        ]
        checkpoint = timezone.now()
        svc._update_snapshot({"instances": [1]}, checkpoint)
        rule.refresh_from_db()
        assert rule.last_check_time == checkpoint
        assert rule.last_triggered_at == checkpoint
        assert rule.snapshot_data == {"instances": [1]}

    def test_无事件不写触发时间(self, patch_model_info):
        rule = make_rule(name="snap_noev")
        svc = SubscriptionTriggerService(rule)
        svc.events = []
        svc._update_snapshot({"instances": []}, timezone.now())
        rule.refresh_from_db()
        assert rule.last_triggered_at is None
