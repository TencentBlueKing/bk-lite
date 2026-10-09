"""平台渠道列表附带当前用户的悬浮栏宽度。"""

import json
from types import SimpleNamespace

import pytest
from rest_framework.test import APIRequestFactory

from apps.opspilot.models import UserWebchatPreference
from apps.opspilot.models.webchat_preference import DEFAULT_WEBCHAT_DOCK_WIDTH
from apps.opspilot.views.skill_channel import list_platform_skill_channels, save_platform_webchat_width

pytestmark = pytest.mark.unit


class _WidthQuery:
    def __init__(self, width):
        self._width = width

    def values_list(self, *args, **kwargs):
        return self

    def first(self):
        return self._width


def test_width_defaults_when_user_has_no_uuid():
    assert UserWebchatPreference.width_for_user_id(None) == DEFAULT_WEBCHAT_DOCK_WIDTH
    assert UserWebchatPreference.width_for_user_id("  ") == DEFAULT_WEBCHAT_DOCK_WIDTH


def test_width_defaults_when_row_missing(monkeypatch):
    monkeypatch.setattr(UserWebchatPreference.objects, "filter", lambda **kwargs: _WidthQuery(None))
    assert UserWebchatPreference.width_for_user_id("11111111-1111-1111-1111-111111111111") == DEFAULT_WEBCHAT_DOCK_WIDTH


def test_width_returns_saved_value(monkeypatch):
    monkeypatch.setattr(UserWebchatPreference.objects, "filter", lambda **kwargs: _WidthQuery(520))
    assert UserWebchatPreference.width_for_user_id("11111111-1111-1111-1111-111111111111") == 520


def test_platform_list_includes_default_width(monkeypatch):
    monkeypatch.setattr(
        "apps.opspilot.views.skill_channel.platform_channels_for_team",
        lambda team, groups: [],
    )
    monkeypatch.setattr(
        "apps.opspilot.views.skill_channel.resolve_system_user_uuid",
        lambda user, assign_if_missing=False: None,
    )
    request = APIRequestFactory().get("/skill_channel/platform/")
    request.user = SimpleNamespace(is_authenticated=True, group_list=[])
    request.COOKIES = {}

    response = list_platform_skill_channels(request)
    body = json.loads(response.content)

    assert response.status_code == 200
    assert body["result"] is True
    assert body["data"] == []
    assert body["webchat_width"] == DEFAULT_WEBCHAT_DOCK_WIDTH


def test_platform_list_includes_saved_width(monkeypatch):
    monkeypatch.setattr(
        "apps.opspilot.views.skill_channel.platform_channels_for_team",
        lambda team, groups: [],
    )
    monkeypatch.setattr(
        "apps.opspilot.views.skill_channel.resolve_system_user_uuid",
        lambda user, assign_if_missing=False: "11111111-1111-1111-1111-111111111111",
    )
    monkeypatch.setattr(UserWebchatPreference, "width_for_user_id", classmethod(lambda cls, user_id: 640))
    request = APIRequestFactory().get("/skill_channel/platform/")
    request.user = SimpleNamespace(is_authenticated=True, group_list=[])
    request.COOKIES = {}

    response = list_platform_skill_channels(request)
    body = json.loads(response.content)

    assert body["webchat_width"] == 640


def test_clamp_width_bounds():
    assert UserWebchatPreference.clamp_width(100) == 320
    assert UserWebchatPreference.clamp_width(900) == 900
    assert UserWebchatPreference.clamp_width(5000) == 3840
    assert UserWebchatPreference.clamp_width("bad") == DEFAULT_WEBCHAT_DOCK_WIDTH
    assert UserWebchatPreference.clamp_width(450) == 450


def test_save_platform_width(monkeypatch):
    monkeypatch.setattr(
        "apps.opspilot.views.skill_channel.resolve_system_user_uuid",
        lambda user, assign_if_missing=False: "11111111-1111-1111-1111-111111111111",
    )
    saved = {}

    def _save(user_id, value):
        saved["user_id"] = user_id
        saved["value"] = value
        return 450

    monkeypatch.setattr(
        UserWebchatPreference,
        "save_width_for_user_id",
        classmethod(lambda cls, user_id, value: _save(user_id, value)),
    )
    request = APIRequestFactory().post("/skill_channel/platform/width/", {"width": 450}, format="json")
    request.user = SimpleNamespace(is_authenticated=True)

    response = save_platform_webchat_width(request)
    body = json.loads(response.content)

    assert response.status_code == 200
    assert body["webchat_width"] == 450
    assert saved["value"] == 450
