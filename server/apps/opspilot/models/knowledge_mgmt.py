import base64

from django.core.validators import FileExtensionValidator
from django.db import models
from django.utils.translation import gettext_lazy as _
from django_minio_backend import MinioBackend, iso_date_prefix

from apps.core.mixinx import PeriodicTaskUtils
from apps.core.models.maintainer_info import MaintainerInfo
from apps.core.models.time_info import TimeInfo
from apps.opspilot.enum import DocumentStatus

KNOWLEDGE_TYPES = [
    "md",
    "docx",
    "xlsx",
    "csv",
    "pptx",
    "pdf",
    "txt",
    "png",
    "jpg",
    "jpeg",
]


class KnowledgeBase(MaintainerInfo, TimeInfo):
    name = models.CharField(max_length=100, db_index=True)
    introduction = models.TextField(blank=True, null=True)
    team = models.JSONField(default=list)
    embed_model = models.ForeignKey(
        "EmbedProvider",
        on_delete=models.CASCADE,
        verbose_name=_("Embed Model"),
        blank=True,
        null=True,
    )
    enable_rerank = models.BooleanField(default=True, verbose_name=_("Enable Rerank"))
    rerank_top_k = models.IntegerField(default=10, verbose_name=_("Rerank Top K"))
    rerank_model = models.ForeignKey(
        "RerankProvider",
        on_delete=models.CASCADE,
        verbose_name=_("Rerank Model"),
        blank=True,
        null=True,
    )
    search_type = models.CharField(
        default="similarity_score_threshold",
        verbose_name=_("Search Type"),
        max_length=50,
    )
    score_threshold = models.FloatField(default=0.7, verbose_name=_("Score threshold"))
    enable_naive_rag = models.BooleanField(default=True)
    enable_qa_rag = models.BooleanField(default=True)
    enable_graph_rag = models.BooleanField(default=False)

    rag_recall_mode = models.CharField(default="chunk", max_length=20)

    rag_size = models.IntegerField(default=50)
    qa_size = models.IntegerField(default=50, verbose_name=_("QA size"))
    graph_size = models.IntegerField(default=50, verbose_name=_("Graph size"))

    class Meta:
        db_table = "knowledge_mgmt_knowledgebase"

    def knowledge_index_name(self):
        return f"knowledge_base_{self.id}"

    def delete(self, *args, **kwargs):
        from apps.opspilot.services.knowledge_search_service import KnowledgeSearchService

        KnowledgeSearchService.delete_es_index(self.knowledge_index_name())
        super().delete(*args, **kwargs)


class KnowledgeDocument(MaintainerInfo, TimeInfo):
    knowledge_base = models.ForeignKey("KnowledgeBase", on_delete=models.CASCADE)
    name = models.CharField(max_length=255, db_index=True, verbose_name=_("name"))
    chunk_size = models.IntegerField(default=0, verbose_name=_("chunk size"))
    train_status = models.IntegerField(default=0, choices=DocumentStatus.CHOICE, verbose_name=_("train status"))
    train_progress = models.FloatField(default=0, verbose_name=_("train progress"))
    general_parse_chunk_size = models.IntegerField(default=256, verbose_name=_("general parse chunk size"))
    general_parse_chunk_overlap = models.IntegerField(default=32, verbose_name=_("general parse chunk overlap"))
    semantic_chunk_parse_embedding_model = models.ForeignKey(
        "EmbedProvider",
        blank=True,
        null=True,
        on_delete=models.CASCADE,
        verbose_name=_("embedding model"),
    )
    enable_ocr_parse = models.BooleanField(default=False, verbose_name=_("enable OCR parse"))
    ocr_model = models.ForeignKey(
        "OCRProvider",
        blank=True,
        null=True,
        on_delete=models.CASCADE,
        verbose_name=_("OCR model"),
    )
    mode = models.CharField(max_length=30, verbose_name=_("mode"), default="full")
    chunk_type = models.CharField(max_length=30, verbose_name=_("chunk type"), default="fixed_size")
    knowledge_source_type = models.CharField(max_length=20, verbose_name=_("source type"), default="file")

    def __str__(self):
        return self.name

    def knowledge_index_name(self):
        return self.knowledge_base.knowledge_index_name()

    def delete(self, *args, **kwargs):
        from apps.opspilot.services.knowledge_search_service import KnowledgeSearchService

        index_name = self.knowledge_base.knowledge_index_name()
        KnowledgeSearchService.delete_es_content(index_name, self.id, self.name)
        return super().delete(*args, **kwargs)  # 调用父类的delete方法来执行实际的删除操作

    class Meta:
        verbose_name = _("Knowledge Document")
        verbose_name_plural = verbose_name
        db_table = "knowledge_mgmt_knowledgedocument"


class FileKnowledge(models.Model):
    file = models.FileField(
        verbose_name=_("File"),
        storage=MinioBackend(bucket_name="munchkin-private"),
        upload_to=iso_date_prefix,
        validators=[FileExtensionValidator(allowed_extensions=KNOWLEDGE_TYPES)],
    )

    knowledge_document = models.ForeignKey(
        "KnowledgeDocument",
        verbose_name=_("Knowledge Document"),
        blank=True,
        null=True,
        on_delete=models.CASCADE,
    )

    def get_file_base64(self):
        return base64.b64encode(self.file.read()).decode("utf-8")

    def save(self, force_insert=False, force_update=False, using=None, update_fields=None):
        super().save(force_insert, force_update, using, update_fields)

    class Meta:
        verbose_name = _("File Knowledge")
        verbose_name_plural = verbose_name
        db_table = "knowledge_mgmt_fileknowledge"

    def delete(self, using=None, keep_parents=False):
        self.file.delete(False)
        return super().delete(using, keep_parents)

    def to_dic(self):
        return {
            "name": self.knowledge_document.name,
        }


