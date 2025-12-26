from django.apps import AppConfig


class MlopsConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'apps.mlops'

    def ready(self):
        import apps.mlops.signals  # noqa: 注册信号处理器
