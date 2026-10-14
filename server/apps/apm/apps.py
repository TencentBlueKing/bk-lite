from django.apps import AppConfig


class ApmConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "apps.apm"
    verbose_name = "APM"

    def ready(self):
        import apps.apm.openapi_api  # noqa
