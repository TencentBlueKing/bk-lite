from django.apps import AppConfig


class NodeMgmtConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'apps.node_mgmt'

    def ready(self):
        import apps.node_mgmt.nats.node  # noqa
        import apps.node_mgmt.nats.permission   #noqa