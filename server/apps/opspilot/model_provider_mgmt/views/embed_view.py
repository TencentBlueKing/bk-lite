from django.http import JsonResponse
from rest_framework import viewsets
from rest_framework.decorators import action

from apps.core.utils.viewset_utils import AuthViewSet
from apps.opspilot.model_provider_mgmt.serializers.embed_serializer import EmbedProviderSerializer
from apps.opspilot.model_provider_mgmt.services.remote_embeddings import RemoteEmbeddings
from apps.opspilot.models import EmbedProvider


class EmbedProviderViewSet(AuthViewSet):
    serializer_class = EmbedProviderSerializer
    queryset = EmbedProvider.objects.all()
    search_fields = ["name"]
    permission_key = "provider.embed_model"

    def list(self, request, *args, **kwargs):
        queryset = self.filter_queryset(self.get_queryset())
        return self.query_by_groups(request, queryset)


class EmbedViewSet(viewsets.ViewSet):
    @action(methods=["post"], detail=False)
    def embed_content(self, request):
        embed_model_id = request.data.get("embed_model_id")
        content = request.data.get("content")
        embed_provider = EmbedProvider.objects.get(id=embed_model_id)
        embedding_service = RemoteEmbeddings(embed_provider)
        result = embedding_service.embed_query(content)
        return JsonResponse({"embedding": result})
