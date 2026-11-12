from django.db import transaction

from apps.core.logger import itsm_logger as logger


def sync_article(article) -> dict:
    """把已发布文章写入 OpsPilot 知识库。没有知识库时保持本地。"""
    from apps.opspilot.models.wiki_mgmt import KnowledgePage, WikiKnowledgeBase

    base = WikiKnowledgeBase.objects.order_by("id").first()
    if base is None:
        return {"status": "local", "reason": "没有知识库"}
    try:
        with transaction.atomic():
            page = KnowledgePage.objects.create(
                knowledge_base=base,
                page_type="article",
                title=article.title[:255],
                contribution="human",
                update_method="itsm",
                created_by=article.updated_by or "system",
                updated_by=article.updated_by or "system",
                domain=article.domain,
                updated_by_domain=article.domain,
            )
    except Exception as exc:
        logger.warning("知识同步失败 article_id=%s error_type=%s", article.id, type(exc).__name__)
        return {"status": "local", "error_type": type(exc).__name__}
    article.status = "synced"
    article.save(update_fields=["status", "updated_at"])
    return {"status": "synced", "page_id": page.id}
