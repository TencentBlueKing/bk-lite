from django.http import JsonResponse
from django.utils.translation import gettext as _
from rest_framework.decorators import action

from apps.core.decorators.api_perminssion import HasRole
from apps.core.logger import logger
from apps.core.utils.viewset_utils import AuthViewSet
from apps.opspilot.bot_mgmt.serializers import BotSerializer
from apps.opspilot.enum import ChannelChoices
from apps.opspilot.models import Bot, BotChannel, Channel, LLMSkill
from apps.opspilot.quota_rule_mgmt.quota_utils import get_quota_client
from apps.opspilot.utils.pilot_client import PilotClient


class BotViewSet(AuthViewSet):
    serializer_class = BotSerializer
    queryset = Bot.objects.all()
    permission_key = "bot"

    def create(self, request, *args, **kwargs):
        data = request.data
        client = get_quota_client(request)
        bot_count, used_bot_count, __ = client.get_bot_quota()
        if bot_count != -1 and bot_count <= used_bot_count:
            return JsonResponse({"result": False, "message": _("Bot count exceeds quota limit.")})
        current_team = data.get("team", []) or [request.COOKIES.get("current_team")]
        bot_obj = Bot.objects.create(
            name=data.get("name"),
            introduction=data.get("introduction"),
            team=current_team,
            channels=[],
            created_by=request.user.username,
            replica_count=data.get("replica_count") or 1,
        )
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

    def update(self, request, *args, **kwargs):
        data = request.data
        is_publish = data.pop("is_publish", False)
        obj: Bot = self.get_object()
        channels = data.pop("channels", [])
        llm_skills = data.pop("llm_skills", [])
        rasa_model = data.pop("rasa_model", None)
        node_port = data.pop("node_port", None)
        if (not request.user.is_superuser) and (obj.created_by != request.user.username):
            data.pop("team", [])
        for key in data.keys():
            setattr(obj, key, data[key])
        if node_port:
            obj.node_port = node_port
        if rasa_model is not None:
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

    @action(methods=["POST"], detail=False)
    def update_bot_channel(self, request):
        channel_id = request.data.get("id")
        enabled = request.data.get("enabled")
        channel_config = request.data.get("channel_config")
        channel = BotChannel.objects.get(id=channel_id)
        channel.enabled = enabled
        if channel_config is not None:
            channel.channel_config = channel_config
        channel.save()
        return JsonResponse({"result": True})

    def destroy(self, request, *args, **kwargs):
        client = PilotClient()
        obj: Bot = self.get_object()
        if obj.online:
            client.stop_pilot(obj.id)
        return super().destroy(request, *args, **kwargs)

    @HasRole()
    def list(self, request, *args, **kwargs):
        name = request.query_params.get("name", "")
        queryset = Bot.objects.filter(name__icontains=name)
        return self.query_by_groups(request, queryset)

    @action(methods=["POST"], detail=False)
    def start_pilot(self, request):
        bot_ids = request.data.get("bot_ids")
        bots = Bot.objects.filter(id__in=bot_ids)
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
    def stop_pilot(self, request):
        bot_ids = request.data.get("bot_ids")
        bots = Bot.objects.filter(id__in=bot_ids)
        client = PilotClient()
        for bot in bots:
            client.stop_pilot(bot.id)
            bot.api_token = ""
            bot.online = False
            bot.save()
        return JsonResponse({"result": True})
