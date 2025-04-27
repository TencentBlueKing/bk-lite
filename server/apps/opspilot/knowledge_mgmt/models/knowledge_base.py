from django.db import models
from django.utils.translation import gettext_lazy as _

from apps.core.logger import logger
from apps.core.models.maintainer_info import MaintainerInfo
from apps.core.models.time_info import TimeInfo


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
    enable_vector_search = models.BooleanField(
        default=True,
        verbose_name=_("Enable Vector Search"),
    )
    vector_search_weight = models.FloatField(default=0.1, verbose_name=_("Vector Search weight"))
    enable_text_search = models.BooleanField(default=True, verbose_name=_("Enable Text Search"))
    text_search_weight = models.FloatField(default=0.9, verbose_name=_("Text Search Weight"))
    enable_rerank = models.BooleanField(default=True, verbose_name=_("Enable Rerank"))
    rerank_top_k = models.IntegerField(default=10, verbose_name=_("Rerank Top K"))
    rerank_model = models.ForeignKey(
        "RerankProvider",
        on_delete=models.CASCADE,
        verbose_name=_("Rerank Model"),
        blank=True,
        null=True,
    )
    rag_k = models.IntegerField(default=50, verbose_name=_("Number of Results"))
    rag_num_candidates = models.IntegerField(default=1000, verbose_name=_("Number of Candidates"))
    text_search_mode = models.CharField(default="match", max_length=20, verbose_name=_("Text search mode"))
    result_count = models.IntegerField(default=50)

    class Meta:
        db_table = "knowledge_mgmt_knowledgebase"

    def knowledge_index_name(self):
        return f"knowledge_base_{self.id}"

    def delete(self, *args, **kwargs):
        from apps.opspilot.knowledge_mgmt.services.knowledge_search_service import KnowledgeSearchService

        KnowledgeSearchService.delete_es_index(self.knowledge_index_name())
        super().delete(*args, **kwargs)

    def recreate_es_index(self):
        from apps.opspilot.knowledge_mgmt.services.knowledge_search_service import KnowledgeSearchService

        try:
            KnowledgeSearchService.delete_es_index(self.knowledge_index_name())
            logger.info("delete es index success")
        except Exception as e:
            logger.error("recreate es index failed")
            logger.exception(e)
