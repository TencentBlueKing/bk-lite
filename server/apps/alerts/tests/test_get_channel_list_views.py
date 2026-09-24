# -- coding: utf-8 --
"""get_channel_list 视图测试：只返回告警出口真实支持的渠道。"""

import json
from unittest.mock import patch

import pytest
from rest_framework.test import APIRequestFactory, force_authenticate

from apps.alerts.views.system_setting import SystemSettingModelViewSet
from apps.system_mgmt.models.channel import Channel
from apps.system_mgmt.models.im_notification_channel import IMNotificationChannel
from apps.system_mgmt.models.integration_instance import IntegrationInstance


def _render(response):
    # WebUtils.response_success returns a JsonResponse (Django), not a DRF Response.
    # JsonResponse has .content (bytes); DRF Response needs .render() first.
    if hasattr(response, "render") and callable(response.render):
        try:
            response.render()
            return json.loads(response.rendered_content)
        except Exception:
            pass
    return json.loads(response.content)


@pytest.mark.django_db
def test_get_channel_list_merges_managed_workflow_channels_and_excludes_plain_nats(authenticated_user):
    authenticated_user.is_superuser = True
    authenticated_user.save(update_fields=["is_superuser"])
    Channel.objects.create(name="邮件A", channel_type="email", config={}, description="", team=[1])
    Channel.objects.create(name="外组织邮件", channel_type="email", config={}, description="", team=[2])
    Channel.objects.create(name="企微应用", channel_type="enterprise_wechat", config={}, description="", team=[1])
    Channel.objects.create(
        name="内部直推",
        channel_type="nats",
        config={"method_name": "receive_alert_events"},
        description="",
        team=[],
    )
    instance = IntegrationInstance.objects.create(
        name="feishu-im",
        provider_key="feishu",
        enabled=True,
        status="ready",
        capability_status={"im_notification": "ready"},
        config={},
    )
    IMNotificationChannel.objects.create(
        name="值班飞书",
        integration_instance=instance,
        enabled=True,
        team=[1],
    )
    IMNotificationChannel.objects.create(
        name="已停用IM",
        integration_instance=instance,
        enabled=False,
        team=[1],
    )
    IMNotificationChannel.objects.create(
        name="外组织IM",
        integration_instance=instance,
        enabled=True,
        team=[2],
    )

    factory = APIRequestFactory()
    request = factory.get("/api/settings/get_channel_list/")
    force_authenticate(request, user=authenticated_user)
    request.COOKIES["current_team"] = "1"

    opspilot = [{"id": 99, "name": "BotA - NATS触发", "team": [2], "bot_id": 12, "node_id": "nats_entry"}]
    orchestration = [{"id": 100, "name": "主机巡检 - 告警入口", "team": [1], "workflow_id": 8, "node_key": "nats_alert"}]
    with patch(
        "apps.alerts.views.system_setting.SystemMgmtUtils.search_opspilot_nats_channels",
        return_value=opspilot,
    ), patch(
        "apps.alerts.views.system_setting.SystemMgmtUtils.search_workflow_orchestration_nats_channels",
        return_value=orchestration,
    ):
        response = SystemSettingModelViewSet.as_view({"get": "get_channel_list"})(request)

    data = _render(response)["data"]
    # 当前组织 email 在，外组织 email 不在
    assert any(item["channel_type"] == "email" and item["team"] == [1] for item in data)
    assert not any("外组织邮件" in item["name"] for item in data)
    # opspilot nats 通道并入（id=99, channel_type=nats）
    assert any(item["id"] == 99 and item["channel_type"] == "nats" and item["team"] == [2] for item in data)
    assert any(item["id"] == 100 and item["channel_type"] == "nats" and item["team"] == [1] for item in data)
    # 普通 nats（内部直推）被排除
    assert not any("内部直推" in item["name"] for item in data)
    wechat = next(item for item in data if "企微应用" in item["name"])
    assert wechat["channel_type"] == "enterprise_wechat"
    im = next(item for item in data if "值班飞书" in item["name"])
    assert im["channel_type"] == "im_notification"
    assert not any("已停用IM" in item["name"] for item in data)
    assert not any("外组织IM" in item["name"] for item in data)
