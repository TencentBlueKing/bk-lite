import importlib.util
import sys
import types
from pathlib import Path
from types import SimpleNamespace

import pytest
from rest_framework import serializers, viewsets


class _Objects:
    @staticmethod
    def all():
        return object()


class _Channel:
    objects = _Objects()


class _ChannelSerializer(serializers.Serializer):
    pass


@pytest.fixture
def channel_view_module(monkeypatch):
    opspilot = types.ModuleType("apps.opspilot")
    opspilot.__path__ = []
    models = types.ModuleType("apps.opspilot.models")
    models.Channel = _Channel
    channel_serializers = types.ModuleType("apps.opspilot.serializers")
    channel_serializers.ChannelSerializer = _ChannelSerializer
    operation_log = types.ModuleType("apps.system_mgmt.utils.operation_log_utils")
    operation_log.log_operation = lambda *args, **kwargs: None

    monkeypatch.setitem(sys.modules, "apps.opspilot", opspilot)
    monkeypatch.setitem(sys.modules, "apps.opspilot.models", models)
    monkeypatch.setitem(sys.modules, "apps.opspilot.serializers", channel_serializers)
    monkeypatch.setitem(sys.modules, "apps.system_mgmt.utils.operation_log_utils", operation_log)

    path = Path(__file__).parents[2] / "opspilot/viewsets/channel_view.py"
    spec = importlib.util.spec_from_file_location("issue4033_channel_view", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _request(*, is_superuser):
    return SimpleNamespace(
        user=SimpleNamespace(is_superuser=is_superuser, roles=[], locale="en"),
        data={},
    )


@pytest.mark.parametrize("action", ["list", "retrieve", "create", "update", "partial_update", "destroy"])
def test_channel_crud_rejects_non_admin(channel_view_module, mocker, action):
    view = channel_view_module.ChannelViewSet()
    parent_action = "update" if action == "partial_update" else action
    parent = mocker.patch.object(viewsets.ModelViewSet, parent_action, side_effect=AssertionError("parent called"))

    response = getattr(view, action)(_request(is_superuser=False), pk=1)

    assert response.status_code == 403
    parent.assert_not_called()


@pytest.mark.parametrize("action", ["list", "retrieve", "create", "update", "partial_update", "destroy"])
def test_channel_crud_keeps_superuser_access(channel_view_module, mocker, action):
    view = channel_view_module.ChannelViewSet()
    expected = SimpleNamespace(status_code=200, data={})
    parent_action = "update" if action == "partial_update" else action
    parent = mocker.patch.object(viewsets.ModelViewSet, parent_action, return_value=expected)
    if action == "destroy":
        mocker.patch.object(view, "get_object", return_value=SimpleNamespace(name="protected"))

    response = getattr(view, action)(_request(is_superuser=True), pk=1)

    assert response is expected
    parent.assert_called_once()
