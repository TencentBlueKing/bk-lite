from django.apps import AppConfig


class DjangoNatsConfig(AppConfig):
    name = "nats_client"

    def ready(self):
        # register rpc-level callback handlers for tests
        import apps.rpc.ansible  # noqa
