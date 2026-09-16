"""文件资料创建时确认对象已落入存储；失败则回滚数据库记录。"""

from django.db import transaction

from apps.core.logger import opspilot_logger as logger

STORAGE_UNAVAILABLE_MESSAGE = "对象存储不可用（MinIO 未就绪），资料上传失败，未保存。请检查对象存储服务后重试。"


class MaterialStorageError(Exception):
    """对象存储写入失败,资料不得保留。"""


def _is_object_storage_error(exc):
    current = exc
    for _ in range(6):
        if current is None:
            return False
        if isinstance(current, (ConnectionError, TimeoutError)):
            return True
        module = getattr(type(current), "__module__", "") or ""
        name = type(current).__name__
        if "minio" in module or "urllib3" in module:
            return True
        if name in {"S3Error", "ServerError", "MaxRetryError", "EndpointConnectionError", "ProtocolError"}:
            return True
        current = getattr(current, "__cause__", None) or getattr(current, "__context__", None)
    return False


def ensure_uploaded_file_exists(material):
    file_field = getattr(material, "file", None)
    file_name = (getattr(file_field, "name", "") or "").strip()
    if not file_name:
        return
    storage = file_field.storage
    try:
        persisted = bool(storage.exists(file_name))
    except Exception as exc:
        logger.warning(
            "wiki material file exists check failed material=%s error_type=%s",
            material.pk,
            type(exc).__name__,
        )
        raise MaterialStorageError(STORAGE_UNAVAILABLE_MESSAGE) from exc
    if not persisted:
        raise MaterialStorageError(STORAGE_UNAVAILABLE_MESSAGE)


def persist_new_material(create_fn):
    try:
        with transaction.atomic():
            material = create_fn()
            ensure_uploaded_file_exists(material)
            return material
    except MaterialStorageError:
        raise
    except Exception as exc:
        if _is_object_storage_error(exc):
            raise MaterialStorageError(STORAGE_UNAVAILABLE_MESSAGE) from exc
        raise
