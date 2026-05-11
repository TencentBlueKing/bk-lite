from django.http import JsonResponse
from django_filters import filters
from django_filters.rest_framework import FilterSet
from rest_framework.decorators import action

from apps.core.decorators.api_permission import HasPermission
from apps.core.utils.viewset_utils import AuthViewSet
from apps.opspilot.models import OCRProvider
from apps.opspilot.serializers.ocr_serializer import OCRProviderSerializer


class ObjFilter(FilterSet):
    name = filters.CharFilter(field_name="name", lookup_expr="icontains")
    enabled = filters.CharFilter(method="filter_enabled")
    vendor = filters.NumberFilter(field_name="vendor_id", lookup_expr="exact")

    @staticmethod
    def filter_enabled(qs, field_name, value):
        """查询类型"""
        if not value:
            return qs
        enabled = value == "1"
        return qs.filter(enabled=enabled)


class OCRProviderViewSet(AuthViewSet):
    queryset = OCRProvider.objects.all()
    serializer_class = OCRProviderSerializer
    permission_key = "provider.ocr_model"
    filterset_class = ObjFilter

    @HasPermission("provide_list-View")
    def list(self, request, *args, **kwargs):
        return super().list(request, *args, **kwargs)

    @HasPermission("provide_list-Add")
    def create(self, request, *args, **kwargs):
        return super().create(request, *args, **kwargs)

    @HasPermission("provide_list-Setting")
    def update(self, request, *args, **kwargs):
        return super().update(request, *args, **kwargs)

    @HasPermission("provide_list-Delete")
    def destroy(self, request, *args, **kwargs):
        return super().destroy(request, *args, **kwargs)

    @action(methods=["GET"], detail=False)
    @HasPermission("provide_list-View")
    def by_vendor(self, request):
        """按供应商查询模型（配置场景，不过滤模型的 team）

        安全控制：验证用户对该供应商有权限（vendor.team 包含用户的 current_team）
        """
        vendor_id = request.query_params.get("vendor")
        if not vendor_id:
            message = self.loader.get("error.vendor_required") if self.loader else "vendor parameter is required"
            return JsonResponse({"result": False, "message": message})

        # 获取用户可见的 team 列表
        current_team = self._parse_current_team_cookie(request)
        if not current_team:
            return self._list(self.get_queryset().none())

        # 过滤：vendor_id + vendor.team 包含用户的 team（安全校验）
        # 不过滤模型自身的 team（配置场景展示所有模型）
        queryset = self.filter_queryset(self.get_queryset()).filter(
            vendor_id=vendor_id,
            vendor__team__contains=current_team,
        )
        return self._list(queryset.order_by(self.ORDERING_FIELD))
