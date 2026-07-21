"""资料(Material)删除时清理 MinIO 文件对象和解析产物。

Material.file 是上传文件在 MinIO 的对象。Django FileField 默认不会随模型删除而删除底层文件,
会造成 MinIO 存储泄漏。通过 post_delete 信号兜底:无论是单条删除(handle_material_deletion)
还是删除知识库时的级联删除(FK CASCADE 同样会触发 post_delete),都会删除对应 MinIO 对象。

MaterialVersion.content_locator 指向 wiki/parsed 下的解析 markdown。资料删除或知识库级联删除时,
MaterialVersion 也会被级联删除,因此在 MaterialVersion 的 post_delete 中清理解析产物。
"""

import logging

from django.db import transaction
from django.db.models.signals import post_delete
from django.dispatch import receiver

from apps.opspilot.models import Material, MaterialVersion
from apps.opspilot.services.wiki.material_service import delete_parsed_markdown, is_parsed_markdown_locator_for_material

logger = logging.getLogger("opspilot")


@receiver(post_delete, sender=Material, dispatch_uid="wiki_material_delete_minio_file")
def delete_material_file_on_delete(sender, instance, **kwargs):
    """事务提交后删除 MinIO 文件；回滚时自动丢弃回调。"""
    file_field = instance.file
    file_name = getattr(file_field, "name", "")
    if not file_name:
        return
    storage = file_field.storage
    material_id = instance.pk

    def cleanup():
        try:
            storage.delete(file_name)
        except Exception:
            logger.exception(
                "删除资料 MinIO 文件失败 material=%s file=%s",
                material_id,
                file_name,
            )

    transaction.on_commit(cleanup, using=kwargs.get("using"))


@receiver(post_delete, sender=MaterialVersion, dispatch_uid="wiki_material_version_delete_parsed_markdown")
def delete_parsed_markdown_on_version_delete(sender, instance, **kwargs):
    """事务提交后删除解析产物；回滚时自动丢弃回调。"""
    locator = instance.content_locator
    material_id = instance.material_id
    if not is_parsed_markdown_locator_for_material(locator, material_id):
        logger.warning(
            "跳过不属于当前资料的解析产物删除 material=%s locator=%s",
            material_id,
            locator,
        )
        return

    def cleanup():
        try:
            delete_parsed_markdown(locator)
        except Exception:
            logger.exception(
                "删除资料解析产物失败 material=%s locator=%s",
                material_id,
                locator,
            )

    transaction.on_commit(cleanup, using=kwargs.get("using"))
