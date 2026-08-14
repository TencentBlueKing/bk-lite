import pytest
from django.db import connection
from django.test import override_settings

from apps.core.tests.migration_helpers import migrate_to, migrated_from

CELERY_BEAT_TARGET = ("django_celery_beat", "0018_improve_crontab_helptext")
OLD_TARGET = [
    ("patch_mgmt", "0010_cross_database_kb_guard"),
    CELERY_BEAT_TARGET,
]
NEW_TARGET = [
    ("patch_mgmt", "0011_scan_setting_timezone"),
    CELERY_BEAT_TARGET,
]


class RequireExplicitMigrationAliasRouter:
    """本迁移的历史模型若未显式选库，将访问导向不存在的别名。"""

    guarded_models = {
        ("patch_mgmt", "scansetting"),
        ("django_celery_beat", "periodictask"),
    }

    def db_for_read(self, model, **_hints):
        if (model._meta.app_label, model._meta.model_name) in self.guarded_models:
            return "implicit_access_forbidden"
        return None

    def db_for_write(self, model, **_hints):
        if (model._meta.app_label, model._meta.model_name) in self.guarded_models:
            return "implicit_access_forbidden"
        return None


@pytest.mark.integration
@pytest.mark.django_db(transaction=True)
def test_scan_setting_timezone_migration_uses_active_database_and_rolls_back():
    """迁移应在当前 schema 所在库保留存量调度时区，并可反向执行。"""
    with migrated_from(connection, OLD_TARGET, NEW_TARGET) as old_apps:
        ScanSetting = old_apps.get_model("patch_mgmt", "ScanSetting")
        CrontabSchedule = old_apps.get_model(
            "django_celery_beat",
            "CrontabSchedule",
        )
        PeriodicTask = old_apps.get_model("django_celery_beat", "PeriodicTask")
        setting, _ = ScanSetting.objects.get_or_create(pk=1)
        schedule = CrontabSchedule.objects.create(
            minute="0",
            hour="10",
            day_of_month="*",
            month_of_year="*",
            day_of_week="5",
            timezone="America/New_York",
        )
        PeriodicTask.objects.update_or_create(
            name="patch_mgmt_periodic_compliance_scan",
            defaults={
                "task": "apps.patch_mgmt.tasks.run_periodic_compliance_scan",
                "crontab": schedule,
                "enabled": True,
            },
        )

        router_path = "apps.patch_mgmt.tests.test_scan_setting_timezone_migration_service." "RequireExplicitMigrationAliasRouter"
        with override_settings(DATABASE_ROUTERS=[router_path]):
            new_apps = migrate_to(connection, NEW_TARGET)

        MigratedSetting = new_apps.get_model("patch_mgmt", "ScanSetting")
        assert MigratedSetting.objects.get(pk=setting.pk).timezone == "America/New_York"

        rolled_back_apps = migrate_to(connection, OLD_TARGET)
        RolledBackSetting = rolled_back_apps.get_model("patch_mgmt", "ScanSetting")
        assert RolledBackSetting.objects.get(pk=setting.pk).time == setting.time
