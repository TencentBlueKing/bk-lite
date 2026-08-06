from rest_framework import routers

from apps.apm.views.control_plane import (
    ApmApplicationViewSet,
    ApmEventViewSet,
    ApmIntegrationConfigurationViewSet,
    ApmNotificationChannelViewSet,
    ApmNotificationDeliveryViewSet,
    ApmNotificationRecipientViewSet,
    ApmPolicyViewSet,
    ApmServiceInstanceViewSet,
    ApmServiceViewSet,
    ApmSloViewSet,
)
from apps.apm.views.dashboard import ApmDashboardViewSet
from apps.apm.views.health import ApmHealthViewSet
from apps.apm.views.traces import ApmTraceViewSet
from apps.apm.views.topology import ApmTopologyViewSet

router = routers.DefaultRouter()
router.register(r"applications", ApmApplicationViewSet, basename="apm-application")
router.register(r"integration-config", ApmIntegrationConfigurationViewSet, basename="apm-integration-config")
router.register(r"instances", ApmServiceInstanceViewSet, basename="apm-instance")
router.register(r"services", ApmServiceViewSet, basename="apm-service")
router.register(r"slos", ApmSloViewSet, basename="apm-slo")
router.register(r"dashboard", ApmDashboardViewSet, basename="apm-dashboard")
router.register(r"health", ApmHealthViewSet, basename="apm-health")
router.register(r"traces", ApmTraceViewSet, basename="apm-trace")
router.register(r"topology", ApmTopologyViewSet, basename="apm-topology")
router.register(r"policies", ApmPolicyViewSet, basename="apm-policy")
router.register(r"events", ApmEventViewSet, basename="apm-event")
router.register(r"notification-channels", ApmNotificationChannelViewSet, basename="apm-notification-channel")
router.register(r"notification-deliveries", ApmNotificationDeliveryViewSet, basename="apm-notification-delivery")
router.register(r"notification-recipients", ApmNotificationRecipientViewSet, basename="apm-notification-recipient")

urlpatterns = router.urls
