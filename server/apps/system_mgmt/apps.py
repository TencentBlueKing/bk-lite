from django.apps import AppConfig


class HandleConfig(AppConfig):
    name = "apps.system_mgmt"

    #
    def ready(self):
        import apps.system_mgmt.nats_api  # noqa
        from apps.system_mgmt.providers.loader import load_builtin_providers

        load_builtin_providers()
