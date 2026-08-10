"""评估结果解析器单元测试"""

import pytest

from apps.patch_mgmt.constants import OSType, RequirementAssessmentStatus
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
    LinuxPatchDetail.objects.create(patch=patch_gzip, pkg_name="gzip", pkg_version="1.10")
    patch_openssl = Patch.objects.create(title="openssl update", os_type=OSType.LINUX, team=[1])
    LinuxPatchDetail.objects.create(patch=patch_openssl, pkg_name="openssl", pkg_version="3.0.8")

    req_gzip = BaselineRequirement.objects.create(baseline=baseline, patch=patch_gzip)
    req_openssl = BaselineRequirement.objects.create(baseline=baseline, patch=patch_openssl)

    stdout = "\n".join([
        f"BKPATCH_LINUX|{req_gzip.id}|gzip|installed|1.10|0|",
        f"BKPATCH_LINUX|{req_openssl.id}|openssl|installed|3.0.7|-1|",
    ])
    result = parsers.assess_requirements(OSType.LINUX, stdout, [req_gzip, req_openssl])

    assert result[req_gzip.id].satisfied is True
    assert result[req_openssl.id].satisfied is False
    assert result[req_gzip.id].evidence["installed_version"] == "1.10"
    assert result[req_openssl.id].reason == "openssl 已安装版本低于最低版本"


@pytest.mark.django_db
@pytest.mark.integration
def test_assess_linux_requirements_checks_every_advisory_package():
    baseline = PatchBaseline.objects.create(name="multi-package", os_type=OSType.LINUX, team=[1])
    patch = Patch.objects.create(title="multi package advisory", os_type=OSType.LINUX, team=[1])
    detail = LinuxPatchDetail.objects.create(
        patch=patch,
        pkg_name="not-upgradable",
        pkg_version="1.0",
    )
    detail.packages = [
        {"name": "not-upgradable", "version": "1.0", "arch": "x86_64"},
        {"name": "openssl", "version": "3.0", "arch": "x86_64"},
        {"name": "openssl", "version": "3.0", "arch": "x86_64"},
        {"name": "", "version": "ignored", "arch": "x86_64"},
    ]
    detail.save(update_fields=["packages"])
    req = BaselineRequirement.objects.create(baseline=baseline, patch=patch)

    stdout = "\n".join(
        [
            f"BKPATCH_LINUX|{req.id}|not-upgradable|installed|1.0|0|",
            f"BKPATCH_LINUX|{req.id}|openssl|installed|2.9|-1|",
        ]
    )
    result = parsers.assess_requirements(OSType.LINUX, stdout, [req])

    assert result[req.id].satisfied is False
    assert result[req.id].evidence["pkg_names"] == ["not-upgradable", "openssl"]
    assert result[req.id].evidence["missing_pkg_names"] == ["openssl"]
    assert result[req.id].reason == "openssl 未满足最低版本要求"


@pytest.mark.django_db
@pytest.mark.integration
def test_assess_linux_requirements_keeps_same_package_version_facts_distinct():
    baseline = PatchBaseline.objects.create(name="same-package-versions", os_type=OSType.LINUX, team=[1])
    patch = Patch.objects.create(title="openssl advisory", os_type=OSType.LINUX, team=[1])
    detail = LinuxPatchDetail.objects.create(patch=patch, pkg_name="openssl", pkg_version="3.0")
    detail.packages = [
        {"name": "openssl", "version": "3.0", "arch": "x86_64"},
        {"name": "openssl", "version": "2.0", "arch": "x86_64"},
    ]
    detail.save(update_fields=["packages"])
    req = BaselineRequirement.objects.create(baseline=baseline, patch=patch)
    stdout = "\n".join(
        [
            f"BKPATCH_LINUX|{req.id}|0|openssl|installed|2.5|-1|",
            f"BKPATCH_LINUX|{req.id}|1|openssl|installed|2.5|0|",
        ]
    )

    result = parsers.assess_requirements(OSType.LINUX, stdout, [req])

    assert result[req.id].status == RequirementAssessmentStatus.MISSING
    assert result[req.id].evidence["missing_pkg_names"] == ["openssl"]


