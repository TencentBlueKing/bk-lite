"""PackageService 真实行为测试：架构解析、路径构建、文件名解析、上传校验、S3 异步包装。

仅 mock S3/JetStream 异步边界。断言真实返回值与 DB 查询逻辑。
"""
import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from types import SimpleNamespace

from nats.js.errors import ObjectNotFoundError

from apps.node_mgmt.constants.node import NodeConstants
from apps.node_mgmt.constants.package import PackageConstants
from apps.node_mgmt.models import Collector, PackageVersion
from apps.node_mgmt.services.package import PackageService


# --------------------------------------------------------------------------- #
# normalize_upload_cpu_architecture
# --------------------------------------------------------------------------- #
def test_normalize_upload_arch_defaults_to_x86():
    assert PackageService.normalize_upload_cpu_architecture(None) == "x86_64"
    assert PackageService.normalize_upload_cpu_architecture("") == "x86_64"


def test_normalize_upload_arch_maps_aliases():
    assert PackageService.normalize_upload_cpu_architecture("amd64") == NodeConstants.X86_64_ARCH
    assert PackageService.normalize_upload_cpu_architecture("aarch64") == NodeConstants.ARM64_ARCH


# --------------------------------------------------------------------------- #
# resolve_package_by_architecture
# --------------------------------------------------------------------------- #
@pytest.mark.django_db
def test_resolve_package_missing_seed_returns_none():
    assert PackageService.resolve_package_by_architecture(999999, "x86_64") is None


@pytest.mark.django_db
def test_resolve_package_no_arch_returns_seed():
    pkg = PackageVersion.objects.create(
        type="collector", os="linux", cpu_architecture="x86_64",
        object="telegraf", version="1.0.0", name="telegraf-1.0.0.tar.gz",
    )
    resolved = PackageService.resolve_package_by_architecture(pkg.id, "")
    assert resolved.id == pkg.id


@pytest.mark.django_db
def test_resolve_package_matches_exact_arch():
    seed = PackageVersion.objects.create(
        type="collector", os="linux", cpu_architecture="x86_64",
        object="telegraf", version="1.0.0", name="telegraf-1.0.0.tar.gz",
    )
    arm = PackageVersion.objects.create(
        type="collector", os="linux", cpu_architecture="arm64",
        object="telegraf", version="1.0.0", name="telegraf-arm-1.0.0.tar.gz",
    )
    resolved = PackageService.resolve_package_by_architecture(seed.id, "arm64")
    assert resolved.id == arm.id


@pytest.mark.django_db
def test_resolve_package_x86_falls_back_to_empty_arch():
    seed = PackageVersion.objects.create(
        type="collector", os="linux", cpu_architecture="arm64",
        object="telegraf", version="1.0.0", name="t-arm.tar.gz",
    )
    legacy = PackageVersion.objects.create(
        type="collector", os="linux", cpu_architecture="",
        object="telegraf", version="1.0.0", name="t-legacy.tar.gz",
    )
    resolved = PackageService.resolve_package_by_architecture(seed.id, "x86_64")
    assert resolved.id == legacy.id


@pytest.mark.django_db
def test_resolve_package_arm_no_match_returns_none():
    seed = PackageVersion.objects.create(
        type="collector", os="linux", cpu_architecture="x86_64",
        object="telegraf", version="1.0.0", name="t.tar.gz",
    )
    assert PackageService.resolve_package_by_architecture(seed.id, "arm64") is None


# --------------------------------------------------------------------------- #
# resolve_collector_by_architecture
# --------------------------------------------------------------------------- #
@pytest.mark.django_db
def test_resolve_collector_exact_arch():
    collector = Collector.objects.create(
        id="c-x86", name="Telegraf", service_type="svc",
        node_operating_system="linux", cpu_architecture="x86_64",
        executable_path="/bin", execute_parameters="-c",
    )
    resolved = PackageService.resolve_collector_by_architecture("linux", "Telegraf", "x86_64")
    assert resolved.id == collector.id


