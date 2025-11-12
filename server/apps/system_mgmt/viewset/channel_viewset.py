from django.http import JsonResponse
from django_filters import filters
from django_filters.rest_framework import FilterSet
from rest_framework import viewsets
from rest_framework.decorators import action

from apps.core.decorators.api_permission import HasPermission
from apps.system_mgmt.models import Channel
from apps.system_mgmt.serializers import ChannelSerializer
from apps.system_mgmt.utils.operation_log_utils import log_operation


class ChannelFilter(FilterSet):
    name = filters.CharFilter(field_name="name", lookup_expr="icontains")
    channel_type = filters.CharFilter(field_name="channel_type", lookup_expr="exact")


class ChannelViewSet(viewsets.ModelViewSet):
    queryset = Channel.objects.all()
    serializer_class = ChannelSerializer
    filterset_class = ChannelFilter

    @HasPermission("Channel_list-View")
    def list(self, request, *args, **kwargs):
        return super().list(request, *args, **kwargs)

    @HasPermission("Channel_list-Add")
    def create(self, request, *args, **kwargs):
        response = super().create(request, *args, **kwargs)

        # 记录操作日志
        if response.status_code == 201:
            channel_name = response.data.get("name", "")
            channel_type = response.data.get("channel_type", "")
            log_operation(request, "create", "channel", f"新增{channel_type}渠道: {channel_name}")

        return response

    @HasPermission("Channel_list-Delete")
    def destroy(self, request, *args, **kwargs):
        obj = self.get_object()
        channel_name = obj.name
        channel_type = obj.channel_type

        response = super().destroy(request, *args, **kwargs)

        # 记录操作日志
        if response.status_code == 204:
            log_operation(request, "delete", "channel", f"删除{channel_type}渠道: {channel_name}")

        return response

    @action(methods=["POST"], detail=True)
    @HasPermission("Channel_list-Edit")
    def update_settings(self, request, *args, **kwargs):
        obj: Channel = self.get_object()
        config = request.data["config"]
        if obj.channel_type == "email":
            obj.encrypt_field("smtp_pwd", config)
            config.setdefault("smtp_pwd", obj.config["smtp_pwd"])
        elif obj.channel_type == "enterprise_wechat":
            obj.encrypt_field("secret", config)
            obj.encrypt_field("token", config)
            obj.encrypt_field("aes_key", config)
            config.setdefault("secret", obj.config["secret"])
            config.setdefault("token", obj.config["token"])
            config.setdefault("aes_key", obj.config["aes_key"])
        elif obj.channel_type == "enterprise_wechat_bot":
            obj.encrypt_field("bot_key", config)
            config.setdefault("bot_key", obj.config["bot_key"])
        obj.config = config
        obj.save()

        # 记录操作日志
        log_operation(request, "update", "channel", f"编辑{obj.channel_type}渠道: {obj.name}")

        return JsonResponse({"result": True})


class TemplateFilter(FilterSet):
    channel_type = filters.CharFilter(field_name="channel_type", lookup_expr="exact")
    name = filters.CharFilter(field_name="name", lookup_expr="lte")
