from django.urls import path
from rest_framework import routers

from apps.opspilot import views
from apps.opspilot.viewsets import (
    BotViewSet,
    ChannelViewSet,
    EmbedProviderViewSet,
    FileKnowledgeViewSet,
    HistoryViewSet,
    KnowledgeBaseViewSet,
    KnowledgeDocumentViewSet,
    KnowledgeGraphViewSet,
    LLMModelViewSet,
    LLMViewSet,
    ManualKnowledgeViewSet,
    ModelTypeViewSet,
    OCRProviderViewSet,
    QAPairsViewSet,
    RasaModelViewSet,
    RerankProviderViewSet,
    RuleViewSet,
    SkillRequestLogViewSet,
    SkillToolsViewSet,
    WebPageKnowledgeViewSet,
    WorkFlowTaskResultViewSet,
)
from apps.opspilot.viewsets.quota_rule_view import QuotaRuleViewSet

router = routers.DefaultRouter()
# model_provider
router.register(r"model_provider_mgmt/embed_provider", EmbedProviderViewSet)
router.register(r"model_provider_mgmt/rerank_provider", RerankProviderViewSet)
router.register(r"model_provider_mgmt/ocr_provider", OCRProviderViewSet)
router.register(r"model_provider_mgmt/llm", LLMViewSet)
router.register(r"model_provider_mgmt/rule", RuleViewSet)
router.register(r"model_provider_mgmt/llm_model", LLMModelViewSet)
router.register(r"model_provider_mgmt/skill_tools", SkillToolsViewSet)
router.register(r"model_provider_mgmt/skill_log", SkillRequestLogViewSet)
router.register(r"model_provider_mgmt/model_type", ModelTypeViewSet)

# bot
router.register(r"bot_mgmt/bot", BotViewSet)
router.register(r"bot_mgmt/rasa_model", RasaModelViewSet, basename="rasa_model")
router.register(r"bot_mgmt/history", HistoryViewSet)
router.register(r"bot_mgmt/workflow_task_result", WorkFlowTaskResultViewSet)

# channel
router.register(r"channel_mgmt/channel", ChannelViewSet)

# knowledge
router.register(r"knowledge_mgmt/knowledge_base", KnowledgeBaseViewSet)
router.register(r"knowledge_mgmt/file_knowledge", FileKnowledgeViewSet)
router.register(r"knowledge_mgmt/knowledge_document", KnowledgeDocumentViewSet)
router.register(r"knowledge_mgmt/web_page_knowledge", WebPageKnowledgeViewSet)
router.register(r"knowledge_mgmt/manual_knowledge", ManualKnowledgeViewSet)
router.register(r"knowledge_mgmt/qa_pairs", QAPairsViewSet)
router.register(r"knowledge_mgmt/knowledge_graph", KnowledgeGraphViewSet)

# quota
router.register(r"quota_rule_mgmt/quota_rule", QuotaRuleViewSet)

urlpatterns = router.urls

# bot open api
urlpatterns += [
    path(
        r"bot_mgmt/bot/<int:bot_id>/get_detail/",
        views.get_bot_detail,
        name="get_bot_detail",
    ),
    path(r"bot_mgmt/rasa_model_download/", views.model_download, name="model_download"),
    path(r"bot_mgmt/skill_execute/", views.skill_execute, name="skill_execute"),
    path(
        r"bot_mgmt/v1/chat/completions",
        views.openai_completions,
        name="openai_completions",
    ),
    path(
        r"bot_mgmt/lobe_chat/v1/chat/completions",
        views.lobe_skill_execute,
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
        r"bot_mgmt/execute_chat_flow_wechat/<int:bot_id>/",
        views.execute_chat_flow_wechat,
        name="execute_chat_flow_wechat",
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
    path(
        r"test/",
        views.test,
        name="test",
    ),
    # path(r"api/bot/automation_skill_execute", AutomationSkillExecuteView.as_view(), name="automation_skill_execute"),
]
