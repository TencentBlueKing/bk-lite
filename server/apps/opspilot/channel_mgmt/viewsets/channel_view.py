from django_filters import filters
from django_filters.rest_framework import FilterSet
from rest_framework import viewsets

from apps.opspilot.channel_mgmt.serializers import ChannelSerializer
from apps.opspilot.models import Channel


class ObjFilter(FilterSet):
    name = filters.CharFilter(field_name="name", lookup_expr="icontains")


class ChannelViewSet(viewsets.ModelViewSet):
    queryset = Channel.objects.all()
    serializer_class = ChannelSerializer
    filterset_class = ObjFilter
