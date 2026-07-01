"""monitor.services.alert_lifecycle_notify.AlertLifecycleNotifier 规格测试。

聚焦不触 DB 的纯逻辑：渠道返回结果归一化、标题/正文/告警中心 payload 拼装、
通知对象/渠道解析、是否通知判定。用 SimpleNamespace 构造 alert/policy/channel。
告警生命周期通知映射直接影响外部告警中心数据，必须准确。
"""

import pydantic.root_model  # noqa

from datetime import datetime
from types import SimpleNamespace

import pytest

from apps.monitor.services.alert_lifecycle_notify import (
    ACTION_TO_ALERT_CENTER,
    LEVEL_TO_ALERT_CENTER,
    AlertLifecycleNotifier,
)

pytestmark = pytest.mark.unit


def _alert(**kwargs):
    base = dict(
        id="alert-1",
        notice_type_ids=[],
        notice_users=[],
        notice_logs=[],
        content="CPU 超阈值",
        level="critical",
        monitor_instance_id="inst-1",
        monitor_instance_name="主机A",
        policy_id=7,
        value=88.5,
        status="active",
        start_event_time=datetime(2026, 1, 1, 10, 0, 0),
        end_event_time=None,
        dimensions={"k": "v"},
        metric_instance_id="m-1",
    )
    base.update(kwargs)
    return SimpleNamespace(**base)


class TestParseChannelResult:
    def test_非字典视为失败(self):
        ok, err = AlertLifecycleNotifier._parse_channel_result(None)
        assert ok is False and err == "invalid response"

    def test_归一化result为False(self):
        ok, err = AlertLifecycleNotifier._parse_channel_result({"result": False, "message": "boom"})
        assert ok is False and err == "boom"

    def test_企微errcode非零失败(self):
        ok, err = AlertLifecycleNotifier._parse_channel_result({"errcode": 40001, "errmsg": "bad token"})
        assert ok is False and err == "bad token"

    def test_飞书code非零失败(self):
        ok, err = AlertLifecycleNotifier._parse_channel_result({"code": 99, "msg": "fail"})
        assert ok is False and err == "fail"

    def test_errcode为零成功(self):
        ok, err = AlertLifecycleNotifier._parse_channel_result({"errcode": 0})
        assert ok is True and err == ""

    def test_无错误字段成功(self):
        ok, err = AlertLifecycleNotifier._parse_channel_result({"data": "x"})
        assert ok is True and err == ""

    def test_result为False无消息走默认(self):
        ok, err = AlertLifecycleNotifier._parse_channel_result({"result": False})
        assert ok is False and err == "Unknown error"


class TestBuildTitle:
    def test_带策略名(self):
        notifier = AlertLifecycleNotifier(policy=SimpleNamespace(name="磁盘策略"))
        assert notifier._build_title(_alert(), "created") == "告警产生：磁盘策略"

    def test_无策略名仅动作标签(self):
        notifier = AlertLifecycleNotifier(policy=None)
        assert notifier._build_title(_alert(), "recovered") == "告警恢复"

    def test_未知动作回退默认标签(self):
        notifier = AlertLifecycleNotifier(policy=None)
        assert notifier._build_title(_alert(), "weird") == "告警通知"


class TestBuildContent:
    def test_关闭动作含操作人与原因(self):
        notifier = AlertLifecycleNotifier(policy=None)
        content = notifier._build_content(_alert(), "closed", operator="admin", reason="误报")
        assert "操作人：admin" in content
        assert "原因：误报" in content
        assert "告警内容：CPU 超阈值" in content
        assert "资源：主机A" in content
        assert "级别：critical" in content
        assert "开始时间：2026-01-01 10:00:00" in content

    def test_升级动作状态行(self):
        notifier = AlertLifecycleNotifier(policy=None)
        content = notifier._build_content(_alert(), "upgraded", "", "")
        assert "状态：告警级别已升级" in content

    def test_恢复动作状态行(self):
        notifier = AlertLifecycleNotifier(policy=None)
        content = notifier._build_content(_alert(), "recovered", "", "")
        assert "状态：已自动恢复" in content

    def test_无实例名回退实例ID(self):
        notifier = AlertLifecycleNotifier(policy=None)
        alert = _alert(monitor_instance_name="")
        content = notifier._build_content(alert, "created", "", "")
        assert "资源：inst-1" in content


class TestBuildAlertCenterPayload:
    def test_字段映射与等级转换(self):
        policy = SimpleNamespace(name="策略X", organizations=[1, 2])
        notifier = AlertLifecycleNotifier(policy=policy)
        alert = _alert(end_event_time=datetime(2026, 1, 1, 11, 0, 0))
        payload = notifier._build_alert_center_payload(alert, "recovered", "op", "rsn", instance_org_map={})

        assert payload["external_id"] == "alert-1"
        assert payload["rule_id"] == "7"
        assert payload["title"] == "CPU 超阈值"
        assert payload["level"] == LEVEL_TO_ALERT_CENTER["critical"] == "0"
        assert payload["action"] == ACTION_TO_ALERT_CENTER["recovered"] == "recovery"
        assert payload["value"] == 88.5
        assert payload["start_time"] == str(int(alert.start_event_time.timestamp()))
        assert payload["end_time"] == str(int(alert.end_event_time.timestamp()))
        assert payload["resource_id"] == "inst-1"
        assert payload["resource_name"] == "主机A"
        # 实例无组织映射 -> 回退策略组织
        assert payload["organizations"] == [1, 2]
        assert payload["labels"]["policy_name"] == "策略X"
        assert payload["labels"]["operator"] == "op"
        assert payload["labels"]["reason"] == "rsn"
        assert payload["labels"]["status"] == "active"

    def test_未知动作默认created且value为None(self):
        notifier = AlertLifecycleNotifier(policy=None)
        alert = _alert(value=None, start_event_time=None)
        payload = notifier._build_alert_center_payload(alert, "unknown", "", "")
        assert payload["action"] == "created"
        assert payload["value"] is None
        assert payload["start_time"] is None

    def test_实例组织优先于策略组织(self):
        policy = SimpleNamespace(name="P", organizations=[99])
        notifier = AlertLifecycleNotifier(policy=policy)
        alert = _alert()
        payload = notifier._build_alert_center_payload(
            alert, "created", "", "", instance_org_map={"inst-1": [5, 6]}
        )
        assert payload["organizations"] == [5, 6]