@pytest.mark.django_db
@pytest.mark.integration
def test_assess_linux_requirements_does_not_reuse_another_structured_spec_fact():
    baseline = PatchBaseline.objects.create(name="partial-output", os_type=OSType.LINUX, team=[1])
    patch = Patch.objects.create(title="openssl advisory", os_type=OSType.LINUX, team=[1])
    detail = LinuxPatchDetail.objects.create(patch=patch, pkg_name="openssl", pkg_version="3.0")
    detail.packages = [
        {"name": "openssl", "version": "3.0", "arch": "x86_64"},
        {"name": "openssl", "version": "2.0", "arch": "x86_64"},
    ]
    detail.save(update_fields=["packages"])
    req = BaselineRequirement.objects.create(baseline=baseline, patch=patch)

    result = parsers.assess_requirements(
        OSType.LINUX,
        f"BKPATCH_LINUX|{req.id}|1|openssl|installed|2.5|0|",
        [req],
    )

    assert result[req.id].status == RequirementAssessmentStatus.UNKNOWN
    assert result[req.id].evidence["unknown_pkg_names"] == ["openssl"]


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
    assert result[req_missing.id].status == RequirementAssessmentStatus.UNKNOWN
    assert "KB5034441" in result[req_present.id].evidence["installed_kbs"]


@pytest.mark.django_db
def test_assess_linux_uses_apt_parser_when_markers_present():
    baseline = PatchBaseline.objects.create(name="apt-baseline", os_type=OSType.LINUX, team=[1])
    patch = Patch.objects.create(title="tar update", os_type=OSType.LINUX, team=[1])
    LinuxPatchDetail.objects.create(patch=patch, pkg_name="tar")
    req = BaselineRequirement.objects.create(baseline=baseline, patch=patch)

    result = parsers.assess_requirements(OSType.LINUX, APT_SAMPLE, [req])

    assert result[req.id].status == RequirementAssessmentStatus.UNKNOWN
    assert result[req.id].satisfied is False


@pytest.mark.django_db
def test_assess_linux_structured_facts_use_native_version_result_and_explicit_absence():
    baseline = PatchBaseline.objects.create(name="linux-facts", os_type=OSType.LINUX, team=[1])
    patch_ok = Patch.objects.create(title="openssl", os_type=OSType.LINUX, team=[1])
    LinuxPatchDetail.objects.create(patch=patch_ok, pkg_name="openssl", pkg_version="3.0.0")
    patch_absent = Patch.objects.create(title="curl", os_type=OSType.LINUX, team=[1])
    LinuxPatchDetail.objects.create(patch=patch_absent, pkg_name="curl", pkg_version="8.0.0")
    req_ok = BaselineRequirement.objects.create(baseline=baseline, patch=patch_ok)
    req_absent = BaselineRequirement.objects.create(baseline=baseline, patch=patch_absent)
    stdout = "\n".join([
        f"BKPATCH_LINUX|{req_ok.id}|openssl|installed|3.0.1|0|",
        f"BKPATCH_LINUX|{req_absent.id}|curl|absent|||",
    ])

    result = parsers.assess_requirements(OSType.LINUX, stdout, [req_ok, req_absent])

    assert result[req_ok.id].status == RequirementAssessmentStatus.SATISFIED
    assert result[req_absent.id].status == RequirementAssessmentStatus.MISSING
    assert result[req_absent.id].reason == "未安装 curl"


