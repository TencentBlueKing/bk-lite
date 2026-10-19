"""失败响应里已经写好的 message 应原样返回，不能再拼成 result:False;message:..."""

import inspect
import json
from types import SimpleNamespace

from rest_framework import status

from config.drf.renderers import CustomRenderer, EventStreamRenderer


def _render(data, status_code):
    renderer = CustomRenderer()
    response = SimpleNamespace(status_code=status_code)
    raw = renderer.render(data, renderer_context={"request": None, "response": response})
    return json.loads(raw)


def test_explicit_error_message_is_not_joined():
    body = _render(
        {"result": False, "message": "The skill package is missing SKILL.md"},
        status.HTTP_400_BAD_REQUEST,
    )
    assert body["result"] is False
    assert body["message"] == "The skill package is missing SKILL.md"


def test_field_validation_errors_are_still_joined():
    body = _render({"name": ["This field is required."]}, status.HTTP_400_BAD_REQUEST)
    assert body["message"] == "name:This field is required."


def test_renderer_does_not_localize_opspilot_errors():
    """英文文案由 opspilot 中间件处理，全局 renderer 不点名 optional app。"""
    renderer = CustomRenderer()
    response = SimpleNamespace(status_code=status.HTTP_400_BAD_REQUEST)
    view = SimpleNamespace(loader=SimpleNamespace(app="opspilot", default_lang="en"))
    raw = renderer.render(
        {"message": "供应商不能为空"},
        renderer_context={"request": None, "response": response, "view": view},
    )
    body = json.loads(raw)
    assert body["message"] == "供应商不能为空"
    assert "apps.opspilot" not in inspect.getsource(CustomRenderer)
    assert "localize_returned_text" not in inspect.getsource(CustomRenderer)
    assert "apps.opspilot" not in inspect.getsource(EventStreamRenderer)
