from django.apps import apps


def build_urlpatterns():
    """裁剪安装不含 CMDB 时不导入它的模型，避免整站 URL 加载失败。"""
    if not apps.is_installed("apps.cmdb"):
        return []
    from rest_framework import routers

    from apps.module_link.views import AccessDraftViewSet, CmdbMonitorTaskViewSet, MonitorCmdbTaskViewSet

    router = routers.DefaultRouter()
    router.register(r"api/cmdb_monitor_tasks", CmdbMonitorTaskViewSet, basename="cmdb_monitor_tasks")
    router.register(r"api/monitor_cmdb_tasks", MonitorCmdbTaskViewSet, basename="monitor_cmdb_tasks")
    router.register(r"api/access_drafts", AccessDraftViewSet, basename="access_drafts")
    return router.urls


urlpatterns = build_urlpatterns()
