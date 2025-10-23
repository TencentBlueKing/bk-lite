from rest_framework import routers

from apps.monitor.views.monitor_alert import MonitorAlertVieSet, MonitorEventVieSet, MonitorAlertMetricSnapshotViewSet
from apps.monitor.views.monitor_instance import MonitorInstanceVieSet
from apps.monitor.views.monitor_metrics import  MetricGroupVieSet, MetricVieSet
from apps.monitor.views.metrics_instance import MetricsInstanceVieSet
from apps.monitor.views.monitor_object import MonitorObjectVieSet
from apps.monitor.views.monitor_policy import MonitorPolicyVieSet
from apps.monitor.views.node_mgmt import NodeMgmtView
from apps.monitor.views.organization_rule import MonitorObjectOrganizationRuleVieSet
from apps.monitor.views.plugin import MonitorPluginVieSet
from apps.monitor.views.system_mgmt import SystemMgmtView

router = routers.DefaultRouter()
router.register(r"api/monitor_object", MonitorObjectVieSet, basename="MonitorObject")
router.register(r"api/metrics_group", MetricGroupVieSet, basename="MetricGroupVieSet")
router.register(r"api/metrics", MetricVieSet, basename="MetricVieSet")
router.register(r"api/metrics_instance", MetricsInstanceVieSet, basename="MetricsInstanceVieSet")
router.register(r"api/organization_rule", MonitorObjectOrganizationRuleVieSet, basename="MonitorObjectOrganizationRule")
router.register(r"api/monitor_instance", MonitorInstanceVieSet, basename="MonitorInstanceVieSet")
router.register(r"api/monitor_policy", MonitorPolicyVieSet, basename="MonitorPolicyVieSet")
router.register(r"api/monitor_plugin", MonitorPluginVieSet, basename="MonitorPluginVieSet")

router.register(r"api/monitor_alert", MonitorAlertVieSet, basename="MonitorAlertVieSet")
router.register(r"api/monitor_event", MonitorEventVieSet, basename="MonitorEventVieSet")
router.register(r"api/monitor_alert_metric_snapshot", MonitorAlertMetricSnapshotViewSet, basename="MonitorAlertMetricSnapshotViewSet")

router.register(r"api/system_mgmt", SystemMgmtView, basename="SystemMgmtView")
router.register(r"api/node_mgmt", NodeMgmtView, basename="NodeMgmtView")
urlpatterns = router.urls
