"""patch_mgmt schema invariant tests.

Todo 2 行为定义：重复别名拒绝、重叠构建号拒绝、
非法状态/关系守卫、代表性记录创建。
"""
import pytest
from django.core.exceptions import ValidationError

from apps.patch_mgmt.constants import (
    OSType,
    PackageStatus,
    PatchSourceType,
    RebootPolicy,
)
from apps.patch_mgmt.models import (
    LinuxPatchDetail,
    Patch,
    PatchSource,
    PatchTarget,
    WindowsPatchDetail,
)


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
