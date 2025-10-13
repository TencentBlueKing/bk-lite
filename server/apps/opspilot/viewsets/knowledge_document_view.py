import hashlib

from django.db import transaction
from django.http import FileResponse, JsonResponse
from django_filters import filters
from django_filters.rest_framework import FilterSet
from django_minio_backend import MinioBackend
from rest_framework.decorators import action

from apps.core.decorators.api_permission import HasPermission
from apps.core.logger import opspilot_logger as logger
from apps.core.viewsets.base_viewset import BaseOpsPilotViewSet
from apps.opspilot.enum import DocumentStatus
from apps.opspilot.models import (
    ConversationTag,
    EmbedProvider,
    FileKnowledge,
    KnowledgeBase,
    KnowledgeDocument,
    KnowledgeGraph,
    KnowledgeTask,
    ManualKnowledge,
    QAPairs,
    WebPageKnowledge,
)
from apps.opspilot.serializers import KnowledgeDocumentSerializer
from apps.opspilot.services.knowledge_search_service import KnowledgeSearchService
from apps.opspilot.tasks import general_embed, general_embed_by_document_list
from apps.opspilot.utils.chunk_helper import ChunkHelper
from apps.opspilot.utils.graph_utils import GraphUtils


class ObjFilter(FilterSet):
    knowledge_base_id = filters.NumberFilter(field_name="knowledge_base_id", lookup_expr="exact")
    name = filters.CharFilter(field_name="name", lookup_expr="icontains")
    knowledge_source_type = filters.CharFilter(field_name="knowledge_source_type", lookup_expr="exact")
    train_status = filters.NumberFilter(field_name="train_status", lookup_expr="exact")


