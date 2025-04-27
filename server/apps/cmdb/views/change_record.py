from rest_framework import viewsets
from rest_framework.decorators import action

from apps.cmdb.filters.change_record import ChangeRecordFilter
from apps.cmdb.language.service import SettingLanguage
from apps.cmdb.models.change_record import OPERATE_TYPE_CHOICES, ChangeRecord
from apps.cmdb.serializers.change_record import ChangeRecordSerializer
from apps.core.utils.web_utils import WebUtils
from config.drf.pagination import CustomPageNumberPagination


class ChangeRecordViewSet(viewsets.ReadOnlyModelViewSet):
    queryset = ChangeRecord.objects.all().order_by("-created_at")
    serializer_class = ChangeRecordSerializer
    filterset_class = ChangeRecordFilter
    pagination_class = CustomPageNumberPagination

    def list(self, request, *args, **kwargs):
        return super().list(request, *args, **kwargs)

    def retrieve(self, request, *args, **kwargs):
        instance = self.get_object()
        serializer = self.get_serializer(instance)
        return WebUtils.response_success(serializer.data)

    @action(methods=["get"], detail=False)
    def enum_data(self, request, *args, **kwargs):
        lan = SettingLanguage(request.user.locale)
        result = dict(OPERATE_TYPE_CHOICES)
        for key in result:
            result[key] = lan.get_val("ChangeRecordType", key) or result[key]
        return WebUtils.response_success(result)
