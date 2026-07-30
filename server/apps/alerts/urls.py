# -- coding: utf-8 --
# @File: urls.py
# @Time: 2025/5/9 14:57
# @Author: windyzhao
from django.urls import include, path
from rest_framework import routers

from apps.alerts.extensions.routes import alert_extension_routes
from apps.alerts.views import (
    AlarmStrategyModelViewSet,
    AlertAssignmentModelViewSet,
    AlertModelViewSet,
    AlertShieldModelViewSet,
    AlertSourceModelViewSet,
    EnrichmentRuleModelViewSet,
    EventModelViewSet,
    IncidentModelViewSet,
    IncidentUpdateViewSet,
    K8sOpenAPIViewSet,
    LevelModelViewSet,
    SystemLogModelViewSet,
    SystemSettingModelViewSet,
    receiver_data,
    receiver_source_data,
    request_test,
)
from apps.alerts.views.action import ActionCallbackView, ActionExecutionViewSet, ActionJobScriptDetailView, ActionJobScriptListView, ActionRuleViewSet

router = routers.DefaultRouter()
router.register(r"api/alert_source", AlertSourceModelViewSet, basename="alert_source")
router.register(r"api/alerts", AlertModelViewSet, basename="alerts")
router.register(r"api/events", EventModelViewSet, basename="events")
router.register(r"api/level", LevelModelViewSet, basename="level")
router.register(r"api/settings", SystemSettingModelViewSet, basename="settings")
router.register(r"api/assignment", AlertAssignmentModelViewSet, basename="assignment")
router.register(r"api/shield", AlertShieldModelViewSet, basename="shield")
router.register(r"api/enrichment", EnrichmentRuleModelViewSet, basename="enrichment")
router.register(r"api/incident", IncidentModelViewSet, basename="incident")
router.register(
    r"api/incident/(?P<incident_pk>\d+)/updates", IncidentUpdateViewSet, basename="incident-updates",
)
router.register(r"api/alarm_strategy", AlarmStrategyModelViewSet, basename="alarm_strategy")
router.register(r"api/log", SystemLogModelViewSet, basename="log")
router.register(r"open_api/k8s", K8sOpenAPIViewSet, basename="alerts_k8s_open_api")
router.register(r"api/action_rule", ActionRuleViewSet, basename="action_rule")
router.register(r"api/action_execution", ActionExecutionViewSet, basename="action_execution")

urlpatterns = [
    path("", include(alert_extension_routes.urlpatterns)),
    path("api/test/", request_test),
    path("api/receiver_data/", receiver_data),
    path("api/source/<str:source_id>/webhook/", receiver_source_data),
    path("api/action_callback/", ActionCallbackView.as_view()),
    path("api/action_job/scripts/", ActionJobScriptListView.as_view()),
    path("api/action_job/scripts/<int:script_id>/", ActionJobScriptDetailView.as_view()),
]

urlpatterns += router.urls