class KnowledgeDocumentViewSet(BaseOpsPilotViewSet):
    queryset = KnowledgeDocument.objects.all()
    serializer_class = KnowledgeDocumentSerializer
    filterset_class = ObjFilter
    ordering = ("-id",)

    @HasPermission("knowledge_document-Delete")
    def destroy(self, request, *args, **kwargs):
        instance: KnowledgeDocument = self.get_object()
        if instance.train_status == DocumentStatus.TRAINING:
            message = self.loader.get("training_document_no_delete") if self.loader else "training document can not be deleted"
            return JsonResponse({"result": False, "message": message})
        with transaction.atomic():
            ConversationTag.objects.filter(knowledge_document_id=instance.id).delete()
            for i in QAPairs.objects.filter(document_id=instance.id):
                i.delete()
            instance.delete()
        return JsonResponse({"result": True})

    @action(methods=["POST"], detail=False)
    @HasPermission("knowledge_document-Train")
    def batch_train(self, request):
        kwargs = request.data
        knowledge_document_ids = kwargs.pop("knowledge_document_ids", [])
        if type(knowledge_document_ids) is not list:
            knowledge_document_ids = [knowledge_document_ids]
        KnowledgeDocument.objects.filter(id__in=knowledge_document_ids).update(train_status=DocumentStatus.TRAINING)
        general_embed.delay(
            knowledge_document_ids,
            request.user.username,
            request.user.domain,
            kwargs["delete_qa_pairs"],
        )
        return JsonResponse({"result": True})

    @action(methods=["GET"], detail=False)
    @HasPermission("knowledge_document-View")
    def get_my_tasks(self, request):
        knowledge_base_id = request.GET.get("knowledge_base_id", 0)
        if not knowledge_base_id:
            message = self.loader.get("knowledge_base_id_required") if self.loader else "knowledge_base_id is required"
            return JsonResponse({"result": False, "message": message})
        task_list = list(
            KnowledgeTask.objects.filter(created_by=request.user.username, knowledge_base_id=knowledge_base_id)
            .values(
                "task_name",
                "train_progress",
                "is_qa_task",
                "completed_count",
                "total_count",
            )
            .order_by("-id")
        )
        for i in task_list:
            # if not i["is_qa_task"]:
            i["train_progress"] = f"{i['completed_count']}/{i['total_count']}"
        # else:
        #     i["train_progress"] = f"{i['train_progress']}%"
        return JsonResponse({"result": True, "data": task_list})

    @action(methods=["POST"], detail=False)
    @HasPermission("knowledge_testing-View")
    def testing(self, request):
        kwargs = request.data
        knowledge_base_id = kwargs.pop("knowledge_base_id", 0)
        query = kwargs.pop("query", "")
        if not query:
            return JsonResponse({"result": False, "message": "query is required"})

        service = KnowledgeSearchService()
        knowledge_base = KnowledgeBase.objects.get(id=knowledge_base_id)
        docs = qa_docs = graph_list = []
        score_threshold = kwargs.get("score_threshold", knowledge_base.score_threshold)
        if kwargs.get("enable_naive_rag", True):
            params = dict(
                kwargs,
                **{
                    "rag_size": kwargs.get("rag_size", knowledge_base.rag_size),
                    "enable_qa_rag": False,
                    "enable_graph_rag": False,
                },
            )
            docs = service.search(knowledge_base, query, params, score_threshold, is_qa=False)
        if kwargs.get("enable_qa_rag", True):
            params = dict(
                kwargs,
                **{
                    "qa_size": kwargs.get("qa_size", knowledge_base.qa_size),
                    "enable_naive_rag": False,
                    "enable_graph_rag": False,
                },
            )
            qa_docs = service.search(knowledge_base, query, params, score_threshold, is_qa=True)
        if kwargs.get("enable_graph_rag", False):
            graph_obj = KnowledgeGraph.objects.filter(knowledge_base_id=knowledge_base.id).first()
            if graph_obj:
                res = GraphUtils.search_graph(graph_obj, kwargs["graph_size"], query)
                if res["result"]:
                    graph_list = res["data"]
        doc_ids = [doc["knowledge_id"] for doc in docs]
        knowledge_document_list = KnowledgeDocument.objects.filter(id__in=set(doc_ids)).values(
            "id", "name", "knowledge_source_type", "created_by", "created_at"
        )
        doc_map = {doc["id"]: doc for doc in knowledge_document_list}
        for i in docs:
            knowledge_id = i.pop("knowledge_id")
            doc_obj = doc_map.get(int(knowledge_id))
            if not doc_obj:
                logger.warning(f"knowledge_id: {knowledge_id} not found")
                continue
            i.update(doc_obj)
        return JsonResponse(
            {
                "result": True,
                "data": {"docs": docs, "qa_docs": qa_docs, "graph_data": graph_list},
            }
        )

    @action(methods=["GET"], detail=True)
    @HasPermission("knowledge_document-View")
    def get_detail(self, request, *args, **kwargs):
        instance: KnowledgeDocument = self.get_object()
        page = int(request.GET.get("page", 1))
        page_size = int(request.GET.get("page_size", 10))
        search_text = request.GET.get("search_term", "")
        index_name = instance.knowledge_index_name()
        res = ChunkHelper.get_document_es_chunk(
            index_name,
            page,
            page_size,
            search_text,
            metadata_filter={"knowledge_id": str(instance.id), "is_doc": "1"},
        )
        return JsonResponse(
            {
                "result": True,
                "data": {
                    "items": [
                        {
                            "id": i["metadata"]["chunk_id"],
                            "qa_count": i["metadata"].get("qa_count", 0),
                            "content": i["page_content"],
                            "index_name": index_name,
                        }
                        for i in res["documents"]
                    ],
                    "count": res["count"],
                },
            }
        )

    @action(methods=["GET"], detail=False)
    @HasPermission("knowledge_document-View")
    def get_chunk_detail(self, request):
        knowledge_id = request.GET.get("knowledge_id")
        instance = KnowledgeDocument.objects.get(id=knowledge_id)
        chunk_id = request.GET.get("chunk_id")
        if not chunk_id:
            return JsonResponse(
                {
                    "result": True,
                    "message": self.loader.get("chunk_id_required") if self.loader else "chunk_id is required",
                }
            )
        index_name = instance.knowledge_index_name()
        res = ChunkHelper.get_document_es_chunk(
            index_name,
            1,
            1,
            "",
            metadata_filter={"chunk_id": chunk_id, "is_doc": "1"},
        )
        if res["documents"]:
            return_data = res["documents"][0]
            return JsonResponse(
                {
                    "result": True,
                    "data": {
                        "id": return_data["metadata"]["chunk_id"],
                        "content": return_data["page_content"],
                        "index_name": index_name,
                    },
                }
            )
        return JsonResponse(
            {
                "result": False,
                "message": "Chunk not found",
            }
        )

    @action(methods=["POST"], detail=False)
    @HasPermission("knowledge_document-Delete")
    def delete_chunks(self, request):
        params = request.data
        chunk_ids = params["ids"]
        keep_qa = not params.get("delete_all", False)
        for chunk_id in chunk_ids:
            result = ChunkHelper.delete_es_content(chunk_id, True, keep_qa)
            if not result:
                return JsonResponse({"result": False, "message": "Failed to delete QA pair."})
        return JsonResponse({"result": True})

    @action(methods=["POST"], detail=True)
    @HasPermission("knowledge_document-Set")
    def enable_chunk(self, request, *args, **kwargs):
        instance: KnowledgeDocument = self.get_object()
        enabled = request.data.get("enabled", False)
        chunk_id = request.data.get("chunk_id", "")
        if not chunk_id:
            return JsonResponse(
                {
                    "result": False,
                    "message": self.loader.get("chunk_id_required") if self.loader else "chunk_id is required",
                }
            )
        try:
            KnowledgeSearchService.change_chunk_enable(instance.knowledge_index_name(), chunk_id, enabled)
            return JsonResponse({"result": True})
        except Exception as e:
            logger.exception(e)
            return JsonResponse(
                {
                    "result": False,
                    "message": self.loader.get("update_failed") if self.loader else "update failed",
                }
            )

    @action(methods=["POST"], detail=False)
    @HasPermission("knowledge_document-Delete")
    def batch_delete(self, request):
        doc_ids = request.data.get("doc_ids", [])
        knowledge_base_id = request.data.get("knowledge_base_id", 0)
        if KnowledgeDocument.objects.filter(id__in=doc_ids, train_status=DocumentStatus.TRAINING).exists():
            return JsonResponse({"result": False, "message": "training document can not be deleted"})
        KnowledgeDocument.objects.filter(id__in=doc_ids).delete()
        index_name = f"knowledge_base_{knowledge_base_id}"
        try:
            for i in doc_ids:
                KnowledgeSearchService.delete_es_content(index_name, str(i))
            QAPairs.objects.filter(document_id__in=doc_ids).delete()
        except Exception as e:
            logger.exception(e)
            return JsonResponse({"result": False, "message": "delete failed"})
        return JsonResponse({"result": True})

    @action(methods=["GET"], detail=True)
    @HasPermission("knowledge_document-View")
    def get_document_detail(self, request, *args, **kwargs):
        obj: KnowledgeDocument = self.get_object()
        result = {
            "document_id": obj.id,
            "name": obj.name,
            "knowledge_source_type": obj.knowledge_source_type,
        }
        knowledge_model_map = {
            "web_page": WebPageKnowledge,
            "manual": ManualKnowledge,
        }
        doc = knowledge_model_map[obj.knowledge_source_type].objects.filter(knowledge_document_id=obj.id).first()
        result.update(doc.to_dict())
        return JsonResponse({"result": True, "data": result})

    @action(methods=["GET"], detail=True)
    @HasPermission("knowledge_document-View")
    def get_instance_detail(self, request, *args, **kwargs):
        instance = self.get_object()
        return JsonResponse(
            {
                "result": True,
                "data": {
                    "knowledge_id": instance.id,
                    "name": instance.name,
                    "knowledge_base_id": instance.knowledge_base_id,
                    "knowledge_source_type": instance.knowledge_source_type,
                },
            }
        )

    @action(methods=["POST"], detail=True)
    @HasPermission("knowledge_document-Set")
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
        if obj.knowledge_source_type == "web_page":
            if doc.sync_enabled:
                doc.create_sync_periodic_task()
            else:
                doc.delete_sync_periodic_task()

        return JsonResponse({"result": True})

    @action(methods=["GET"], detail=True)
    @HasPermission("knowledge_document-View")
    def get_file_link(self, request, *args, **kwargs):
        instance: KnowledgeDocument = self.get_object()
        if instance.knowledge_source_type != "file":
            return JsonResponse(
                {
                    "result": False,
                    "message": self.loader.get("not_a_file") if self.loader else "Not a file",
                }
            )
        file_obj = FileKnowledge.objects.filter(knowledge_document_id=instance.id).first()
        if not file_obj:
            return JsonResponse(
                {
                    "result": False,
                    "message": self.loader.get("file_not_found") if self.loader else "File not found",
                }
            )
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
        return JsonResponse({"result": True})

    @action(methods=["POST"], detail=False)
    @HasPermission("knowledge_document-Set")
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
    @HasPermission("knowledge_document-Set")
    def update_chunk_settings(self, request):
        kwargs = request.data
        knowledge_document_list = kwargs.get("knowledge_document_list", [])
        KnowledgeDocument.objects.filter(id__in=knowledge_document_list).update(
            general_parse_chunk_size=kwargs.get("general_parse_chunk_size", 128),
            general_parse_chunk_overlap=kwargs.get("general_parse_chunk_overlap", 32),
            semantic_chunk_parse_embedding_model_id=kwargs.get("semantic_chunk_parse_embedding_model", None),
            chunk_type=kwargs.get("chunk_type", "fixed_size"),
        )
        general_embed.delay(knowledge_document_list, request.user.username, request.user.domain)
        return JsonResponse({"result": True})

    @action(methods=["POST"], detail=False)
    @HasPermission("knowledge_document-View")
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
    @HasPermission("knowledge_document-Set")
    def preview_chunk(self, request):
        kwargs = request.data
        document = KnowledgeDocument.objects.get(id=kwargs["knowledge_document_id"])
        document.chunk_type = kwargs.get("chunk_type", "fixed_size")
        document.general_parse_chunk_size = kwargs.get("general_parse_chunk_size", 128)
        document.general_parse_chunk_overlap = kwargs.get("general_parse_chunk_overlap", 32)
        if kwargs.get("semantic_chunk_parse_embedding_model", None):
            document.semantic_chunk_parse_embedding_model = EmbedProvider.objects.get(id=kwargs["semantic_chunk_parse_embedding_model"])
        res = general_embed_by_document_list(
            [document],
            is_show=True,
            username=request.user.username,
            domain=request.user.domain,
        )
        return JsonResponse({"result": True, "data": res})
