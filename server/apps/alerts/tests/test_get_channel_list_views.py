# -- coding: utf-8 --
"""get_channel_list 视图测试：并入 opspilot 托管 nats 通道，排除普通 nats。"""

import json

import pytest
from unittest.mock import patch
from rest_framework.test import APIRequestFactory, force_authenticate

from apps.alerts.views.system_setting import SystemSettingModelViewSet
from apps.system_mgmt.models.channel import Channel


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
def test_get_channel_list_merges_opspilot_and_excludes_plain_nats(authenticated_user):
    Channel.objects.create(name="邮件A", channel_type="email", config={}, description="", team=[])
    Channel.objects.create(
        name="内部直推", channel_type="nats",
        config={"method_name": "receive_alert_events"}, description="", team=[],
    )

    factory = APIRequestFactory()
    request = factory.get("/api/settings/get_channel_list/")
    force_authenticate(request, user=authenticated_user)

    opspilot = [{"id": 99, "name": "BotA - NATS触发", "team": [2], "bot_id": 12, "node_id": "nats_entry"}]
    with patch(
        "apps.alerts.views.system_setting.SystemMgmtUtils.search_opspilot_nats_channels",
        return_value=opspilot,
    ):
        response = SystemSettingModelViewSet.as_view({"get": "get_channel_list"})(request)

    data = _render(response)["data"]
    # 普通 email 在
    assert any(item["channel_type"] == "email" for item in data)
    # opspilot nats 通道并入（id=99, channel_type=nats）
    assert any(item["id"] == 99 and item["channel_type"] == "nats" for item in data)
    # 普通 nats（内部直推）被排除
    assert not any("内部直推" in item["name"] for item in data)
