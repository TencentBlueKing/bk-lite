"""手工 Windows 补丁包校验与私有存储。"""

import hashlib
import logging
from datetime import timedelta
from pathlib import Path

from django.db import transaction
from django.utils import timezone

from apps.patch_mgmt.config import (
    PATCH_MGMT_MAX_PACKAGE_SIZE_MB,
    PATCH_MGMT_PACKAGE_UPLOAD_TIMEOUT,
)
from apps.patch_mgmt.constants import OSType, PackageStatus
from apps.patch_mgmt.models import Patch, WindowsPatchDetail

logger = logging.getLogger("app")


class WindowsPackageError(ValueError):
    """手工 Windows 补丁包不可接受。"""


def _safe_file_name(value: str) -> str:
    return Path(str(value or "package")).name


def _validate_and_hash(uploaded_file) -> tuple[str, str, int, str]:
    file_name = _safe_file_name(getattr(uploaded_file, "name", ""))
    extension = Path(file_name).suffix.lower()
    if extension not in {".msu", ".cab"}:
        raise WindowsPackageError("仅支持 .msu 和 .cab 补丁包")

    file_size = int(getattr(uploaded_file, "size", 0) or 0)
    max_bytes = PATCH_MGMT_MAX_PACKAGE_SIZE_MB * 1024 * 1024
    if file_size <= 0:
        raise WindowsPackageError("补丁包不能为空")
    if file_size > max_bytes:
        raise WindowsPackageError(
            f"补丁包不能超过 {PATCH_MGMT_MAX_PACKAGE_SIZE_MB}MB"
        )

    uploaded_file.seek(0)
    signature = uploaded_file.read(4)
    # MSU 在不同代际可能表现为 ZIP 或 Cabinet 容器；CAB 的规范文件头为 MSCF。
    if extension == ".msu" and not (
        signature.startswith(b"PK") or signature == b"MSCF"
    ):
        raise WindowsPackageError(".msu 文件头无效")
    if extension == ".cab" and signature != b"MSCF":
        raise WindowsPackageError(".cab 文件头无效")

    uploaded_file.seek(0)
    digest = hashlib.sha256()
    for chunk in uploaded_file.chunks():
        digest.update(chunk)
    uploaded_file.seek(0)
    return file_name, extension, file_size, digest.hexdigest()


def _mark_failed(patch: Patch, detail, message: str) -> None:
    patch.pkg_status = PackageStatus.DOWNLOAD_FAILED
    patch.save(update_fields=["pkg_status", "updated_at"])
    detail.package_error = message[:1000]
    detail.save(update_fields=["package_error"])


@transaction.atomic
def store_windows_package(patch: Patch, uploaded_file) -> dict:
    """校验并保存手工补丁包，成功后才将补丁置为就绪。"""
    if patch.os_type != OSType.WINDOWS:
        raise WindowsPackageError("仅 Windows 补丁支持上传文件")
    if patch.pkg_status != PackageStatus.DOWNLOADING:
        raise WindowsPackageError("当前补丁状态不允许上传文件")

    detail = patch.windows_detail
    try:
        file_name, extension, file_size, sha256 = _validate_and_hash(uploaded_file)
        detail.package_original_name = file_name
        detail.package_extension = extension
        detail.package_size = file_size
        detail.package_sha256 = sha256
        detail.package_error = ""
        detail.package_file.save(file_name, uploaded_file, save=False)
        detail.package_uploaded_at = timezone.now()
        detail.save(
            update_fields=[
                "package_file",
                "package_original_name",
                "package_extension",
                "package_size",
                "package_sha256",
                "package_error",
                "package_uploaded_at",
            ]
        )
    except WindowsPackageError as exc:
        _mark_failed(patch, detail, str(exc))
        raise
    except Exception as exc:
        if detail.package_file:
            try:
                detail.package_file.delete(save=False)
            except Exception:
                pass
        _mark_failed(patch, detail, f"补丁包存储失败: {exc}")
        raise WindowsPackageError("补丁包存储失败") from exc

    patch.pkg_status = PackageStatus.READY
    patch.save(update_fields=["pkg_status", "updated_at"])
    return {
        "file_name": file_name,
        "file_size": file_size,
        "sha256": sha256,
        "extension": extension,
    }


@transaction.atomic
def replace_failed_windows_package(patch: Patch, uploaded_file) -> dict:
    """仅对失败记录重新上传，就绪文件不允许替换。"""
    if patch.pkg_status != PackageStatus.DOWNLOAD_FAILED:
        raise WindowsPackageError("仅上传失败的补丁允许替换文件")

    detail = patch.windows_detail
    if detail.package_file:
        try:
            detail.package_file.delete(save=False)
        except Exception as exc:
            raise WindowsPackageError("无法清理上次失败的补丁包") from exc

    patch.pkg_status = PackageStatus.DOWNLOADING
    patch.save(update_fields=["pkg_status", "updated_at"])
    return store_windows_package(patch, uploaded_file)


def expire_stale_windows_package_uploads(
    *,
    timeout_seconds: int = PATCH_MGMT_PACKAGE_UPLOAD_TIMEOUT,
    now=None,
) -> int:
    """将长期未完成上传的手工 Windows 补丁收口为失败。"""
    current = now or timezone.now()
    deadline = current - timedelta(seconds=max(int(timeout_seconds), 1))
    stale_ids = list(
        Patch.objects.filter(
            os_type=OSType.WINDOWS,
            pkg_status=PackageStatus.DOWNLOADING,
            updated_at__lt=deadline,
        ).values_list("id", flat=True)
    )
    expired = 0
    for patch_id in stale_ids:
        with transaction.atomic():
            try:
                patch = (
                    Patch.objects.select_for_update()
                    .get(pk=patch_id)
                )
            except Patch.DoesNotExist:
                continue
            if (
                patch.pkg_status != PackageStatus.DOWNLOADING
                or patch.updated_at >= deadline
            ):
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
                detail.package_error = "补丁包上传超时，请编辑后重新选择文件上传"
                detail.save(update_fields=["package_error"])
            expired += 1
    return expired
