from rest_framework.routers import DefaultRouter

from apps.workflow_orchestration.views import (
    AtomConfigTemplateViewSet,
    AtomDefinitionViewSet,
    ExecutionArtifactViewSet,
    WorkflowExecutionViewSet,
    WorkflowInteractionViewSet,
    WorkflowTriggerViewSet,
    WorkflowViewSet,
)

router = DefaultRouter()
router.register(r"api/atom-config-templates", AtomConfigTemplateViewSet, basename="workflow-orchestration-atom-config-template")
router.register(r"api/atoms", AtomDefinitionViewSet, basename="workflow-orchestration-atom")
router.register(r"api/workflows", WorkflowViewSet, basename="workflow-orchestration-workflow")
router.register(r"api/executions", WorkflowExecutionViewSet, basename="workflow-orchestration-execution")
router.register(r"api/interactions", WorkflowInteractionViewSet, basename="workflow-orchestration-interaction")
router.register(r"api/triggers", WorkflowTriggerViewSet, basename="workflow-orchestration-trigger")
router.register(r"api/artifacts", ExecutionArtifactViewSet, basename="workflow-orchestration-artifact")

urlpatterns = router.urls
