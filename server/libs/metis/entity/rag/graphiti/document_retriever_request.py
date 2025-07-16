from typing import List
from pydantic import BaseModel


class DocumentRetrieverRequest(BaseModel):
    embed_model_base_url: str = ''
    embed_model_api_key: str = ''
    embed_model_name: str = ''

    rerank_model_base_url: str = ''
    rerank_model_api_key: str = ''
    rerank_model_name: str = ''

    size: int = 100
    group_ids: List[str] = []

    search_query: str = ''
