"""opspilot.utils.bot_utils 辅助函数测试。

覆盖纯逻辑/可 mock 边界的函数：
- set_time_range：解析 ISO 时间字符串；空值回退当天 00:00:00 / 23:59:59.999999
- get_department_hierarchy：从子部门逐级回溯到根，返回根→子顺序
- get_ding_talk_user_groups：组装 {id,name} 列表（mock 钉钉 client）
- get_enterprise_wechat_user_groups：跨多部门去重（mock cache + client）
- insert_skill_log：skill_id 为 None 时早退、不写库
真实外部边界（钉钉/企微 client、cache、DB）均被 mock。
"""

import datetime

import pytest

from apps.opspilot.utils import bot_utils
from apps.opspilot.utils.bot_utils import (
    get_department_hierarchy,
    get_ding_talk_user_groups,
    get_enterprise_wechat_user_groups,
    set_time_range,
)

pytestmark = pytest.mark.unit


class TestSetTimeRange:
    def test_解析显式起止时间(self):
        end, start = set_time_range("2026-01-02T10:30:00.000000Z", "2026-01-01T08:00:00.000000Z")
        assert start == datetime.datetime(2026, 1, 1, 8, 0, 0)
        assert end == datetime.datetime(2026, 1, 2, 10, 30, 0)

    def test_空起始回退当天零点(self, mocker):
        fixed = datetime.datetime(2026, 5, 20, 15, 45, 30)
        mock_dt = mocker.patch("apps.opspilot.utils.bot_utils.datetime")
        mock_dt.datetime.today.return_value = fixed
        mock_dt.datetime.strptime = datetime.datetime.strptime

        end, start = set_time_range("", "")
        assert start == fixed.replace(hour=0, minute=0, second=0, microsecond=0)
        assert end == fixed.replace(hour=23, minute=59, second=59, microsecond=999999)

    def test_仅给起始_结束回退当天末刻(self, mocker):
        fixed = datetime.datetime(2026, 5, 20, 15, 45, 30)
        mock_dt = mocker.patch("apps.opspilot.utils.bot_utils.datetime")
        mock_dt.datetime.today.return_value = fixed
        mock_dt.datetime.strptime = datetime.datetime.strptime

        end, start = set_time_range("", "2026-05-01T00:00:00.000000Z")
        assert start == datetime.datetime(2026, 5, 1, 0, 0, 0)
        assert end == fixed.replace(hour=23, minute=59, second=59, microsecond=999999)


class TestGetDepartmentHierarchy:
    def _departments(self):
        return [
            {"id": 1, "name": "总部", "parentid": 0},
            {"id": 2, "name": "研发中心", "parentid": 1},
            {"id": 3, "name": "平台组", "parentid": 2},
        ]

    def test_逐级回溯并按根到子排序(self):
        result = get_department_hierarchy(3, self._departments())
        assert result == [
            {"id": 1, "name": "总部"},
            {"id": 2, "name": "研发中心"},
            {"id": 3, "name": "平台组"},
        ]

    def test_顶级部门只返回自身(self):
        result = get_department_hierarchy(1, self._departments())
        assert result == [{"id": 1, "name": "总部"}]

    def test_未知部门返回空(self):
        assert get_department_hierarchy(999, self._departments()) == []


class TestGetDingTalkUserGroups:
    def test_组装部门_id_与名称(self, mocker):
        client = mocker.Mock()
        client.get_user_department.return_value = [10, 20]
        client.get_department_name.side_effect = lambda i: f"dept-{i}"

        groups = get_ding_talk_user_groups("sender-1", client)
        assert groups == [{"id": 10, "name": "dept-10"}, {"id": 20, "name": "dept-20"}]
        client.get_user_department.assert_called_once_with("sender-1")

    def test_无部门返回空(self, mocker):
        client = mocker.Mock()
        client.get_user_department.return_value = []
        assert get_ding_talk_user_groups("s", client) == []


class TestGetEnterpriseWechatUserGroups:
    def _all_groups(self):
        return [
            {"id": 1, "name": "总部", "parentid": 0},
            {"id": 2, "name": "研发", "parentid": 1},
            {"id": 3, "name": "测试", "parentid": 1},
        ]

    def test_缓存命中时不调用_client(self, mocker):
        mocker.patch("apps.opspilot.utils.bot_utils.cache.get", return_value=self._all_groups())
        client = mocker.Mock()

        groups = get_enterprise_wechat_user_groups(client, [2], bot_id=7)
        # 命中缓存，不应调用 department.get
        client.department.get.assert_not_called()
        assert {g["id"] for g in groups} == {1, 2}

    def test_缓存未命中时回源_client(self, mocker):
        mocker.patch("apps.opspilot.utils.bot_utils.cache.get", return_value=None)
        client = mocker.Mock()
        client.department.get.return_value = self._all_groups()

        groups = get_enterprise_wechat_user_groups(client, [2], bot_id=7)
        client.department.get.assert_called_once()
        assert {g["id"] for g in groups} == {1, 2}

    def test_多部门层级去重(self, mocker):
        mocker.patch("apps.opspilot.utils.bot_utils.cache.get", return_value=self._all_groups())
        client = mocker.Mock()

        # 部门 2 与 3 共享父级 1，结果中 1 只出现一次
        groups = get_enterprise_wechat_user_groups(client, [2, 3], bot_id=7)
        ids = [g["id"] for g in groups]
        assert ids.count(1) == 1
        assert set(ids) == {1, 2, 3}


class TestInsertSkillLog:
    def test_skill_id_为_none_时早退不写库(self, mocker):
        create = mocker.patch("apps.opspilot.utils.bot_utils.SkillRequestLog.objects.create")
        result = bot_utils.insert_skill_log("127.0.0.1", None, {}, {})
        assert result is None
        create.assert_not_called()

    def test_有_skill_id_时写入日志(self, mocker):
        create = mocker.patch("apps.opspilot.utils.bot_utils.SkillRequestLog.objects.create")
        bot_utils.insert_skill_log(
            "10.0.0.5", 42, {"resp": 1}, {"req": 2}, state=False, user_message="hi"
        )
        create.assert_called_once_with(
            skill_id=42,
            response_detail={"resp": 1},
            request_detail={"req": 2},
            state=False,
            current_ip="10.0.0.5",
            user_message="hi",
        )
