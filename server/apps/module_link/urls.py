from django.apps import apps


def build_urlpatterns():
    """CMDB 与监控都装入才注册胶水路由。缺一就不要导入对方模型，否则整站 URL 加载失败。"""
    if not apps.is_installed("apps.cmdb") or not apps.is_installed("apps.monitor"):
        return []
    from rest_framework import routers

    from apps.module_link.views import AccessDraftViewSet, CmdbMonitorTaskViewSet, MonitorCmdbTaskViewSet

    router = routers.DefaultRouter()
    router.register(r"api/cmdb_monitor_tasks", CmdbMonitorTaskViewSet, basename="cmdb_monitor_tasks")
    router.register(r"api/monitor_cmdb_tasks", MonitorCmdbTaskViewSet, basename="monitor_cmdb_tasks")
    router.register(r"api/access_drafts", AccessDraftViewSet, basename="access_drafts")
    return router.urls


urlpatterns = build_urlpatterns()
