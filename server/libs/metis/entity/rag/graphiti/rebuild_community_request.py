from typing import List
from pydantic import BaseModel


class RebuildCommunityRequest(BaseModel):
    group_ids: List[str] = []
    openai_api_key: str = ""
    openai_api_base: str = ""
    embed_model_base_url: str = ""
    embed_model_name: str = ""
    embed_model_api_key: str = ""
    rerank_model_base_url: str = ""
    rerank_model_name: str = ""
    rerank_model_api_key: str = ""
