from django.db import models
from django.utils.translation import gettext_lazy as _

from apps.core.models.maintainer_info import MaintainerInfo
from apps.core.models.time_info import TimeInfo


class DocumentStatus(object):
    TRAINING = 0
    READY = 1
    ERROR = 2
    PENDING = 3
    CHUNKING = 4

    CHOICE = (
        (TRAINING, _("Training")),
        (READY, _("Ready")),
        (ERROR, _("Error")),
        (PENDING, _("Pending")),
        (CHUNKING, _("Chunking")),
    )


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
        "OCRProvider", blank=True, null=True, on_delete=models.CASCADE, verbose_name=_("OCR model")
    )
    mode = models.CharField(max_length=30, verbose_name=_("mode"), default="full")
    chunk_type = models.CharField(max_length=30, verbose_name=_("chunk type"), default="fixed_size")
    knowledge_source_type = models.CharField(max_length=20, verbose_name=_("source type"), default="file")

    def __str__(self):
        return self.name

    def knowledge_index_name(self):
        return self.knowledge_base.knowledge_index_name()

    def delete(self, *args, **kwargs):
        from apps.opspilot.knowledge_mgmt.services.knowledge_search_service import KnowledgeSearchService

        index_name = self.knowledge_base.knowledge_index_name()
        KnowledgeSearchService.delete_es_content(index_name, self.id, self.name)
        return super().delete(*args, **kwargs)  # 调用父类的delete方法来执行实际的删除操作

    class Meta:
        verbose_name = _("Knowledge Document")
        verbose_name_plural = verbose_name
        db_table = "knowledge_mgmt_knowledgedocument"
