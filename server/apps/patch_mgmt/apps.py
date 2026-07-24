from django.apps import AppConfig


class PatchMgmtConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "apps.patch_mgmt"
    verbose_name = "补丁管理"

    def ready(self):
        import apps.patch_mgmt.nats_api  # noqa
