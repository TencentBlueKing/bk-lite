"""评估结果解析器单元测试"""

import pytest

from apps.patch_mgmt.constants import OSType
from apps.patch_mgmt.models import (
    BaselineRequirement,
    HostBaselineBinding,
    LinuxPatchDetail,
    Patch,
    PatchBaseline,
    PatchTarget,
    WindowsPatchDetail,
)
from apps.patch_mgmt.services import assess_parsers as parsers


APT_SAMPLE = """
Reading package lists... Done
Building dependency tree... Done
Reading state information... Done
Calculating upgrade... Done
The following packages will be upgraded:
  gzip perl-base tar
3 upgraded, 0 newly installed, 0 to remove and 0 not upgraded.
Inst gzip [1.10-10ubuntu4] (1.10-10ubuntu4.1 Ubuntu:24.04/noble-updates [amd64])
Inst perl-base [5.38.2-3.2build2] (5.38.2-3.2build2.1 Ubuntu:24.04/noble-updates [amd64])
Inst tar [1.35+dfsg-3build1] (1.35+dfsg-3build1.1 Ubuntu:24.04/noble-updates [amd64])
Conf gzip (1.10-10ubuntu4.1 Ubuntu:24.04/noble-updates [amd64])
"""

YUM_SAMPLE = """
Last metadata expiration check: 0:00:01 ago on Fri Jul 10 06:00:00 2026 UTC.
Available Upgrades
gzip.x86_64     1.10-10ubuntu4.1     noble-updates
perl-base.x86_64 5.38.2-3.2build2.1  noble-updates
tar.x86_64      1.35+dfsg-3build1.1  noble-updates
"""

DNF_SAMPLE = """
Last metadata expiration check: 0:00:01 ago.
Available Upgrades
curl.x86_64     7.76.1-26.el9_3.2    baseos
openssl.x86_64  1:3.0.7-25.el9_3     baseos
"""

HOTFIX_SAMPLE = """
HotFixID
KB5034441
KB5034763
KB5035857
"""


def test_parse_apt_upgradable():
    pkgs = parsers.parse_apt_upgradable(APT_SAMPLE)
    assert pkgs == {"gzip", "perl-base", "tar"}


def test_parse_apt_no_upgrades():
    stdout = "0 upgraded, 0 newly installed, 0 to remove and 0 not upgraded.\n"
    assert parsers.parse_apt_upgradable(stdout) == set()


def test_parse_yum_upgradable():
    pkgs = parsers.parse_yum_dnf_upgradable(YUM_SAMPLE)
    assert pkgs == {"gzip", "perl-base", "tar"}


def test_parse_dnf_upgradable():
    pkgs = parsers.parse_yum_dnf_upgradable(DNF_SAMPLE)
    assert pkgs == {"curl", "openssl"}


def test_parse_windows_hotfixes():
    kbs = parsers.parse_windows_hotfixes(HOTFIX_SAMPLE)
    assert kbs == {"KB5034441", "KB5034763", "KB5035857"}


def test_parse_windows_hotfixes_lowercase():
    kbs = parsers.parse_windows_hotfixes("kb123456\nKB999999")
    assert kbs == {"KB123456", "KB999999"}


@pytest.mark.django_db
def test_assess_linux_requirements():
    baseline = PatchBaseline.objects.create(name="linux-baseline", os_type=OSType.LINUX, team=[1])
    patch_gzip = Patch.objects.create(title="gzip update", os_type=OSType.LINUX, team=[1])
    LinuxPatchDetail.objects.create(patch=patch_gzip, pkg_name="gzip")
    patch_openssl = Patch.objects.create(title="openssl update", os_type=OSType.LINUX, team=[1])
    LinuxPatchDetail.objects.create(patch=patch_openssl, pkg_name="openssl")

    req_gzip = BaselineRequirement.objects.create(baseline=baseline, patch=patch_gzip)
    req_openssl = BaselineRequirement.objects.create(baseline=baseline, patch=patch_openssl)

    result = parsers.assess_requirements(OSType.LINUX, DNF_SAMPLE, [req_gzip, req_openssl])

    assert result[req_gzip.id].satisfied is True
    assert result[req_openssl.id].satisfied is False
    assert "curl" in result[req_gzip.id].evidence["upgradable_packages"]
    assert result[req_openssl.id].reason == "检测到 openssl 有待更新"


@pytest.mark.django_db
def test_assess_windows_requirements():
    baseline = PatchBaseline.objects.create(name="win-baseline", os_type=OSType.WINDOWS, team=[1])
    patch_present = Patch.objects.create(title="present kb", os_type=OSType.WINDOWS, team=[1])
    WindowsPatchDetail.objects.create(patch=patch_present, kb_number="KB5034441")
    patch_missing = Patch.objects.create(title="missing kb", os_type=OSType.WINDOWS, team=[1])
    WindowsPatchDetail.objects.create(patch=patch_missing, kb_number="KB9999999")

    req_present = BaselineRequirement.objects.create(baseline=baseline, patch=patch_present)
    req_missing = BaselineRequirement.objects.create(baseline=baseline, patch=patch_missing)

    result = parsers.assess_requirements(OSType.WINDOWS, HOTFIX_SAMPLE, [req_present, req_missing])

    assert result[req_present.id].satisfied is True
    assert result[req_missing.id].satisfied is False
    assert "KB5034441" in result[req_present.id].evidence["installed_kbs"]


@pytest.mark.django_db
def test_assess_linux_uses_apt_parser_when_markers_present():
    baseline = PatchBaseline.objects.create(name="apt-baseline", os_type=OSType.LINUX, team=[1])
    patch = Patch.objects.create(title="tar update", os_type=OSType.LINUX, team=[1])
    LinuxPatchDetail.objects.create(patch=patch, pkg_name="tar")
    req = BaselineRequirement.objects.create(baseline=baseline, patch=patch)

    result = parsers.assess_requirements(OSType.LINUX, APT_SAMPLE, [req])

    assert result[req.id].satisfied is False
    assert result[req.id].evidence["pkg_name"] == "tar"
