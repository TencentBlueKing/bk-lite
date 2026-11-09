from django.apps import AppConfig


class ItsmConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "apps.itsm"
    verbose_name = "ITSM"

    def ready(self):
        import apps.itsm.nats  # noqa: F401
        import apps.itsm.signals  # noqa: F401
