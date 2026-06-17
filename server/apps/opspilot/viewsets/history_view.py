from django.core.paginator import Paginator
from django.db import connection
from django.db.models import Count, Max, Min, OuterRef, Subquery
from django.db.models.functions import TruncDay
from django.http import JsonResponse
from rest_framework import viewsets
from rest_framework.decorators import action

from apps.core.decorators.api_permission import HasPermission
from apps.opspilot.enum import ChannelChoices
from apps.opspilot.models import BotConversationHistory, ConversationTag
from apps.opspilot.serializers.history_serializer import HistorySerializer
from apps.opspilot.utils.bot_utils import set_time_range
from apps.opspilot.utils.team_permission_mixin import TeamPermissionMixin


class HistoryViewSet(TeamPermissionMixin, viewsets.ModelViewSet):
    serializer_class = HistorySerializer
    queryset = BotConversationHistory.objects.all()
    # 只允许自定义 action 使用的 HTTP 方法
    http_method_names = ["get", "post", "head", "options"]

    def list(self, request, *args, **kwargs):
        """禁用内置 list 接口"""
        return JsonResponse({"result": False, "message": "此接口已禁用"}, status=405)

    def create(self, request, *args, **kwargs):
        """禁用内置 create 接口"""
        return JsonResponse({"result": False, "message": "此接口已禁用"}, status=405)

    def retrieve(self, request, *args, **kwargs):
        """禁用内置 retrieve 接口"""
        return JsonResponse({"result": False, "message": "此接口已禁用"}, status=405)

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

        # 验证用户有权限访问该 bot
        self._validate_bot_permission(request, bot_id)

        earliest_conversation_subquery = (
            BotConversationHistory.objects.filter(bot=OuterRef("bot"), channel_user=OuterRef("channel_user"), created_at__date=OuterRef("day"))
            .order_by("created_at")
            .values("conversation")[:1]
        )
        base_queryset = (
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
        )

        # PostgreSQL 使用 ArrayAgg，其他数据库使用回退方案
        if connection.vendor == "postgresql":
            from django.contrib.postgres.aggregates import ArrayAgg

            aggregated_data = base_queryset.annotate(
                count=Count("id"),
                ids=ArrayAgg("id"),
                earliest_created_at=Min("created_at"),
                last_updated_at=Max("created_at"),
                title=Subquery(earliest_conversation_subquery),
            ).order_by("-earliest_created_at")
        else:
            # 回退方案：不使用 ArrayAgg，后续在 get_log_by_page 中处理
            aggregated_data = base_queryset.annotate(
                count=Count("id"),
                earliest_created_at=Min("created_at"),
                last_updated_at=Max("created_at"),
                title=Subquery(earliest_conversation_subquery),
            ).order_by("-earliest_created_at")
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
            # 获取 ids：PostgreSQL 已有 ArrayAgg 结果，其他数据库需要单独查询
            if "ids" in entry:
                ids = entry["ids"]
            else:
                # 回退方案：根据聚合条件查询对应的 ID 列表
                ids = list(
                    BotConversationHistory.objects.filter(
                        channel_user__user_id=entry["channel_user__user_id"],
                        channel_user__channel_type=entry["channel_user__channel_type"],
                        created_at__date=entry["day"],
                    ).values_list("id", flat=True)
                )

            result.append(
                {
                    "sender_id": entry["channel_user__user_id"],
                    "username": entry["channel_user__name"],
                    "channel_type": dict(ChannelChoices.choices).get(
                        entry["channel_user__channel_type"],
                        entry["channel_user__channel_type"],
                    ),
                    "count": entry["count"],
                    "ids": ids,
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
            .values("id", "conversation_role", "conversation")
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
                    "has_tag": i["id"] in tag_map,
                    "tag_id": tag_map.get(i["id"], 0),
                }
            )
        return JsonResponse({"result": True, "data": return_data})
