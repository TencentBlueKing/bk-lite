import sys

from django.apps import AppConfig


class CmdbConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "apps.cmdb"

    def ready(self):
        is_running_migrations = 'makemigrations' in sys.argv or 'migrate' in sys.argv
        if not is_running_migrations:
            import apps.cmdb.nats  # noqa
