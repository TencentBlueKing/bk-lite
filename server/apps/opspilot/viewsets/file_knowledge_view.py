from django.core.files.base import ContentFile
from django.http import JsonResponse
from rest_framework.decorators import action

from apps.core.decorators.api_permission import HasPermission
from apps.core.logger import opspilot_logger as logger
from apps.core.viewsets.base_viewset import BaseOpsPilotViewSet
from apps.opspilot.models import FileKnowledge
from apps.opspilot.serializers import FileKnowledgeSerializer
from apps.opspilot.utils.knowledge_utils import KnowledgeDocumentUtils
from apps.opspilot.utils.quota_utils import get_quota_client


class FileKnowledgeViewSet(BaseOpsPilotViewSet):
    queryset = FileKnowledge.objects.all()
    serializer_class = FileKnowledgeSerializer
    ordering = ("-id",)
    search_fields = ("name",)

    @action(methods=["POST"], detail=False)
    @HasPermission("knowledge_document-Add")
    def create_file_knowledge(self, request):
        kwargs = request.data
        files = request.FILES.getlist("files")
        if not request.user.is_superuser:
            client = get_quota_client(request)
            file_size = sum(i.size for i in files) / 1024 / 1024
            file_quota, used_file_size, __ = client.get_file_quota()
            if file_quota != -1 and file_quota < file_size + used_file_size:
                no_used_file_size = file_quota - used_file_size
                return JsonResponse(
                    {
                        "result": False,
                        "message": f"File size exceeds quota limit. Available size: {no_used_file_size} MB",
                    }
                )
        result = self.import_file_knowledge(files, kwargs, request.user.username, request.user.domain)
        return JsonResponse(result)

    @staticmethod
    def import_file_knowledge(files, kwargs, username, domain):
        file_knowledge_list = []
        try:
            for file_obj in files:
                title = file_obj.name
                if not title:
                    logger.warning(f"File with empty title found: {title}")
                    continue
                kwargs["name"] = title
                kwargs["knowledge_source_type"] = "file"
                new_doc = KnowledgeDocumentUtils.get_new_document(kwargs, username, domain)
                content_file = ContentFile(file_obj.read(), name=title)
                file_knowledge_list.append(FileKnowledge(file=content_file, knowledge_document_id=new_doc.id))
            objs = FileKnowledge.objects.bulk_create(file_knowledge_list, batch_size=10)
            return {"result": True, "data": [i.knowledge_document_id for i in objs]}
        except Exception as e:
            logger.error(f"Failed to import file: {e}")
            return {"result": False, "message": "Failed to import file."}
