# -- coding: utf-8 --
# @File: urls.py
# @Time: 2025/5/9 14:57
# @Author: windyzhao
from django.urls import path
from rest_framework import routers

from apps.alerts.views import (
    AlertSourceModelViewSet,
    AlertModelViewSet,
    EventModelViewSet,
    LevelModelViewSet,
    IncidentModelViewSet,
    SystemSettingModelViewSet,
    SystemLogModelViewSet,
    AlertAssignmentModelViewSet,
    AlertShieldModelViewSet,
    AlarmStrategyModelViewSet,
    receiver_data,
    request_test,
)

router = routers.DefaultRouter()
router.register(r"api/alert_source", AlertSourceModelViewSet, basename="alert_source")
router.register(r"api/alerts", AlertModelViewSet, basename="alerts")
router.register(r"api/events", EventModelViewSet, basename="events")
router.register(r"api/level", LevelModelViewSet, basename="level")
router.register(r"api/settings", SystemSettingModelViewSet, basename="settings")
router.register(r"api/assignment", AlertAssignmentModelViewSet, basename="assignment")
router.register(r"api/shield", AlertShieldModelViewSet, basename="shield")
router.register(r"api/incident", IncidentModelViewSet, basename="incident")
router.register(
    r"api/alarm_strategy", AlarmStrategyModelViewSet, basename="alarm_strategy"
)
router.register(r"api/log", SystemLogModelViewSet, basename="log")

urlpatterns = [
    path("api/test/", request_test),
    path("api/receiver_data/", receiver_data),
]

urlpatterns += router.urls
