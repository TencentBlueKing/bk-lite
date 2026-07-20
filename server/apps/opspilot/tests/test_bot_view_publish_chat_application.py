"""BotViewSet.update 发布 workflow 时,ChatApplication 必须正确创建(回归保护)。

Issue 现场:用户配置 workflow 里的 web_chat 节点 → 保存并发布(is_publish=True)
→ /opspilot/studio/chat 应用对话页面列表查不到这个 app。
再次点开 web 应用节点保存才出现。

根因(已修):BotViewSet.update 中 flow.save() 末尾会触发
ChatApplication.sync_applications_from_workflow,这个方法按 bot.online 决定
create / delete:
  - bot.online=False → 删除所有 ChatApplication
  - bot.online=True  → 创建/更新
原 update 顺序是 flow.save() 先于 obj.online = is_publish,导致 sync 读到旧值
False,把刚配的 web_chat 应用全删了。后续即使 obj.online=True,也没有再触发 sync
去重建。

修复:把 obj.online = is_publish 与 obj.save() 提到 flow.save() 之前,确保 sync
读到最新 online=True。

测试覆盖:端到端跑 BotViewSet.update,验证 is_publish=True + workflow 含
web_chat 节点时,ChatApplication 立即创建成功(无需二次保存)。
"""

from unittest.mock import patch

import pytest
from rest_framework.test import APIRequestFactory, force_authenticate

from apps.base.models import User
from apps.opspilot.models import Bot, BotWorkFlow, ChatApplication
from apps.opspilot.viewsets.bot_view import BotViewSet

pytestmark = pytest.mark.django_db


def _make_superuser(username="bot_pub_su"):
    user = User.objects.create_user(
        username=username,
        password="x",
        domain="domain.com",
        locale="en",
        group_list=[{"id": 1, "name": "T1"}],
        roles=["admin"],
    )
    user.is_superuser = True
    user.save()
    return user


def _make_chatflow_bot(user):
    bot = Bot.objects.create(
        name="chatflow-bot",
        bot_type=3,  # 3 = CHAT_FLOW
        online=False,
        team=[1],
        created_by=user.username,
        updated_by=user.username,
    )
    BotWorkFlow.objects.create(
        bot=bot,
        flow_json={"nodes": [], "edges": []},
        web_json={"nodes": [], "edges": []},
    )
    return bot


def _patch_celery():
    """Mock create_celery_task + sync_opspilot_nats_channels_for_bot,避免 Celery / NATS 依赖。"""
    return [
        patch("apps.opspilot.viewsets.bot_view.create_celery_task", lambda bot_id, work_data: None),
        patch(
            "apps.opspilot.viewsets.bot_view.sync_opspilot_nats_channels_for_bot",
            lambda bot: None,
        ),
    ]


def _put_update(user, bot, body):
    factory = APIRequestFactory()
    request = factory.put("/", data=body, format="json")
    force_authenticate(request, user=user)
    request.COOKIES["current_team"] = "1"
    view = BotViewSet.as_view({"put": "update"})
    return view(request, pk=bot.id)


def _web_chat_workflow():
    """含一个 web_chat 入口节点的 workflow_data。"""
    return {
        "nodes": [
            {
                "id": "node-web-1",
                "type": "web_chat",
                "data": {
                    "type": "web_chat",
                    "config": {
                        "appName": "测试应用",
                        "appIcon": "duihuazhinengti",
                        "appDescription": "一个测试 web chat 应用",
                    },
                },
            }
        ],
        "edges": [],
    }


class TestPublishCreatesChatApplication:
    """workflow publish 时 ChatApplication 必须立即创建(无需再保存一次)。"""

    def test_publish_with_web_chat_creates_chat_application(self):
        user = _make_superuser()
        bot = _make_chatflow_bot(user)

        body = {
            "workflow_data": _web_chat_workflow(),
            "is_publish": True,
        }

        with _patch_celery()[0], _patch_celery()[1]:
            response = _put_update(user, bot, body)

        assert response.status_code == 200, response.content
        bot.refresh_from_db()
        assert bot.online is True, "publish 后 bot.online 必须为 True"

        apps = ChatApplication.objects.filter(bot=bot)
        assert apps.count() == 1, f"应创建 1 个 ChatApplication,实际 {apps.count()} 个"
        app = apps.first()
        assert app.node_id == "node-web-1"
        assert app.app_type == "web_chat"
        assert app.app_name == "测试应用"
        assert app.app_description == "一个测试 web chat 应用"
        assert app.app_icon == "duihuazhinengti"

    def test_save_without_publish_does_not_create_chat_application(self):
        """仅保存不发布(online 仍 False),sync 会删 ChatApplication;新建 workflow
        没有 app 可删,所以最终 0 条。这是当前产品行为,锁定它。"""
        user = _make_superuser()
        bot = _make_chatflow_bot(user)

        body = {
            "workflow_data": _web_chat_workflow(),
            "is_publish": False,
        }

        with _patch_celery()[0], _patch_celery()[1]:
            response = _put_update(user, bot, body)

        assert response.status_code == 200
        bot.refresh_from_db()
        assert bot.online is False
        # sync 在 online=False 时删所有相关应用,新建 0 条
        assert ChatApplication.objects.filter(bot=bot).count() == 0

    def test_publish_then_workflow_update_keeps_chat_application(self):
        """连续两次 publish:第一次创建,第二次更新 app_name,记录不被删,数量仍为 1。"""
        user = _make_superuser()
        bot = _make_chatflow_bot(user)

        with _patch_celery()[0], _patch_celery()[1]:
            # 第一次 publish
            _put_update(user, bot, {"workflow_data": _web_chat_workflow(), "is_publish": True})
            assert ChatApplication.objects.filter(bot=bot).count() == 1

            # 第二次更新 appName
            wf2 = {
                "nodes": [
                    {
                        "id": "node-web-1",
                        "type": "web_chat",
                        "data": {
                            "type": "web_chat",
                            "config": {
                                "appName": "新名字",
                                "appIcon": "duihuazhinengti",
                                "appDescription": "改个名",
                            },
                        },
                    }
                ],
                "edges": [],
            }
            _put_update(user, bot, {"workflow_data": wf2, "is_publish": True})

        apps = ChatApplication.objects.filter(bot=bot)
        assert apps.count() == 1, "node_id 不变,应更新而非新建,数量仍 1"
        apps.first().app_name == "新名字"
        assert apps.first().app_name == "新名字"
