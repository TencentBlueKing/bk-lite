"""全局扫描设置视图"""

from rest_framework import status
from rest_framework.decorators import action
from rest_framework.response import Response

from apps.core.decorators.api_permission import HasPermission
from apps.core.utils.viewset_utils import AuthViewSet
from apps.patch_mgmt.models import ScanSetting
from apps.patch_mgmt.serializers.scan_setting import ScanSettingSerializer


class ScanSettingViewSet(AuthViewSet):
    """全局扫描设置视图集（单例资源）"""

    queryset = ScanSetting.objects.all()
    serializer_class = ScanSettingSerializer
    permission_key = "patch_source"

    def get_object(self):
        return ScanSetting.get_singleton()

    @HasPermission("patch_source-View")
    def list(self, request, *args, **kwargs):
        """返回当前全局扫描设置（单例）"""
        instance = self.get_object()
        serializer = self.get_serializer(instance)
        return Response(serializer.data)

    @action(detail=False, methods=["put", "patch"], url_path="save")
    @HasPermission("patch_source-Edit")
    def save_settings(self, request):
        """保存全局扫描设置（单例，无需传 id）"""
        instance = self.get_object()
        serializer = self.get_serializer(
            instance, data=request.data, partial=request.method == "PATCH"
        )
        serializer.is_valid(raise_exception=True)
        serializer.save()
        return Response(serializer.data)

    @HasPermission("patch_source-View")
    def retrieve(self, request, *args, **kwargs):
        """获取全局扫描设置详情"""
        instance = self.get_object()
        serializer = self.get_serializer(instance)
        return Response(serializer.data)
