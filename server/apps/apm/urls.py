from rest_framework import routers

from apps.apm.views.control_plane import (
    ApmEventViewSet,
    ApmIngestSourceViewSet,
    ApmNotificationChannelViewSet,
    ApmPolicyViewSet,
    ApmServiceInstanceViewSet,
    ApmServiceViewSet,
)
from apps.apm.views.machine_auth import ApmMachineAuthViewSet
from apps.apm.views.health import ApmHealthViewSet
from apps.apm.views.traces import ApmTraceViewSet

router = routers.DefaultRouter()
router.register(r"ingest-sources", ApmIngestSourceViewSet, basename="apm-ingest-source")
router.register(r"instances", ApmServiceInstanceViewSet, basename="apm-instance")
router.register(r"services", ApmServiceViewSet, basename="apm-service")
router.register(r"machine-auth", ApmMachineAuthViewSet, basename="apm-machine-auth")
router.register(r"health", ApmHealthViewSet, basename="apm-health")
router.register(r"traces", ApmTraceViewSet, basename="apm-trace")
router.register(r"policies", ApmPolicyViewSet, basename="apm-policy")
router.register(r"events", ApmEventViewSet, basename="apm-event")
router.register(r"notification-channels", ApmNotificationChannelViewSet, basename="apm-notification-channel")

urlpatterns = router.urls
