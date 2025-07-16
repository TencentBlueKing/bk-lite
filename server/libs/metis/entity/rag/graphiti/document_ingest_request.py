from typing import List
from pydantic import BaseModel
from langchain_core.documents import Document


class GraphitiRagDocumentIngestRequest(BaseModel):
    openai_api_key: str = ''
    openai_model: str = ''
    openai_api_base: str = ''

    rerank_model_base_url: str = ''
    rerank_model_name: str = ''
    rerank_model_api_key: str = ''

    embed_model_base_url: str = ''
    embed_model_api_key: str = ''
    embed_model_name: str = ''

    group_id: str = ''
    rebuild_community: bool = False

    docs: List[Document]
