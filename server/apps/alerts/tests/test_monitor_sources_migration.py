"""仅在独立测试表上执行真实 0031 正反向迁移，不触碰业务表。"""

from importlib import import_module

import pytest
from django.db import connection, models
from django.db.migrations.state import ModelState, ProjectState


@pytest.mark.integration
@pytest.mark.django_db(transaction=True)
def test_monitor_sources_migration_defaults_existing_rows_and_is_reversible():
    state = ProjectState()
    state.add_model(
        ModelState(
            "alerts",
            "Alert",
            [
                ("id", models.AutoField(primary_key=True)),
                ("title", models.CharField(max_length=100)),
            ],
            options={"db_table": "test_monitor_sources_migration_probe"},
        )
    )
    historical = state.apps.get_model("alerts", "Alert")
    with connection.schema_editor() as editor:
        editor.create_model(historical)
    try:
        old = historical.objects.create(title="升级前告警")
        migration = import_module("apps.alerts.migrations.0031_alert_push_source_ids").Migration("0031_alert_push_source_ids", "alerts")
        with connection.schema_editor() as editor:
            new_state = migration.apply(state.clone(), editor)
        upgraded = new_state.apps.get_model("alerts", "Alert")
        assert upgraded.objects.get(pk=old.pk).push_source_ids == []
        upgraded.objects.filter(pk=old.pk).update(push_source_ids=["001", "1", "prod"])
        assert upgraded.objects.get(pk=old.pk).push_source_ids == ["001", "1", "prod"]
        assert upgraded.objects.create(title="升级后告警").push_source_ids == []
        with connection.schema_editor() as editor:
            migration.unapply(state.clone(), editor)
        assert list(historical.objects.order_by("pk").values_list("title", flat=True)) == ["升级前告警", "升级后告警"]
    finally:
        with connection.schema_editor() as editor:
            editor.delete_model(historical)
