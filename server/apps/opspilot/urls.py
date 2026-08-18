from django.urls import path
from rest_framework import routers

from apps.opspilot import views
from apps.opspilot.viewsets import (
    BotViewSet,
    ChannelViewSet,
    ChatApplicationViewSet,
    EmbedProviderViewSet,
    HistoryViewSet,
    LLMModelViewSet,
    LLMViewSet,
    MemorySpaceViewSet,
    MemoryViewSet,
    ModelVendorViewSet,
    OCRProviderViewSet,
    RasaModelViewSet,
    RerankProviderViewSet,
    SkillPackageViewSet,
    SkillRequestLogViewSet,
    SkillToolsViewSet,
    WikiBuildRecordViewSet,
    WikiCheckItemViewSet,
    WikiDirectoryViewSet,
    WikiKnowledgeBaseViewSet,
    WikiMaterialViewSet,
    WikiPageViewSet,
    WorkFlowTaskResultViewSet,
)
from apps.opspilot.viewsets.memory_engine_view import MemoryEngineViewSet
from apps.opspilot.viewsets.skill_channel_view import SkillChannelViewSet
from apps.opspilot.viewsets.wiki_media_proxy_view import WikiParsedMediaProxyView

router = routers.DefaultRouter()
# model_provider
router.register(r"model_provider_mgmt/embed_provider", EmbedProviderViewSet)
router.register(r"model_provider_mgmt/rerank_provider", RerankProviderViewSet)
router.register(r"model_provider_mgmt/ocr_provider", OCRProviderViewSet)
router.register(r"model_provider_mgmt/llm", LLMViewSet)
router.register(r"model_provider_mgmt/llm_model", LLMModelViewSet)
router.register(r"model_provider_mgmt/skill_tools", SkillToolsViewSet)
router.register(r"model_provider_mgmt/skill_packages", SkillPackageViewSet)
router.register(r"model_provider_mgmt/skill_log", SkillRequestLogViewSet)
router.register(r"model_provider_mgmt/model_vendor", ModelVendorViewSet)
router.register(r"model_provider_mgmt/skill_channel", SkillChannelViewSet, basename="skill_channel")

# bot
router.register(r"bot_mgmt/bot", BotViewSet)
router.register(r"bot_mgmt/rasa_model", RasaModelViewSet, basename="rasa_model")
router.register(r"bot_mgmt/history", HistoryViewSet)
router.register(r"bot_mgmt/workflow_task_result", WorkFlowTaskResultViewSet)
router.register(r"bot_mgmt/chat_application", ChatApplicationViewSet)

# channel
router.register(r"channel_mgmt/channel", ChannelViewSet)

# memory
router.register(r"memory_mgmt/memory_space", MemorySpaceViewSet)
router.register(r"memory_mgmt/memory", MemoryViewSet)
router.register(r"memory_mgmt/memory_engines", MemoryEngineViewSet, basename="memory_engines")

# wiki (new knowledge base)
router.register(r"wiki_mgmt/knowledge_base", WikiKnowledgeBaseViewSet, basename="wiki_knowledge_base")
router.register(r"wiki_mgmt/directory", WikiDirectoryViewSet, basename="wiki_directory")
router.register(r"wiki_mgmt/material", WikiMaterialViewSet, basename="wiki_material")
router.register(r"wiki_mgmt/page", WikiPageViewSet, basename="wiki_page")
router.register(r"wiki_mgmt/build_record", WikiBuildRecordViewSet, basename="wiki_build_record")
router.register(r"wiki_mgmt/check_item", WikiCheckItemViewSet, basename="wiki_check_item")

urlpatterns = router.urls

# wiki media 同源代理（HMAC，供 <img> 无 Bearer 加载）
_wiki_media_proxy = WikiParsedMediaProxyView.as_view()
_wiki_media_proxy.api_exempt = True
urlpatterns += [
    path(
        r"wiki_mgmt/media/",
        _wiki_media_proxy,
        name="wiki_parsed_media_proxy",
    ),
]

