import pytest

from apps.patch_mgmt.constants import OSType, PatchSourceType
from apps.patch_mgmt.serializers.patch import LinuxPatchDetailSerializer, WindowsPatchDetailSerializer
from apps.patch_mgmt.serializers.patch_source import PatchSourceSerializer
from apps.patch_mgmt.serializers.patch_target import PatchTargetSerializer


def _serializer_context(request_factory, authenticated_user):
    request = request_factory.post("/")
    request.user = authenticated_user
    return {"request": request}


@pytest.mark.django_db
def test_patch_source_serializer_normalizes_linux_alias(request_factory, authenticated_user):
    serializer = PatchSourceSerializer(
        data={
            "name": "Ubuntu source",
            "source_type": PatchSourceType.APT_REPO,
            "url": "https://mirrors.example.com/ubuntu",
            "distro_name": "Ubuntu",
            "os_version": "22.04",
            "arch": "amd64",
            "team": [1],
        },
        context=_serializer_context(request_factory, authenticated_user),
    )

    assert serializer.is_valid(), serializer.errors
    assert serializer.validated_data["arch"] == "x86_64"


@pytest.mark.django_db
def test_patch_source_serializer_removes_wsus_source_architecture(request_factory, authenticated_user):
    serializer = PatchSourceSerializer(
        data={
            "name": "WSUS",
            "source_type": PatchSourceType.WSUS,
            "url": "http://wsus.example.com:8530",
            "arch": "x64",
            "auth_user": "administrator",
            "auth_password": "test-password",
            "team": [1],
        },
        context=_serializer_context(request_factory, authenticated_user),
    )

    assert serializer.is_valid(), serializer.errors
    assert serializer.validated_data["arch"] == ""


@pytest.mark.django_db
def test_patch_target_serializer_persists_normalized_node_architecture(request_factory, authenticated_user):
    serializer = PatchTargetSerializer(
        data={
            "name": "linux-arm",
            "ip": "192.0.2.10",
            "os_type": OSType.LINUX,
            "source_type": "node_mgmt",
            "node_id": "node-arm",
            "arch": "aarch64",
            "team": [1],
        },
        context=_serializer_context(request_factory, authenticated_user),
    )

    assert serializer.is_valid(), serializer.errors
    target = serializer.save()
    assert target.arch == "arm64"


@pytest.mark.django_db
def test_patch_target_serializer_rejects_windows_arm64(request_factory, authenticated_user):
    serializer = PatchTargetSerializer(
        data={
            "name": "windows-arm",
            "ip": "192.0.2.11",
            "os_type": OSType.WINDOWS,
            "source_type": "node_mgmt",
            "node_id": "node-windows-arm",
            "arch": "ARM64",
            "team": [1],
        },
        context=_serializer_context(request_factory, authenticated_user),
    )

    assert serializer.is_valid() is False
    assert "arch" in serializer.errors


def test_linux_patch_detail_serializer_normalizes_architecture_aliases():
    serializer = LinuxPatchDetailSerializer(
        data={
            "pkg_name": "openssl",
            "pkg_version": "1.0",
            "distro_name": "Ubuntu",
            "architectures": ["amd64", "x86_64"],
            "repo_type": "apt",
        }
    )

    assert serializer.is_valid(), serializer.errors
    assert serializer.validated_data["architectures"] == ["x86_64"]


def test_windows_patch_detail_serializer_normalizes_x64_and_rejects_x86():
    supported = WindowsPatchDetailSerializer(
        data={
            "kb_number": "KB1234567",
            "product_list": ["Windows Server 2022"],
            "architectures": ["x64"],
        }
    )
    unsupported = WindowsPatchDetailSerializer(
        data={
            "kb_number": "KB1234568",
            "product_list": ["Windows Server 2022"],
            "architectures": ["x86"],
        }
    )

    assert supported.is_valid(), supported.errors
    assert supported.validated_data["architectures"] == ["x86_64"]
    assert unsupported.is_valid() is False
    assert "architectures" in unsupported.errors


def test_windows_patch_detail_serializer_defaults_architecture_to_x86_64():
    serializer = WindowsPatchDetailSerializer(
        data={
            "kb_number": "KB1234569",
            "product_list": ["Windows Server 2022"],
        }
    )

    assert serializer.is_valid(), serializer.errors
    assert serializer.validated_data["architectures"] == ["x86_64"]

    empty_serializer = WindowsPatchDetailSerializer(
        data={
            "kb_number": "KB1234570",
            "product_list": ["Windows Server 2022"],
            "architectures": [],
        }
    )
    assert empty_serializer.is_valid(), empty_serializer.errors
    assert empty_serializer.validated_data["architectures"] == ["x86_64"]
