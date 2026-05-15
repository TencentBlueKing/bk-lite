from typing import Any

from django.db import models
from django.http import JsonResponse
from rest_framework.decorators import action

from apps.core.decorators.api_permission import HasPermission
from apps.core.utils.viewset_utils import AuthViewSet
from apps.opspilot.models import EmbedProvider, LLMModel, OCRProvider, RerankProvider
from apps.opspilot.models.model_provider_mgmt import ModelVendor
from apps.opspilot.serializers.model_vendor_serializer import ModelVendorSerializer, ModelVendorTestConnectionSerializer
from apps.opspilot.services.model_vendor_sync_service import ModelVendorSyncService


class ModelVendorViewSet(AuthViewSet):
    """ModelVendor 视图集，继承 AuthViewSet 获得 current_team 权限验证"""

    serializer_class = ModelVendorSerializer
    queryset = ModelVendor.objects.all()
    ordering = ("-id",)
    search_fields = ("name", "vendor_type")
    ORGANIZATION_FIELD = "team"  # ModelVendor.team 是 JSONField (list)

    @HasPermission("provide_list-View")
    def list(self, request, *args, **kwargs):
        """重写 list 方法，添加 model_count 统计"""
        # 调用父类的 list 获取权限过滤后的 queryset
        queryset = self.filter_queryset(self.get_queryset())
        filtered_queryset = self.get_queryset_by_permission(request, queryset)

        serializer = self.get_serializer(filtered_queryset.order_by(self.ORDERING_FIELD), many=True)
        return_data = serializer.data

        # 统计每个 vendor 的 model 数量
        vendor_counts = {}
        for provider_model_class in (LLMModel, EmbedProvider, OCRProvider, RerankProvider):
            provider_counts = dict(
                provider_model_class.objects.filter(enabled=True)
                .values("vendor_id")
                .annotate(count=models.Count("id"))
                .values_list("vendor_id", "count")
            )
            for vendor_id, provider_count in provider_counts.items():
                vendor_counts[vendor_id] = vendor_counts.get(vendor_id, 0) + provider_count

        for item in return_data:
            item["model_count"] = vendor_counts.get(item["id"], 0)

        return JsonResponse({"result": True, "data": return_data})

    @HasPermission("provide_list-Add")
    def create(self, request, *args, **kwargs):
        return super().create(request, *args, **kwargs)

    @HasPermission("provide_list-Setting")
    def update(self, request, *args, **kwargs):
        return super().update(request, *args, **kwargs)

    @HasPermission("provide_list-Delete")
    def destroy(self, request, *args, **kwargs):
        return super().destroy(request, *args, **kwargs)

    @action(methods=["POST"], detail=False)
    @HasPermission("provide_list-Add")
    def test_connection(self, request):
        serializer = ModelVendorTestConnectionSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        raw_validated_data = serializer.validated_data
        validated_data: dict[str, Any] = raw_validated_data if isinstance(raw_validated_data, dict) else {}
        api_base = validated_data.get("api_base") or ""
        resolved_api_key = validated_data.get("resolved_api_key") or ""
        protocol_type = validated_data.get("protocol_type") or "openai"
        vendor_type = validated_data.get("vendor_type") or ""
        locale = getattr(request.user, "locale", "en") or "en"
        try:
            # 测试连接策略：
            # - anthropic vendor type + anthropic protocol: 使用 Anthropic API 验证
            # - deepseek/other + anthropic protocol: 使用 Anthropic 协议验证（但用 deepseek 模型）
            # - 其他情况: 使用 OpenAI /models 端点验证
            if protocol_type == "anthropic":
                if vendor_type == "anthropic":
                    # 真正的 Anthropic 供应商，使用 Claude 模型验证
                    ModelVendorSyncService.test_anthropic_connection(api_base, resolved_api_key, locale=locale)
                else:
                    # DeepSeek/other 使用 Anthropic 协议，用 deepseek-chat 模型验证
                    test_model = "deepseek-chat" if vendor_type == "deepseek" else "deepseek-chat"
                    ModelVendorSyncService.test_anthropic_connection(api_base, resolved_api_key, model=test_model, locale=locale)
            else:
                ModelVendorSyncService.fetch_models_with_credentials(api_base, resolved_api_key, protocol_type=protocol_type, locale=locale)
        except Exception as error:
            return JsonResponse({"result": False, "message": str(error)})
        return JsonResponse({"result": True})

    @action(methods=["POST"], detail=True)
    @HasPermission("provide_list-Setting")
    def sync_models(self, request, pk=None):
        vendor = self.get_object()
        locale = getattr(request.user, "locale", "en") or "en"
        try:
            ModelVendorSyncService.sync_vendor_models(vendor, locale=locale)
        except ValueError as error:
            return JsonResponse({"result": False, "message": str(error)})
        except Exception as error:
            return JsonResponse({"result": False, "message": str(error)})
        return JsonResponse({"result": True})
