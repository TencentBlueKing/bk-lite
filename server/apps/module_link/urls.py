from rest_framework import routers

from apps.module_link.views import AccessDraftViewSet, CmdbMonitorTaskViewSet

router = routers.DefaultRouter()
router.register(r"api/cmdb_monitor_tasks", CmdbMonitorTaskViewSet, basename="cmdb_monitor_tasks")
router.register(r"api/access_drafts", AccessDraftViewSet, basename="access_drafts")

urlpatterns = router.urls
