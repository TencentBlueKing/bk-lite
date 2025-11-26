"""
知识库相关的 Django Signal 处理器

使用信号解耦模型删除逻辑，避免循环依赖
"""
from django.db.models.signals import post_delete
from django.dispatch import receiver

from apps.core.logger import opspilot_logger as logger


@receiver(post_delete, sender="opspilot.KnowledgeBase")
def cleanup_knowledge_base_es_index(sender, instance, **kwargs):
    """
    清理知识库的 Elasticsearch 索引

    在 KnowledgeBase 删除后触发，删除对应的 ES 索引
    使用延迟导入避免循环依赖
    """
    try:
        from apps.opspilot.services.knowledge_search_service import KnowledgeSearchService

        index_name = instance.knowledge_index_name()
        KnowledgeSearchService.delete_es_index(index_name)
        logger.info(f"成功删除知识库 ES 索引: {index_name}")
    except Exception as e:
        logger.error(f"删除知识库 ES 索引失败: {str(e)}, knowledge_base_id={instance.id}")


@receiver(post_delete, sender="opspilot.KnowledgeDocument")
def cleanup_knowledge_document_es_content(sender, instance, **kwargs):
    """
    清理知识文档的 Elasticsearch 内容

    在 KnowledgeDocument 删除后触发，删除对应的 ES 文档内容
    使用延迟导入避免循环依赖
    """
    try:
        from apps.opspilot.services.knowledge_search_service import KnowledgeSearchService

        index_name = instance.knowledge_base.knowledge_index_name()
        KnowledgeSearchService.delete_es_content(index_name, instance.id, instance.name)
        logger.info(f"成功删除知识文档 ES 内容: document_id={instance.id}, name={instance.name}")
    except Exception as e:
        logger.error(f"删除知识文档 ES 内容失败: {str(e)}, document_id={instance.id}")


@receiver(post_delete, sender="opspilot.QAPairs")
def cleanup_qa_pairs_es_content(sender, instance, **kwargs):
    """
    清理问答对的 Elasticsearch 内容

    在 QAPairs 删除后触发，删除对应的 ES 问答对内容
    使用延迟导入避免循环依赖
    """
    try:
        from apps.opspilot.utils.chunk_helper import ChunkHelper

        ChunkHelper.delete_es_content(instance.id)
        logger.info(f"成功删除问答对 ES 内容: qa_pairs_id={instance.id}")
    except Exception as e:
        logger.error(f"删除问答对 ES 内容失败: {str(e)}, qa_pairs_id={instance.id}")
