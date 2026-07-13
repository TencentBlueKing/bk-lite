"""cmdb.services.subscription_task.SubscriptionTaskService 测试。

规格（真实输出/分支/契约，仅 mock 外部边界）：
- 纯静态格式化：标题/正文/聚合摘要/关联摘要/时间格式化/ID 解析/触发类型展示；
- check_rules：无规则跳过；有事件分组派发；异常隔离不中断；
- send_notifications：分布式锁（cache.add）幂等；无事件组提前退出并释放锁；
  正常逐组发送并 finally 释放锁；
- _process_single_event_group：规则停用跳过；逐渠道发送，结果失败/成功分支；
- _get_receivers_from_recipients：合并 users + group_users（RPC mock）；
- _get_instance_name_map：InstanceManage mock 返回，构建 id->name。
"""
import pydantic.root_model  # noqa

import pytest
from django.db import IntegrityError, transaction

from apps.cmdb.constants.subscription import TriggerType
from apps.cmdb.models.subscription_delivery import (
    SubscriptionDelivery,
    SubscriptionDeliveryStatus,
)
from apps.cmdb.models.subscription_rule import SubscriptionRule
from apps.cmdb.services.subscription_task import SubscriptionTaskService
from apps.cmdb.services.subscription_trigger import TriggerEvent

pytestmark = pytest.mark.django_db


class TestSubscriptionDeliveryModel:
    def _create_rule(self):
        return SubscriptionRule.objects.create(name="delivery-rule", organization=1, model_id="host",)

    def _create_delivery(self, rule, **overrides):
        values = {
            "dedupe_key": "a" * 64,
            "rule": rule,
            "rule_id_snapshot": rule.id,
            "trigger_type": TriggerType.ATTRIBUTE_CHANGE.value,
            "events": [make_event(rule_id=rule.id).to_dict()],
            "recipients": {"users": ["alice"]},
            "channel_id": 1,
        }
        values.update(overrides)
        return SubscriptionDelivery.objects.create(**values)

    def test_delivery_model_dedupe_key必须唯一(self):
        rule = self._create_rule()
        self._create_delivery(rule)

        with pytest.raises(IntegrityError), transaction.atomic():
            self._create_delivery(rule)

    def test_delivery_model删除规则后保留投递快照(self):
        rule = self._create_rule()
        delivery = self._create_delivery(rule)
        rule_id = rule.id

        rule.delete()

        delivery.refresh_from_db()
        assert delivery.rule is None
        assert delivery.rule_id_snapshot == rule_id

    def test_delivery_model默认处于待发送且未尝试(self):
        delivery = self._create_delivery(self._create_rule())

        assert delivery.status == SubscriptionDeliveryStatus.PENDING
        assert delivery.attempt_count == 0


def make_event(
    rule_id=1,
    trigger_type=TriggerType.ATTRIBUTE_CHANGE.value,
    inst_id=10,
    inst_name="主机A",
    change_summary="cpu: 2 -> 4",
    triggered_at="2026-06-24T08:00:00Z",
    model_name="主机",
    model_id="host",
):
    return TriggerEvent(
        rule_id=rule_id,
        rule_name="规则1",
        model_id=model_id,
        model_name=model_name,
        trigger_type=trigger_type,
        inst_id=inst_id,
        inst_name=inst_name,
        change_summary=change_summary,
        triggered_at=triggered_at,
    )


