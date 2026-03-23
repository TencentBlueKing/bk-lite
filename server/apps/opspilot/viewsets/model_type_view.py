from django.db import models
from django.http import JsonResponse
from rest_framework.decorators import action

from apps.core.utils.viewset_utils import GenericViewSetFun, LanguageViewSet
from apps.opspilot.models import EmbedProvider, LLMModel, OCRProvider, RerankProvider
from apps.opspilot.models.model_provider_mgmt import ModelVendor
from apps.opspilot.serializers.model_type_serializer import ModelVendorSerializer


class ModelVendorViewSet(LanguageViewSet, GenericViewSetFun):
    serializer_class = ModelVendorSerializer
    queryset = ModelVendor.objects.all()
    ordering = ("index",)
    search_fields = ("name", "vendor_type")

    def list(self, request, *args, **kwargs):
        provider_type = request.query_params.get("provider_type", "")
        queryset = self.filter_queryset(self.get_queryset())
        serializer = self.get_serializer(queryset, many=True)
        return_data = serializer.data
        provider_model_map = {
            "llm": LLMModel,
            "embed": EmbedProvider,
            "ocr": OCRProvider,
            "rerank": RerankProvider,
        }
        if provider_type in provider_model_map:
            provider_model_class = provider_model_map[provider_type]
            model_queryset = self.get_queryset_by_permission(request, provider_model_class.objects.all(), f"provider.{provider_type}_model")
            vendor_counts = dict(model_queryset.values("vendor_id").annotate(count=models.Count("id")).values_list("vendor_id", "count"))
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
    def change_index(self, request):
        params = request.data
        new_index = params["index"]
        obj = ModelVendor.objects.get(id=params["id"])
        old_index = obj.index
        if old_index == new_index:
            return JsonResponse({"result": True})
        if old_index < new_index:
            ModelVendor.objects.filter(index__gt=old_index, index__lte=new_index).update(index=models.F("index") - 1)
        else:
            ModelVendor.objects.filter(index__gte=new_index, index__lt=old_index).update(index=models.F("index") + 1)
        obj.index = new_index
        obj.save(update_fields=["index"])
        return JsonResponse({"result": True})
