from rest_framework.routers import DefaultRouter

from apps.workflow.views import (
    AtomConfigTemplateViewSet,
    AtomDefinitionViewSet,
    ExecutionArtifactViewSet,
    WorkflowExecutionViewSet,
    WorkflowInteractionViewSet,
    WorkflowTriggerViewSet,
    WorkflowViewSet,
)

router = DefaultRouter()
router.register(r"api/atom-config-templates", AtomConfigTemplateViewSet, basename="workflow-atom-config-template")
router.register(r"api/atoms", AtomDefinitionViewSet, basename="workflow-atom")
router.register(r"api/workflows", WorkflowViewSet, basename="workflow-workflow")
router.register(r"api/executions", WorkflowExecutionViewSet, basename="workflow-execution")
router.register(r"api/interactions", WorkflowInteractionViewSet, basename="workflow-interaction")
router.register(r"api/triggers", WorkflowTriggerViewSet, basename="workflow-trigger")
router.register(r"api/artifacts", ExecutionArtifactViewSet, basename="workflow-artifact")

urlpatterns = router.urls
