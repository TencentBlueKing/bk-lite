from django.contrib.postgres.aggregates import ArrayAgg
from django.core.paginator import Paginator
from django.db import transaction
from django.db.models import Count, Max, Min, OuterRef, Subquery
from django.db.models.functions import TruncDay
from django.http import JsonResponse
from rest_framework import viewsets
from rest_framework.decorators import action

from apps.core.decorators.api_permission import HasPermission
from apps.opspilot.enum import ChannelChoices
from apps.opspilot.models import BotConversationHistory, ConversationTag, KnowledgeDocument, ManualKnowledge
from apps.opspilot.serializers.history_serializer import HistorySerializer
from apps.opspilot.tasks import invoke_document_to_es
from apps.opspilot.utils.bot_utils import set_time_range
from apps.opspilot.utils.knowledge_utils import KnowledgeDocumentUtils


class HistoryViewSet(viewsets.ModelViewSet):
    serializer_class = HistorySerializer
    queryset = BotConversationHistory.objects.all()

    @action(methods=["GET"], detail=False)
    @HasPermission("bot_conversation_log-View")
    def search_log(self, request):
        (
            bot_id,
            channel_type,
            end_time,
            page,
            page_size,
            search,
            start_time,
        ) = self.set_log_params(request)

        earliest_conversation_subquery = (
            BotConversationHistory.objects.filter(
                bot=OuterRef("bot"),
                channel_user=OuterRef("channel_user"),
                created_at__date=OuterRef("day"),
            )
            .order_by("created_at")
            .values("conversation")[:1]
        )
        aggregated_data = (
            BotConversationHistory.objects.filter(
                created_at__range=(start_time, end_time),
                bot_id=bot_id,
                channel_user__channel_type__in=channel_type,
                channel_user__name__icontains=search,
            )
            .annotate(day=TruncDay("created_at"))
            .values(
                "day",
                "channel_user__user_id",
                "channel_user__name",
                "channel_user__channel_type",
            )
            .annotate(
                count=Count("id"),
                ids=ArrayAgg("id"),
                earliest_created_at=Min("created_at"),
                last_updated_at=Max("created_at"),
                title=Subquery(earliest_conversation_subquery),
            )
            .order_by("-earliest_created_at")
        )
        paginator, result = self.get_log_by_page(aggregated_data, page, page_size)
        return JsonResponse({"result": True, "data": {"items": result, "count": paginator.count}})

    @staticmethod
    def get_log_by_page(aggregated_data, page, page_size):
        paginator = Paginator(aggregated_data, page_size)
        # 将结果转换为期望的格式
        result = []
        try:
            page_data = paginator.page(page)
        except Exception:
            # 处理无效的页码请求
            page_data = paginator.page(1)  # 返回第一页数据
        for entry in page_data:
            result.append(
                {
                    "sender_id": entry["channel_user__user_id"],
                    "username": entry["channel_user__name"],
                    "channel_type": dict(ChannelChoices.choices).get(
                        entry["channel_user__channel_type"],
                        entry["channel_user__channel_type"],
                    ),
                    "count": entry["count"],
                    "ids": entry["ids"],
                    "created_at": entry["earliest_created_at"].strftime("%Y-%m-%dT%H:%M:%S.%fZ"),
                    "updated_at": entry["last_updated_at"].strftime("%Y-%m-%dT%H:%M:%S.%fZ"),
                    "title": entry["title"],
                }
            )
        return paginator, result

    @staticmethod
    def set_log_params(request):
        start_time_str = request.GET.get("start_time")
        end_time_str = request.GET.get("end_time")
        page_size = int(request.GET.get("page_size", 10))
        page = int(request.GET.get("page", 1))
        bot_id = request.GET.get("bot_id")
        search = request.GET.get("search", "")
        channel_type = request.GET.get("channel_type", "")
        if not channel_type:
            channel_type = list(dict(ChannelChoices.choices).keys())
        else:
            channel_type = channel_type.split(",")
        end_time, start_time = set_time_range(end_time_str, start_time_str)
        return bot_id, channel_type, end_time, page, page_size, search, start_time

    @action(methods=["POST"], detail=False)
    @HasPermission("bot_conversation_log-View")
    def get_log_detail(self, request):
        ids = request.data.get("ids")
        page_size = int(request.data.get("page_size", 10))
        page = int(request.data.get("page", 1))
        history_list = (
            BotConversationHistory.objects.filter(id__in=ids)
            .values("id", "conversation_role", "conversation", "citing_knowledge")
            .order_by("created_at")
        )
        paginator = Paginator(history_list, page_size)
        # 将结果转换为期望的格式
        try:
            page_data = paginator.page(page)
        except Exception:
            page_data = []
        return_data = []
        tag_map = dict(ConversationTag.objects.filter(answer_id__in=ids).values_list("answer_id", "id"))
        for i in page_data:
            return_data.append(
                {
                    "id": i["id"],
                    "role": i["conversation_role"],
                    "content": i["conversation"],
                    "citing_knowledge": i["citing_knowledge"],
                    "has_tag": i["id"] in tag_map,
                    "tag_id": tag_map.get(i["id"], 0),
                }
            )
        return JsonResponse({"result": True, "data": return_data})

    @action(methods=["GET"], detail=False)
    @HasPermission("bot_conversation_log-View")
    def get_tag_detail(self, request):
        tag_obj = ConversationTag.objects.get(id=request.GET.get("tag_id"))
        return JsonResponse(
            {
                "result": True,
                "data": {
                    "knowledge_base_id": tag_obj.knowledge_base_id,
                    "content": tag_obj.content,
                    "question": tag_obj.question,
                },
            }
        )

    @action(methods=["POST"], detail=False)
    @HasPermission("bot_conversation_log-Mark")
    def set_tag(self, request):
        kwargs = request.data
        params = {
            "knowledge_source_type": "manual",
            "name": kwargs["question"],
            "knowledge_base_id": kwargs["knowledge_base_id"],
        }
        with transaction.atomic():
            tag_obj = self.get_or_create_tag(kwargs)
            new_doc = KnowledgeDocumentUtils.get_new_document(params, request.user.username, request.user.domain)
            ManualKnowledge.objects.create(
                knowledge_document_id=new_doc.id,
                content=kwargs.get("content", ""),
            )
            tag_obj.knowledge_document_id = new_doc.id
            tag_obj.content = kwargs["content"]
            tag_obj.save()
        invoke_document_to_es.delay(new_doc.id)
        return JsonResponse({"result": True, "data": {"tag_id": tag_obj.id}})

    @action(methods=["POST"], detail=False)
    @HasPermission("bot_conversation_log-Mark")
    def remove_tag(self, request):
        tag_obj = ConversationTag.objects.get(id=request.data.get("tag_id"))
        doc_obj = KnowledgeDocument.objects.filter(id=tag_obj.knowledge_document_id).first()
        with transaction.atomic():
            if doc_obj:
                doc_obj.delete()
            tag_obj.delete()
        return JsonResponse({"result": True})

    @staticmethod
    def get_or_create_tag(kwargs):
        tag_obj = ConversationTag.objects.filter(id=kwargs["tag_id"]).first()
        if tag_obj:
            doc_obj = KnowledgeDocument.objects.filter(id=tag_obj.knowledge_document_id).first()
            if doc_obj:
                doc_obj.delete()
            tag_obj.knowledge_base_id = kwargs["knowledge_base_id"]
            tag_obj.question = kwargs["question"]
        else:
            tag_obj = ConversationTag.objects.create(
                knowledge_base_id=kwargs["knowledge_base_id"],
                answer_id=kwargs.get("answer_id"),
                question=kwargs["question"],
                knowledge_document_id=0,
                content=kwargs["content"],
            )
        return tag_obj
