from django.urls import path
from rest_framework import routers

from apps.opspilot.bot_mgmt import views
from apps.opspilot.bot_mgmt.viewsets import BotViewSet, HistoryViewSet, RasaModelViewSet
from apps.opspilot.channel_mgmt.viewsets import ChannelViewSet
from apps.opspilot.knowledge_mgmt.viewsets import (
    FileKnowledgeViewSet,
    KnowledgeBaseViewSet,
    KnowledgeDocumentViewSet,
    ManualKnowledgeViewSet,
    WebPageKnowledgeViewSet,
)
from apps.opspilot.model_provider_mgmt.views import (
    EmbedProviderViewSet,
    EmbedViewSet,
    LLMModelViewSet,
    LLMViewSet,
    OCRProviderViewSet,
    RerankProviderViewSet,
    RerankViewSet,
    RuleViewSet,
    SkillRequestLogViewSet,
    SkillToolsViewSet,
)
from apps.opspilot.quota_rule_mgmt.views import QuotaRuleViewSet

router = routers.DefaultRouter()
# model_provider
router.register(r"model_provider_mgmt/embed", EmbedViewSet, basename="embed")
router.register(r"model_provider_mgmt/embed_provider", EmbedProviderViewSet)
router.register(r"model_provider_mgmt/rerank_provider", RerankProviderViewSet)
router.register(r"model_provider_mgmt/ocr_provider", OCRProviderViewSet)
router.register(r"model_provider_mgmt/rerank", RerankViewSet, basename="rerank")
router.register(r"model_provider_mgmt/llm", LLMViewSet)
router.register(r"model_provider_mgmt/rule", RuleViewSet)
router.register(r"model_provider_mgmt/llm_model", LLMModelViewSet)
router.register(r"model_provider_mgmt/skill_tools", SkillToolsViewSet)
router.register(r"model_provider_mgmt/skill_log", SkillRequestLogViewSet)

# bot
router.register(r"bot_mgmt/bot", BotViewSet)
router.register(r"bot_mgmt/rasa_model", RasaModelViewSet, basename="rasa_model")
router.register(r"bot_mgmt/history", HistoryViewSet)

# channel
router.register(r"channel_mgmt/channel", ChannelViewSet)

# knowledge
router.register(r"knowledge_mgmt/knowledge_base", KnowledgeBaseViewSet)
router.register(r"knowledge_mgmt/file_knowledge", FileKnowledgeViewSet)
router.register(r"knowledge_mgmt/knowledge_document", KnowledgeDocumentViewSet)
router.register(r"knowledge_mgmt/web_page_knowledge", WebPageKnowledgeViewSet)
router.register(r"knowledge_mgmt/manual_knowledge", ManualKnowledgeViewSet)

# quota
router.register(r"quota_rule_mgmt/quota_rule", QuotaRuleViewSet)


urlpatterns = router.urls

# bot open api
urlpatterns += [
    path(r"bot_mgmt/bot/<int:bot_id>/get_detail/", views.get_bot_detail, name="get_bot_detail"),
    path(r"bot_mgmt/rasa_model_download/", views.model_download, name="model_download"),
    path(r"bot_mgmt/skill_execute/", views.skill_execute, name="skill_execute"),
    path(r"bot_mgmt/v1/chat/completions", views.openai_completions, name="openai_completions"),
    path(r"bot_mgmt/get_active_users_line_data/", views.get_active_users_line_data, name="get_active_users_line_data"),
    path(
        r"bot_mgmt/get_conversations_line_data/", views.get_conversations_line_data, name="get_conversations_line_data"
    ),
    path(
        r"bot_mgmt/get_total_token_consumption/", views.get_total_token_consumption, name="get_total_token_consumption"
    ),
    path(
        r"bot_mgmt/get_token_consumption_overview/",
        views.get_token_consumption_overview,
        name="get_token_consumption_overview",
    ),
    # path(r"api/bot/automation_skill_execute", AutomationSkillExecuteView.as_view(), name="automation_skill_execute"),
]
