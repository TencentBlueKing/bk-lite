import hashlib

from django.conf import settings
from django.db import transaction
from django.http import FileResponse, JsonResponse
from django.utils.translation import gettext as _
from django_filters import filters
from django_filters.rest_framework import FilterSet
from django_minio_backend import MinioBackend
from langserve import RemoteRunnable
from rest_framework import viewsets
from rest_framework.decorators import action

from apps.core.logger import logger
from apps.opspilot.knowledge_mgmt.models.knowledge_document import DocumentStatus
from apps.opspilot.knowledge_mgmt.serializers import KnowledgeDocumentSerializer
from apps.opspilot.knowledge_mgmt.services.knowledge_search_service import KnowledgeSearchService
from apps.opspilot.model_provider_mgmt.models import EmbedProvider, OCRProvider
from apps.opspilot.models import (
    ConversationTag,
    FileKnowledge,
    KnowledgeBase,
    KnowledgeDocument,
    ManualKnowledge,
    WebPageKnowledge,
)
from apps.opspilot.tasks import general_embed, general_embed_by_document_list
from apps.opspilot.utils.chat_server_helper import ChatServerHelper


class ObjFilter(FilterSet):
    knowledge_base_id = filters.NumberFilter(field_name="knowledge_base_id", lookup_expr="exact")
    name = filters.CharFilter(field_name="name", lookup_expr="icontains")
    knowledge_source_type = filters.CharFilter(field_name="knowledge_source_type", lookup_expr="exact")
    train_status = filters.NumberFilter(field_name="train_status", lookup_expr="exact")


