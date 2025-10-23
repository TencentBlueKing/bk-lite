# -- coding: utf-8 --
# @File: urls.py
# @Time: 2025/7/14 16:35
# @Author: windyzhao

from rest_framework import routers

from apps.operation_analysis.views.view import DataSourceAPIModelViewSet, DashboardModelViewSet, DirectoryModelViewSet, \
    TopologyModelViewSet, NameSpaceModelViewSet, DataSourceTagModelViewSet, ArchitectureModelViewSet

router = routers.DefaultRouter()
router.register(r"api/data_source", DataSourceAPIModelViewSet, basename="data_source")
router.register(r"api/dashboard", DashboardModelViewSet, basename="dashboard")
router.register(r"api/directory", DirectoryModelViewSet, basename="directory")
router.register(r"api/topology", TopologyModelViewSet, basename="topology")
router.register(r"api/architecture", ArchitectureModelViewSet, basename="architecture")
router.register(r"api/namespace", NameSpaceModelViewSet, basename="namespace")
router.register(r"api/tag", DataSourceTagModelViewSet, basename="tag")

urlpatterns = [
    # path("api/test/", request_test),
]

urlpatterns += router.urls
