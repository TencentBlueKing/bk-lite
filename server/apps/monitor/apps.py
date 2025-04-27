from django.apps import AppConfig
from django.db.models.signals import post_migrate



class MonitorConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'apps.monitor'

    def ready(self):
        from apps.monitor.initialization.update_grouping_rule import create_periodic_task
        post_migrate.connect(create_periodic_task)
