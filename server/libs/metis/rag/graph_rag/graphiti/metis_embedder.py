from graphiti_core.embedder.client import EmbedderClient
from libs.metis.embed.embed_builder import EmbedBuilder
from libs.metis.rag.graph_rag.graphiti.metis_embedder_config import MetisEmbedderConfig


class MetisEmbedder(EmbedderClient):
    def __init__(self, config: MetisEmbedderConfig):
        self.embed = EmbedBuilder.get_embed(
            config.url, config.model_name,
            config.api_key, config.url)

    async def create(
        self, input_data: str
    ) -> list[float]:
        return self.embed.embed_documents(input_data)[0]

    async def create_batch(self, input_data_list: list[str]) -> list[list[float]]:
        return self.embed.embed_documents(input_data_list)
