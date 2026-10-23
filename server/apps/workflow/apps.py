from django.apps import AppConfig


class WorkflowConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "apps.workflow"
    label = "workflow"
    verbose_name = "编排中心"

    def ready(self):
        from apps.workflow import nats_api  # noqa: F401
        from apps.workflow import openapi_api  # noqa: F401