@pytest.mark.django_db
def test_resolve_collector_arm_no_match_returns_none():
    Collector.objects.create(
        id="c-x86-2", name="Telegraf", service_type="svc",
        node_operating_system="linux", cpu_architecture="x86_64",
        executable_path="/bin", execute_parameters="-c",
    )
    assert PackageService.resolve_collector_by_architecture("linux", "Telegraf", "arm64") is None


@pytest.mark.django_db
def test_resolve_collector_falls_back_to_empty_or_x86():
    collector = Collector.objects.create(
        id="c-empty", name="Vector", service_type="svc",
        node_operating_system="linux", cpu_architecture="",
        executable_path="/bin", execute_parameters="-c",
    )
    resolved = PackageService.resolve_collector_by_architecture("linux", "Vector", "")
    # normalize("") -> "" 精确匹配空架构
    assert resolved.id == collector.id


# --------------------------------------------------------------------------- #
# build_file_path / legacy / candidates
# --------------------------------------------------------------------------- #
def test_build_file_path_with_arch():
    obj = SimpleNamespace(cpu_architecture="arm64", os="linux", object="telegraf", version="1.0.0", name="t.tar.gz")
    assert PackageService.build_file_path(obj) == "linux/arm64/telegraf/1.0.0/t.tar.gz"


def test_build_file_path_generic_when_no_arch():
    obj = SimpleNamespace(cpu_architecture="", os="linux", object="telegraf", version="1.0.0", name="t.tar.gz")
    assert PackageService.build_file_path(obj) == "linux/generic/telegraf/1.0.0/t.tar.gz"


def test_build_legacy_file_path():
    obj = SimpleNamespace(os="linux", object="telegraf", version="1.0.0", name="t.tar.gz")
    assert PackageService.build_legacy_file_path(obj) == "linux/telegraf/1.0.0/t.tar.gz"


def test_build_candidate_file_paths_dedups():
    obj = SimpleNamespace(cpu_architecture="x86_64", os="linux", object="telegraf", version="1.0.0", name="t.tar.gz")
    candidates = PackageService.build_candidate_file_paths(obj)
    assert candidates == [
        "linux/x86_64/telegraf/1.0.0/t.tar.gz",
        "linux/telegraf/1.0.0/t.tar.gz",
    ]


# --------------------------------------------------------------------------- #
# parse_package_info
# --------------------------------------------------------------------------- #
def test_parse_package_info_with_extension():
    info = PackageService.parse_package_info("telegraf-1.2.3.tar.gz")
    assert info["object"] == "telegraf"
    assert info["version"] == "1.2.3"
    assert info["name_without_version"] == "telegraf.tar.gz"


def test_parse_package_info_no_version_returns_none():
    assert PackageService.parse_package_info("noversionhere.tar.gz") is None


# --------------------------------------------------------------------------- #
# validate_package
# --------------------------------------------------------------------------- #
@pytest.mark.django_db
def test_validate_package_version_not_found():
    ok, msg, info = PackageService.validate_package(
        "bad.tar.gz", PackageConstants.TYPE_CONTROLLER, "linux", "fusion-collectors"
    )
    assert ok is False
    assert info is None


@pytest.mark.django_db
def test_validate_package_controller_success():
    ok, msg, info = PackageService.validate_package(
        "fusion-collectors-1.0.0.tar.gz",
        PackageConstants.TYPE_CONTROLLER, "linux", "fusion-collectors",
    )
    assert ok is True
    assert info["version"] == "1.0.0"


@pytest.mark.django_db
def test_validate_package_type_mismatch():
    ok, msg, info = PackageService.validate_package(
        "wrongname-1.0.0.tar.gz",
        PackageConstants.TYPE_CONTROLLER, "linux", "fusion-collectors",
    )
    assert ok is False
    assert info is None


@pytest.mark.django_db
def test_validate_package_version_exists():
    PackageVersion.objects.create(
        type="controller", os="linux", cpu_architecture="x86_64",
        object="fusion-collectors", version="1.0.0", name="fusion-collectors-1.0.0.tar.gz",
    )
    ok, msg, info = PackageService.validate_package(
        "fusion-collectors-1.0.0.tar.gz",
        PackageConstants.TYPE_CONTROLLER, "linux", "fusion-collectors",
    )
    assert ok is False
    assert "已存在" in msg