class WebPageKnowledge(models.Model, PeriodicTaskUtils):
    url = models.URLField(verbose_name=_("URL"))
    knowledge_document = models.ForeignKey(
        "KnowledgeDocument",
        verbose_name=_("Knowledge Document"),
        blank=True,
        null=True,
        on_delete=models.CASCADE,
    )
    max_depth = models.IntegerField(verbose_name=_("max depth"), default=1)
    sync_enabled = models.BooleanField(verbose_name=_("Sync Enabled"), default=False)
    sync_time = models.CharField(verbose_name=_("Sync Time"), null=True, blank=True)

    class Meta:
        verbose_name = _("Web Page Knowledge")
        verbose_name_plural = verbose_name
        db_table = "knowledge_mgmt_webpageknowledge"

    def to_dict(self):
        return {
            "url": self.url,
            "max_depth": self.max_depth,
            "sync_enabled": self.sync_enabled,
            "sync_time": self.sync_time,
        }

    def create_sync_periodic_task(self):
        sync_time = self.sync_time or "00:00"
        task_name = f"sync_web_page_knowledge_{self.id}"
        task_args = f"[{self.id}]"
        task_path = "apps.opspilot.tasks.sync_web_page_knowledge"
        self.create_periodic_task(sync_time, task_name, task_args, task_path)

    def delete_sync_periodic_task(self):
        task_name = f"sync_web_page_knowledge_{self.id}"
        self.delete_periodic_task(task_name)


class ManualKnowledge(models.Model):
    content = models.TextField(verbose_name=_("content"))
    knowledge_document = models.ForeignKey(
        "KnowledgeDocument",
        verbose_name=_("Knowledge Document"),
        blank=True,
        null=True,
        on_delete=models.CASCADE,
    )

    class Meta:
        verbose_name = _("Manual Knowledge")
        verbose_name_plural = verbose_name
        db_table = "knowledge_mgmt_manualknowledge"

    def to_dict(self):
        return {
            "content": self.content,
        }


class QAPairs(MaintainerInfo, TimeInfo):
    """问答对模型"""

    # 基础字段
    name = models.CharField(max_length=255, verbose_name="问答对名称")
    description = models.TextField(blank=True, null=True, verbose_name="描述")

    # 外键关系
    knowledge_base = models.ForeignKey("KnowledgeBase", on_delete=models.CASCADE)
    llm_model = models.ForeignKey("LLMModel", on_delete=models.CASCADE, null=True, blank=True)
    answer_llm_model = models.ForeignKey(
        "LLMModel",
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name="answer_llm_model",
    )

    # 问答对相关字段
    qa_count = models.IntegerField(default=0, verbose_name="问答对数量")
    generate_count = models.IntegerField(default=0, verbose_name="生成的数据")
    document_id = models.IntegerField(default=0, verbose_name="文档ID")
    document_source = models.CharField(max_length=50, default="file", verbose_name="文档来源")
    status = models.CharField(max_length=50, default="completed", verbose_name="状态")
    create_type = models.CharField(max_length=20, default="document")
    question_prompt = models.TextField(blank=True, null=True, verbose_name="问题提示词", default="")
    answer_prompt = models.TextField(blank=True, null=True, verbose_name="答案提示词", default="")

    def delete(self, *args, **kwargs):
        from apps.opspilot.utils.chunk_helper import ChunkHelper

        ChunkHelper.delete_es_content(self.id)
        return super().delete(*args, **kwargs)  # 调用父类的delete方法来执行实际的删除操作


class KnowledgeGraph(MaintainerInfo, TimeInfo):
    knowledge_base = models.OneToOneField("KnowledgeBase", on_delete=models.CASCADE)
    llm_model = models.ForeignKey("LLMModel", on_delete=models.CASCADE)
    rerank_model = models.ForeignKey("RerankProvider", on_delete=models.CASCADE, null=True, blank=True)
    embed_model = models.ForeignKey("EmbedProvider", on_delete=models.CASCADE, null=True, blank=True)
    rebuild_community = models.BooleanField(default=False, verbose_name="是否重建社区")
    doc_list = models.JSONField(default=list)
    status = models.CharField(max_length=50, default="completed", verbose_name="状态")


class GraphChunkMap(models.Model):
    knowledge_graph = models.ForeignKey(KnowledgeGraph, on_delete=models.CASCADE)
    chunk_id = models.CharField(max_length=255, verbose_name="Chunk ID")
    graph_id = models.CharField(max_length=255, verbose_name="Graph ID")


class KnowledgeTask(models.Model):
    task_name = models.CharField(max_length=100, verbose_name="Task Name")
    train_progress = models.FloatField(default=0, verbose_name="Train Progress")
    knowledge_ids = models.JSONField(default=list, verbose_name="Knowledge IDs")
    knowledge_base_id = models.IntegerField(default=0, verbose_name="Knowledge IDs")
    created_by = models.CharField(max_length=100, verbose_name="Created By")
    domain = models.CharField(max_length=100, default="domain.com", verbose_name="Domain")
    is_qa_task = models.BooleanField(default=False, verbose_name="Is QA Task")
    completed_count = models.IntegerField(default=0)
    total_count = models.IntegerField(default=0)
