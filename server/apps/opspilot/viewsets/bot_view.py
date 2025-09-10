from django.http import JsonResponse
from django.utils.translation import gettext as _
from django_filters import filters
from django_filters.rest_framework import FilterSet
from rest_framework.decorators import action

from apps.core.decorators.api_permission import HasPermission
from apps.core.logger import opspilot_logger as logger
from apps.core.utils.viewset_utils import AuthViewSet
from apps.opspilot.enum import BotTypeChoice, ChannelChoices
from apps.opspilot.models import Bot, BotChannel, Channel, LLMSkill
from apps.opspilot.serializers import BotSerializer
from apps.opspilot.utils.pilot_client import PilotClient
from apps.opspilot.utils.quota_utils import get_quota_client


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

    @HasPermission("bot_list-Add")
    def create(self, request, *args, **kwargs):
        data = request.data
        if not request.user.is_superuser:
            client = get_quota_client(request)
            bot_count, used_bot_count, __ = client.get_bot_quota()
            if bot_count != -1 and bot_count <= used_bot_count:
                return JsonResponse({"result": False, "message": _("Bot count exceeds quota limit.")})
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
        if data.get("bot_type", BotTypeChoice.PILOT) == BotTypeChoice.PILOT:
            channel_list = Channel.objects.all()
            BotChannel.objects.bulk_create(
                [
                    BotChannel(
                        bot_id=bot_obj.id,
                        name=i.name,
                        channel_type=i.channel_type,
                        channel_config=i.channel_config,
                        enabled=i.channel_type == ChannelChoices.WEB,
                    )
                    for i in channel_list
                ]
            )
        return JsonResponse({"result": True})

    @HasPermission("bot_settings-Edit")
    def update(self, request, *args, **kwargs):
        obj: Bot = self.get_object()
        if not request.user.is_superuser:
            current_team = request.COOKIES.get("current_team", "0")
            has_permission = self.get_has_permission(request.user, obj, current_team)
            if not has_permission:
                return JsonResponse(
                    {
                        "result": False,
                        "message": _("You do not have permission to update this bot."),
                    }
                )
        data = request.data
        is_publish = data.pop("is_publish", False)
        channels = data.pop("channels", [])
        llm_skills = data.pop("llm_skills", [])
        rasa_model = data.pop("rasa_model", None)
        node_port = data.pop("node_port", None)
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
        obj.updated_by = request.user.username
        obj.save()
        if is_publish:
            client = PilotClient()
            try:
                client.start_pilot(obj)
            except Exception as e:
                logger.exception(e)
                return JsonResponse({"result": False, "message": _("Pilot start failed.")})
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
                {
                    "id": i.id,
                    "name": i.name,
                    "channel_type": i.channel_type,
                    "channel_config": i.format_channel_config(),
                    "enabled": i.enabled,
                }
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
            has_permission = self.get_has_permission(request.user, channel.bot, current_team)
            if not has_permission:
                return JsonResponse(
                    {
                        "result": False,
                        "message": _("You do not have permission to update this bot."),
                    }
                )

        channel.enabled = enabled
        if channel_config is not None:
            channel.channel_config = channel_config
        channel.save()
        return JsonResponse({"result": True})

    @HasPermission("bot_list-Delete")
    def destroy(self, request, *args, **kwargs):
        obj = self.get_object()
        if obj.online:
            client = PilotClient()
            client.stop_pilot(obj)
        return super().destroy(request, *args, **kwargs)

    @action(methods=["POST"], detail=False)
    @HasPermission("bot_settings-Save&Publish")
    def start_pilot(self, request):
        bot_ids = request.data.get("bot_ids")
        bots = Bot.objects.filter(id__in=bot_ids)
        if not request.user.is_superuser:
            current_team = request.COOKIES.get("current_team", "0")
            has_permission = self.get_has_permission(request.user, bots, current_team, is_list=True)
            if not has_permission:
                return JsonResponse(
                    {
                        "result": False,
                        "message": _("You do not have permission to start this bot."),
                    }
                )
        client = PilotClient()
        for bot in bots:
            if not bot.api_token:
                bot.api_token = bot.get_api_token()
            bot.save()
            client.start_pilot(bot)
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
            has_permission = self.get_has_permission(request.user, bots, current_team, is_list=True)
            if not has_permission:
                return JsonResponse(
                    {
                        "result": False,
                        "message": _("You do not have permission to stop this bot"),
                    }
                )

        client = PilotClient()
        for bot in bots:
            client.stop_pilot(bot)
            bot.api_token = ""
            bot.online = False
            bot.save()
        return JsonResponse({"result": True})
