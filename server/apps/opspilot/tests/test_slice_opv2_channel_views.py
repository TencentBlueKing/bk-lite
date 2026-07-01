"""opspilot-views2 切片: viewsets/channel_view.ChannelViewSet 真实 DRF + DB 测试。

通过 APIRequestFactory 真实驱动 DRF ModelViewSet、真实 ORM 落库，断言:
- create 落库 Channel 并写 OperationLog(create);
- update 修改字段并写 OperationLog(update);
- destroy 物理删除并写 OperationLog(delete);
- name icontains 过滤生效;
- ChannelSerializer 读取时对密钥字段脱敏(format_channel_config)。
不 mock 任何外部边界——log_operation/Channel 加解密均走真实 DB/Fernet。
"""

import pydantic.root_model  # noqa
import pytest
from rest_framework.test import APIRequestFactory, force_authenticate

from apps.opspilot.models import Channel
from apps.opspilot.viewsets.channel_view import ChannelViewSet

pytestmark = pytest.mark.django_db


def _json(resp):
    import json

    if hasattr(resp, "data"):
        return resp.data
    return json.loads(resp.content.decode("utf-8"))


def _user():
    from apps.base.models import User

    u = User.objects.create_user(
        username=f"ch_su_{User.objects.count()}",
        password="x",
        domain="domain.com",
        locale="en",
        group_list=[{"id": 1, "name": "T1"}],
    )
    u.is_superuser = True
    u.save()
    return u


def _op_count():
    from apps.system_mgmt.models import OperationLog

    return OperationLog.objects.filter(app="opspilot").count()


class TestCreate:
    def test_create_落库并写操作日志(self):
        user = _user()
        before = _op_count()
        factory = APIRequestFactory()
        request = factory.post(
            "/",
            data={"name": "ch-a", "channel_type": "web", "enabled": True},
            format="json",
        )
        force_authenticate(request, user=user)
        resp = ChannelViewSet.as_view({"post": "create"})(request)

        assert resp.status_code == 201
        body = _json(resp)
        assert body["name"] == "ch-a"
        # 真实落库
        obj = Channel.objects.get(id=body["id"])
        assert obj.channel_type == "web"
        assert obj.enabled is True
        # 写了一条操作日志
        from apps.system_mgmt.models import OperationLog

        assert _op_count() == before + 1
        log = OperationLog.objects.filter(app="opspilot", action_type="create").latest("id")
        assert "新增渠道: ch-a" == log.summary


class TestUpdate:
    def test_update_修改字段并写操作日志(self):
        user = _user()
        ch = Channel.objects.create(name="old", channel_type="web", enabled=False)
        before = _op_count()
        factory = APIRequestFactory()
        request = factory.put(
            "/",
            data={"name": "new-name", "channel_type": "web", "enabled": True},
            format="json",
        )
        force_authenticate(request, user=user)
        resp = ChannelViewSet.as_view({"put": "update"})(request, pk=ch.id)

        assert resp.status_code == 200
        ch.refresh_from_db()
        assert ch.name == "new-name"
        assert ch.enabled is True
        assert _op_count() == before + 1
        from apps.system_mgmt.models import OperationLog

        log = OperationLog.objects.filter(app="opspilot", action_type="update").latest("id")
        assert log.summary == "编辑渠道: new-name"


class TestDestroy:
    def test_destroy_物理删除并写操作日志(self):
        user = _user()
        ch = Channel.objects.create(name="to-del", channel_type="web")
        ch_id = ch.id
        before = _op_count()
        factory = APIRequestFactory()
        request = factory.delete("/")
        force_authenticate(request, user=user)
        resp = ChannelViewSet.as_view({"delete": "destroy"})(request, pk=ch_id)

        assert resp.status_code == 204
        assert not Channel.objects.filter(id=ch_id).exists()
        assert _op_count() == before + 1
        from apps.system_mgmt.models import OperationLog

        log = OperationLog.objects.filter(app="opspilot", action_type="delete").latest("id")
        assert log.summary == "删除渠道: to-del"


class TestListFilter:
    def test_name_icontains过滤(self):
        user = _user()
        Channel.objects.create(name="alpha-web", channel_type="web")
        Channel.objects.create(name="beta-web", channel_type="web")
        factory = APIRequestFactory()
        request = factory.get("/?name=alpha")
        force_authenticate(request, user=user)
        resp = ChannelViewSet.as_view({"get": "list"})(request)

        assert resp.status_code == 200
        names = {item["name"] for item in _json(resp)}
        assert "alpha-web" in names
        assert "beta-web" not in names


class TestSerializerMasking:
    def test_读取时密钥字段脱敏(self):
        """channel_config 内 secret/token/aes_key/client_secret 读取时被掩码为 ******。"""
        user = _user()
        # web 渠道不在 CHANNEL_ENCRYPT_CONFIG 中，save 不加密;format_channel_config 仍掩码展示
        ch = Channel.objects.create(
            name="cfg",
            channel_type="web",
            channel_config={"some_key": {"secret": "s3cr3t", "url": "http://x"}},
        )
        factory = APIRequestFactory()
        request = factory.get("/")
        force_authenticate(request, user=user)
        resp = ChannelViewSet.as_view({"get": "retrieve"})(request, pk=ch.id)

        assert resp.status_code == 200
        cfg = _json(resp)["channel_config"]
        assert cfg["some_key"]["secret"] == "******"
        # 非敏感字段保持原值
        assert cfg["some_key"]["url"] == "http://x"

    def test_空config直接返回(self):
        user = _user()
        ch = Channel.objects.create(name="empty", channel_type="web", channel_config=None)
        factory = APIRequestFactory()
        request = factory.get("/")
        force_authenticate(request, user=user)
        resp = ChannelViewSet.as_view({"get": "retrieve"})(request, pk=ch.id)
        assert resp.status_code == 200
        assert _json(resp)["channel_config"] is None
