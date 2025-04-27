import base64

from django.core.validators import FileExtensionValidator
from django.db import models
from django.utils.translation import gettext_lazy as _
from django_minio_backend import MinioBackend, iso_date_prefix

KNOWLEDGE_TYPES = ["md", "docx", "xlsx", "csv", "pptx", "pdf", "txt", "png", "jpg", "jpeg"]


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
