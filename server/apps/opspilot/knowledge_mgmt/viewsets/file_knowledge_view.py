from django.core.files.base import ContentFile
from django.http import JsonResponse
from django.utils.translation import gettext as _
from rest_framework import viewsets
from rest_framework.decorators import action

from apps.core.logger import logger
from apps.opspilot.knowledge_mgmt.serializers import FileKnowledgeSerializer
from apps.opspilot.knowledge_mgmt.utils import KnowledgeDocumentUtils
from apps.opspilot.models import FileKnowledge
from apps.opspilot.quota_rule_mgmt.quota_utils import get_quota_client


class FileKnowledgeViewSet(viewsets.ModelViewSet):
    queryset = FileKnowledge.objects.all()
    serializer_class = FileKnowledgeSerializer
    ordering = ("-id",)
    search_fields = ("name",)

    @action(methods=["POST"], detail=False)
    def create_file_knowledge(self, request):
        kwargs = request.data
        client = get_quota_client(request)
        files = request.FILES.getlist("files")
        file_size = sum(i.size for i in files) / 1024 / 1024
        file_quota, used_file_size, __ = client.get_file_quota()
        if file_quota != -1 and file_quota < file_size + used_file_size:
            no_used_file_size = file_quota - used_file_size
            return JsonResponse(
                {
                    "result": False,
                    "message": _(f"File size exceeds quota limit. Available size: {no_used_file_size} MB"),
                }
            )
        result = self.import_file_knowledge(files, kwargs, request.user.username)
        return JsonResponse(result)

    @staticmethod
    def import_file_knowledge(files, kwargs, username):
        file_knowledge_list = []
        try:
            for file_obj in files:
                title = file_obj.name
                if not title:
                    logger.warning(f"File with empty title found: {title}")
                    continue
                kwargs["name"] = title
                kwargs["knowledge_source_type"] = "file"
                new_doc = KnowledgeDocumentUtils.get_new_document(kwargs, username)
                content_file = ContentFile(file_obj.read(), name=title)
                file_knowledge_list.append(FileKnowledge(file=content_file, knowledge_document_id=new_doc.id))
            objs = FileKnowledge.objects.bulk_create(file_knowledge_list, batch_size=10)
            return {"result": True, "data": [i.knowledge_document_id for i in objs]}
        except Exception as e:
            logger.error(f"Failed to import file: {e}")
            return {"result": False, "message": _("Failed to import file.")}
