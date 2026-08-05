import pytest

from apps.patch_mgmt.constants import OSType, PatchSourceType
from apps.patch_mgmt.utils.architecture import (
    ARM64,
    X86_64,
    UnsupportedArchitecture,
    normalize_architecture,
    normalize_architectures,
    repository_architecture,
    repository_package_applies,
    supported_architectures,
)


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        ("x86_64", X86_64),
        ("amd64", X86_64),
        ("AMD64", X86_64),
        ("x64", X86_64),
        ("arm64", ARM64),
        ("ARM64", ARM64),
        ("aarch64", ARM64),
    ],
)
def test_normalize_architecture_accepts_platform_aliases(value, expected):
    assert normalize_architecture(value) == expected


def test_normalize_architecture_rejects_unsupported_32_bit_value():
    with pytest.raises(UnsupportedArchitecture):
        normalize_architecture("x86")


def test_normalize_architectures_replaces_repository_independent_arch_with_source_scope():
    assert normalize_architectures(["noarch", "x86_64"], fallback=X86_64) == [X86_64]
    assert normalize_architectures(["all"], fallback=ARM64) == [ARM64]


@pytest.mark.parametrize(
    ("source_type", "canonical", "expected"),
    [
        (PatchSourceType.APT_REPO, X86_64, "amd64"),
        (PatchSourceType.APT_REPO, ARM64, "arm64"),
        (PatchSourceType.YUM_REPO, X86_64, "x86_64"),
        (PatchSourceType.YUM_REPO, ARM64, "aarch64"),
        (PatchSourceType.DNF_REPO, X86_64, "x86_64"),
        (PatchSourceType.DNF_REPO, ARM64, "aarch64"),
        (PatchSourceType.WSUS, X86_64, "x64"),
        (PatchSourceType.WSUS, ARM64, "ARM64"),
    ],
)
def test_repository_architecture_maps_at_adapter_seam(source_type, canonical, expected):
    assert repository_architecture(canonical, source_type) == expected


@pytest.mark.parametrize(
    ("source_type", "target_architecture", "package_architecture", "expected"),
    [
        (PatchSourceType.YUM_REPO, X86_64, "x86_64", True),
        (PatchSourceType.YUM_REPO, X86_64, "noarch", True),
        (PatchSourceType.YUM_REPO, X86_64, "i686", False),
        (PatchSourceType.DNF_REPO, ARM64, "aarch64", True),
        (PatchSourceType.DNF_REPO, ARM64, "noarch", True),
        (PatchSourceType.DNF_REPO, ARM64, "x86_64", False),
        (PatchSourceType.APT_REPO, X86_64, "amd64", True),
        (PatchSourceType.APT_REPO, X86_64, "all", True),
        (PatchSourceType.APT_REPO, X86_64, "arm64", False),
    ],
)
def test_repository_package_applies_at_adapter_seam(
    source_type,
    target_architecture,
    package_architecture,
    expected,
):
    assert (
        repository_package_applies(
            package_architecture,
            source_type=source_type,
            target_architecture=target_architecture,
        )
        is expected
    )


def test_supported_architectures_match_bklite_platform_matrix():
    assert supported_architectures(OSType.LINUX) == (X86_64, ARM64)
    assert supported_architectures(OSType.WINDOWS) == (X86_64,)