class TestResolveNotice:
    def test_告警自带notice优先(self):
        notifier = AlertLifecycleNotifier(policy=SimpleNamespace(notice=True, notice_type_ids=[9], notice_users=["u9"]))
        alert = _alert(notice_type_ids=[1, 2], notice_users=["u1"])
        assert notifier._resolve_notice_type_ids(alert) == [1, 2]
        assert notifier._resolve_notice_users(alert) == ["u1"]

    def test_回退策略notice(self):
        notifier = AlertLifecycleNotifier(policy=SimpleNamespace(notice=True, notice_type_ids=[9], notice_users=["u9"]))
        alert = _alert(notice_type_ids=[], notice_users=[])
        assert notifier._resolve_notice_type_ids(alert) == [9]
        assert notifier._resolve_notice_users(alert) == ["u9"]

    def test_无策略返回空(self):
        notifier = AlertLifecycleNotifier(policy=None)
        alert = _alert(notice_type_ids=[], notice_users=[])
        assert notifier._resolve_notice_type_ids(alert) == []
        assert notifier._resolve_notice_users(alert) == []


class TestIsAlertCenterChannel:
    def test_nats告警中心渠道(self):
        ch = SimpleNamespace(channel_type="nats", config={"method_name": "receive_alert_events"})
        assert AlertLifecycleNotifier(None)._is_alert_center_channel(ch) is True

    def test_普通渠道(self):
        ch = SimpleNamespace(channel_type="wechat", config={})
        assert AlertLifecycleNotifier(None)._is_alert_center_channel(ch) is False

    def test_None渠道(self):
        assert AlertLifecycleNotifier(None)._is_alert_center_channel(None) is False


class TestHasSuccessfulCreatedNotice:
    def test_存在成功created记录(self):
        alert = _alert(
            notice_logs=[
                {"action": "created", "channel_id": 3, "success": True},
            ]
        )
        assert AlertLifecycleNotifier(None)._has_successful_created_notice(alert, 3) is True

    def test_渠道不匹配(self):
        alert = _alert(notice_logs=[{"action": "created", "channel_id": 99, "success": True}])
        assert AlertLifecycleNotifier(None)._has_successful_created_notice(alert, 3) is False

    def test_非created动作忽略(self):
        alert = _alert(notice_logs=[{"action": "recovered", "channel_id": 3, "success": True}])
        assert AlertLifecycleNotifier(None)._has_successful_created_notice(alert, 3) is False

    def test_非字典记录跳过(self):
        alert = _alert(notice_logs=["bad", {"action": "created", "channel_id": 3, "success": False}])
        assert AlertLifecycleNotifier(None)._has_successful_created_notice(alert, 3) is False


class TestShouldNotifyChannel:
    def _nats_channel(self):
        return SimpleNamespace(channel_type="nats", config={"method_name": "receive_alert_events"})

    def _normal_channel(self):
        return SimpleNamespace(channel_type="wechat", config={})

    def test_仅告警中心范围跳过普通渠道(self):
        notifier = AlertLifecycleNotifier(policy=None)
        assert notifier._should_notify_channel(_alert(), self._normal_channel(), 1, "created", "alert_center_only") is False

    def test_policy通知开启全部放行(self):
        notifier = AlertLifecycleNotifier(policy=SimpleNamespace(notice=True))
        assert notifier._should_notify_channel(_alert(), self._normal_channel(), 1, "created", "all_configured") is True

    def test_policy通知关闭created动作拦截(self):
        notifier = AlertLifecycleNotifier(policy=SimpleNamespace(notice=False))
        assert notifier._should_notify_channel(_alert(), self._normal_channel(), 1, "created", "all_configured") is False

    def test_policy关闭无成功created前置则拦截(self):
        notifier = AlertLifecycleNotifier(policy=SimpleNamespace(notice=False))
        alert = _alert(notice_logs=[])
        assert notifier._should_notify_channel(alert, self._normal_channel(), 1, "recovered", "all_configured") is False

    def test_policy关闭升级仅告警中心放行(self):
        notifier = AlertLifecycleNotifier(policy=SimpleNamespace(notice=False))
        alert = _alert(notice_logs=[{"action": "created", "channel_id": 1, "success": True}])
        # 普通渠道升级不放行
        assert notifier._should_notify_channel(alert, self._normal_channel(), 1, "upgraded", "all_configured") is False
        # 告警中心渠道升级放行
        assert notifier._should_notify_channel(alert, self._nats_channel(), 1, "upgraded", "all_configured") is True

    def test_policy关闭恢复有前置则放行(self):
        notifier = AlertLifecycleNotifier(policy=SimpleNamespace(notice=False))
        alert = _alert(notice_logs=[{"action": "created", "channel_id": 1, "success": True}])
        assert notifier._should_notify_channel(alert, self._normal_channel(), 1, "recovered", "all_configured") is True
