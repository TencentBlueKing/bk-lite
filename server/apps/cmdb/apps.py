from django.apps import AppConfig


class CmdbConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "apps.cmdb"

    def ready(self):
        import apps.cmdb.nats.nats  # noqa
        import apps.cmdb.openapi_api  # noqa
        from apps.cmdb.services.pc_discovery import install_pc_vm_metric_reconcile

        install_pc_vm_metric_reconcile()
