from django.apps import AppConfig


class CmdbConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "apps.cmdb"

    def ready(self):
        import apps.cmdb.nats.nats  # noqa
