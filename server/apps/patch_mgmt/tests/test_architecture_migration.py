import pytest
from django.db import connection
from django.db.migrations.executor import MigrationExecutor


@pytest.mark.django_db(transaction=True)
def test_architecture_migration_normalizes_aliases_and_clears_unsupported_values():
    old_target = [("patch_mgmt", "0002_governance_record_snapshot")]
    new_target = [("patch_mgmt", "0003_normalize_cpu_architectures")]
    executor = MigrationExecutor(connection)
    executor.migrate(old_target)

    try:
        old_apps = executor.loader.project_state(old_target).apps
        Patch = old_apps.get_model("patch_mgmt", "Patch")
        PatchSource = old_apps.get_model("patch_mgmt", "PatchSource")
        PatchTarget = old_apps.get_model("patch_mgmt", "PatchTarget")
        LinuxPatchDetail = old_apps.get_model("patch_mgmt", "LinuxPatchDetail")
        WindowsPatchDetail = old_apps.get_model("patch_mgmt", "WindowsPatchDetail")

        apt_source = PatchSource.objects.create(
            name="apt-amd64", source_type="apt_repo", arch="amd64"
        )
        wsus_source = PatchSource.objects.create(
            name="wsus-x64", source_type="wsus", arch="x64"
        )
        linux_target = PatchTarget.objects.create(
            name="linux-arm", ip="192.0.2.1", os_type="linux", arch="aarch64"
        )
        windows_target = PatchTarget.objects.create(
            name="windows-arm", ip="192.0.2.2", os_type="windows", arch="ARM64"
        )
        unsupported_target = PatchTarget.objects.create(
            name="linux-x86", ip="192.0.2.3", os_type="linux", arch="x86"
        )

        linux_patch = Patch.objects.create(title="linux", os_type="linux")
        linux_patch.sources.add(apt_source)
        LinuxPatchDetail.objects.create(
            patch=linux_patch,
            architectures=["all", "aarch64", "x86"],
        )
        windows_patch = Patch.objects.create(title="windows", os_type="windows")
        WindowsPatchDetail.objects.create(
            patch=windows_patch,
            architectures=["x64", "ARM64", "x86"],
        )
        windows_patch_without_arch = Patch.objects.create(
            title="windows-no-arch",
            os_type="windows",
        )
        WindowsPatchDetail.objects.create(
            patch=windows_patch_without_arch,
            architectures=[],
        )

        executor = MigrationExecutor(connection)
        executor.migrate(new_target)
        new_apps = executor.loader.project_state(new_target).apps
        MigratedSource = new_apps.get_model("patch_mgmt", "PatchSource")
        MigratedTarget = new_apps.get_model("patch_mgmt", "PatchTarget")
        MigratedLinuxDetail = new_apps.get_model("patch_mgmt", "LinuxPatchDetail")
        MigratedWindowsDetail = new_apps.get_model("patch_mgmt", "WindowsPatchDetail")

        assert MigratedSource.objects.get(pk=apt_source.pk).arch == "x86_64"
        assert MigratedSource.objects.get(pk=wsus_source.pk).arch == ""
        assert MigratedTarget.objects.get(pk=linux_target.pk).arch == "arm64"
        assert MigratedTarget.objects.get(pk=windows_target.pk).arch == ""
        assert MigratedTarget.objects.get(pk=unsupported_target.pk).arch == ""
        assert MigratedLinuxDetail.objects.get(pk=linux_patch.pk).architectures == [
            "x86_64",
            "arm64",
        ]
        assert MigratedWindowsDetail.objects.get(pk=windows_patch.pk).architectures == [
            "x86_64"
        ]
        assert MigratedWindowsDetail.objects.get(
            pk=windows_patch_without_arch.pk
        ).architectures == ["x86_64"]
    finally:
        MigrationExecutor(connection).migrate(new_target)
