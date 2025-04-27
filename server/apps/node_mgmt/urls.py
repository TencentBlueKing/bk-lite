from rest_framework import routers

from apps.node_mgmt.views.child_config import ChildConfigViewSet
from apps.node_mgmt.views.cloud_region import CloudRegionViewSet
from apps.node_mgmt.views.collector import CollectorViewSet
from apps.node_mgmt.views.collector_configuration import CollectorConfigurationViewSet
from apps.node_mgmt.views.controller import ControllerViewSet
from apps.node_mgmt.views.installer import InstallerViewSet
from apps.node_mgmt.views.package import PackageMgmtView
from apps.node_mgmt.views.sidecar_env import SidecarEnvViewSet
from apps.node_mgmt.views.node import NodeViewSet
from apps.node_mgmt.views.sidecar import SidecarViewSet, OpenSidecarViewSet

router = routers.DefaultRouter(trailing_slash=True)
router.register(r"api/node", NodeViewSet, basename="node")
router.register(r"api/sidecar", SidecarViewSet, basename="sidecar")
router.register(r'api/cloud_region', CloudRegionViewSet, basename='cloud_region')
router.register(r'api/sidecar_env', SidecarEnvViewSet, basename='env_variable')
router.register(r"api/collector", CollectorViewSet, basename="collector")
router.register(r"api/controller", ControllerViewSet, basename="controller")
router.register(r"api/configuration", CollectorConfigurationViewSet, basename="configuration")
router.register(r"api/child_config", ChildConfigViewSet, basename="ChildConfigViewSet")
router.register(r"api/installer", InstallerViewSet, basename="InstallerViewSet")
router.register(r"api/package", PackageMgmtView, basename="PackageMgmtView")


router_without_slash = routers.DefaultRouter(trailing_slash=False)
router_without_slash.register(r"open_api", OpenSidecarViewSet, basename="open_node")

urlpatterns = router.urls + router_without_slash.urls
