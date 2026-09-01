"""OpsPilot NATS：模块列表/分页与工作流触发行为。"""
from types import SimpleNamespace
from unittest.mock import patch

import pytest

from apps.opspilot.models import Bot, BotWorkFlow, LLMSkill
from apps.opspilot.nats_api import get_opspilot_module_data, get_opspilot_module_list, trigger_workflow_by_nats

pytestmark = pytest.mark.django_db


def test_get_opspilot_module_list_and_unknown_module():
    modules = get_opspilot_module_list()
    assert modules[0] == {"name": "bot", "display_name": "Studio"}
    provider = [m for m in modules if m["name"] == "provider"][0]
    assert [c["name"] for c in provider["children"]] == [
        "llm_model",
        "ocr_model",
        "embed_model",
        "rerank_model",
    ]
    assert get_opspilot_module_data("unknown", None, 1, 10, 1) == {
        "result": False,
        "message": "Unknown module: unknown",
    }
    assert get_opspilot_module_data("provider", "bad", 1, 10, 1) == {
        "result": False,
        "message": "Unknown child_module: bad",
    }


def test_get_opspilot_module_data_pages_team_scoped_items():
    Bot.objects.create(name="in-team", team=[3])
    Bot.objects.create(name="other-team", team=[9])
    LLMSkill.objects.create(name="skill-in", team=[3])
    out = get_opspilot_module_data("bot", None, 1, 10, 3)
    assert out["count"] == 1
    assert out["items"] == [{"id": Bot.objects.get(name="in-team").id, "name": "in-team"}]
    skill_out = get_opspilot_module_data("skill", None, 1, 10, 3)
    assert skill_out["count"] == 1
    assert skill_out["items"][0]["name"] == "skill-in"


def test_trigger_workflow_by_nats_missing_workflow_and_engine_success():
    assert trigger_workflow_by_nats("", 1, ["u"], 1, "n1") == {
        "result": False,
        "message": "message is required",
    }
    bot = Bot.objects.create(name="nats-bot", team=[1])
    assert trigger_workflow_by_nats("hello", 1, ["u1"], bot.id, "start") == {
        "result": False,
        "message": "Bot workflow not found",
    }
    BotWorkFlow.objects.create(bot=bot, flow_json={}, web_json={})
    engine = SimpleNamespace(execution_id="exec-1", execute=lambda data: {"success": True, "echo": data["message"]})
    with patch("apps.opspilot.nats_api.create_chat_flow_engine", return_value=engine) as create:
        out = trigger_workflow_by_nats("hello", 1, ["u1", None], bot.id, "start")
    create.assert_called_once()
    assert create.call_args.args[1] == "start"
    assert create.call_args.kwargs["entry_type"] == "nats"
    assert out == {
        "result": True,
        "data": {"success": True, "echo": "hello"},
        "entry_type": "nats",
        "execution_id": "exec-1",
    }
