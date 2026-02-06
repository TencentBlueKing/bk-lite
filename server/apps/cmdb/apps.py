import sys
from django.apps import AppConfig


class CmdbConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "apps.cmdb"

    def ready(self):
        # 仅在 runserver 时初始化所有缓存（避免在 migrate 等命令时加载）
        if 'runserver' in sys.argv:
            import apps.cmdb.nats.nats  # noqa
            from apps.cmdb.display_field import init_all_caches_on_startup
            init_all_caches_on_startup()

