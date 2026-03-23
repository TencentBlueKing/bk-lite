from django.core.paginator import Paginator
from django.db import connection
from django.db.models import Count, Max, Min
from django.db.models.functions import TruncDay
from django.http import JsonResponse
from django_filters import filters
from django_filters.rest_framework import FilterSet
from rest_framework.decorators import action

from apps.core.decorators.api_permission import HasPermission
from apps.core.utils.viewset_utils import AuthViewSet
from apps.opspilot.enum import BotTypeChoice, WorkFlowExecuteType
from apps.opspilot.models import Bot, BotChannel, BotWorkFlow, LLMSkill, WorkFlowConversationHistory
from apps.opspilot.serializers import BotSerializer
from apps.opspilot.utils.bot_utils import set_time_range
from apps.opspilot.utils.celery_task_utils import create_celery_task, delete_celery_task
from apps.opspilot.utils.schedule_utils import get_crontab_next_runs


class BotFilter(FilterSet):
    name = filters.CharFilter(field_name="name", lookup_expr="icontains")
    bot_type = filters.CharFilter(method="filter_bot_type")

    @staticmethod
    def filter_bot_type(qs, field_name, value):
        """查询类型"""
        if not value:
            return qs
        return qs.filter(bot_type__in=[int(i.strip()) for i in value.split(",") if i.strip()])


