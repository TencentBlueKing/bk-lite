from typing import List

from langchain_core.documents import Document

from pydantic import BaseModel


class DocumentIngestRequest(BaseModel):
    embed_model_base_url: str = ''
    embed_model_api_key: str = ''
    embed_model_name: str = ''

    index_name: str
    index_mode: str = ''
    chunk_size: int = 50
    max_chunk_bytes: int = 200000000
    docs: List[Document]
