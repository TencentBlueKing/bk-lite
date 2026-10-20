from django.apps import AppConfig


class ModuleLinkConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "apps.module_link"
    verbose_name = "跨模块同步任务"
