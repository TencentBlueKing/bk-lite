import requests
from libs.graphiti_core.cross_encoder.client import CrossEncoderClient
from libs.metis.rag.graph_rag.graphiti.metis_raranker_config import MetisRerankerConfig
from libs.metis.rerank.rerank_manager import ReRankManager


class MetisRerankerClient(CrossEncoderClient):
    def __init__(self, config: MetisRerankerConfig):
        self.config = config

    async def rank(self, query: str, passages: list[str]) -> list[tuple[str, float]]:
        if self.config.url.startswith("local:"):
            return ReRankManager.rerank(self.config.url, query=query, docs=passages)
        else:
            headers = {
                "accept": "application/json", "Content-Type": "application/json",
                "Authorization": f"Bearer {self.config.api_key}"
            }

            data = {
                "model": self.config.model_name,
                "query": query,
                "documents": passages,
            }
            response = requests.post(
                self.config.url, headers=headers, json=data, timeout=10)
            response.raise_for_status()

            rerank_api_result = response.json()

            rerank_result_items = rerank_api_result['results']
            return rerank_result_items