class TestFormatHelpers:
    pytestmark = pytest.mark.unit

    def test_触发类型展示_已知与未知(self):
        assert SubscriptionTaskService._get_trigger_type_display(TriggerType.ATTRIBUTE_CHANGE.value) == "属性变化"
        assert SubscriptionTaskService._get_trigger_type_display("xx") == "xx"

    def test_时间格式化_iso与非法原样(self):
        out = SubscriptionTaskService._format_triggered_at("2026-06-24T08:00:00Z")
        assert out == "2026-06-24 08:00:00"
        assert SubscriptionTaskService._format_triggered_at("bad") == "bad"

    def test_change_summary_新增删除前缀(self):
        added = make_event(trigger_type=TriggerType.INSTANCE_ADDED.value)
        deleted = make_event(trigger_type=TriggerType.INSTANCE_DELETED.value)
        assert SubscriptionTaskService._format_change_summary(added) == "+ 主机A"
        assert SubscriptionTaskService._format_change_summary(deleted) == "- 主机A"

    def test_change_summary_普通原样(self):
        e = make_event(change_summary="cpu: 2 -> 4")
        assert SubscriptionTaskService._format_change_summary(e) == "cpu: 2 -> 4"

    def test_parse_relation_ids_正常与非法(self):
        assert SubscriptionTaskService._parse_relation_ids("[1, 2, 3]") == [1, 2, 3]
        assert SubscriptionTaskService._parse_relation_ids("") == []
        # 非法表达式
        assert SubscriptionTaskService._parse_relation_ids("not_a_list") == []
        # 非 list
        assert SubscriptionTaskService._parse_relation_ids("123") == []
        # 含不可转 int 的项被跳过
        assert SubscriptionTaskService._parse_relation_ids("[1, 'x', 2]") == [1, 2]


class TestBuildTitle:
    pytestmark = pytest.mark.unit

    def test_单实例_普通类型含实例名(self):
        title = SubscriptionTaskService._build_title("主机", [make_event()], TriggerType.ATTRIBUTE_CHANGE.value)
        assert title == "主机 主机A 属性变化"

    def test_单实例_新增不含实例名(self):
        e = make_event(trigger_type=TriggerType.INSTANCE_ADDED.value)
        title = SubscriptionTaskService._build_title("主机", [e], TriggerType.INSTANCE_ADDED.value)
        assert title == "主机 出现新增实例"

    def test_多实例_用计数与复数后缀(self):
        events = [make_event(inst_id=i) for i in range(3)]
        title = SubscriptionTaskService._build_title("主机", events, TriggerType.ATTRIBUTE_CHANGE.value)
        assert title == "主机 3 个实例属性变化"

    def test_未知触发类型_默认后缀(self):
        title = SubscriptionTaskService._build_title("主机", [make_event()], "unknown")
        assert title == "主机 主机A 变化"


class TestBuildNotificationContent:
    pytestmark = pytest.mark.unit

    def test_空事件_默认标题正文(self):
        title, content = SubscriptionTaskService._build_notification_content(SubscriptionRule(name="r", model_id="host"), [])
        assert "规则触发" in title
        assert content == "无触发事件"

    def test_单事件_属性变化_包含变化摘要(self):
        rule = SubscriptionRule(name="r", model_id="host")
        title, content = SubscriptionTaskService._build_notification_content(rule, [make_event()])
        assert "主机A" in title
        assert "模型：主机" in content
        assert "实例：主机A" in content
        assert "变化摘要：cpu: 2 -> 4" in content
        assert "触发时间：2026-06-24 08:00:00" in content

    def test_单事件_到期_用到期信息标签(self):
        rule = SubscriptionRule(name="r", model_id="host")
        e = make_event(trigger_type=TriggerType.EXPIRATION.value, change_summary="3天后到期")
        _, content = SubscriptionTaskService._build_notification_content(rule, [e])
        assert "到期信息：3天后到期" in content

    def test_多事件_少量_逐条列出(self):
        rule = SubscriptionRule(name="r", model_id="host")
        events = [
            make_event(inst_id=1, inst_name="A", triggered_at="2026-06-24T08:00:00Z"),
            make_event(inst_id=2, inst_name="B", triggered_at="2026-06-24T09:00:00Z"),
        ]
        _, content = SubscriptionTaskService._build_notification_content(rule, events)
        assert "1）A：" in content
        assert "2）B：" in content
        # 时间不同 -> 范围
        assert "触发时间范围：" in content

    def test_多事件_同时间_用单一触发时间(self):
        rule = SubscriptionRule(name="r", model_id="host")
        events = [
            make_event(inst_id=1, inst_name="A"),
            make_event(inst_id=2, inst_name="B"),
        ]
        _, content = SubscriptionTaskService._build_notification_content(rule, events)
        assert "触发时间：2026-06-24 08:00:00" in content
        assert "触发时间范围" not in content

    def test_多事件_超阈值_聚合摘要(self):
        rule = SubscriptionRule(name="r", model_id="host")
        events = [make_event(inst_id=i, inst_name=f"H{i}") for i in range(6)]
        _, content = SubscriptionTaskService._build_notification_content(rule, events)
        assert "变化摘要：修改 6 个" in content


