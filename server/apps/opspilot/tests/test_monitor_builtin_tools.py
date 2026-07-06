from datetime import timedelta

import pytest
from django.utils import timezone

from apps.core.utils.loader import LanguageLoader
from apps.opspilot.models import WorkflowAttachmentAsset
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


def test_builtin_tool_display_name_keys_exist_in_en_and_zh():
    """所有写入 SkillTools 的内置工具都应在中英文 yaml 中配置 display_name(tools.{name}.name)。"""
    en_loader = LanguageLoader(app="opspilot", default_lang="en")
    zh_loader = LanguageLoader(app="opspilot", default_lang="zh-Hans")

    tool_names = [
        "monitor",
        "attachment_file",
        "current_time",
        "duckduckgo",
        "fetch",
        "github",
        "jenkins",
        "kubernetes",
        "kubernetes_data_collection",
        "postgres",
        "mysql",
        "oracle",
        "mssql",
        "redis",
        "elasticsearch",
        "python",
        "shell",
        "ssh",
        "browser_use",
        "agent_browser",
    ]
    for name in tool_names:
        assert en_loader.get(f"tools.{name}.name"), f"missing en display name for {name}"
        assert zh_loader.get(f"tools.{name}.name"), f"missing zh display name for {name}"

    # 内置工具的展示名不应等于 ID 式的 name（至少中文要有可读名称）
    assert zh_loader.get("tools.current_time.name") != "current_time"
    assert zh_loader.get("tools.monitor.name") != "monitor"


def test_build_builtin_monitor_tool_display_name_uses_translation(mocker):
    mocker.patch.object(
        LanguageLoader,
        "get",
        side_effect=lambda key: {
            f"tools.{builtin_tools.BUILTIN_MONITOR_TOOL_NAME}.name": "监控",
        }.get(key, ""),
    )
    loader = LanguageLoader(app="opspilot", default_lang="zh-Hans")

    data = builtin_tools.build_builtin_monitor_tool(loader)

    # name 仍作为 ID，display_name 走翻译
    assert data["name"] == "monitor"
    assert data["display_name"] == "监控"


def test_build_builtin_monitor_tool_display_name_falls_back_when_untranslated(mocker):
    mocker.patch.object(LanguageLoader, "get", side_effect=lambda key: "")
    loader = LanguageLoader(app="opspilot", default_lang="en")

    data = builtin_tools.build_builtin_monitor_tool(loader)

    assert data["display_name"] == "Monitor"


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


def test_build_builtin_attachment_tool_exposes_subtool(mocker):
    mocker.patch.object(
        LanguageLoader,
        "get",
        side_effect=lambda key: {
            f"tools.{builtin_tools.BUILTIN_ATTACHMENT_FILE_TOOL_NAME}.description": "Attachment built-in tool",
            f"tools.{builtin_tools.BUILTIN_ATTACHMENT_FILE_TOOL_NAME}.tools.generate_attachment_file.description": "Generate attachment file",
        }.get(key, ""),
    )
    loader = LanguageLoader(app="opspilot", default_lang="en")

    data = builtin_tools.build_builtin_attachment_file_tool(loader)

    assert data["name"] == "attachment_file"
    assert data["params"]["url"] == "langchain:attachment_file"
    assert data["params"]["kwargs"] == []
    assert any(tool["name"] == "generate_attachment_file" for tool in data["tools"])


@pytest.mark.django_db
def test_generate_attachment_file_creates_workflow_asset():
    from apps.opspilot.metis.llm.tools.attachment.generate_attachment import generate_attachment_file

    result = generate_attachment_file.func(
        filename="report.md",
        content="# report",
        file_type="md",
        title="Daily Report",
        config={
            "configurable": {
                "execution_id": "exec-1",
                "attachment_id": "daily_report",
                "node_id": "agent_node",
                "flow_id": "flow-1",
                "user_id": "tester",
            }
        },
    )

    from apps.opspilot.services.workflow_attachment_service import build_signed_attachment_download_url

    asset = WorkflowAttachmentAsset.objects.get(execution_id="exec-1", attachment_id="daily_report")
    asset.file.open("rb")
    try:
        content = asset.file.read()
    finally:
        asset.file.close()

    assert result["file_url"].startswith("/api/proxy/opspilot/bot_mgmt/workflow_attachment/download/")
    assert result["file_url"] == build_signed_attachment_download_url(asset)
    assert result["filename"] == "report.md"
    assert content == b"# report"