class BotViewSet(AuthViewSet):
    serializer_class = BotSerializer
    queryset = Bot.objects.all()
    permission_key = "bot"
    filterset_class = BotFilter

    def query_by_groups(self, request, queryset):
        """重写排序逻辑：置顶优先，再按 ID 倒序"""
        new_queryset = self.get_queryset_by_permission(request, queryset)
        return self._list(new_queryset.order_by("-is_pinned", "-id"))

    @action(methods=["POST"], detail=True)
    @HasPermission("bot_settings-Edit")
    def toggle_pin(self, request, pk=None):
        """切换工作台置顶状态"""
        instance = self.get_object()
        if not request.user.is_superuser:
            current_team = request.COOKIES.get("current_team", "0")
            include_children = request.COOKIES.get("include_children", "0") == "1"
            has_permission = self.get_has_permission(request.user, instance, current_team, include_children=include_children)
            if not has_permission:
                message = self.loader.get("error.no_bot_update_permission") if self.loader else "You do not have permission to update this bot."
                return JsonResponse({"result": False, "message": message})
        instance.is_pinned = not instance.is_pinned
        instance.save(update_fields=["is_pinned"])
        return JsonResponse({"result": True, "data": {"is_pinned": instance.is_pinned}})

    @HasPermission("bot_list-Add")
    def create(self, request, *args, **kwargs):
        data = request.data
        current_team = data.get("team", []) or [int(request.COOKIES.get("current_team"))]
        bot_obj = Bot.objects.create(
            name=data.get("name"),
            introduction=data.get("introduction"),
            team=current_team,
            channels=[],
            created_by=request.user.username,
            replica_count=data.get("replica_count") or 1,
            bot_type=data.get("bot_type", BotTypeChoice.PILOT),
        )
        BotWorkFlow.objects.create(bot_id=bot_obj.id)
        return JsonResponse({"result": True})

    @HasPermission("bot_settings-Edit")
    def update(self, request, *args, **kwargs):
        obj: Bot = self.get_object()
        if not request.user.is_superuser:
            current_team = request.COOKIES.get("current_team", "0")
            include_children = request.COOKIES.get("include_children", "0") == "1"
            has_permission = self.get_has_permission(request.user, obj, current_team, include_children=include_children)
            if not has_permission:
                msg = self.loader.get("error.no_bot_update_permission") if self.loader else "You do not have permission to update this bot."
                return JsonResponse({"result": False, "message": msg})
        data = request.data
        is_publish = data.pop("is_publish", False)
        channels = data.pop("channels", [])
        llm_skills = data.pop("llm_skills", [])
        rasa_model = data.pop("rasa_model", None)
        node_port = data.pop("node_port", None)
        workflow_data = data.pop("workflow_data", None)
        if (not request.user.is_superuser) and (obj.created_by != request.user.username):
            data.pop("team", [])
        if "team" in data:
            delete_team = [i for i in obj.team if i not in data["team"]]
            self.delete_rules(obj.id, delete_team)
        for key in data.keys():
            setattr(obj, key, data[key])
        if node_port:
            obj.node_port = node_port
        if rasa_model:
            obj.rasa_model_id = rasa_model
        if channels:
            obj.channels = channels
        if llm_skills:
            obj.llm_skills.set(LLMSkill.objects.filter(id__in=llm_skills))
        if is_publish and not obj.api_token:
            obj.api_token = obj.get_api_token()
        if workflow_data:
            # 直接使用 workflow_data 作为 flow_json
            flow = BotWorkFlow.objects.get(bot_id=obj.id)
            flow.flow_json = workflow_data
            flow.web_json = workflow_data
            flow.save()
        obj.updated_by = request.user.username
        obj.save()
        if is_publish:
            # 只有 CHAT_FLOW 类型,创建 Celery 任务
            create_celery_task(obj.id, workflow_data)
            obj.online = is_publish
            obj.save()

        return JsonResponse({"result": True})

    @HasPermission("bot_channel-View")
    @action(methods=["GET"], detail=False)
    def get_bot_channels(self, request):
        bot_id = request.GET.get("bot_id")
        channels = BotChannel.objects.filter(bot_id=bot_id)
        return_data = []
        for i in channels:
            return_data.append(
                {"id": i.id, "name": i.name, "channel_type": i.channel_type, "channel_config": i.format_channel_config(), "enabled": i.enabled}
            )
        return JsonResponse({"result": True, "data": return_data})

    @HasPermission("bot_channel-Setting")
    @action(methods=["POST"], detail=False)
    def update_bot_channel(self, request):
        channel_id = request.data.get("id")
        enabled = request.data.get("enabled")
        channel_config = request.data.get("channel_config")
        channel = BotChannel.objects.get(id=channel_id)
        if not request.user.is_superuser:
            current_team = request.COOKIES.get("current_team", "0")
            include_children = request.COOKIES.get("include_children", "0") == "1"
            has_permission = self.get_has_permission(request.user, channel.bot, current_team, include_children=include_children)
            if not has_permission:
                message = self.loader.get("error.no_bot_update_permission") if self.loader else "You do not have permission to update this bot."
                return JsonResponse({"result": False, "message": message})

        channel.enabled = enabled
        if channel_config is not None:
            channel.channel_config = channel_config
        channel.save()
        return JsonResponse({"result": True})

    @HasPermission("bot_list-Delete")
    def destroy(self, request, *args, **kwargs):
        obj = self.get_object()
        # 只有 CHAT_FLOW 类型,删除 Celery 任务
        delete_celery_task(obj.id)
        return super().destroy(request, *args, **kwargs)

    @action(methods=["POST"], detail=False)
    @HasPermission("bot_settings-Save&Publish")
    def start_pilot(self, request):
        bot_ids = request.data.get("bot_ids")
        bots = Bot.objects.filter(id__in=bot_ids)
        if not request.user.is_superuser:
            current_team = request.COOKIES.get("current_team", "0")
            include_children = request.COOKIES.get("include_children", "0") == "1"
            has_permission = self.get_has_permission(request.user, bots, current_team, is_list=True, include_children=include_children)
            if not has_permission:
                message = self.loader.get("error.no_bot_start_permission") if self.loader else "You do not have permission to start this bot."
                return JsonResponse({"result": False, "message": message})
        # 只有 CHAT_FLOW 类型
        for bot in bots:
            if not bot.api_token:
                bot.api_token = bot.get_api_token()
            bot.save()
            workflow_data = BotWorkFlow.objects.filter(bot_id=bot.id).first()
            if workflow_data:
                create_celery_task(bot.id, workflow_data.web_json)
            bot.online = True
            bot.save()
        return JsonResponse({"result": True})

    @action(methods=["POST"], detail=False)
    @HasPermission("bot_settings-Save&Publish")
    def stop_pilot(self, request):
        bot_ids = request.data.get("bot_ids")
        bots = Bot.objects.filter(id__in=bot_ids)
        if not request.user.is_superuser:
            current_team = request.COOKIES.get("current_team", "0")
            include_children = request.COOKIES.get("include_children", "0") == "1"
            has_permission = self.get_has_permission(request.user, bots, current_team, is_list=True, include_children=include_children)
            if not has_permission:
                message = self.loader.get("error.no_bot_stop_permission") if self.loader else "You do not have permission to stop this bot"
                return JsonResponse({"result": False, "message": message})

        # 只有 CHAT_FLOW 类型
        for bot in bots:
            delete_celery_task(bot.id)
            bot.api_token = ""
            bot.online = False
            bot.save()
        return JsonResponse({"result": True})

    @action(methods=["GET"], detail=False)
    @HasPermission("bot_conversation_log-View")
    def search_workflow_log(self, request):
        """
        ChatFlow 对话历史列表
        根据 entry_type、bot_id、user_id 聚合一天内的历史记录
        """
        (
            bot_id,
            entry_type,
            end_time,
            page,
            page_size,
            search,
            start_time,
        ) = self._set_workflow_log_params(request)

        # 聚合查询：按天、bot_id、user_id、entry_type 分组
        # 注意：title 字段在 _get_workflow_log_by_page 中单独查询，避免 GROUP BY 子查询问题（达梦不支持）
        base_queryset = (
            WorkFlowConversationHistory.objects.filter(
                conversation_time__range=(start_time, end_time),
                bot_id=bot_id,
                entry_type__in=entry_type,
                user_id__icontains=search,
            )
            .annotate(day=TruncDay("conversation_time"))
            .values("day", "bot_id", "user_id", "entry_type")
        )

        # PostgreSQL 使用 ArrayAgg，其他数据库使用回退方案
        if connection.vendor == "postgresql":
            from django.contrib.postgres.aggregates import ArrayAgg

            aggregated_data = base_queryset.annotate(
                count=Count("id"),
                ids=ArrayAgg("id"),
                earliest_created_at=Min("conversation_time"),
                last_updated_at=Max("conversation_time"),
            ).order_by("-earliest_created_at")
        else:
            # 回退方案：不使用 ArrayAgg，后续在 _get_workflow_log_by_page 中处理
            aggregated_data = base_queryset.annotate(
                count=Count("id"),
                earliest_created_at=Min("conversation_time"),
                last_updated_at=Max("conversation_time"),
            ).order_by("-earliest_created_at")

        paginator, result = self._get_workflow_log_by_page(aggregated_data, page, page_size)
        return JsonResponse({"result": True, "data": {"items": result, "count": paginator.count}})

    @action(methods=["POST"], detail=False)
    @HasPermission("bot_conversation_log-View")
    def get_workflow_log_detail(self, request):
        """
        获取单次对话详情
        根据 ids 获取具体的对话记录
        """
        ids = request.data.get("ids")
        page_size = int(request.data.get("page_size", 10))
        page = int(request.data.get("page", 1))

        history_list = (
            WorkFlowConversationHistory.objects.filter(id__in=ids)
            .values("id", "conversation_role", "conversation_content", "conversation_time", "entry_type")
            .order_by("conversation_time")
        )

        paginator = Paginator(history_list, page_size)
        try:
            page_data = paginator.page(page)
        except Exception:
            page_data = []

        return_data = []
        for i in page_data:
            return_data.append(
                {
                    "id": i["id"],
                    "role": i["conversation_role"],
                    "content": i["conversation_content"],
                    "conversation_time": i["conversation_time"].strftime("%Y-%m-%dT%H:%M:%S.%fZ"),
                    "entry_type": dict(WorkFlowExecuteType.choices).get(
                        i["entry_type"],
                        i["entry_type"],
                    ),
                }
            )
        return JsonResponse({"result": True, "data": return_data})

    @staticmethod
    def _set_workflow_log_params(request):
        """设置 ChatFlow 对话历史查询参数"""
        start_time_str = request.GET.get("start_time")
        end_time_str = request.GET.get("end_time")
        page_size = int(request.GET.get("page_size", 10))
        page = int(request.GET.get("page", 1))
        bot_id = request.GET.get("bot_id")
        search = request.GET.get("search", "")
        entry_type = request.GET.get("entry_type", "")

        # 处理 entry_type，如果为空则使用所有类型（排除 celery）
        if not entry_type:
            entry_type = [choice[0] for choice in WorkFlowExecuteType.choices if choice[0] != "celery"]
        else:
            entry_type = entry_type.split(",")

        end_time, start_time = set_time_range(end_time_str, start_time_str)
        return bot_id, entry_type, end_time, page, page_size, search, start_time

    @staticmethod
    def _get_workflow_log_by_page(aggregated_data, page, page_size):
        """分页处理 ChatFlow 对话历史"""
        paginator = Paginator(aggregated_data, page_size)
        result = []
        try:
            page_data = paginator.page(page)
        except Exception:
            page_data = paginator.page(1)

        for entry in page_data:
            # 将 TruncDay 返回的 datetime 转换为 date，确保跨数据库兼容性
            entry_day = entry["day"].date() if hasattr(entry["day"], "date") else entry["day"]

            # 获取 ids：PostgreSQL 已有 ArrayAgg 结果，其他数据库需要单独查询
            if "ids" in entry:
                ids = entry["ids"]
            else:
                # 回退方案：根据聚合条件查询对应的 ID 列表
                ids = list(
                    WorkFlowConversationHistory.objects.filter(
                        bot_id=entry["bot_id"],
                        user_id=entry["user_id"],
                        entry_type=entry["entry_type"],
                        conversation_time__date=entry_day,
                    ).values_list("id", flat=True)
                )

            # 获取 title：查询当天最早的对话内容作为标题
            # 此查询从主聚合查询中分离，避免 GROUP BY 子查询问题（达梦等数据库不支持）
            title_record = (
                WorkFlowConversationHistory.objects.filter(
                    bot_id=entry["bot_id"],
                    user_id=entry["user_id"],
                    conversation_time__date=entry_day,
                )
                .order_by("conversation_time")
                .values_list("conversation_content", flat=True)
                .first()
            )
            title = title_record[:100] if title_record else ""

            result.append(
                {
                    "bot_id": entry["bot_id"],
                    "user_id": entry["user_id"],
                    "entry_type": dict(WorkFlowExecuteType.choices).get(
                        entry["entry_type"],
                        entry["entry_type"],
                    ),
                    "count": entry["count"],
                    "ids": ids,
                    "created_at": entry["earliest_created_at"].strftime("%Y-%m-%dT%H:%M:%S.%fZ"),
                    "updated_at": entry["last_updated_at"].strftime("%Y-%m-%dT%H:%M:%S.%fZ"),
                    "title": title,
                }
            )
        return paginator, result

    @action(methods=["POST"], detail=False)
    def preview_crontab(self, request):
        """
        Preview next execution times for a crontab expression.

        Request body:
            crontab_expression: str - 5-field crontab expression (minute hour day month weekday)
            count: int - Number of next executions to return (default: 6, max: 20)

        Returns:
            result: bool - Success flag
            data: list - List of next execution times in "YYYY-MM-DD HH:MM:SS" format
            message: str - Error message if failed
        """
        crontab_expression = request.data.get("crontab_expression", "")
        count = min(int(request.data.get("count", 6)), 20)  # Max 20

        if not crontab_expression:
            message = self.loader.get("error.crontab_expression_required") if self.loader else "crontab_expression is required"
            return JsonResponse({"result": False, "message": message})
        try:
            next_runs = get_crontab_next_runs(crontab_expression, count=count)
            return JsonResponse({"result": True, "data": next_runs})
        except ValueError:
            template = self.loader.get("error.invalid_crontab_expression") if self.loader else "Invalid crontab expression: {expression}"
            message = template.format(expression=crontab_expression)
            return JsonResponse({"result": False, "message": message})
