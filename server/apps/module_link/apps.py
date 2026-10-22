from django.apps import AppConfig


class ModuleLinkConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "apps.module_link"
    verbose_name = "跨模块同步任务"

    def ready(self):
        from django.conf import settings

        from apps.module_link.license_policy import apply_module_link_license_exempt, inject_inherit_middleware

        apply_module_link_license_exempt()
        inject_inherit_middleware(settings)
