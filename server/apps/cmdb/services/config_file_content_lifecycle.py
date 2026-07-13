import hashlib
import uuid

from django.core.files.base import ContentFile
from django.db import transaction
from django.db.models import F
from django.utils.timezone import now

from apps.cmdb.models.config_file_version import ConfigFileContentStatus, ConfigFileVersion
from apps.core.logger import cmdb_logger as logger


class ConfigFileContentLifecycle:
    TEMP_PREFIX = "tmp/config-file"

    @staticmethod
    def _storage():
        return ConfigFileVersion._meta.get_field("content").storage

    @classmethod
    def stage_content(cls, text_content: str) -> str:
        temp_key = f"{cls.TEMP_PREFIX}/{uuid.uuid4().hex}.txt"
        content = ContentFile((text_content or "").encode("utf-8"), name=temp_key)
        return cls._storage().save(temp_key, content)

    @classmethod
    def discard_temp_content(cls, temp_key: str) -> None:
        if not temp_key:
            return
        try:
            cls._storage().delete(temp_key)
        except Exception:
            logger.exception("[ConfigFileContent] 清理临时对象失败 temp_key=%s", temp_key)

    @classmethod
    def publish_version(cls, version_id: int) -> bool:
        version_obj = ConfigFileVersion.objects.filter(id=version_id).first()
        if not version_obj:
            return False
        if version_obj.content_status == ConfigFileContentStatus.READY:
            return True
        if version_obj.content_status not in (ConfigFileContentStatus.PENDING, ConfigFileContentStatus.ERROR):
            return False

        try:
            if not version_obj.temp_content_key:
                raise RuntimeError("配置正文缺少临时对象键")
            storage = cls._storage()
            with storage.open(version_obj.temp_content_key, "rb") as temp_file:
                raw_content = temp_file.read()
            if hashlib.sha256(raw_content).hexdigest() != version_obj.content_hash:
                raise RuntimeError("配置正文临时对象哈希不匹配")

            formal_key = version_obj.content.name
            if storage.exists(formal_key):
                with storage.open(formal_key, "rb") as formal_file:
                    if hashlib.sha256(formal_file.read()).hexdigest() != version_obj.content_hash:
                        raise RuntimeError("配置正文正式对象键内容冲突")
                saved_key = formal_key
            else:
                saved_key = storage.save(formal_key, ContentFile(raw_content, name=formal_key))

            updated = ConfigFileVersion.objects.filter(
                id=version_id,
                content_status__in=[ConfigFileContentStatus.PENDING, ConfigFileContentStatus.ERROR],
                temp_content_key=version_obj.temp_content_key,
            ).update(
                content=saved_key,
                content_status=ConfigFileContentStatus.READY,
                temp_content_key="",
                content_error="",
                content_attempt_count=F("content_attempt_count") + 1,
                content_updated_at=now(),
            )
            if updated:
                cls.discard_temp_content(version_obj.temp_content_key)
                return True
            return ConfigFileVersion.objects.filter(id=version_id, content_status=ConfigFileContentStatus.READY).exists()
        except Exception as error:
            logger.exception("[ConfigFileContent] 发布正式对象失败 version_id=%s", version_id)
            ConfigFileVersion.objects.filter(
                id=version_id,
                content_status__in=[ConfigFileContentStatus.PENDING, ConfigFileContentStatus.ERROR],
            ).update(
                content_status=ConfigFileContentStatus.ERROR,
                content_error=str(error)[:1000],
                content_attempt_count=F("content_attempt_count") + 1,
                content_updated_at=now(),
            )
            return False

    @classmethod
    def request_delete(cls, version_id: int) -> bool:
        with transaction.atomic():
            version_obj = ConfigFileVersion.objects.select_for_update().filter(id=version_id).first()
            if not version_obj:
                return False
            if version_obj.content_status != ConfigFileContentStatus.DELETE_PENDING:
                ConfigFileVersion.objects.filter(id=version_id).update(
                    content_status=ConfigFileContentStatus.DELETE_PENDING,
                    content_error="",
                    content_updated_at=now(),
                )
            transaction.on_commit(
                lambda target_id=version_id: cls.delete_version(target_id),
                robust=True,
            )
        return True

    @classmethod
    def delete_version(cls, version_id: int) -> bool:
        version_obj = ConfigFileVersion.objects.filter(
            id=version_id,
            content_status=ConfigFileContentStatus.DELETE_PENDING,
        ).first()
        if not version_obj:
            return not ConfigFileVersion.objects.filter(id=version_id).exists()

        try:
            storage = cls._storage()
            for object_key in dict.fromkeys([version_obj.content.name, version_obj.temp_content_key]):
                if object_key:
                    storage.delete(object_key)
            deleted, _ = ConfigFileVersion.objects.filter(
                id=version_id,
                content_status=ConfigFileContentStatus.DELETE_PENDING,
            ).delete()
            return bool(deleted)
        except Exception as error:
            logger.exception("[ConfigFileContent] 删除正文失败 version_id=%s", version_id)
            ConfigFileVersion.objects.filter(
                id=version_id,
                content_status=ConfigFileContentStatus.DELETE_PENDING,
            ).update(
                content_error=str(error)[:1000],
                content_attempt_count=F("content_attempt_count") + 1,
                content_updated_at=now(),
            )
            return False
