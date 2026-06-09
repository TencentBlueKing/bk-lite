"""Webhook 告警源适配器覆盖测试。

对照 spec/prd/告警中心·集成：Webhook 源接收推送请求并转换为事件。
"""

import json

import pytest
from rest_framework.test import APIRequestFactory

from apps.alerts.common.source_adapter.webhook import WebhookAdapter
from apps.alerts.models.alert_source import AlertSource
from apps.alerts.models.models import Level


@pytest.fixture
def event_levels(db):
    from apps.alerts.constants.constants import LevelType

    for lid in (0, 1, 2, 3):
        Level.objects.create(level_id=lid, level_name=f"L{lid}", level_display_name=f"等级{lid}", level_type=LevelType.EVENT)


@pytest.fixture
def webhook_source(db):
    return AlertSource.objects.create(
        name="wh", source_id="wh", source_type="webhook", secret="x",
        config={"event_fields_mapping": {"title": "title", "level": "level", "item": "item", "start_time": "start_time"}},
    )


def test_validate_config_and_connection():
    assert WebhookAdapter.validate_config({}) is True
    assert WebhookAdapter.test_connection(WebhookAdapter.__new__(WebhookAdapter)) is True
    assert WebhookAdapter.fetch_alerts(WebhookAdapter.__new__(WebhookAdapter)) == []


@pytest.mark.django_db
def test_process_webhook_request_json(event_levels, webhook_source):
    adapter = WebhookAdapter(alert_source=webhook_source)
    factory = APIRequestFactory()
    body = {"title": "事件A", "level": "0", "item": "cpu", "start_time": "1700000000"}
    request = factory.post("/wh/", data=json.dumps(body), content_type="application/json")
    event = adapter.process_webhook_request(request)
    assert event.title == "事件A"


@pytest.mark.django_db
def test_process_webhook_request_invalid_raises(event_levels, webhook_source):
    adapter = WebhookAdapter(alert_source=webhook_source)
    factory = APIRequestFactory()
    request = factory.post("/wh/", data="not json", content_type="application/json")
    with pytest.raises(Exception):
        adapter.process_webhook_request(request)