@pytest.mark.django_db
def test_assess_linux_marks_foreign_distribution_requirement_not_applicable():
    baseline = PatchBaseline.objects.create(name="linux-applicability", os_type=OSType.LINUX, team=[1])
    patch = Patch.objects.create(title="Ubuntu only", os_type=OSType.LINUX, team=[1])
    LinuxPatchDetail.objects.create(
        patch=patch,
        pkg_name="ubuntu-only-package",
        pkg_version="1.0",
        distro_name="Ubuntu",
        os_version_range="24.04",
        architectures=["x86_64"],
        repo_type="apt",
    )
    requirement = BaselineRequirement.objects.create(baseline=baseline, patch=patch)
    stdout = "\n".join(
        [
            "BKPATCH_HOST|LINUX|rocky|rhel centos fedora|9.6|x86_64|dnf",
            f"BKPATCH_LINUX|{requirement.id}|ubuntu-only-package|absent|||",
        ]
    )

    result = parsers.assess_requirements(OSType.LINUX, stdout, [requirement])

    assert result[requirement.id].status == RequirementAssessmentStatus.NOT_APPLICABLE
    assert "发行版" in result[requirement.id].reason


@pytest.mark.django_db
def test_assess_linux_marks_foreign_multi_package_requirement_not_applicable():
    baseline = PatchBaseline.objects.create(name="multi-package-applicability", os_type=OSType.LINUX, team=[1])
    patch = Patch.objects.create(title="Ubuntu multi-package", os_type=OSType.LINUX, team=[1])
    detail = LinuxPatchDetail.objects.create(
        patch=patch,
        pkg_name="ubuntu-package-a",
        pkg_version="1.0",
        distro_name="Ubuntu",
        os_version_range="24.04",
        architectures=["x86_64"],
        repo_type="apt",
    )
    detail.packages = [
        {"name": "ubuntu-package-a", "version": "1.0", "arch": "x86_64"},
        {"name": "ubuntu-package-b", "version": "2.0", "arch": "x86_64"},
    ]
    detail.save(update_fields=["packages"])
    requirement = BaselineRequirement.objects.create(baseline=baseline, patch=patch)
    stdout = "\n".join(
        [
            "BKPATCH_HOST|LINUX|rocky|rhel centos fedora|9.6|x86_64|dnf",
            f"BKPATCH_LINUX|{requirement.id}|0|ubuntu-package-a|absent|||",
            f"BKPATCH_LINUX|{requirement.id}|1|ubuntu-package-b|absent|||",
        ]
    )

    result = parsers.assess_requirements(OSType.LINUX, stdout, [requirement])

    assert result[requirement.id].status == RequirementAssessmentStatus.NOT_APPLICABLE
    assert result[requirement.id].evidence["not_applicable_pkg_names"] == [
        "ubuntu-package-a",
        "ubuntu-package-b",
    ]


@pytest.mark.django_db
def test_assess_linux_treats_yum_requirement_as_applicable_on_dnf_host():
    baseline = PatchBaseline.objects.create(name="rpm-family", os_type=OSType.LINUX, team=[1])
    patch = Patch.objects.create(title="Rocky yum package", os_type=OSType.LINUX, team=[1])
    LinuxPatchDetail.objects.create(
        patch=patch,
        pkg_name="cloud-init",
        pkg_version="24.4-8.el9",
        distro_name="Rocky Linux",
        os_version_range="9",
        architectures=["aarch64"],
        repo_type="yum",
    )
    requirement = BaselineRequirement.objects.create(baseline=baseline, patch=patch)
    stdout = "\n".join(
        [
            "BKPATCH_HOST|LINUX|rocky|rhel centos fedora|9.6|arm64|dnf",
            f"BKPATCH_LINUX|{requirement.id}|cloud-init|absent|||",
        ]
    )

    result = parsers.assess_requirements(OSType.LINUX, stdout, [requirement])

    assert result[requirement.id].status == RequirementAssessmentStatus.MISSING