class KnowledgeDocumentViewSet(viewsets.ModelViewSet):
    queryset = KnowledgeDocument.objects.all()
    serializer_class = KnowledgeDocumentSerializer
    filterset_class = ObjFilter
    ordering = ("-id",)

    def destroy(self, request, *args, **kwargs):
        instance: KnowledgeDocument = self.get_object()
        if instance.train_status == DocumentStatus.TRAINING:
            return JsonResponse({"result": False, "message": _("training document can not be deleted")})
        with transaction.atomic():
            ConversationTag.objects.filter(knowledge_document_id=instance.id).delete()
            instance.delete()
        return JsonResponse({"result": True})

    @action(methods=["POST"], detail=False)
    def batch_train(self, request):
        kwargs = request.data
        knowledge_document_ids = kwargs.pop("knowledge_document_ids", [])
        if type(knowledge_document_ids) is not list:
            knowledge_document_ids = [knowledge_document_ids]
        KnowledgeDocument.objects.filter(id__in=knowledge_document_ids).update(train_status=DocumentStatus.TRAINING)
        general_embed.delay(knowledge_document_ids)
        return JsonResponse({"result": True})

    @action(methods=["POST"], detail=False)
    def testing(self, request):
        kwargs = request.data
        knowledge_base_id = kwargs.pop("knowledge_base_id", 0)
        query = kwargs.pop("query", "")
        if not query:
            return JsonResponse({"result": False, "message": _("query is required")})

        service = KnowledgeSearchService()
        knowledge_base = KnowledgeBase.objects.get(id=knowledge_base_id)
        docs = service.search(knowledge_base, query, kwargs)
        doc_ids = [doc["knowledge_id"] for doc in docs]
        knowledge_document_list = KnowledgeDocument.objects.filter(id__in=set(doc_ids)).values(
            "id", "name", "knowledge_source_type", "created_by", "created_at"
        )
        doc_map = {doc["id"]: doc for doc in knowledge_document_list}
        for i in docs:
            knowledge_id = i.pop("knowledge_id")
            doc_obj = doc_map.get(knowledge_id)
            if not doc_obj:
                logger.warning(f"knowledge_id: {knowledge_id} not found")
                continue
            i.update(doc_obj)
        return JsonResponse({"result": True, "data": docs})

    @action(methods=["GET"], detail=True)
    def get_detail(self, request, *args, **kwargs):
        instance: KnowledgeDocument = self.get_object()
        url = f"{settings.METIS_SERVER_URL}/api/rag/list_rag_document"
        count_url = f"{settings.METIS_SERVER_URL}/api/rag/count_index_document"
        search_text = request.GET.get("search_text", "")
        page = int(request.GET.get("page", 1))
        page_size = int(request.GET.get("page_size", 10))
        query = {
            "index_name": instance.knowledge_index_name(),
            "page": page,
            "size": page_size,
            "metadata_filter": {},
            "query": search_text,
        }
        res = ChatServerHelper.post_chat_server(query, url)
        count_res = ChatServerHelper.post_chat_server(query, count_url)
        return JsonResponse(
            {
                "result": True,
                "data": {
                    "items": [
                        {"id": i["metadata"]["chunk_id"], "content": i["page_content"]} for i in res["documents"]
                    ],
                    "count": count_res["count"],
                },
            }
        )

    @action(methods=["POST"], detail=True)
    def enable_chunk(self, request, *args, **kwargs):
        instance: KnowledgeDocument = self.get_object()
        enabled = request.data.get("enabled", False)
        chunk_id = request.data.get("chunk_id", "")
        if not chunk_id:
            return JsonResponse({"result": False, "message": _("chunk_id is required")})
        try:
            KnowledgeSearchService.change_chunk_enable(instance.knowledge_index_name(), chunk_id, enabled)
            return JsonResponse({"result": True})
        except Exception as e:
            logger.exception(e)
            return JsonResponse({"result": False, "message": _("update failed")})

    @action(methods=["POST"], detail=True)
    def delete_chunk(self, request, *args, **kwargs):
        instance: KnowledgeDocument = self.get_object()
        chunk_id = request.data.get("chunk_id", "")
        if not chunk_id:
            return JsonResponse({"result": False, "message": _("chunk_id is required")})
        try:
            KnowledgeSearchService.delete_es_content(instance.knowledge_index_name(), chunk_id, instance.name, True)
            return JsonResponse({"result": True})
        except Exception as e:
            logger.exception(e)
            return JsonResponse({"result": False, "message": _("delete failed")})

    @action(methods=["POST"], detail=False)
    def batch_delete(self, request):
        doc_ids = request.data.get("doc_ids", [])
        knowledge_base_id = request.data.get("knowledge_base_id", 0)
        if KnowledgeDocument.objects.filter(id__in=doc_ids, train_status=DocumentStatus.TRAINING).exists():
            return JsonResponse({"result": False, "message": _("training document can not be deleted")})
        KnowledgeDocument.objects.filter(id__in=doc_ids).delete()
        index_name = f"knowledge_base_{knowledge_base_id}"
        try:
            KnowledgeSearchService.delete_es_content(
                index_name,
                ",".join([str(i) for i in doc_ids]),
            )
        except Exception as e:
            logger.exception(e)
            return JsonResponse({"result": False, "message": _("delete failed")})
        return JsonResponse({"result": True})

    @action(methods=["GET"], detail=True)
    def get_document_detail(self, request, *args, **kwargs):
        obj: KnowledgeDocument = self.get_object()
        result = {"document_id": obj.id, "name": obj.name, "knowledge_source_type": obj.knowledge_source_type}
        knowledge_model_map = {
            "web_page": WebPageKnowledge,
            "manual": ManualKnowledge,
        }
        doc = knowledge_model_map[obj.knowledge_source_type].objects.filter(knowledge_document_id=obj.id).first()
        result.update(doc.to_dict())
        return JsonResponse({"result": True, "data": result})

    @action(methods=["POST"], detail=True)
    def update_document_base_info(self, request, *args, **kwargs):
        obj: KnowledgeDocument = self.get_object()
        knowledge_model_map = {
            "web_page": WebPageKnowledge,
            "manual": ManualKnowledge,
        }
        doc = knowledge_model_map[obj.knowledge_source_type].objects.filter(knowledge_document_id=obj.id).first()
        params = request.data
        name = params.pop("name", "")
        for key, value in params.items():
            setattr(doc, key, value)
        if name:
            obj.name = name
            obj.save()
        doc.save()
        return JsonResponse({"result": True})

    @action(methods=["GET"], detail=True)
    def get_file_link(self, request, *args, **kwargs):
        instance: KnowledgeDocument = self.get_object()
        if instance.knowledge_source_type != "file":
            return JsonResponse({"result": False, "message": _("Not a file")})
        file_obj = FileKnowledge.objects.filter(knowledge_document_id=instance.id).first()
        if not file_obj:
            return JsonResponse({"result": False, "message": _("File not found")})
        storage = MinioBackend(bucket_name="munchkin-private")
        file_data = storage.open(file_obj.file.name, "rb")
        # Calculate ETag
        data = file_data.read()
        etag = hashlib.md5(data).hexdigest()
        # Reset file pointer to start
        file_data.seek(0)
        response = FileResponse(file_data)
        response["ETag"] = etag
        return response

    @action(methods=["POST"], detail=False)
    def submit_settings(self, request):
        kwargs = request.data
        knowledge_document_list = kwargs.pop("knowledge_document_list", [])
        document_map = {int(i.pop("id")): i for i in knowledge_document_list}
        knowledge_source_type = kwargs.pop("knowledge_source_type")
        ids = list(document_map.keys())
        return_data = []
        remote_runnable = RemoteRunnable(settings.DOC_PARSE_SERVICE_URL)
        if knowledge_source_type == "file":
            file_list = FileKnowledge.objects.filter(knowledge_document_id__in=ids)
            for i in file_list:
                file_params = document_map.get(i.knowledge_document_id)
                ocr_config = {}
                if file_params["enable_ocr_parse"]:
                    ocr_config = OCRProvider.objects.filter(id=file_params["ocr_model"]).first().ocr_config
                parse_params = {
                    "ocr_config": ocr_config,
                    "source_type": "file",
                    "files": [i.file.file],
                    "mode": file_params["parse_type"],
                }
                res = remote_runnable.invoke(parse_params)
                if res["result"]:
                    return_data.append({"id": i.knowledge_document_id, "data": res["data"]})
        elif knowledge_source_type == "web_page":
            web_page_obj = WebPageKnowledge.objects.filter(knowledge_document_id__in=ids).first()
            parse_params = {
                "ocr_config": {},
                "source_type": "web_page",
                "mode": "full",
                "url": web_page_obj.url,
                "max_depth": web_page_obj.max_depth,
            }
            res = remote_runnable.invoke(parse_params)
            return_data.append({"id": ids[0], "data": res["data"]})

        else:
            manual_txt = ManualKnowledge.objects.filter(knowledge_document_id__in=ids).first().content
            parse_params = {
                "ocr_config": {},
                "source_type": "web_page",
                "mode": "full",
                "content": manual_txt,
            }
            res = remote_runnable.invoke(parse_params)
            return_data.append({"id": ids[0], "data": res["data"]})
        return JsonResponse({"result": True, "data": return_data})

    @action(methods=["POST"], detail=False)
    def update_parse_settings(self, request):
        kwargs = request.data
        knowledge_document_list = kwargs.pop("knowledge_document_list", [])
        document_map = {int(i.pop("id")): i for i in knowledge_document_list}
        update_list = list(KnowledgeDocument.objects.filter(id__in=list(document_map.keys())))
        for i in update_list:
            params = document_map.get(i.id)
            i.enable_ocr_parse = params.get("enable_ocr_parse", False)
            i.mode = params.get("mode", "full")
            if params.get("enable_ocr_parse"):
                i.ocr_model_id = params["ocr_model"]
        KnowledgeDocument.objects.bulk_update(update_list, ["enable_ocr_parse", "mode", "ocr_model_id"], batch_size=10)
        return JsonResponse({"result": True})

    @action(methods=["POST"], detail=False)
    def update_chunk_settings(self, request):
        kwargs = request.data
        knowledge_document_list = kwargs.get("knowledge_document_list", [])
        KnowledgeDocument.objects.filter(id__in=knowledge_document_list).update(
            general_parse_chunk_size=kwargs.get("general_parse_chunk_size", 128),
            general_parse_chunk_overlap=kwargs.get("general_parse_chunk_overlap", 32),
            semantic_chunk_parse_embedding_model_id=kwargs.get("semantic_chunk_parse_embedding_model", None),
            chunk_type=kwargs.get("chunk_type", "fixed_size"),
        )
        return JsonResponse({"result": True})

    @action(methods=["POST"], detail=False)
    def get_doc_list_config(self, request):
        doc_ids = request.data.get("doc_ids", [])
        doc_list = KnowledgeDocument.objects.filter(id__in=doc_ids).values(
            "id",
            "name",
            "general_parse_chunk_size",
            "general_parse_chunk_overlap",
            "semantic_chunk_parse_embedding_model_id",
            "enable_ocr_parse",
            "ocr_model_id",
            "mode",
            "knowledge_source_type",
        )
        return JsonResponse({"result": True, "data": list(doc_list)})

    @action(methods=["POST"], detail=False)
    def preview_chunk(self, request):
        kwargs = request.data
        document = KnowledgeDocument.objects.get(id=kwargs["knowledge_document_id"])
        document.chunk_type = kwargs.get("chunk_type", "fixed_size")
        document.general_parse_chunk_size = kwargs.get("general_parse_chunk_size", 128)
        document.general_parse_chunk_overlap = kwargs.get("general_parse_chunk_overlap", 32)
        if kwargs.get("semantic_chunk_parse_embedding_model", None):
            document.semantic_chunk_parse_embedding_model = EmbedProvider.objects.get(
                id=kwargs["semantic_chunk_parse_embedding_model"]
            )
        res = general_embed_by_document_list([document], is_show=True)
        return JsonResponse({"result": True, "data": res})
