from apps.core.utils.loader import LanguageLoader
from apps.opspilot.services import builtin_tools
from apps.opspilot.services.chat_service import ChatService


def test_monitor_language_keys_exist_in_en_and_zh():
    en_loader = LanguageLoader(app="opspilot", default_lang="en")
    zh_loader = LanguageLoader(app="opspilot", default_lang="zh-Hans")

    assert en_loader.get("tools.monitor.name")
    assert en_loader.get("tools.monitor.description")
    assert en_loader.get("tools.monitor.tools.monitor_list_objects.description")

    assert zh_loader.get("tools.monitor.name")
    assert zh_loader.get("tools.monitor.description")
    assert zh_loader.get("tools.monitor.tools.monitor_list_objects.description")


def test_build_builtin_monitor_tool_exposes_constructor_and_subtools(mocker):
    mocker.patch.object(
        LanguageLoader,
        "get",
        side_effect=lambda key: {
            f"tools.{builtin_tools.BUILTIN_MONITOR_TOOL_NAME}.description": "Monitor built-in tool",
            f"tools.{builtin_tools.BUILTIN_MONITOR_TOOL_NAME}.tools.monitor_list_objects.description": "List monitor objects",
        }.get(key, ""),
    )
    loader = LanguageLoader(app="opspilot", default_lang="en")

    data = builtin_tools.build_builtin_monitor_tool(loader)

    assert data["name"] == "monitor"
    assert data["params"]["url"] == "langchain:monitor"
    assert [item["key"] for item in data["params"]["kwargs"]] == ["username", "password", "domain", "team_id"]
    assert any(tool["name"] == "monitor_list_objects" for tool in data["tools"])


def test_build_builtin_monitor_runtime_tool_has_langchain_url():
    data = builtin_tools.build_builtin_monitor_runtime_tool({"username": "alice", "password": "secret", "domain": "tenant-a.com"})

    assert data == {
        "name": "monitor",
        "url": "langchain:monitor",
        "enable_auth": False,
        "auth_token": "",
        "extra_param_prompt": {"username": "alice", "password": "secret", "domain": "tenant-a.com"},
    }


def test_chat_service_passes_monitor_kwargs_to_extra_param_prompt(mocker):
    llm_model = mocker.Mock()
    llm_model.openai_api_base = "https://example.com/v1"
    llm_model.openai_api_key = "key"
    llm_model.model_name = "gpt-4o"

    mocker.patch("apps.opspilot.services.history_service.history_service.process_user_message_and_images", return_value=("hello", []))
    mocker.patch("apps.opspilot.services.history_service.history_service.process_chat_history", return_value=[])
    mocker.patch("apps.opspilot.services.chat_service.resolve_skill_params", return_value="system")

    kwargs = {
        "user_message": "hello",
        "chat_history": [],
        "skill_prompt": "system",
        "skill_params": [],
        "temperature": 0.1,
        "user_id": 1,
        "enable_rag": False,
        "enable_rag_knowledge_source": False,
        "skill_type": 1,
        "locale": "zh-Hans",
        "tools": [
            {
                "name": "monitor",
                "kwargs": [
                    {"key": "username", "value": "alice", "type": "string"},
                    {"key": "password", "value": "secret", "type": "password"},
                    {"key": "domain", "value": "tenant-a.com", "type": "string"},
                ],
            }
        ],
    }

    chat_kwargs, _, _ = ChatService.format_chat_server_kwargs(kwargs, llm_model)

    assert chat_kwargs["tools_servers"] == [
        {
            "name": "monitor",
            "url": "langchain:monitor",
            "enable_auth": False,
            "auth_token": "",
            "extra_param_prompt": {"username": "alice", "password": "secret", "domain": "tenant-a.com"},
        }
    ]
