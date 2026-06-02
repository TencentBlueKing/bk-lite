from django.apps import AppConfig


class OpspilotConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "apps.opspilot"
    verbose_name = "opspilot management"

    def ready(self):
        import apps.opspilot.nats_api  # noqa
        import apps.opspilot.signals  # noqa: 注册信号处理器
        from apps.opspilot.memory.engines.local_engine import LocalMemoryEngine
        from apps.opspilot.memory.engines.registry import MemoryEngineRegistry

        MemoryEngineRegistry.register("local", LocalMemoryEngine)
