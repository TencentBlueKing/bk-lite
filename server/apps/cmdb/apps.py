import sys
from django.apps import AppConfig


class CmdbConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "apps.cmdb"

    def ready(self):
        import apps.cmdb.nats.nats  # noqa

        # 发现接缝④：guarded 调用企业版运行时引导（配置/采集注册等），缺 enterprise 则跳过
        try:
            from apps.cmdb.enterprise import bootstrap as enterprise_bootstrap
            enterprise_bootstrap.install()
        except ModuleNotFoundError:
            pass

        # 仅在 runserver 时初始化所有缓存（避免在 migrate 等命令时加载）
        if 'runserver' in sys.argv:
            from apps.cmdb.display_field import init_all_caches_on_startup
            init_all_caches_on_startup()

