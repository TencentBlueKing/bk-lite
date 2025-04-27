from django.apps import AppConfig


class HandleConfig(AppConfig):
    name = "apps.system_mgmt"

    #
    def ready(self):
        import apps.system_mgmt.nats_api  # noqa