# bot open api
urlpatterns += [
    path(
        r"bot_mgmt/bot/<int:bot_id>/get_detail/",
        views.get_bot_detail,
        name="get_bot_detail",
    ),
    path(r"bot_mgmt/skill_execute/", views.skill_execute, name="skill_execute"),
    path(
        r"bot_mgmt/v1/chat/completions",
        views.openai_completions,
        name="openai_completions",
    ),
    path(
        r"bot_mgmt/get_active_users_line_data/",
        views.get_active_users_line_data,
        name="get_active_users_line_data",
    ),
    path(
        r"bot_mgmt/get_conversations_line_data/",
        views.get_conversations_line_data,
        name="get_conversations_line_data",
    ),
    path(
        r"bot_mgmt/get_total_token_consumption/",
        views.get_total_token_consumption,
        name="get_total_token_consumption",
    ),
    path(
        r"bot_mgmt/get_token_consumption_overview/",
        views.get_token_consumption_overview,
        name="get_token_consumption_overview",
    ),
    path(
        r"bot_mgmt/execute_chat_flow/<int:bot_id>/<str:node_id>/",
        views.execute_chat_flow,
        name="execute_chat_flow",
    ),
    path(
        r"bot_mgmt/workflow_attachment/download/<str:download_token>/",
        views.download_workflow_attachment,
        name="download_workflow_attachment",
    ),
    path(
        r"bot_mgmt/interrupt_chat_flow_execution/",
        views.interrupt_chat_flow_execution,
        name="interrupt_chat_flow_execution",
    ),
    path(
        r"bot_mgmt/submit_approval/",
        views.submit_approval,
        name="submit_approval",
    ),
    path(
        r"bot_mgmt/submit_choice/",
        views.submit_choice,
        name="submit_choice",
    ),
    path(
        r"bot_mgmt/execute_chat_flow_wechat/<int:bot_id>/",
        views.execute_chat_flow_wechat,
        name="execute_chat_flow_wechat",
    ),
    path(
        r"bot_mgmt/execute_chat_flow_enterprise_wechat_aibot/<int:bot_id>/",
        views.execute_chat_flow_enterprise_wechat_aibot,
        name="execute_chat_flow_enterprise_wechat_aibot",
    ),
    path(
        r"bot_mgmt/execute_chat_flow_wechat_official/<int:bot_id>/",
        views.execute_chat_flow_wechat_official,
        name="execute_chat_flow_wechat_official",
    ),
    path(
        r"bot_mgmt/execute_chat_flow_dingtalk/<int:bot_id>/",
        views.execute_chat_flow_dingtalk,
        name="execute_chat_flow_dingtalk",
    ),
    # 智能体渠道发布
    path(
        r"skill_channel/platform/",
        views.list_platform_skill_channels,
        name="list_platform_skill_channels",
    ),
    path(
        r"skill_channel/web_chat/",
        views.list_web_chat_skill_channels,
        name="list_web_chat_skill_channels",
    ),
    path(
        r"skill_channel/web_skills/",
        views.list_published_web_skills,
        name="list_published_web_skills",
    ),
    path(
        r"skill_channel/skill/<int:skill_id>/chat/",
        views.execute_published_web_skill_chat,
        name="execute_published_web_skill_chat",
    ),
    path(
        r"skill_channel/conversations/",
        views.list_skill_channel_conversations,
        name="list_skill_channel_conversations",
    ),
    path(
        r"skill_channel/conversations/messages/",
        views.list_skill_channel_session_messages,
        name="list_skill_channel_session_messages",
    ),
    path(
        r"skill_channel/conversations/delete/",
        views.delete_skill_channel_session,
        name="delete_skill_channel_session",
    ),
    path(
        r"skill_channel/<int:channel_id>/chat/",
        views.execute_skill_channel_chat,
        name="execute_skill_channel_chat",
    ),
    path(
        r"skill_channel/embedded/<int:skill_id>/<int:channel_id>/",
        views.execute_skill_embedded_chat,
        name="execute_skill_embedded_chat",
    ),
    path(
        r"skill_channel/<int:channel_id>/<str:channel_type>/",
        views.execute_skill_channel_im,
        name="execute_skill_channel_im",
    ),
    # path(r"api/bot/automation_skill_execute", AutomationSkillExecuteView.as_view(), name="automation_skill_execute"),
]
