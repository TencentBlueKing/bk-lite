from apps.opspilot.enum import DocumentStatus
from apps.opspilot.models import KnowledgeDocument


class KnowledgeDocumentUtils(object):
    @staticmethod
    def get_new_document(kwargs, username, domain="domain.com", ocr_model=None):
        return KnowledgeDocument.objects.create(
            knowledge_base_id=kwargs["knowledge_base_id"],
            name=kwargs["name"],
            knowledge_source_type=kwargs["knowledge_source_type"],
            created_by=username,
            train_status=DocumentStatus.PENDING,
            enable_ocr_parse=True,
            ocr_model=ocr_model,
            domain=domain,
        )
