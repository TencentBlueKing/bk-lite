from django.db import models
from django.utils.translation import gettext_lazy as _


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
