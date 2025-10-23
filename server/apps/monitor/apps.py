from django.apps import AppConfig


class MonitorConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "apps.monitor"

    def ready(self):
        import apps.monitor.nats.permission  # noqa
        import apps.monitor.nats.monitor  # noqa
