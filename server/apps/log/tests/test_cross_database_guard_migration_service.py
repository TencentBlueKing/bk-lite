import pytest
from django.db import IntegrityError, connection, transaction
from django.db.migrations.executor import MigrationExecutor

from apps.core.tests.migration_helpers import migrate_to, migrated_from

OLD_TARGET = [("log", "0019_k8sinstalltoken")]
NEW_TARGET = [("log", "0020_cross_database_extractor_guards")]


@pytest.mark.integration
@pytest.mark.django_db(transaction=True)
def test_existing_log_extractor_data_survives_portable_unique_upgrade_and_rollback():
    with migrated_from(connection, OLD_TARGET, NEW_TARGET) as old_apps:
        CollectType = old_apps.get_model("log", "CollectType")
        CollectInstance = old_apps.get_model("log", "CollectInstance")
        Extractor = old_apps.get_model("log", "LogExtractor")

        collect_type = CollectType.objects.create(
            name="existing-file-collector",
            collector="vector",
            icon="file",
            description="preserve-collect-type",
            default_query="preserve-query",
            attrs=[{"preserve": True}],
        )
        collect_instance = CollectInstance.objects.create(
            id="existing-log-instance",
            name="existing-log-instance",
            collect_type=collect_type,
            node_id="existing-node",
        )
        extractor = Extractor.objects.create(
            name="existing-extractor",
            collect_instance=collect_instance,
            condition={"when": "preserve"},
            extractor_type="regex",
            source_field="message",
            target_field="preserved_target",
            delete_source=False,
            config={"pattern": "preserve"},
            sort_order=7,
        )

        new_apps = migrate_to(connection, NEW_TARGET)
        MigratedExtractor = new_apps.get_model("log", "LogExtractor")
        migrated = MigratedExtractor.objects.get(pk=extractor.pk)
        assert (
            migrated.name,
            migrated.collect_instance_id,
            migrated.condition,
            migrated.extractor_type,
            migrated.source_field,
            migrated.target_field,
            migrated.config,
            migrated.sort_order,
        ) == (
            "existing-extractor",
            "existing-log-instance",
            {"when": "preserve"},
            "regex",
            "message",
            "preserved_target",
            {"pattern": "preserve"},
            7,
        )

        with pytest.raises(IntegrityError), transaction.atomic():
            MigratedExtractor.objects.create(
                name="existing-extractor",
                collect_instance_id="existing-log-instance",
                condition={},
                extractor_type="copy",
                source_field="message",
                target_field="duplicate",
                config={},
                sort_order=8,
            )

        rolled_back_apps = migrate_to(connection, OLD_TARGET)
        RolledBackExtractor = rolled_back_apps.get_model("log", "LogExtractor")
        assert RolledBackExtractor.objects.get(pk=extractor.pk).target_field == "preserved_target"


@pytest.mark.integration
@pytest.mark.django_db(transaction=True)
@pytest.mark.parametrize("duplicate_field", ["name", "sort_order"])
def test_mysql_duplicate_log_extractor_preflight_can_be_fixed_and_retried(duplicate_field):
    if connection.vendor != "mysql":
        pytest.skip("验证 MySQL 5.7 非事务 DDL 的失败恢复")

    with migrated_from(connection, OLD_TARGET, NEW_TARGET) as old_apps:
        CollectType = old_apps.get_model("log", "CollectType")
        CollectInstance = old_apps.get_model("log", "CollectInstance")
        Extractor = old_apps.get_model("log", "LogExtractor")
        collect_type = CollectType.objects.create(name="duplicate-collector", collector="vector")
        collect_instance = CollectInstance.objects.create(
            id="duplicate-log-instance",
            name="duplicate-log-instance",
            collect_type=collect_type,
            node_id="duplicate-node",
        )
        extractor_data = {
            "name": "duplicate-extractor",
            "collect_instance": collect_instance,
            "condition": {},
            "extractor_type": "copy",
            "source_field": "message",
            "target_field": "target",
            "config": {},
            "sort_order": 71,
        }
        Extractor.objects.create(**extractor_data)
        duplicate_data = extractor_data.copy()
        if duplicate_field == "name":
            duplicate_data["sort_order"] = 72
        else:
            duplicate_data["name"] = "duplicate-extractor-other"
        duplicate = Extractor.objects.create(**duplicate_data)

        try:
            with pytest.raises(RuntimeError, match="重复名称或顺序"):
                MigrationExecutor(connection).migrate(NEW_TARGET)

            with connection.cursor() as cursor:
                constraints = connection.introspection.get_constraints(cursor, Extractor._meta.db_table)
            assert "log_extractor_instance_name_portable_uniq" not in constraints
            assert "log_extractor_instance_order_portable_uniq" not in constraints
        finally:
            duplicate.delete()

        migrated_apps = migrate_to(connection, NEW_TARGET)
        MigratedExtractor = migrated_apps.get_model("log", "LogExtractor")
        assert MigratedExtractor.objects.get().sort_order == 71
