"""patch_mgmt schema invariant tests.

Todo 2 行为定义：重复别名拒绝、重叠构建号拒绝、
非法状态/关系守卫、代表性记录创建。
"""

from types import SimpleNamespace

import pytest
from django.db import IntegrityError, transaction

from apps.patch_mgmt.constants import OSType, PackageStatus, PatchSourceType
from apps.patch_mgmt.models import LinuxPatchDetail, Patch, PatchSource, WindowsPatchDetail

# ── Patch + detail table creation ───────────────────────────────────────────


@pytest.mark.django_db
class TestPatchRecordCreation:
    """补丁主记录及 OS 扩展 detail 表创建与关联。"""

    def test_windows_patch_with_detail(self):
        source = PatchSource.objects.create(
            name="WSUS",
            source_type=PatchSourceType.WSUS,
            url="http://wsus.example.com:8530",
        )
        patch = Patch.objects.create(
            title="2024-01 Security Update for Windows Server 2019 (KB5034441)",
            os_type=OSType.WINDOWS,
            severity="critical",
            cve_list=["CVE-2024-21234"],
        )
        patch.sources.add(source)
        detail = WindowsPatchDetail.objects.create(
            patch=patch,
            kb_number="KB5034441",
            product_list=["Windows Server 2019"],
            architectures=["x64"],
        )
        assert patch.windows_detail.kb_number == "KB5034441"
        assert detail.patch_id == patch.pk
        assert detail.kb_number_guard is True

    def test_windows_kb_unique_guard_allows_blank_and_rejects_duplicate(self):
        first = Patch.objects.create(title="First Windows Patch", os_type=OSType.WINDOWS)
        second = Patch.objects.create(title="Second Windows Patch", os_type=OSType.WINDOWS)
        third = Patch.objects.create(title="Third Windows Patch", os_type=OSType.WINDOWS)
        WindowsPatchDetail.objects.create(patch=first, kb_number="KB5034442")
        WindowsPatchDetail.objects.create(patch=second, kb_number="")
        WindowsPatchDetail.objects.create(patch=third, kb_number="")

        with pytest.raises(IntegrityError), transaction.atomic():
            duplicate = Patch.objects.create(title="Duplicate Windows Patch", os_type=OSType.WINDOWS)
            WindowsPatchDetail.objects.create(patch=duplicate, kb_number="KB5034442")

        bulk_duplicate = Patch.objects.create(title="Bulk Duplicate Windows Patch", os_type=OSType.WINDOWS)
        with pytest.raises(IntegrityError), transaction.atomic():
            WindowsPatchDetail.objects.bulk_create([WindowsPatchDetail(patch=bulk_duplicate, kb_number="KB5034442")])

    def test_mysql_kb_guard_migration_rejects_duplicate_without_clearing_kb(self):
        from importlib import import_module

        from django.apps import apps
        from django.db import connection, models

        if connection.vendor != "mysql":
            pytest.skip("MySQL 5.7 legacy data migration contract")

        first_patch = Patch.objects.create(title="First Legacy KB", os_type=OSType.WINDOWS)
        duplicate_patch = Patch.objects.create(title="Duplicate Legacy KB", os_type=OSType.WINDOWS)
        first = WindowsPatchDetail.objects.create(patch=first_patch, kb_number="KB5034443")
        duplicate = WindowsPatchDetail(patch=duplicate_patch, kb_number="KB5034443", kb_number_guard=None)
        models.QuerySet(model=WindowsPatchDetail, using="default").bulk_create([duplicate])

        migration = import_module("apps.patch_mgmt.migrations.0010_cross_database_kb_guard")
        schema_editor = SimpleNamespace(connection=connection)
        with pytest.raises(RuntimeError, match="重复 KB 编号"):
            migration.ensure_kb_numbers_unique(apps, schema_editor)

        first.refresh_from_db()
        duplicate.refresh_from_db()
        assert first.kb_number_guard is True
        assert duplicate.kb_number == "KB5034443"
        assert duplicate.kb_number_guard is None

    def test_linux_patch_with_detail(self):
        patch = Patch.objects.create(title="openssl security update", os_type=OSType.LINUX)
        detail = LinuxPatchDetail.objects.create(
            patch=patch,
            pkg_name="openssl",
            pkg_version="3.0.2-1ubuntu1.10",
            distro_name="ubuntu",
            repo_type="apt",
        )
        assert patch.linux_detail.pkg_name == "openssl"
        assert detail.patch_id == patch.pk

    def test_default_pkg_status_is_pending(self):
        patch = Patch.objects.create(title="Test Patch", os_type=OSType.WINDOWS)
        assert patch.pkg_status == PackageStatus.PENDING

    def test_source_removed_when_no_m2m(self):
        """M2M 后补丁默认无来源（手动创建），sources 为空。"""
        source = PatchSource.objects.create(name="WSUS", source_type=PatchSourceType.WSUS)
        patch = Patch.objects.create(title="Test Patch", os_type=OSType.WINDOWS)
        patch.sources.add(source)
        source.delete()
        patch.refresh_from_db()
        assert patch.sources.count() == 0
