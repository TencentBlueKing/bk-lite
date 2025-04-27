from django.http import JsonResponse
from langchain_core.documents import Document
from rest_framework import viewsets
from rest_framework.decorators import action

from apps.core.utils.viewset_utils import AuthViewSet
from apps.opspilot.model_provider_mgmt.serializers.rerank_serializer import RerankProviderSerializer
from apps.opspilot.model_provider_mgmt.services.rerank_service import RerankService
from apps.opspilot.models import RerankProvider


class RerankViewSet(viewsets.ViewSet):
    @action(methods=["post"], detail=False)
    def rerank_sentences(self, request):
        rerank_id = request.data.get("rerank_id")
        top_k = request.data.get("top_k")
        sentences = request.data.get("sentences")
        query = request.data.get("query")

        reranker = RerankProvider.objects.get(id=rerank_id)

        rerank_service = RerankService()
        docs = []
        for sentence in sentences:
            docs.append(Document(page_content=sentence))
        results = rerank_service.execute(reranker, docs, query, top_k)
        response = []
        for result in results:
            response.append({"content": result.page_content, "relevance_score": result.metadata["relevance_score"]})
        return JsonResponse({"rerank_result": response})


class RerankProviderViewSet(AuthViewSet):
    queryset = RerankProvider.objects.all()
    serializer_class = RerankProviderSerializer
    permission_key = "provider.rerank_model"
