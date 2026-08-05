from django.apps import AppConfig


class OpspilotConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "apps.opspilot"
    verbose_name = "opspilot management"

    def ready(self):
        from apps.opspilot.services.wiki.wiki_budget_service import load_wiki_budget_config

        load_wiki_budget_config(force_reload=True)
        import apps.opspilot.nats_api  # noqa
        import apps.opspilot.signals  # noqa: F401  # 注册信号处理器
        from apps.opspilot.memory.engines.local_engine import LocalMemoryEngine
        from apps.opspilot.memory.engines.registry import MemoryEngineRegistry

        MemoryEngineRegistry.register("local", LocalMemoryEngine)
