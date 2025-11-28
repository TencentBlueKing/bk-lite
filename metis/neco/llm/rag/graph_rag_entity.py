from pydantic import BaseModel, Field
from typing import List, Literal, Optional
from langchain_core.documents import Document

class DocumentRetrieverRequest(BaseModel):
    embed_model_base_url: str = ''
    embed_model_api_key: Optional[str] = ''
    embed_model_name: Optional[str] = ''

    rerank_model_base_url: Optional[str] = ''
    rerank_model_api_key: Optional[str] = ''
    rerank_model_name: Optional[str] = ''

    size: Optional[int] = 100
    group_ids: Optional[List[str]] = []

    search_query: str = ''

class DocumentDeleteRequest(BaseModel):
    uuids: List[str] = []
    
class DocumentIngestRequest(BaseModel):
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

class DocumentListRequest(BaseModel):
    group_id: str
     
class IndexDeleteRequest(BaseModel):
    group_id: str
     
class RebuildCommunityRequest(BaseModel):
    group_ids: List[str] = []
    openai_api_key: str = ""
    openai_api_base: str = ""
    openai_model: str = ""
    embed_model_base_url: str = ""
    embed_model_name: str = ""
    embed_model_api_key: str = ""
    rerank_model_base_url: str = ""
    rerank_model_name: str = ""
    rerank_model_api_key: str = ""
     