class TestAggregatedSummary:
    pytestmark = pytest.mark.unit

    def test_混合类型聚合(self):
        events = [
            make_event(trigger_type=TriggerType.INSTANCE_ADDED.value),
            make_event(trigger_type=TriggerType.ATTRIBUTE_CHANGE.value, change_summary="cpu: 2 -> 4"),
            make_event(trigger_type=TriggerType.RELATION_CHANGE.value),
            make_event(trigger_type=TriggerType.EXPIRATION.value),
            make_event(trigger_type=TriggerType.INSTANCE_DELETED.value),
            make_event(trigger_type=TriggerType.CONFIG_FILE.value),
        ]
        out = SubscriptionTaskService._build_aggregated_summary(events)
        assert "新增 1 个" in out
        assert "修改 1 个（cpu）" in out
        assert "关联变化 1 个" in out
        assert "到期提醒 1 个" in out
        assert "删除 1 个" in out
        assert "配置文件关联 1 个" in out

    def test_空事件_默认发生变化(self):
        assert SubscriptionTaskService._build_aggregated_summary([]) == "发生变化"


class TestRelationChangeSummary:
    pytestmark = pytest.mark.unit

    def test_无关联模型匹配_原样返回(self):
        out = SubscriptionTaskService._format_relation_change_summary("普通文本")
        assert out == "普通文本"

    def test_有新增删除_替换为名称(self, mocker):
        summary = "关联模型[host]变化, 新增关联: [1], 删除关联: [2]"
        mocker.patch.object(
            SubscriptionTaskService, "_get_instance_name_map", return_value={1: "主机1", 2: "主机2"},
        )
        out = SubscriptionTaskService._format_relation_change_summary(summary)
        assert "新增关联: [主机1]" in out
        assert "删除关联: [主机2]" in out

    def test_名称映射为空_原样返回(self, mocker):
        summary = "关联模型[host]变化, 新增关联: [1]"
        mocker.patch.object(SubscriptionTaskService, "_get_instance_name_map", return_value={})
        out = SubscriptionTaskService._format_relation_change_summary(summary)
        assert out == summary


class TestGetInstanceNameMap:
    pytestmark = pytest.mark.unit

    def test_空参数返回空(self):
        assert SubscriptionTaskService._get_instance_name_map("", [1]) == {}
        assert SubscriptionTaskService._get_instance_name_map("host", []) == {}

    def test_正常构建_id到名称(self, mocker):
        mocker.patch(
            "apps.cmdb.services.subscription_task.InstanceManage.instance_list",
            return_value=([{"_id": 1, "inst_name": "主机1"}, {"_id": 2, "inst_name": "主机2"}, {"inst_name": "无id"},], 3,),  # 无 _id 跳过
        )
        out = SubscriptionTaskService._get_instance_name_map("host", [1, 2])
        assert out == {1: "主机1", 2: "主机2"}

    def test_查询异常返回空(self, mocker):
        mocker.patch(
            "apps.cmdb.services.subscription_task.InstanceManage.instance_list", side_effect=RuntimeError("db down"),
        )
        assert SubscriptionTaskService._get_instance_name_map("host", [1]) == {}


class TestDecodeAndGroup:
    pytestmark = pytest.mark.unit

    def test_decode_event_dicts_跳过非法(self):
        valid = make_event().to_dict()
        events = SubscriptionTaskService._decode_event_dicts([valid, {"bad": "missing fields"}])
        assert len(events) == 1
        assert events[0].inst_name == "主机A"

    def test_build_event_groups_按规则与类型分组(self):
        events = [
            make_event(rule_id=1, trigger_type=TriggerType.ATTRIBUTE_CHANGE.value),
            make_event(rule_id=1, trigger_type=TriggerType.ATTRIBUTE_CHANGE.value, inst_id=11),
            make_event(rule_id=1, trigger_type=TriggerType.INSTANCE_ADDED.value),
            make_event(rule_id=2, trigger_type=TriggerType.ATTRIBUTE_CHANGE.value),
        ]
        groups = SubscriptionTaskService._build_event_groups(events)
        assert len(groups) == 3
        attr_group = next(g for g in groups if g["rule_id"] == 1 and g["trigger_type"] == TriggerType.ATTRIBUTE_CHANGE.value)
        assert len(attr_group["events"]) == 2