@pytest.mark.django_db
def test_build_signed_attachment_download_url_uses_proxy_path():
    """build_signed_attachment_download_url must return a /api/proxy/... path so browsers
    route the download request through the Next.js proxy rather than treating it as a page route."""
    from django.core.files.base import ContentFile

    from apps.opspilot.services.workflow_attachment_service import build_signed_attachment_download_url, resolve_signed_attachment_token

    asset = WorkflowAttachmentAsset.objects.create(
        execution_id="exec-url-test",
        attachment_id="att-url-test",
        filename="test.md",
        mime_type="text/markdown",
        file=ContentFile(b"data", name="f.md"),
    )

    url = build_signed_attachment_download_url(asset)

    assert url.startswith("/api/proxy/opspilot/bot_mgmt/workflow_attachment/download/")
    # The signed token must be decodable back to the same asset
    resolved = resolve_signed_attachment_token(url.rsplit("/download/", 1)[1].rstrip("/"))
    assert resolved is not None
    assert resolved.id == asset.id


@pytest.mark.django_db
def test_generate_attachment_file_auto_generates_unique_attachment_ids():
    from apps.opspilot.metis.llm.tools.attachment.generate_attachment import generate_attachment_file

    first = generate_attachment_file.func(
        filename="report.md",
        content="# report",
        file_type="md",
        config={
            "configurable": {
                "execution_id": "exec-2",
                "node_id": "agent_node",
                "flow_id": "flow-1",
                "user_id": "tester",
            }
        },
    )
    second = generate_attachment_file.func(
        filename="report-2.md",
        content="# report 2",
        file_type="md",
        config={
            "configurable": {
                "execution_id": "exec-2",
                "node_id": "agent_node",
                "flow_id": "flow-1",
                "user_id": "tester",
            }
        },
    )

    first_asset = WorkflowAttachmentAsset.objects.get(execution_id="exec-2", attachment_id=first["attachment_id"])
    second_asset = WorkflowAttachmentAsset.objects.get(execution_id="exec-2", attachment_id=second["attachment_id"])

    assert first_asset.attachment_id == "agent_node"
    assert second_asset.attachment_id == "agent_node__1"
    assert first_asset.source_node_id == "agent_node"
    assert second_asset.source_node_id == "agent_node"


@pytest.mark.django_db
def test_cleanup_expired_workflow_attachments_removes_old_assets():
    from apps.opspilot.services.workflow_attachment_service import cleanup_expired_workflow_attachments, create_workflow_attachment_asset

    expired_asset = create_workflow_attachment_asset(
        execution_id="exec-old",
        attachment_id="old-1",
        filename="old.md",
        content_bytes=b"old",
        mime_type="text/markdown",
        source_node_id="agent_node",
        flow_id="flow-1",
        created_by="tester",
    )
    recent_asset = create_workflow_attachment_asset(
        execution_id="exec-new",
        attachment_id="new-1",
        filename="new.md",
        content_bytes=b"new",
        mime_type="text/markdown",
        source_node_id="agent_node",
        flow_id="flow-1",
        created_by="tester",
    )

    WorkflowAttachmentAsset.objects.filter(id=expired_asset.id).update(created_at=timezone.now() - timedelta(days=4))

    deleted_count = cleanup_expired_workflow_attachments(retention_days=3)

    assert deleted_count == 1
    assert not WorkflowAttachmentAsset.objects.filter(id=expired_asset.id).exists()
    assert WorkflowAttachmentAsset.objects.filter(id=recent_asset.id).exists()


def test_opspilot_config_registers_workflow_attachment_cleanup_schedule():
    from apps.opspilot import config

    cleanup_schedule = config.CELERY_BEAT_SCHEDULE["cleanup-expired-workflow-attachments"]

    assert cleanup_schedule["task"] == "apps.opspilot.tasks.cleanup_expired_workflow_attachments_task"


def test_opspilot_config_registers_daily_memory_cache_flush_schedule():
    from apps.opspilot import config

    flush_schedule = config.CELERY_BEAT_SCHEDULE["flush-pending-memory-write-cache"]

    assert flush_schedule["task"] == "apps.opspilot.tasks.flush_all_pending_memory_write_cache"


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


def test_chat_service_passes_attachment_id_to_extra_config(mocker):
    llm_model = mocker.Mock()
    llm_model.openai_api_base = "https://example.com/v1"
    llm_model.openai_api_key = "key"
    llm_model.model_name = "gpt-4o"
    llm_model.protocol_type = "openai"

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
        "attachment_id": "daily_report",
        "tools": [
            {
                "id": builtin_tools.BUILTIN_ATTACHMENT_FILE_TOOL_ID,
                "name": builtin_tools.BUILTIN_ATTACHMENT_FILE_TOOL_NAME,
                "kwargs": [],
            }
        ],
    }

    chat_kwargs, _, _ = ChatService.format_chat_server_kwargs(kwargs, llm_model)

    assert chat_kwargs["extra_config"]["attachment_id"] == "daily_report"
    assert chat_kwargs["tools_servers"] == [
        {
            "name": "attachment_file",
            "url": "langchain:attachment_file",
            "enable_auth": False,
            "auth_token": "",
            "extra_tools_prompt": "",
            "extra_param_prompt": {},
        }
    ]
