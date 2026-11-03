"""全局扫描设置视图"""

import json

from rest_framework import status
from rest_framework.decorators import action
from rest_framework.exceptions import MethodNotAllowed
from rest_framework.parsers import FormParser, JSONParser, MultiPartParser
from rest_framework.response import Response

from apps.core.decorators.api_permission import HasPermission
from apps.core.utils.viewset_utils import AuthViewSet
from apps.patch_mgmt.models import ScanSetting
from apps.patch_mgmt.serializers.scan_setting import ScanSettingSerializer
from apps.patch_mgmt.services.notification_config import load_notification_candidates


class ScanSettingViewSet(AuthViewSet):
    """全局扫描设置视图集（单例资源）"""

    queryset = ScanSetting.objects.all()
    serializer_class = ScanSettingSerializer
    permission_key = "patch_scan_setting"

    def create(self, request, *args, **kwargs):
        raise MethodNotAllowed(request.method)

    def update(self, request, *args, **kwargs):
        raise MethodNotAllowed(request.method)

    def partial_update(self, request, *args, **kwargs):
        raise MethodNotAllowed(request.method)

    def destroy(self, request, *args, **kwargs):
        raise MethodNotAllowed(request.method)

    def get_object(self):
        return ScanSetting.get_singleton()

    @HasPermission("patch_scan_setting-View")
    def list(self, request, *args, **kwargs):
        """返回当前全局扫描设置（单例）"""
        instance = self.get_object()
        serializer = self.get_serializer(instance)
        return Response(serializer.data)

    @action(
        detail=False,
        methods=["put", "patch"],
        url_path="save",
        parser_classes=[JSONParser, MultiPartParser, FormParser],
    )
    @HasPermission("patch_scan_setting-Edit")
    def save_settings(self, request):
        """保存全局扫描设置。新的离线目录和其余设置在同一次请求里提交。"""
        instance = self.get_object()
        try:
            payload, uploaded = _save_payload(request)
        except ValueError as exc:
            return Response({"payload": [str(exc)]}, status=status.HTTP_400_BAD_REQUEST)
        context = self.get_serializer_context()
        context["offline_catalog_upload"] = uploaded
        serializer = self.get_serializer(
            instance,
            data=payload,
            partial=request.method == "PATCH",
            context=context,
        )
        serializer.is_valid(raise_exception=True)
        serializer.save()
        return Response(serializer.data)

    @HasPermission("patch_scan_setting-View")
    def retrieve(self, request, *args, **kwargs):
        """获取全局扫描设置详情"""
        instance = self.get_object()
        serializer = self.get_serializer(instance)
        return Response(serializer.data)

    @action(detail=False, methods=["get"], url_path="notification_candidates")
    @HasPermission("patch_scan_setting-View")
    def notification_candidates(self, request):
        """返回当前用户在当前组织可选的通知渠道和接收人。"""
        candidates = load_notification_candidates(request)
        return Response(
            {
                "channels": candidates["channels"],
                "users": candidates["users"],
            }
        )


def _save_payload(request):
    """没带文件时沿用 JSON 设置；带了文件时，设置放在 payload 里和文件一起提交。"""
    uploaded = request.FILES.get("file")
    if not uploaded:
        return request.data, None
    raw = request.data.get("payload")
    if not isinstance(raw, str) or not raw.strip():
        raise ValueError("保存内容缺失")
    try:
        payload = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise ValueError("保存内容不是有效的 JSON") from exc
    if not isinstance(payload, dict):
        raise ValueError("保存内容不是有效的 JSON")
    return payload, uploaded
