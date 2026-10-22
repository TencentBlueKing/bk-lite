"""安装前磁盘预算的纯计算。"""

from apps.patch_mgmt.services.disk_budget import (
    LinuxDiskProbe,
    MountFreeSpace,
    cab_expansion_limit_bytes,
    linux_disk_shortfall,
    manual_install_requirement_bytes,
    manual_stage_requirement_bytes,
    parse_install_sizes,
    parse_linux_disk_probe,
    parse_windows_free_bytes,
    windows_disk_shortfall,
)


def test_manual_stage_budget_includes_file_cab_expansion_and_reserve(monkeypatch):
    monkeypatch.setattr(
        "apps.patch_mgmt.services.disk_budget.windows_disk_reserve_bytes",
        lambda: 100,
    )

    required = manual_stage_requirement_bytes([(50, ".msu"), (10, ".cab")])

    assert required == 50 + 10 + cab_expansion_limit_bytes(10) + 100


def test_manual_install_budget_does_not_count_the_file_already_on_disk(monkeypatch):
    monkeypatch.setattr(
        "apps.patch_mgmt.services.disk_budget.windows_disk_reserve_bytes",
        lambda: 100,
    )

    required = manual_install_requirement_bytes([(50, ".msu"), (10, ".cab")])

    assert required == cab_expansion_limit_bytes(10) + 100


def test_windows_shortfall_reports_insufficient_space_without_probing_wua():
    code, reason = windows_disk_shortfall(10, 100, action="stage")

    assert code == "disk_insufficient"
    assert "staging" in reason


def test_windows_probe_failure_is_distinct_from_insufficient_space():
    code, reason = windows_disk_shortfall(None, 100, action="install")
    assert code == "disk_probe_failed"
    assert "Unable to read" in reason
    assert parse_windows_free_bytes("BKPATCH_DISK|ERROR|probe_failed") is None
    assert parse_windows_free_bytes("BKPATCH_DISK|WINDOWS|4096") == 4096


def test_linux_same_filesystem_adds_download_growth_and_reserve():
    probe = LinuxDiskProbe(
        root=MountFreeSpace("/", 1000),
        cache=MountFreeSpace("/", 1000),
    )

    code, reason = linux_disk_shortfall(probe, 400, 400, reserve_bytes=300)

    assert code == "disk_insufficient"
    assert "root filesystem" in reason


def test_linux_split_filesystem_checks_cache_and_root_separately():
    probe = LinuxDiskProbe(
        root=MountFreeSpace("/", 5000),
        cache=MountFreeSpace("/var", 100),
    )

    code, reason = linux_disk_shortfall(probe, 400, 100, reserve_bytes=50)

    assert code == "disk_insufficient"
    assert "download cache" in reason
    assert "root filesystem" not in reason


def test_parse_apt_and_dnf_install_sizes():
    apt = parse_install_sizes("Need to get 0 B/1,234 kB of archives.\n" "After this operation, 2 MB of additional disk space will be used.\n")
    dnf = parse_install_sizes("Total download size: 5.0 M\nInstalled size: 9 M\n")
    freed = parse_install_sizes("Need to get 10 kB of archives.\nAfter this operation, 3 MB disk space will be freed.\n")

    assert apt == (0, 2 * 1024 * 1024)
    assert dnf == (int(5 * 1024 * 1024), 9 * 1024 * 1024)
    assert freed == (10 * 1024, 0)


def test_apt_print_uris_and_installed_size_are_the_disk_inputs():
    from apps.patch_mgmt.services.disk_budget import parse_apt_download_bytes, parse_apt_installed_bytes

    download = parse_apt_download_bytes("'http://ports.ubuntu.com/ubuntu-ports/pool/main/h/hello/hello.deb' hello.deb 25184 MD5Sum:abc\n")
    installed = parse_apt_installed_bytes("Package: hello\nInstalled-Size: 144\nPackage: hello\nInstalled-Size: 999\n")

    assert download == 25184
    assert installed == 144 * 1024


def test_linux_probe_parser_rejects_incomplete_output():
    parsed = parse_linux_disk_probe("BKPATCH_DISK|root|/|100\nBKPATCH_DISK|cache|/var|40\n")

    assert parsed.root.free_bytes == 100
    assert parsed.cache.mount == "/var"
    assert parsed.same_filesystem is False
    assert parse_linux_disk_probe("BKPATCH_DISK|ERROR|probe_failed").error == "probe_failed"
