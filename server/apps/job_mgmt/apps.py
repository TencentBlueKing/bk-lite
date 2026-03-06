from django.apps import AppConfig


class JobMgmtConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "apps.job_mgmt"
    verbose_name = "作业管理"

    def ready(self):
        import apps.job_mgmt.nats_api  # noqa
