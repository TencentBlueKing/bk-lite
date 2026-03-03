from rest_framework import routers

from apps.monitor.views.infra import InfraViewSet
from apps.monitor.views.manual_collect import ManualCollect
from apps.monitor.views.monitor_alert import MonitorAlertViewSet, MonitorEventViewSet
from apps.monitor.views.monitor_instance import MonitorInstanceViewSet
from apps.monitor.views.monitor_metrics import MetricGroupViewSet, MetricViewSet
from apps.monitor.views.metrics_instance import MetricsInstanceViewSet
from apps.monitor.views.monitor_object import MonitorObjectViewSet
from apps.monitor.views.monitor_policy import MonitorPolicyViewSet
from apps.monitor.views.node_mgmt import NodeMgmtView
from apps.monitor.views.organization_rule import MonitorObjectOrganizationRuleViewSet
from apps.monitor.views.plugin import MonitorPluginViewSet
from apps.monitor.views.system_mgmt import SystemMgmtView
from apps.monitor.views.monitor_condition import MonitorConditionViewSet
from apps.monitor.views.unit import UnitViewSet

router = routers.DefaultRouter()
router.register(r"api/monitor_object", MonitorObjectViewSet, basename="MonitorObject")
router.register(r"api/metrics_group", MetricGroupViewSet, basename="MetricGroupViewSet")
router.register(r"api/metrics", MetricViewSet, basename="MetricViewSet")
router.register(
    r"api/metrics_instance", MetricsInstanceViewSet, basename="MetricsInstanceViewSet"
)
router.register(
    r"api/organization_rule",
    MonitorObjectOrganizationRuleViewSet,
    basename="MonitorObjectOrganizationRule",
)
router.register(
    r"api/monitor_instance", MonitorInstanceViewSet, basename="MonitorInstanceViewSet"
)
router.register(
    r"api/monitor_policy", MonitorPolicyViewSet, basename="MonitorPolicyViewSet"
)
router.register(
    r"api/monitor_plugin", MonitorPluginViewSet, basename="MonitorPluginViewSet"
)

router.register(
    r"api/monitor_alert", MonitorAlertViewSet, basename="MonitorAlertViewSet"
)
router.register(
    r"api/monitor_event", MonitorEventViewSet, basename="MonitorEventViewSet"
)

router.register(r"api/system_mgmt", SystemMgmtView, basename="SystemMgmtView")
router.register(r"api/node_mgmt", NodeMgmtView, basename="NodeMgmtView")

router.register(r"api/manual_collect", ManualCollect, basename="ManualCollect")
router.register(r"api/unit", UnitViewSet, basename="UnitViewSet")
router.register(
    r"api/monitor_condition",
    MonitorConditionViewSet,
    basename="MonitorConditionViewSet",
)
router.register(r"open_api/infra", InfraViewSet, basename="InfraViewSet")
urlpatterns = router.urls
