"""内置补丁源初始化服务测试。"""

from django.core.management import call_command

import pytest

from apps.patch_mgmt.constants import PatchSourceType
from apps.patch_mgmt.models import PatchSource


pytestmark = [pytest.mark.unit, pytest.mark.django_db]


def test_init_patch_sources_creates_one_current_source_for_each_linux_repo_type():
    call_command("init_patch_sources")

    builtins = PatchSource.objects.filter(is_builtin=True).order_by("builtin_key")

    assert builtins.count() == 3
    assert set(builtins.values_list("builtin_key", flat=True)) == {
        "oracle-linux-9-yum-baseos",
        "rocky-linux-9-dnf-baseos",
        "ubuntu-24-04-apt-main-security",
    }
    assert list(
        builtins.values("source_type")
        .order_by("source_type")
        .values_list("source_type", flat=True)
    ) == sorted(
        [
            PatchSourceType.YUM_REPO,
            PatchSourceType.DNF_REPO,
            PatchSourceType.APT_REPO,
        ]
    )
    assert all(source.team == [] for source in builtins)
    assert all(source.is_enabled for source in builtins)
    assert all(source.connectivity_status == "unknown" for source in builtins)
    assert all(source.last_checked_at is None for source in builtins)


def test_init_patch_sources_is_idempotent_and_preserves_runtime_configuration():
    call_command("init_patch_sources")
    source = PatchSource.objects.get(builtin_key="rocky-linux-9-dnf-baseos")
    source.url = "https://mirror.example.com/rocky/9"
    source.proxy_host = "proxy.example.com"
    source.proxy_port = 8080
    source.is_enabled = False
    source.save()

    call_command("init_patch_sources")

    source.refresh_from_db()
    assert PatchSource.objects.filter(is_builtin=True).count() == 3
    assert source.url == "https://mirror.example.com/rocky/9"
    assert source.proxy_host == "proxy.example.com"
    assert source.proxy_port == 8080
    assert source.is_enabled is False


def test_init_patch_sources_recreates_a_missing_builtin_source():
    call_command("init_patch_sources")
    PatchSource.objects.get(
        builtin_key="ubuntu-24-04-apt-main-security"
    ).delete()

    call_command("init_patch_sources")

    recreated = PatchSource.objects.get(
        builtin_key="ubuntu-24-04-apt-main-security"
    )
    assert recreated.url == "https://security.ubuntu.com/ubuntu"
    assert recreated.distro_name == "Ubuntu"
    assert recreated.os_version == "24.04"
