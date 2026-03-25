from typing import Any

from django.db import models
from django.http import JsonResponse
from rest_framework.decorators import action

from apps.core.utils.viewset_utils import GenericViewSetFun, LanguageViewSet
from apps.opspilot.models import EmbedProvider, LLMModel, OCRProvider, RerankProvider
from apps.opspilot.models.model_provider_mgmt import ModelVendor
from apps.opspilot.serializers.model_vendor_serializer import ModelVendorSerializer, ModelVendorTestConnectionSerializer
from apps.opspilot.services.model_vendor_sync_service import ModelVendorSyncService


class ModelVendorViewSet(LanguageViewSet, GenericViewSetFun):
    serializer_class = ModelVendorSerializer
    queryset = ModelVendor.objects.all()
    ordering = ("-id",)
    search_fields = ("name", "vendor_type")

    def list(self, request, *args, **kwargs):
        queryset = self.filter_queryset(self.get_queryset())
        serializer = self.get_serializer(queryset, many=True)
        return_data = serializer.data
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

    def update(self, request, *args, **kwargs):
        instance = self.get_object()
        if instance.is_build_in:
            message = self.loader.get("error.builtin_model_types_no_modify") if self.loader else "Built-in vendors cannot be modified"
            return JsonResponse({"result": False, "message": message})
        return super().update(request, *args, **kwargs)

    def destroy(self, request, *args, **kwargs):
        instance = self.get_object()
        if instance.is_build_in:
            message = self.loader.get("error.builtin_model_types_no_delete") if self.loader else "Built-in vendors cannot be deleted"
            return JsonResponse({"result": False, "message": message})
        return super().destroy(request, *args, **kwargs)

    @action(methods=["POST"], detail=False)
    def test_connection(self, request):
        serializer = ModelVendorTestConnectionSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        raw_validated_data = serializer.validated_data
        validated_data: dict[str, Any] = raw_validated_data if isinstance(raw_validated_data, dict) else {}
        api_base = validated_data.get("api_base") or ""
        resolved_api_key = validated_data.get("resolved_api_key") or ""
        locale = getattr(request.user, "locale", "en") or "en"
        try:
            ModelVendorSyncService.fetch_models_with_credentials(api_base, resolved_api_key, locale=locale)
        except Exception as error:
            return JsonResponse({"result": False, "message": str(error)})
        return JsonResponse({"result": True})

    @action(methods=["POST"], detail=True)
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