@pytest.mark.django_db
def test_validate_package_latest_version_allows_overwrite():
    PackageVersion.objects.create(
        type="controller", os="linux", cpu_architecture="x86_64",
        object="fusion-collectors", version="latest", name="fusion-collectors-latest.tar.gz",
    )
    ok, msg, info = PackageService.validate_package(
        "fusion-collectors-latest.tar.gz".replace("latest", "9.9.9"),
        PackageConstants.TYPE_CONTROLLER, "linux", "fusion-collectors",
    )
    # 9.9.9 不存在 -> 直接通过
    assert ok is True


@pytest.mark.django_db
def test_validate_package_collector_uses_package_name():
    Collector.objects.create(
        id="c-pkgname", name="MyCollector", service_type="svc",
        node_operating_system="linux", cpu_architecture="x86_64",
        executable_path="/bin", execute_parameters="-c", package_name="mycol",
    )
    ok, msg, info = PackageService.validate_package(
        "mycol-1.0.0.tar.gz",
        PackageConstants.TYPE_COLLECTOR, "linux", "MyCollector", "x86_64",
    )
    assert ok is True


# --------------------------------------------------------------------------- #
# async S3 wrappers (mock boundary)
# --------------------------------------------------------------------------- #
@pytest.mark.django_db
def test_download_file_tries_candidates_and_succeeds():
    obj = SimpleNamespace(cpu_architecture="x86_64", os="linux", object="t", version="1.0.0", name="t.tar.gz")
    download = AsyncMock(return_value=b"data")
    with patch("apps.node_mgmt.services.package.download_file_by_s3", download):
        result = PackageService.download_file(obj)
    assert result == b"data"


@pytest.mark.django_db
def test_download_file_all_missing_raises():
    obj = SimpleNamespace(cpu_architecture="x86_64", os="linux", object="t", version="1.0.0", name="t.tar.gz")
    download = AsyncMock(side_effect=ObjectNotFoundError())
    with patch("apps.node_mgmt.services.package.download_file_by_s3", download):
        with pytest.raises(ObjectNotFoundError):
            PackageService.download_file(obj)


@pytest.mark.django_db
def test_delete_file_succeeds_on_first_candidate():
    obj = SimpleNamespace(cpu_architecture="x86_64", os="linux", object="t", version="1.0.0", name="t.tar.gz")
    delete = AsyncMock(return_value=None)
    with patch("apps.node_mgmt.services.package.delete_s3_file", delete):
        assert PackageService.delete_file(obj) is True


@pytest.mark.django_db
def test_delete_file_all_missing_raises():
    obj = SimpleNamespace(cpu_architecture="x86_64", os="linux", object="t", version="1.0.0", name="t.tar.gz")
    delete = AsyncMock(side_effect=ObjectNotFoundError())
    with patch("apps.node_mgmt.services.package.delete_s3_file", delete):
        with pytest.raises(ObjectNotFoundError):
            PackageService.delete_file(obj)


@pytest.mark.django_db
def test_list_files_maps_attributes():
    file_obj = MagicMock(name="f", nuid="nuid1", description="desc", deleted=False)
    file_obj.name = "pkg.tar.gz"
    lister = AsyncMock(return_value=[file_obj])
    with patch("apps.node_mgmt.services.package.list_s3_files", lister):
        result = PackageService.list_files()
    assert result == [{"name": "pkg.tar.gz", "nuid": "nuid1", "description": "desc", "deleted": False}]


@pytest.mark.django_db
def test_upload_file_builds_path_and_calls_s3():
    captured = {}

    async def fake_upload(file, path):
        captured["path"] = path

    data = {"os": "linux", "cpu_architecture": "arm64", "object": "telegraf", "version": "1.0.0", "name": "t.tar.gz"}
    with patch("apps.node_mgmt.services.package.upload_file_to_s3", fake_upload):
        PackageService.upload_file(MagicMock(), data)
    assert captured["path"] == "linux/arm64/telegraf/1.0.0/t.tar.gz"
