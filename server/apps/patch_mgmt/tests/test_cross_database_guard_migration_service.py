import pytest
from django.db import IntegrityError, connection, transaction
from django.db.migrations.executor import MigrationExecutor
from django.db.migrations.recorder import MigrationRecorder

from apps.core.tests.migration_helpers import migrate_to, migrated_from

OLD_TARGET = [("patch_mgmt", "0008_patch_deleted_source_snapshots")]
NEW_TARGET = [("patch_mgmt", "0009_cross_database_kb_guard")]


@pytest.mark.integration
@pytest.mark.django_db(transaction=True)
def test_existing_windows_patch_data_survives_guard_upgrade_and_rollback():
    with migrated_from(connection, OLD_TARGET, NEW_TARGET) as old_apps:
        Patch = old_apps.get_model("patch_mgmt", "Patch")
        WindowsPatchDetail = old_apps.get_model("patch_mgmt", "WindowsPatchDetail")

        identified_patch = Patch.objects.create(
            title="existing-identified-patch",
            os_type="windows",
            applicable_scope={"preserve": "scope"},
        )
        blank_patch = Patch.objects.create(
            title="existing-blank-kb-patch",
            os_type="windows",
            applicable_scope={"preserve": "blank"},
        )
        identified = WindowsPatchDetail.objects.create(
            patch=identified_patch,
            kb_number="KB-MIGRATION-7001",
            product_list=["Windows Server 2022"],
            architectures=["x86_64"],
            ms_bulletin="MS-PRESERVE",
        )
        blank = WindowsPatchDetail.objects.create(
            patch=blank_patch,
            kb_number="",
            product_list=["Windows 11"],
            architectures=["arm64"],
        )

        new_apps = migrate_to(connection, NEW_TARGET)
        MigratedDetail = new_apps.get_model("patch_mgmt", "WindowsPatchDetail")

        migrated_identified = MigratedDetail.objects.get(pk=identified.pk)
        migrated_blank = MigratedDetail.objects.get(pk=blank.pk)
        assert (
            migrated_identified.kb_number,
            migrated_identified.product_list,
            migrated_identified.architectures,
            migrated_identified.ms_bulletin,
            migrated_identified.kb_number_guard,
        ) == (
            "KB-MIGRATION-7001",
            ["Windows Server 2022"],
            ["x86_64"],
            "MS-PRESERVE",
            True,
        )
        assert (migrated_blank.kb_number, migrated_blank.product_list, migrated_blank.kb_number_guard) == (
            "",
            ["Windows 11"],
            None,
        )

        duplicate_patch = new_apps.get_model("patch_mgmt", "Patch").objects.create(
            title="duplicate-kb-patch",
            os_type="windows",
        )
        with pytest.raises(IntegrityError), transaction.atomic():
            MigratedDetail.objects.create(
                patch=duplicate_patch,
                kb_number="KB-MIGRATION-7001",
                kb_number_guard=True,
            )

        rolled_back_apps = migrate_to(connection, OLD_TARGET)
        RolledBackDetail = rolled_back_apps.get_model("patch_mgmt", "WindowsPatchDetail")
        assert RolledBackDetail.objects.get(pk=identified.pk).ms_bulletin == "MS-PRESERVE"


@pytest.mark.integration
@pytest.mark.django_db(transaction=True)
def test_mysql_duplicate_kb_preflight_can_be_fixed_and_retried():
    if connection.vendor != "mysql":
        pytest.skip("验证 MySQL 5.7 非事务 DDL 的失败恢复")

    with migrated_from(connection, OLD_TARGET, NEW_TARGET) as old_apps:
        Patch = old_apps.get_model("patch_mgmt", "Patch")
        WindowsPatchDetail = old_apps.get_model("patch_mgmt", "WindowsPatchDetail")
        first_patch = Patch.objects.create(title="duplicate-kb-first", os_type="windows")
        second_patch = Patch.objects.create(title="duplicate-kb-second", os_type="windows")
        WindowsPatchDetail.objects.create(patch=first_patch, kb_number="KB-DUPLICATE-MIGRATION")
        duplicate = WindowsPatchDetail.objects.create(
            patch=second_patch,
            kb_number="KB-DUPLICATE-MIGRATION",
        )

        try:
            with pytest.raises(RuntimeError, match="重复 KB 编号"):
                MigrationExecutor(connection).migrate(NEW_TARGET)

            with connection.cursor() as cursor:
                columns = {column.name for column in connection.introspection.get_table_description(cursor, WindowsPatchDetail._meta.db_table)}
            assert "kb_number_guard" not in columns
            assert not MigrationRecorder(connection).migration_qs.filter(app="patch_mgmt", name="0009_cross_database_kb_guard").exists()
        finally:
            duplicate.delete()

        migrated_apps = migrate_to(connection, NEW_TARGET)
        MigratedDetail = migrated_apps.get_model("patch_mgmt", "WindowsPatchDetail")
        assert MigratedDetail.objects.get().kb_number_guard is True
