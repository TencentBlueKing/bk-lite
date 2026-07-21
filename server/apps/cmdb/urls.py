from django.urls import path
from rest_framework import routers

from apps.cmdb.open_api import views as open_views
from apps.cmdb.views.change_record import ChangeRecordViewSet
from apps.cmdb.views.classification import ClassificationViewSet
from apps.cmdb.views.collect import CollectModelViewSet, OidModelViewSet
from apps.cmdb.views.collect_tool import CollectToolViewSet
from apps.cmdb.views.config_file import ConfigFileVersionViewSet
from apps.cmdb.views.custom_reporting import CustomReportingIngestViewSet, CustomReportingTaskViewSet
from apps.cmdb.views.field_group import FieldGroupViewSet
from apps.cmdb.views.instance import InstanceViewSet
from apps.cmdb.views.k8s_setup import K8sSetupOpenViewSet, K8sSetupViewSet
from apps.cmdb.views.model import ModelViewSet
from apps.cmdb.views.node_mgmt_sync import NodeMgmtSyncViewSet
from apps.cmdb.views.public_enum_library import PublicEnumLibraryViewSet
from apps.cmdb.views.subscription import SubscriptionViewSet
from apps.cmdb.views.user_personal_config import UserPersonalConfigViewSet

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
router.register(r"api/custom_reporting/tasks", CustomReportingTaskViewSet, basename="custom_reporting_tasks")
router.register(r"api/custom_reporting/ingest", CustomReportingIngestViewSet, basename="custom_reporting_ingest")

open_api_patterns = [
    path("api/open/classifications", open_views.OpenClassificationListView.as_view()),
    path("api/open/models", open_views.OpenModelListView.as_view()),
    path("api/open/models/<str:model_id>", open_views.OpenModelDetailView.as_view()),
    path(
        "api/open/models/<str:model_id>/attributes",
        open_views.OpenModelAttrsView.as_view(),
    ),
    path(
        "api/open/models/<str:model_id>/associations",
        open_views.OpenModelAssociationsView.as_view(),
    ),
    path(
        "api/open/models/<str:model_id>/instances",
        open_views.OpenInstanceCollectionView.as_view(),
    ),
    path(
        "api/open/models/<str:model_id>/instances/batch_create",
        open_views.OpenBatchCreateView.as_view(),
    ),
    path(
        "api/open/models/<str:model_id>/instances/batch_update",
        open_views.OpenBatchUpdateView.as_view(),
    ),
    path(
        "api/open/models/<str:model_id>/instances/batch_delete",
        open_views.OpenBatchDeleteView.as_view(),
    ),
    path(
        "api/open/models/<str:model_id>/instances/<int:inst_id>",
        open_views.OpenInstanceDetailView.as_view(),
    ),
    path(
        "api/open/models/<str:model_id>/instances/<int:inst_id>/associations",
        open_views.OpenInstanceAssociationsView.as_view(),
    ),
    path(
        "api/open/models/<str:model_id>/instances/<int:inst_id>/associations/<int:association_id>",
        open_views.OpenInstanceAssociationDetailView.as_view(),
    ),
]

urlpatterns = open_api_patterns + router.urls