class TestGetReceivers:
    pytestmark = pytest.mark.unit

    def test_合并users与组用户(self):
        class FakeClient:
            def get_group_users(self, group_id, include_children=False):
                return {
                    "result": True,
                    "data": [{"username": "bob"}, {"username": "alice"}, {}],
                }

        recipients = {"users": ["bob"], "groups": [100]}
        out = SubscriptionTaskService._get_receivers_from_recipients(FakeClient(), recipients)
        assert set(out) == {"bob", "alice"}

    def test_非dict_recipients_返回空(self):
        out = SubscriptionTaskService._get_receivers_from_recipients(object(), None)
        assert out == []

    def test_组查询异常_隔离(self):
        class FakeClient:
            def get_group_users(self, group_id, include_children=False):
                raise RuntimeError("rpc fail")

        out = SubscriptionTaskService._get_receivers_from_recipients(FakeClient(), {"users": ["bob"], "groups": [1]})
        assert out == ["bob"]


class TestCheckRules:
    def test_无启用规则_提前返回(self, mocker):
        dispatch = mocker.patch.object(SubscriptionTaskService, "_dispatch_send_notifications_async")
        SubscriptionTaskService.check_rules()
        dispatch.assert_not_called()

    def test_有事件_派发异步发送(self, mocker):
        SubscriptionRule.objects.create(name="r1", organization=1, model_id="host", is_enabled=True)
        trigger_service = mocker.patch("apps.cmdb.services.subscription_task.SubscriptionTriggerService")
        trigger_service.return_value.process.return_value = [make_event()]
        dispatch = mocker.patch.object(SubscriptionTaskService, "_dispatch_send_notifications_async")
        SubscriptionTaskService.check_rules()
        dispatch.assert_called_once()
        kwargs = dispatch.call_args.kwargs
        assert kwargs["source"] == "check_rules"
        assert len(kwargs["event_groups"]) == 1

    def test_规则处理异常_隔离不中断(self, mocker):
        SubscriptionRule.objects.create(name="r_err", organization=1, model_id="host", is_enabled=True)
        trigger_service = mocker.patch("apps.cmdb.services.subscription_task.SubscriptionTriggerService")
        trigger_service.return_value.process.side_effect = RuntimeError("boom")
        dispatch = mocker.patch.object(SubscriptionTaskService, "_dispatch_send_notifications_async")
        # 不抛异常，且因无事件不派发
        SubscriptionTaskService.check_rules()
        dispatch.assert_not_called()

    def test_无事件_不派发(self, mocker):
        SubscriptionRule.objects.create(name="r_noev", organization=1, model_id="host", is_enabled=True)
        trigger_service = mocker.patch("apps.cmdb.services.subscription_task.SubscriptionTriggerService")
        trigger_service.return_value.process.return_value = []
        dispatch = mocker.patch.object(SubscriptionTaskService, "_dispatch_send_notifications_async")
        SubscriptionTaskService.check_rules()
        dispatch.assert_not_called()


