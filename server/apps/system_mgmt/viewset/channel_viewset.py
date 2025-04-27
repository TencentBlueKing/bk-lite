from django.http import JsonResponse
from django_filters import filters
from django_filters.rest_framework import FilterSet
from rest_framework import viewsets
from rest_framework.decorators import action

from apps.system_mgmt.models import Channel
from apps.system_mgmt.serializers import ChannelSerializer


class ChannelFilter(FilterSet):
    name = filters.CharFilter(field_name="name", lookup_expr="icontains")
    channel_type = filters.CharFilter(field_name="channel_type", lookup_expr="exact")


class ChannelViewSet(viewsets.ModelViewSet):
    queryset = Channel.objects.all()
    serializer_class = ChannelSerializer
    filterset_class = ChannelFilter

    @action(methods=["POST"], detail=True)
    def update_settings(self, request, *args, **kwargs):
        obj: Channel = self.get_object()
        config = request.data["config"]
        if obj.channel_type == "email":
            obj.encrypt_field("smtp_pwd", config)
        elif obj.channel_type == "enterprise_wechat":
            obj.encrypt_field("secret", config)
            obj.encrypt_field("token", config)
            obj.encrypt_field("aes_key", config)
        elif obj.channel_type == "enterprise_wechat_bot":
            obj.encrypt_field("bot_key", config)
        obj.config = config
        obj.save()
        return JsonResponse({"result": True})


class TemplateFilter(FilterSet):
    channel_type = filters.CharFilter(field_name="channel_type", lookup_expr="exact")
    name = filters.CharFilter(field_name="name", lookup_expr="lte")
