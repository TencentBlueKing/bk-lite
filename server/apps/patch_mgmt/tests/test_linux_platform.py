"""Linux 原生包生态识别协议测试。"""

from apps.patch_mgmt.services.linux_platform import (
    linux_host_facts_command,
    package_manager_family,
    parse_linux_host_facts,
    validate_linux_host_facts,
)


def test_parse_complete_apt_host_facts():
    facts = parse_linux_host_facts(
        "noise\nBKPATCH_HOST|LINUX|ubuntu|debian|24.04|x86_64|apt\n"
    )

    assert facts.distro_id == "ubuntu"
    assert facts.distro_like == ("debian",)
    assert facts.package_manager == "apt"
    assert validate_linux_host_facts(facts) == ""


def test_conflicting_native_databases_are_rejected():
    facts = parse_linux_host_facts(
        "BKPATCH_HOST|LINUX|custom|linux|1|x86_64|conflict"
    )

    assert "dpkg 与 RPM" in validate_linux_host_facts(facts)


def test_detection_uses_native_databases_instead_of_command_priority():
    command = linux_host_facts_command(marker="patch-connectivity-ok")

    assert "/var/lib/dpkg/status" in command
    assert "rpm -qa" in command
    assert "has_dpkg" in command and "has_rpm" in command
    assert "manager=conflict" in command
    assert "patch-connectivity-ok" in command
    assert "&>" not in command


def test_package_manager_family_allows_dnf_and_yum_but_not_apt_mix():
    assert package_manager_family("apt_repo") == "apt"
    assert package_manager_family("dnf") == "rpm"
    assert package_manager_family("yum_repo") == "rpm"