class TestSendNotifications:
    def setup_method(self):
        from django.core.cache import cache

        cache.delete(SubscriptionTaskService.SEND_LOCK_KEY)

    def teardown_method(self):
        from django.core.cache import cache

        cache.delete(SubscriptionTaskService.SEND_LOCK_KEY)

    def test_锁占用_跳过(self, mocker):
        mocker.patch("apps.cmdb.services.subscription_task.cache.add", return_value=False)
        process = mocker.patch.object(SubscriptionTaskService, "_process_single_event_group")
        SubscriptionTaskService.send_notifications(event_groups=[{"events": []}])
        process.assert_not_called()

    def test_无事件组_释放锁退出(self, mocker):
        add = mocker.patch("apps.cmdb.services.subscription_task.cache.add", return_value=True)
        delete = mocker.patch("apps.cmdb.services.subscription_task.cache.delete")
        SubscriptionTaskService.send_notifications(event_groups=None)
        add.assert_called_once()
        delete.assert_called_once_with(SubscriptionTaskService.SEND_LOCK_KEY)

    def test_正常处理每组并释放锁(self, mocker):
        mocker.patch("apps.cmdb.services.subscription_task.cache.add", return_value=True)
        delete = mocker.patch("apps.cmdb.services.subscription_task.cache.delete")
        mocker.patch("apps.cmdb.services.subscription_task.SystemMgmt")
        process = mocker.patch.object(SubscriptionTaskService, "_process_single_event_group")
        groups = [{"events": [1]}, {"events": [2]}]
        SubscriptionTaskService.send_notifications(event_groups=groups)
        assert process.call_count == 2
        delete.assert_called_with(SubscriptionTaskService.SEND_LOCK_KEY)


class TestProcessSingleEventGroup:
    pytestmark = pytest.mark.django_db

    def test_无有效事件_跳过(self, mocker):
        client = mocker.MagicMock()
        SubscriptionTaskService._process_single_event_group({"events": []}, client)
        client.send_msg_with_channel.assert_not_called()

    def test_规则停用_跳过(self, mocker):
        client = mocker.MagicMock()
        group = {
            "trigger_type": TriggerType.ATTRIBUTE_CHANGE.value,
            "events": [make_event(rule_id=99999).to_dict()],
        }
        SubscriptionTaskService._process_single_event_group(group, client)
        client.send_msg_with_channel.assert_not_called()

    def test_逐渠道发送_成功与失败分支(self, mocker):
        rule = SubscriptionRule.objects.create(
            name="r_send", organization=1, model_id="host", is_enabled=True, recipients={"users": ["bob"], "groups": []}, channel_ids=[1, 2],
        )
        client = mocker.MagicMock()
        # 渠道1成功，渠道2失败
        client.send_msg_with_channel.side_effect = [
            {"result": True},
            {"result": False, "message": "失败"},
        ]
        group = {
            "trigger_type": TriggerType.ATTRIBUTE_CHANGE.value,
            "events": [make_event(rule_id=rule.id).to_dict()],
        }
        SubscriptionTaskService._process_single_event_group(group, client)
        assert client.send_msg_with_channel.call_count == 2
        # 校验入参契约
        call = client.send_msg_with_channel.call_args_list[0]
        assert call.kwargs["channel_id"] == 1
        assert call.kwargs["receivers"] == ["bob"]
        assert "host" not in call.kwargs["title"]  # title 用 model_name 非 id

    def test_非dict返回_记为失败不抛(self, mocker):
        rule = SubscriptionRule.objects.create(
            name="r_baddict", organization=1, model_id="host", is_enabled=True, recipients={"users": ["bob"]}, channel_ids=[1],
        )
        client = mocker.MagicMock()
        client.send_msg_with_channel.return_value = "not a dict"
        group = {
            "trigger_type": TriggerType.ATTRIBUTE_CHANGE.value,
            "events": [make_event(rule_id=rule.id).to_dict()],
        }
        # 不应抛异常
        SubscriptionTaskService._process_single_event_group(group, client)
        client.send_msg_with_channel.assert_called_once()


class TestDispatchAsync:
    pytestmark = pytest.mark.unit

    def test_派发调用send_task(self, mocker):
        send_task = mocker.patch("apps.core.celery.app.send_task")
        SubscriptionTaskService._dispatch_send_notifications_async(source="test", event_groups=[{"rule_id": 1}])
        send_task.assert_called_once()
        args, kwargs = send_task.call_args
        assert args[0] == SubscriptionTaskService.SEND_TASK_NAME
        assert kwargs["kwargs"]["event_groups"] == [{"rule_id": 1}]

    def test_派发异常_隔离不抛(self, mocker):
        mocker.patch("apps.core.celery.app.send_task", side_effect=RuntimeError("broker down"))
        # 不应抛异常
        SubscriptionTaskService._dispatch_send_notifications_async(source="test", event_groups=[{"rule_id": 1}])
