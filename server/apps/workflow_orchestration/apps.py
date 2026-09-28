from django.apps import AppConfig


class WorkflowOrchestrationConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "apps.workflow_orchestration"
    verbose_name = "编排中心"

    def ready(self):
        from apps.workflow_orchestration import nats_api  # noqa: F401
        from apps.workflow_orchestration import openapi_api  # noqa: F401
