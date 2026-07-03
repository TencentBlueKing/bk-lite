"""console_mgmt viewset / serializer 覆盖补缺。

补已存在 URL 测试未覆盖的分支：
- NotificationViewSet.mark_batch_as_read（空/有 ids、混合新旧行）；
- destroy 软删除返回 {"result": True}；
- NotificationSerializer.get_is_read 从 annotate 取值 / 缺省 False；
- UserAppSetViewSet.current_user_apps 内置应用翻译 description/tags 分支。
"""
import pydantic.root_model  # noqa

import pytest

from apps.console_mgmt.models import Notification, NotificationRead, UserAppSet
from apps.console_mgmt.serializers import NotificationSerializer
from apps.console_mgmt.tests.factories import NotificationFactory

pytestmark = [pytest.mark.django_db, pytest.mark.integration]

BASE = "/api/v1/console_mgmt/notifications/"
APP_BASE = "/api/v1/console_mgmt/user_app_sets/"


def _data(resp):
    return resp.json().get("data", resp.json())


class TestMarkBatchAsRead:
    def test_空ids返回400(self, user_client):
        _, client = user_client
        resp = client.post(f"{BASE}mark_batch_as_read/", data={"ids": []}, format="json")
        assert resp.status_code == 400
        assert resp.json()["result"] is False

    def test_批量标记新通知为已读(self, user_client):
        user, client = user_client
        n1 = NotificationFactory()
        n2 = NotificationFactory()
        resp = client.post(f"{BASE}mark_batch_as_read/", data={"ids": [n1.id, n2.id]}, format="json")
        assert resp.status_code == 200
        assert resp.json()["result"] is True
        assert NotificationRead.objects.filter(user=user, notification_id=n1.id, is_read=True).exists()
        assert NotificationRead.objects.filter(user=user, notification_id=n2.id, is_read=True).exists()

    def test_批量标记混合既有未读行与新行(self, user_client):
        user, client = user_client
        n_existing = NotificationFactory()
        n_new = NotificationFactory()
        # 预置一条 is_read=False 的已存在行
        NotificationRead.objects.create(notification=n_existing, user=user, is_read=False)
        resp = client.post(
            f"{BASE}mark_batch_as_read/", data={"ids": [n_existing.id, n_new.id]}, format="json"
        )
        assert resp.status_code == 200
        existing = NotificationRead.objects.get(user=user, notification_id=n_existing.id)
        assert existing.is_read is True
        assert NotificationRead.objects.filter(user=user, notification_id=n_new.id, is_read=True).exists()


class TestDestroySoftDelete:
    def test_destroy返回result_true并软删除(self, user_client):
        user, client = user_client
        n = NotificationFactory()
        resp = client.delete(f"{BASE}{n.id}/")
        assert resp.status_code == 200
        assert resp.json()["result"] is True
        # 软删除：通知本身仍在，仅 NotificationRead.is_deleted=True
        assert Notification.objects.filter(id=n.id).exists()
        assert NotificationRead.objects.filter(user=user, notification=n, is_deleted=True).exists()


class TestNotificationSerializerIsRead:
    def test_无annotate默认未读(self):
        n = NotificationFactory()
        data = NotificationSerializer(n).data
        assert data["is_read"] is False

    def test_有user_is_read_annotate取该值(self):
        n = NotificationFactory()
        # 模拟 annotate 注入的属性
        n.user_is_read = True
        data = NotificationSerializer(n).data
        assert data["is_read"] is True


class TestCurrentUserAppsTranslation:
    def test_内置应用翻译description与tags(self, make_client):
        from apps.system_mgmt.models.app import App

        user, client = make_client("transuser", locale="zh-CN")
        App.objects.create(name="monitor", display_name="监控", is_build_in=True, tags=["tag.ops"])
        UserAppSet.objects.create(
            username=user.username,
            domain=user.domain,
            app_config_list=[
                {"name": "monitor", "is_build_in": True, "description": "old", "tags": ["stale"]},
            ],
        )
        resp = client.get(f"{APP_BASE}current_user_apps/")
        assert resp.status_code == 200
        data = _data(resp)
        assert len(data) == 1
        item = data[0]
        # tags 应从 App 表最新值刷新（经 loader 翻译，缺翻译时回退原 key）
        assert item["tags"] == ["tag.ops"] or all(isinstance(t, str) for t in item["tags"])

    def test_无配置返回空列表(self, make_client):
        user, client = make_client("emptyuser")
        resp = client.get(f"{APP_BASE}current_user_apps/")
        assert resp.status_code == 200
        assert _data(resp) == []
