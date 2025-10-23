from django.apps import AppConfig


class LogConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'apps.log'

    def ready(self):
        import apps.log.nats.permission  # noqa
        import apps.log.nats.log # noqa