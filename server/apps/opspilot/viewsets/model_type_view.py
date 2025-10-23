from django.db import models
from django.http import JsonResponse
from rest_framework.decorators import action

from apps.core.utils.viewset_utils import GenericViewSetFun, LanguageViewSet
from apps.opspilot.models import EmbedProvider, LLMModel, ModelType, OCRProvider, RerankProvider
from apps.opspilot.serializers.model_type_serializer import ModelTypeSerializer


class ModelTypeViewSet(LanguageViewSet, GenericViewSetFun):
    serializer_class = ModelTypeSerializer
    queryset = ModelType.objects.all()
    ordering = ("index",)
    search_fields = ("name", "display_name")

    def list(self, request, *args, **kwargs):
        provider_type = request.query_params.get("provider_type", "")
        queryset = self.filter_queryset(self.get_queryset())
        queryset = queryset.filter(tags__contains=provider_type)
        serializer = self.get_serializer(queryset, many=True)
        return_data = serializer.data
        provider_model_map = {
            "llm": LLMModel,
            "embed": EmbedProvider,
            "ocr": OCRProvider,
            "rerank": RerankProvider,
        }
        if provider_type in provider_model_map:
            provider_model_class = provider_model_map.get(provider_type, LLMModel)
            # 统计每个 model_type 的数量
            queryset = provider_model_class.objects.all()
            permission_key = f"provider.{provider_type}_model"
            model_queryset = self.get_queryset_by_permission(request, queryset, permission_key)
            model_type_counts = model_queryset.values("model_type_id").annotate(count=models.Count("id")).values_list("model_type_id", "count")
            model_type_count_dict = dict(model_type_counts)
            # 在序列化数据中添加统计信息
            for item in return_data:
                item["model_count"] = model_type_count_dict.get(item["id"], 0)

        return JsonResponse({"result": True, "data": return_data})

    def update(self, request, *args, **kwargs):
        instance = self.get_object()
        if instance.is_build_in:
            message = self.loader.get("builtin_model_types_no_modify") if self.loader else "Built-in model types cannot be modified"
            return JsonResponse(
                {
                    "result": False,
                    "message": message,
                }
            )
        return super().update(request, *args, **kwargs)

    def destroy(self, request, *args, **kwargs):
        instance = self.get_object()
        if instance.is_build_in:
            message = self.loader.get("builtin_model_types_no_delete") if self.loader else "Built-in model types cannot be deleted"
            return JsonResponse(
                {
                    "result": False,
                    "message": message,
                }
            )
        return super().destroy(request, *args, **kwargs)

    @action(methods=["POST"], detail=False)
    def change_index(self, request):
        params = request.data
        new_index = params["index"]
        obj = ModelType.objects.get(id=params["id"])
        old_index = obj.index
        if old_index == new_index:
            return JsonResponse({"result": True})
        if old_index < new_index:
            ModelType.objects.filter(index__gt=old_index, index__lte=new_index).update(index=models.F("index") - 1)
        else:
            ModelType.objects.filter(index__gte=new_index, index__lt=old_index).update(index=models.F("index") + 1)
        obj.index = new_index
        obj.save()

        return JsonResponse({"result": True})
