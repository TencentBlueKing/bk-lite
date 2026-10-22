"""手工 Windows 补丁包校验与私有存储。"""

import hashlib
from dataclasses import dataclass
from datetime import timedelta
from pathlib import Path

from django.db import transaction
from django.db.models import Q
from django.utils import timezone

from apps.core.logger import patch_mgmt_logger as logger
from apps.patch_mgmt.config import PATCH_MGMT_MAX_PACKAGE_SIZE_MB, PATCH_MGMT_PACKAGE_UPLOAD_TIMEOUT
from apps.patch_mgmt.constants import OSType, PackageStatus
from apps.patch_mgmt.exceptions import CodedMessageError
from apps.patch_mgmt.models import Patch, WindowsPatchDetail
from apps.patch_mgmt.services.windows_dotnet import normalize_declared_dotnet_version
from apps.patch_mgmt.services.windows_package_identity import (
    WindowsPackageIdentityError,
    inspect_windows_update_package,
    package_sha256,
    read_package_bytes,
)
from apps.patch_mgmt.utils.i18n import patch_message


class WindowsPackageError(CodedMessageError):
    """手工 Windows 补丁包不可接受。"""


class WindowsPackageStorageError(WindowsPackageError):
    """补丁包已通过校验，但对象存储不可用。"""


@dataclass(frozen=True)
class PreparedWindowsPackage:
    file_name: str
    extension: str
    file_size: int
    sha256: str


def _safe_file_name(value: str) -> str:
    return Path(str(value or "package")).name


def prepare_windows_package(uploaded_file) -> PreparedWindowsPackage:
    file_name = _safe_file_name(getattr(uploaded_file, "name", ""))
    extension = Path(file_name).suffix.lower()
    if extension not in {".msu", ".cab"}:
        raise WindowsPackageError("package_extension", "Only .msu and .cab patch packages are supported")

    file_size = int(getattr(uploaded_file, "size", 0) or 0)
    max_bytes = PATCH_MGMT_MAX_PACKAGE_SIZE_MB * 1024 * 1024
    if file_size <= 0:
        raise WindowsPackageError("package_empty", "The patch package is empty")
    if file_size > max_bytes:
        raise WindowsPackageError(
            "package_too_large",
            "The patch package cannot exceed {limit} MB",
            limit=PATCH_MGMT_MAX_PACKAGE_SIZE_MB,
        )

    uploaded_file.seek(0)
    signature = uploaded_file.read(4)
    # MSU 在不同代际可能表现为 ZIP 或 Cabinet 容器；CAB 的规范文件头为 MSCF。
    if extension == ".msu" and not (signature.startswith(b"PK") or signature == b"MSCF"):
        raise WindowsPackageError("package_msu_header", "The .msu file header is invalid")
    if extension == ".cab" and signature != b"MSCF":
        raise WindowsPackageError("package_cab_header", "The .cab file header is invalid")

    uploaded_file.seek(0)
    digest = hashlib.sha256()
    for chunk in uploaded_file.chunks():
        digest.update(chunk)
    uploaded_file.seek(0)
    return PreparedWindowsPackage(
        file_name=file_name,
        extension=extension,
        file_size=file_size,
        sha256=digest.hexdigest(),
    )


def _lock_patch(patch: Patch) -> Patch:
    return Patch.objects.select_for_update().get(pk=patch.pk)


def _mark_failed(patch: Patch, detail, message: str) -> None:
    with transaction.atomic():
        locked = _lock_patch(patch)
        if locked.pkg_status != PackageStatus.DOWNLOADING:
            return
        locked.pkg_status = PackageStatus.DOWNLOAD_FAILED
        locked.save(update_fields=["pkg_status", "updated_at"])
        try:
            locked_detail = locked.windows_detail
        except WindowsPatchDetail.DoesNotExist:
            locked_detail = detail
        locked_detail.package_error = message[:1000]
        locked_detail.save(update_fields=["package_error"])


def _declared_dotnet_version(value: str) -> str:
    try:
        return normalize_declared_dotnet_version(value)
    except ValueError as exc:
        raise WindowsPackageError("package_dotnet_invalid", "The declared .NET version is invalid") from exc


