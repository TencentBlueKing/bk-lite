"""Wiki parsed markdown 对象存储清理。"""

import logging

from apps.opspilot.services.wiki import material_service

logger = logging.getLogger("opspilot")


def _parsed_markdown_prefix_for_knowledge_base(knowledge_base_id):
    try:
        kb_id = int(knowledge_base_id)
    except (TypeError, ValueError):
        return ""
    if kb_id <= 0:
        return ""
    return f"wiki/parsed/{kb_id}/"


def _storage_object_name(item):
    if isinstance(item, tuple):
        return item[0]
    return getattr(item, "object_name", "")


def delete_knowledge_base_parsed_markdown(knowledge_base_id):
    """清理单个知识库的 parsed 残留对象,严格限制在 wiki/parsed/<kb_id>/ 前缀内。"""
    prefix = _parsed_markdown_prefix_for_knowledge_base(knowledge_base_id)
    if not prefix:
        return {"prefix": "", "deleted": 0, "skipped": 0}

    storage = material_service._PARSED_STORAGE
    try:
        objects = storage.listdir(storage.bucket)
    except Exception:
        logger.exception("knowledge base parsed 目录扫描失败 prefix=%s", prefix)
        return {"prefix": prefix, "deleted": 0, "skipped": 0}

    deleted = 0
    skipped = 0
    for item in objects:
        object_name = (_storage_object_name(item) or "").strip()
        if not object_name.startswith(prefix):
            skipped += 1
            continue
        if not material_service._is_safe_parsed_markdown_locator(object_name):
            skipped += 1
            continue
        if material_service.delete_parsed_markdown(object_name):
            deleted += 1
        else:
            skipped += 1
    return {"prefix": prefix, "deleted": deleted, "skipped": skipped}
