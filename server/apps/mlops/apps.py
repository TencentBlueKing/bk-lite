from django.apps import AppConfig


class MlopsConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "apps.mlops"

    def ready(self):
        import apps.mlops.signals  # noqa: 注册信号处理器
        import apps.mlops.nats_api  # noqa: 注册 MLOps RPC 处理器
