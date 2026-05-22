from django_filters import filters
from django_filters.rest_framework import FilterSet
from rest_framework import viewsets

from apps.opspilot.models import Channel
from apps.opspilot.serializers import ChannelSerializer
from apps.system_mgmt.utils.operation_log_utils import log_operation


class ObjFilter(FilterSet):
    name = filters.CharFilter(field_name="name", lookup_expr="icontains")


class ChannelViewSet(viewsets.ModelViewSet):
    queryset = Channel.objects.all()
    serializer_class = ChannelSerializer
    filterset_class = ObjFilter

    def create(self, request, *args, **kwargs):
        response = super().create(request, *args, **kwargs)
        if response.status_code >= 200 and response.status_code < 300:
            channel_name = response.data.get("name") if isinstance(response.data, dict) else None
            if not channel_name:
                channel_name = request.data.get("name", "")
            log_operation(request, "create", "opspilot", f"新增渠道: {channel_name}")
        return response

    def update(self, request, *args, **kwargs):
        response = super().update(request, *args, **kwargs)
        if response.status_code >= 200 and response.status_code < 300:
            channel_name = response.data.get("name") if isinstance(response.data, dict) else None
            if not channel_name:
                channel_name = request.data.get("name", "")
            log_operation(request, "update", "opspilot", f"编辑渠道: {channel_name}")
        return response

    def destroy(self, request, *args, **kwargs):
        obj = self.get_object()
        response = super().destroy(request, *args, **kwargs)
        if response.status_code >= 200 and response.status_code < 300:
            log_operation(request, "delete", "opspilot", f"删除渠道: {obj.name}")
        return response
