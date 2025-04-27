from django.db import models
from django.utils.translation import gettext_lazy as _


class WebPageKnowledge(models.Model):
    url = models.URLField(verbose_name=_("URL"))
    knowledge_document = models.ForeignKey(
        "KnowledgeDocument",
        verbose_name=_("Knowledge Document"),
        blank=True,
        null=True,
        on_delete=models.CASCADE,
    )
    max_depth = models.IntegerField(verbose_name=_("max depth"), default=1)

    class Meta:
        verbose_name = _("Web Page Knowledge")
        verbose_name_plural = verbose_name
        db_table = "knowledge_mgmt_webpageknowledge"

    def to_dict(self):
        return {
            "url": self.url,
            "max_depth": self.max_depth,
        }
