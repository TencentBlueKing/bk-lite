# -- coding: utf-8 --
# @File: urls.py
# @Time: 2025/7/14 16:35
# @Author: windyzhao

from rest_framework import routers

from apps.operation_analysis.views.datasource_view import DataSourceAPIModelViewSet, DataSourceTagModelViewSet, NameSpaceModelViewSet
from apps.operation_analysis.views.import_export_view import ImportExportViewSet
from apps.operation_analysis.views.openapi_import_export_view import OpenImportExportViewSet
from apps.operation_analysis.views.scene_widget_view import SceneWidgetViewSet
from apps.operation_analysis.views.view import ArchitectureModelViewSet, DashboardModelViewSet, DirectoryModelViewSet, TopologyModelViewSet

router = routers.DefaultRouter()
router.register(r"api/data_source", DataSourceAPIModelViewSet, basename="data_source")
router.register(r"api/dashboard", DashboardModelViewSet, basename="dashboard")
router.register(r"api/directory", DirectoryModelViewSet, basename="directory")
router.register(r"api/topology", TopologyModelViewSet, basename="topology")
router.register(r"api/architecture", ArchitectureModelViewSet, basename="architecture")
router.register(r"api/namespace", NameSpaceModelViewSet, basename="namespace")
router.register(r"api/tag", DataSourceTagModelViewSet, basename="tag")
router.register(r"api/import_export", ImportExportViewSet, basename="import_export")
router.register(r"api/scene_widgets", SceneWidgetViewSet, basename="scene_widgets")

router_open_api = routers.DefaultRouter(trailing_slash=False)
router_open_api.register(r"open_api/import_export", OpenImportExportViewSet, basename="open_import_export")

urlpatterns = router.urls + router_open_api.urls
