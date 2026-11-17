import json
from types import SimpleNamespace

import pytest

from apps.opspilot.views import chat_flow


@pytest.mark.asyncio
async def test_restful_entry_passes_trigger_type_to_workflow(request_factory, mocker):
    user = SimpleNamespace(username="alice", domain="example.com", group_list=[], timezone="")
    bot = SimpleNamespace(id=1, online=True)
    workflow = SimpleNamespace(flow_json={"nodes": []})
    engine = mocker.MagicMock(execution_id="run-1")
    engine._get_node_by_id.return_value = {"type": "restful"}
    engine.execute.return_value = {"success": True}
    mocker.patch.object(chat_flow, "get_loader", return_value=SimpleNamespace(default_lang="zh-Hans"))
    mocker.patch.object(chat_flow, "validate_openai_token", return_value=(True, user))
    mocker.patch.object(chat_flow, "capture_caller_identity", return_value={"team_id": 1})
    mocker.patch.object(chat_flow.Bot.objects, "filter").return_value.filter.return_value.first.return_value = bot
    mocker.patch.object(chat_flow.BotWorkFlow.objects, "filter").return_value.first.return_value = workflow
    mocker.patch.object(chat_flow, "create_chat_flow_engine", return_value=engine)
    request = request_factory.post("/", data=json.dumps({"message": "检查告警"}), content_type="application/json")
    response = await chat_flow.execute_chat_flow(request, bot_id=1, node_id="rest-node")
    assert response.status_code == 200
    assert engine.execute.call_args.args[0]["entry_type"] == "restful"
