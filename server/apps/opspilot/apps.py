from django.apps import AppConfig
from django.db.models.signals import post_migrate


class OpspilotConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "apps.opspilot"
    verbose_name = "opspilot management"

    def ready(self):
        import apps.opspilot.nats_api  # noqa
        from apps.opspilot.signals.user_create_signal import user_create_signal

        post_migrate.connect(user_create_signal, sender=self)
