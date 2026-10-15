from apps.core.logger import configure_loguru
from django.apps import AppConfig


class CoreConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "apps.core"

    def ready(self):
        from apps.core.db_patches import apply_patches

        configure_loguru()
        apply_patches()
