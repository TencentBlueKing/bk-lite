from rest_framework import routers

from apps.cmdb.views.change_record import ChangeRecordViewSet
from apps.cmdb.views.classification import ClassificationViewSet
from apps.cmdb.views.collect import CollectModelViewSet, OidModelViewSet
from apps.cmdb.views.collect_tool import CollectToolViewSet
from apps.cmdb.views.config_file import ConfigFileVersionViewSet
from apps.cmdb.views.field_group import FieldGroupViewSet
from apps.cmdb.views.instance import InstanceViewSet
from apps.cmdb.views.model import ModelViewSet
from apps.cmdb.views.public_enum_library import PublicEnumLibraryViewSet
from apps.cmdb.views.subscription import SubscriptionViewSet
from apps.cmdb.views.node_mgmt_sync import NodeMgmtSyncViewSet
from apps.cmdb.views.user_personal_config import UserPersonalConfigViewSet
from apps.cmdb.views.k8s_setup import K8sSetupViewSet, K8sSetupOpenViewSet

router = routers.DefaultRouter()
router.register(r"api/classification", ClassificationViewSet, basename="classification")
router.register(r"api/model", ModelViewSet, basename="model")
router.register(r"api/instance", InstanceViewSet, basename="instance")
router.register(r"api/change_record", ChangeRecordViewSet, basename="change_record")
router.register(r"api/collect", CollectModelViewSet, basename="collect")
router.register(r"api/config_file_versions", ConfigFileVersionViewSet, basename="config_file_versions")
router.register(r"api/oid", OidModelViewSet, basename="oid")
router.register(r"api/field_groups", FieldGroupViewSet, basename="field_groups")
router.register(r"api/user_configs", UserPersonalConfigViewSet, basename="user_configs")
router.register(
    r"api/public_enum_libraries",
    PublicEnumLibraryViewSet,
    basename="public_enum_libraries",
)
router.register(r"api/subscription", SubscriptionViewSet, basename="subscription")
router.register(r"api/node_mgmt_sync", NodeMgmtSyncViewSet, basename="node_mgmt_sync")
router.register(r"api/collect_tool", CollectToolViewSet, basename="collect_tool")
router.register(r"api/k8s_setup", K8sSetupViewSet, basename="k8s_setup")
router.register(r"open_api/k8s_setup", K8sSetupOpenViewSet, basename="k8s_setup_open")

urlpatterns = router.urls

try:
    enterprise_urls = __import__("apps.cmdb.enterprise.urls", fromlist=["urlpatterns"])
    urlpatterns += enterprise_urls.urlpatterns
except ModuleNotFoundError as exc:
    if exc.name not in {"apps.cmdb.enterprise", "apps.cmdb.enterprise.urls"}:
        raise
