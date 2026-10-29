"""Windows 离线扫描目录的保存与评估前检查。"""

import hashlib
from pathlib import Path

from django.utils import timezone

from apps.patch_mgmt.config import PATCH_MGMT_MAX_PACKAGE_SIZE_MB
from apps.patch_mgmt.models import ScanSetting

OFFLINE_CATALOG_DOWNLOAD_URL = "https://catalog.s.download.windowsupdate.com/microsoftupdate/v6/wsusscan/wsusscn2.cab"
OFFLINE_CATALOG_SERVICE_NAME = "BK-Lite Offline Catalog"
WINDOWS_OFFLINE_CATALOG_NAME = "wsusscn2.cab"


class OfflineCatalogError(Exception):
    """离线目录不可用。message 是可直接展示的原因。"""

    def __init__(self, message: str):
        super().__init__(message)
        self.message = message


def offline_catalog_is_available(setting: ScanSetting) -> bool:
    return bool(setting.offline_catalog_file and setting.offline_catalog_sha256)


def prepare_offline_catalog_upload(uploaded_file):
    """校验上传文件是 Cabinet，并计算摘要。调用方随后可以把文件指针从头保存。"""
    file_name = Path(str(getattr(uploaded_file, "name", "") or "")).name
    if Path(file_name).suffix.lower() != ".cab":
        raise OfflineCatalogError("离线目录必须是 .cab 文件")
    file_size = int(getattr(uploaded_file, "size", 0) or 0)
    max_bytes = PATCH_MGMT_MAX_PACKAGE_SIZE_MB * 1024 * 1024
    if file_size <= 0:
        raise OfflineCatalogError("离线目录是空文件")
    if file_size > max_bytes:
        raise OfflineCatalogError(f"离线目录不能超过 {PATCH_MGMT_MAX_PACKAGE_SIZE_MB} MB")

    uploaded_file.seek(0)
    signature = uploaded_file.read(4)
    if signature != b"MSCF":
        raise OfflineCatalogError("离线目录不是有效的 Cabinet 文件")

    uploaded_file.seek(0)
    digest = hashlib.sha256()
    for chunk in uploaded_file.chunks():
        digest.update(chunk)
    uploaded_file.seek(0)
    return file_name, file_size, digest.hexdigest()


def assign_offline_catalog(setting: ScanSetting, uploaded_file, prepared: tuple[str, int, str]) -> str:
    """把已校验的目录写到存储并填到 setting 上，不保存模型。返回被替换的对象名。"""
    file_name, file_size, digest = prepared
    uploaded_file.seek(0)
    previous_name = setting.offline_catalog_file.name if setting.offline_catalog_file else ""
    setting.offline_catalog_file.save(file_name, uploaded_file, save=False)
    setting.offline_catalog_filename = file_name
    setting.offline_catalog_size = file_size
    setting.offline_catalog_sha256 = digest
    setting.offline_catalog_uploaded_at = timezone.now()
    current_name = setting.offline_catalog_file.name
    if previous_name and previous_name != current_name:
        return previous_name
    return ""
