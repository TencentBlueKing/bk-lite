"""console_mgmt 通知接口的生产规格测试。

规格要点（NotificationViewSet）：
- 创建/完整更新/部分更新一律 405（通知由 RPC 产生，只读 + 状态变更）；
- 已读/删除状态按用户隔离（NotificationRead 每用户独立）；
- destroy 为软删除：仅对当前用户隐藏，不影响他人；
- 列表默认排除当前用户已删除项，支持 app_module / unread_only 过滤；
- unread_count 统计当前用户未读（排除已删除/已读）。
"""

import pytest

from apps.console_mgmt.models import NotificationRead
from apps.console_mgmt.tests.factories import NotificationFactory

pytestmark = [pytest.mark.django_db, pytest.mark.integration]

BASE = "/api/v1/console_mgmt/notifications/"


def _list(resp):
    """列表接口经全局响应封装为 {code,data,message,result}，业务数据在 data。"""
    return resp.json()["data"]


class TestWriteContracts:
    def test_创建被禁用_405(self, user_client):
        _, client = user_client
        resp = client.post(BASE, data={"content": "x"}, format="json")
        assert resp.status_code == 405

    def test_完整更新被禁用_405(self, user_client):
        _, client = user_client
        n = NotificationFactory()
        resp = client.put(f"{BASE}{n.id}/", data={"content": "x"}, format="json")
        assert resp.status_code == 405

    def test_部分更新被禁用_405(self, user_client):
        _, client = user_client
        n = NotificationFactory()
        resp = client.patch(f"{BASE}{n.id}/", data={"content": "x"}, format="json")
        assert resp.status_code == 405


class TestListAndFilter:
    def test_列表返回全部通知(self, user_client):
        _, client = user_client
        NotificationFactory.create_batch(3)
        resp = client.get(BASE)
        assert resp.status_code == 200
        assert len(_list(resp)) == 3

    def test_按模块过滤(self, user_client):
        _, client = user_client
        NotificationFactory(app_module="monitor")
        NotificationFactory(app_module="cmdb")
        resp = client.get(BASE, {"app_module": "cmdb"})
        data = _list(resp)
        assert len(data) == 1
        assert data[0]["app_module"] == "cmdb"

    def test_unread_only_过滤已读(self, user_client):
        user, client = user_client
        read = NotificationFactory()
        NotificationFactory()  # 未读
        client.post(f"{BASE}{read.id}/mark_as_read/")
        resp = client.get(BASE, {"unread_only": "true"})
        assert len(_list(resp)) == 1


class TestPerUserIsolation:
    def test_软删除仅对当前用户隐藏(self, make_client):
        n = NotificationFactory()
        alice, ac = make_client("alice")
        bob, bc = make_client("bob")

        # alice 删除
        resp = ac.delete(f"{BASE}{n.id}/")
        assert resp.status_code == 200
        assert resp.json()["result"] is True

        # alice 看不到，bob 仍可见
        assert len(_list(ac.get(BASE))) == 0
        assert len(_list(bc.get(BASE))) == 1
        # 落库为软删除记录，原通知未被物理删除
        assert NotificationRead.objects.filter(notification=n, user=alice, is_deleted=True).exists()

    def test_已读状态按用户隔离(self, make_client):
        n = NotificationFactory()
        alice, ac = make_client("alice")
        bob, bc = make_client("bob")

        ac.post(f"{BASE}{n.id}/mark_as_read/")

        # alice 显示已读，bob 仍未读
        assert _list(ac.get(BASE))[0]["is_read"] is True
        assert _list(bc.get(BASE))[0]["is_read"] is False


class TestMarkActions:
    def test_mark_all_as_read(self, user_client):
        _, client = user_client
        NotificationFactory.create_batch(3)
        resp = client.post(f"{BASE}mark_all_as_read/")
        assert resp.json()["result"] is True
        assert _list(client.get(BASE, {"unread_only": "true"})) == []

    def test_mark_all_as_read_同时处理既有未读行与新行(self, user_client):
        """验证 DB 侧集合运算正确性：
        - 已有 is_read=False 的 NotificationRead 行必须被 UPDATE；
        - 尚无 NotificationRead 行的通知必须被 INSERT；
        - 返回的已标记数量 = 两者之和。
        revert-fail 准则：若去掉 UPDATE 步骤，n2_read 仍为 False，断言失败。
        """
        user, client = user_client
        n1 = NotificationFactory()  # 有 NotificationRead(is_read=False) 的情况
        n2 = NotificationFactory()  # 完全无 NotificationRead 行的情况
        n3 = NotificationFactory()  # 已经 is_read=True，不应计入

        NotificationRead.objects.create(notification=n1, user=user, is_read=False)
        NotificationRead.objects.create(notification=n3, user=user, is_read=True)

        resp = client.post(f"{BASE}mark_all_as_read/")
        data = resp.json()
        assert data["result"] is True
        # n1(UPDATE) + n2(INSERT) = 2；n3 已读不重复计
        assert "已标记 2 条" in data["message"]

        # DB 状态验证
        assert NotificationRead.objects.get(notification=n1, user=user).is_read is True
        assert NotificationRead.objects.get(notification=n2, user=user).is_read is True

    def test_mark_all_as_read_已全部已读时无操作(self, user_client):
        """所有通知均已有 is_read=True 行时，返回 0 条已标记。"""
        user, client = user_client
        n = NotificationFactory()
        NotificationRead.objects.create(notification=n, user=user, is_read=True)

        resp = client.post(f"{BASE}mark_all_as_read/")
        assert resp.json()["result"] is True
        assert "已标记 0 条" in resp.json()["message"]

    def test_mark_batch_as_read_拒绝非整数数组(self, user_client):
        """revert-fail：若去掉 serializer 校验，字符串会被 set(ids) 拆成字符集合继续写库。"""
        _, client = user_client

        for payload in ({"ids": "123"}, {"ids": [1, "x"]}, {"ids": []}):
            resp = client.post(f"{BASE}mark_batch_as_read/", data=payload, format="json")
            assert resp.status_code == 400
            assert resp.json()["result"] is False

    def test_mark_batch_as_read_过滤不存在的通知ID(self, user_client):
        """revert-fail：若直接 bulk_create 缺失 ID，数据库外键会抛 IntegrityError。"""
        user, client = user_client
        notification = NotificationFactory()
        missing_id = notification.id + 10000

        resp = client.post(
            f"{BASE}mark_batch_as_read/",
            data={"ids": [notification.id, missing_id]},
            format="json",
        )

        data = resp.json()
        assert resp.status_code == 200
        assert data["result"] is True
        assert data["data"]["skipped_ids"] == [missing_id]
        assert NotificationRead.objects.filter(notification=notification, user=user, is_read=True).exists()
        assert not NotificationRead.objects.filter(notification_id=missing_id, user=user).exists()

    def test_unread_count_排除已读与已删除(self, user_client):
        _, client = user_client
        read = NotificationFactory()
        deleted = NotificationFactory()
        NotificationFactory()  # 仍未读
        client.post(f"{BASE}{read.id}/mark_as_read/")
        client.delete(f"{BASE}{deleted.id}/")
        resp = client.get(f"{BASE}unread_count/")
        assert resp.json()["data"]["count"] == 1