def store_windows_package(
    patch: Patch,
    uploaded_file,
    *,
    prepared: PreparedWindowsPackage | None = None,
    declared_dotnet_version: str = "",
) -> dict:
    """校验并保存手工补丁包，成功后才将补丁置为就绪。"""
    if patch.os_type != OSType.WINDOWS:
        raise WindowsPackageError("package_windows_only", "Only Windows patches can upload a package file")

    detail = None
    try:
        with transaction.atomic():
            locked = _lock_patch(patch)
            if locked.os_type != OSType.WINDOWS:
                raise WindowsPackageError("package_windows_only", "Only Windows patches can upload a package file")
            if locked.pkg_status != PackageStatus.DOWNLOADING:
                raise WindowsPackageError("package_status_blocked", "The current patch status does not allow a package upload")
            detail = locked.windows_detail
            package = prepared or prepare_windows_package(uploaded_file)
            payload = read_package_bytes(uploaded_file)
            if package_sha256(payload) != package.sha256:
                raise WindowsPackageError("package_hash_mismatch", "The patch package content does not match its checksum")
            try:
                identity = inspect_windows_update_package(
                    payload,
                    expected_kb=detail.kb_number,
                    file_name=package.file_name,
                    declared_dotnet_version=_declared_dotnet_version(declared_dotnet_version),
                )
            except WindowsPackageIdentityError as exc:
                raise WindowsPackageError(exc.code, exc.default, **exc.params) from exc
            detail.package_original_name = package.file_name
            detail.package_extension = package.extension
            detail.package_dotnet_version = identity.dotnet_version
            detail.package_size = package.file_size
            detail.package_sha256 = package.sha256
            detail.package_error = ""
            detail.package_file.save(package.file_name, uploaded_file, save=False)
            detail.package_uploaded_at = timezone.now()
            detail.save(
                update_fields=[
                    "package_file",
                    "package_original_name",
                    "package_extension",
                    "package_dotnet_version",
                    "package_size",
                    "package_sha256",
                    "package_error",
                    "package_uploaded_at",
                ]
            )
            locked.pkg_status = PackageStatus.READY
            locked.save(update_fields=["pkg_status", "updated_at"])
    except WindowsPackageError as exc:
        if detail is None:
            raise
        _mark_failed(patch, detail, str(exc))
        raise
    except Exception as exc:
        if detail is not None and detail.package_file:
            try:
                detail.package_file.delete(save=False)
            except Exception:
                pass
        if detail is None:
            raise
        _mark_failed(
            patch,
            detail,
            patch_message(
                None,
                "error.package_store_failed",
                "Failed to store the patch package: {cause}",
                cause=exc,
            ),
        )
        raise WindowsPackageStorageError("package_store_failed", "Failed to store the patch package") from exc

    return {
        "file_name": package.file_name,
        "file_size": package.file_size,
        "sha256": package.sha256,
        "extension": package.extension,
    }


def replace_failed_windows_package(
    patch: Patch,
    uploaded_file,
    *,
    prepared: PreparedWindowsPackage | None = None,
    declared_dotnet_version: str = "",
) -> dict:
    """仅对失败记录重新上传，就绪文件不允许替换。"""
    with transaction.atomic():
        locked = _lock_patch(patch)
        if locked.pkg_status != PackageStatus.DOWNLOAD_FAILED:
            raise WindowsPackageError("package_replace_only_failed", "Only a failed upload can be replaced")

        detail = locked.windows_detail
        if detail.package_file:
            try:
                detail.package_file.delete(save=False)
            except Exception as exc:
                raise WindowsPackageError("package_cleanup_failed", "The previous failed patch package could not be removed") from exc

        locked.pkg_status = PackageStatus.DOWNLOADING
        locked.save(update_fields=["pkg_status", "updated_at"])
    return store_windows_package(
        locked,
        uploaded_file,
        prepared=prepared,
        declared_dotnet_version=declared_dotnet_version,
    )


def expire_stale_windows_package_uploads(
    *,
    timeout_seconds: int = PATCH_MGMT_PACKAGE_UPLOAD_TIMEOUT,
    now=None,
) -> int:
    """将长期未完成上传的手工 Windows 补丁收口为失败。

    兼容旧版本留下的 pending 元数据记录；已绑定补丁源或有同步时间的
    pending 记录不属于手工上传，不在此处收口。
    """
    current = now or timezone.now()
    deadline = current - timedelta(seconds=max(int(timeout_seconds), 1))
    stale_ids = list(
        Patch.objects.filter(
            os_type=OSType.WINDOWS,
            updated_at__lt=deadline,
        )
        .filter(
            Q(pkg_status=PackageStatus.DOWNLOADING)
            | Q(
                pkg_status=PackageStatus.PENDING,
                sources__isnull=True,
                last_synced_at__isnull=True,
            )
        )
        .distinct()
        .values_list("id", flat=True)
    )
    expired = 0
    for patch_id in stale_ids:
        with transaction.atomic():
            try:
                patch = Patch.objects.select_for_update().get(pk=patch_id)
            except Patch.DoesNotExist:
                continue
            is_legacy_pending_upload = patch.pkg_status == PackageStatus.PENDING and patch.last_synced_at is None and not patch.sources.exists()
            if not (patch.updated_at < deadline and (patch.pkg_status == PackageStatus.DOWNLOADING or is_legacy_pending_upload)):
                continue
            try:
                detail = patch.windows_detail
            except WindowsPatchDetail.DoesNotExist:  # 详情异常时也要收口主记录
                detail = None
            if detail and detail.package_file:
                try:
                    detail.package_file.delete(save=False)
                except Exception:  # noqa: BLE001
                    logger.warning(
                        "清理超时 Windows 补丁包失败: patch_id=%s",
                        patch.id,
                        exc_info=True,
                    )
            patch.pkg_status = PackageStatus.DOWNLOAD_FAILED
            patch.save(update_fields=["pkg_status", "updated_at"])
            if detail:
                detail.package_error = patch_message(
                    None,
                    "error.package_upload_timeout",
                    "The patch package upload timed out. Edit the patch and select the file again",
                )
                detail.save(update_fields=["package_error"])
            expired += 1
    return expired