@pytest.mark.django_db
def test_assess_windows_marks_definite_product_mismatch_not_applicable():
    baseline = PatchBaseline.objects.create(name="windows-applicability", os_type=OSType.WINDOWS, team=[1])
    patch = Patch.objects.create(title="Windows Server 2019 only", os_type=OSType.WINDOWS, team=[1])
    WindowsPatchDetail.objects.create(
        patch=patch,
        kb_number="KB9999999",
        product_list=["Windows Server 2019"],
        architectures=["x64"],
    )
    requirement = BaselineRequirement.objects.create(baseline=baseline, patch=patch)
    stdout = "\n".join(
        [
            "BKPATCH_HOST|WINDOWS|Microsoft Windows Server 2022 Standard|10.0|20348|AMD64",
            "===WUA===",
            "===WUA_INSTALLED===",
            "===HOTFIX===",
        ]
    )

    result = parsers.assess_requirements(OSType.WINDOWS, stdout, [requirement])

    assert result[requirement.id].status == RequirementAssessmentStatus.NOT_APPLICABLE
    assert "产品" in result[requirement.id].reason


@pytest.mark.django_db
def test_assess_windows_wua_offer_is_authoritative_over_catalog_product_metadata():
    baseline = PatchBaseline.objects.create(name="windows-wua-authority", os_type=OSType.WINDOWS, team=[1])
    patch = Patch.objects.create(title="WUA offered update", os_type=OSType.WINDOWS, team=[1])
    WindowsPatchDetail.objects.create(
        patch=patch,
        kb_number="KB5000003",
        product_list=["Windows 11"],
        architectures=["x64"],
    )
    requirement = BaselineRequirement.objects.create(baseline=baseline, patch=patch)
    stdout = "\n".join(
        [
            "BKPATCH_HOST|WINDOWS|Microsoft Windows Server 2022 Standard|10.0|20348|AMD64",
            "===WUA===",
            "KB5000003|Important|Applicable update",
            "===WUA_INSTALLED===",
            "===HOTFIX===",
        ]
    )

    result = parsers.assess_requirements(OSType.WINDOWS, stdout, [requirement])

    assert result[requirement.id].status == RequirementAssessmentStatus.MISSING


@pytest.mark.django_db
def test_assess_windows_neither_installed_nor_offered_is_unknown():
    baseline = PatchBaseline.objects.create(name="win-unknown", os_type=OSType.WINDOWS, team=[1])
    patch = Patch.objects.create(title="unknown kb", os_type=OSType.WINDOWS, team=[1])
    WindowsPatchDetail.objects.create(patch=patch, kb_number="KB5999999")
    req = BaselineRequirement.objects.create(baseline=baseline, patch=patch)

    result = parsers.assess_requirements(
        OSType.WINDOWS,
        "===WUA===\n===HOTFIX===\nKB5000001",
        [req],
    )

    assert result[req.id].status == RequirementAssessmentStatus.UNKNOWN


@pytest.mark.django_db
def test_assess_windows_uses_current_wua_installed_updates():
    baseline = PatchBaseline.objects.create(name="win-wua-installed", os_type=OSType.WINDOWS, team=[1])
    patch = Patch.objects.create(title="defender intelligence", os_type=OSType.WINDOWS, team=[1])
    WindowsPatchDetail.objects.create(patch=patch, kb_number="KB2267602")
    req = BaselineRequirement.objects.create(baseline=baseline, patch=patch)
    stdout = "\n".join([
        "===WUA===",
        "KB4052623|Critical|Platform update for Microsoft Defender Antivirus",
        "===WUA_INSTALLED===",
        "KB2267602||Microsoft Defender Antivirus security intelligence update",
        "===HOTFIX===",
        "KB5072653",
    ])

    result = parsers.assess_requirements(OSType.WINDOWS, stdout, [req])

    assert result[req.id].status == RequirementAssessmentStatus.SATISFIED
    assert result[req.id].reason == "已安装 KB2267602"
    assert "KB2267602" in result[req.id].evidence["installed_kbs"]
