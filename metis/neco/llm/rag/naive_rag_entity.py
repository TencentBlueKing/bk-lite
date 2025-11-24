from pydantic import BaseModel, Field
from typing import List, Literal, Optional
from langchain_core.documents import Document
from neco.llm.rag.graph_rag_entity import DocumentRetrieverRequest as GraphitiDocumentRetrieverRequest

class DocumentCountRequest(BaseModel):
    index_name: str
    metadata_filter: dict = {}
    query: str
    
class DocumentDeleteRequest(BaseModel):
    chunk_ids: list[str]
    knowledge_ids: list[str]
    keep_qa: bool
    
class DocumentIngestRequest(BaseModel):
    embed_model_base_url: str = ''
    embed_model_api_key: str = ''
    embed_model_name: str = ''

    index_name: str
    index_mode: str = ''
    chunk_size: int = 50
    max_chunk_bytes: int = 200000000
    docs: List[Document]

class DocumentListRequest(BaseModel):
    index_name: str
    page: int
    size: int
    metadata_filter: dict
    query: str
    sort_field: Optional[str] = Field(
        default="created_time", description="排序字段，默认为创建时间")
    sort_order: Optional[str] = Field(
        default="desc", description="排序方式，支持asc/desc，默认为desc")

class DocumentMetadataUpdateRequest(BaseModel):
    knowledge_ids: list[str] = []
    chunk_ids: list[str] = []
    metadata: dict = {}    


class DocumentRetrieverRequest(BaseModel):
    """文档检索请求参数

    支持pgvector的两种搜索模式：
    1. mmr: 最大边际相关性搜索（兼顾相关性和多样性）
    2. similarity_score_threshold: 混合搜索（结合向量搜索和全文搜索，使用RRF合并）
    """

    # 基础参数
    index_name: str
    search_query: str = ''
    metadata_filter: Optional[dict] = {}

    # 核心搜索参数
    k: int = Field(default=5, ge=1, le=100, description="返回的文档数量")
    search_type: Literal["mmr", "similarity_score_threshold"] = Field(
        default="similarity_score_threshold",
        description="搜索类型：mmr(最大边际相关性)、similarity_score_threshold(混合搜索)"
    )

    # 相似度阈值搜索参数（仅在search_type为similarity_score_threshold时必需）
    score_threshold: Optional[float] = Field(
        default=0.7,
        ge=0.0,
        le=1.0,
        description="相似度阈值，在混合搜索中用于过滤向量搜索结果"
    )

    # MMR搜索参数（仅在search_type为mmr时使用）
    fetch_k: Optional[int] = Field(
        default=None,
        ge=1,
        description="MMR算法候选文档数量，默认为k的3倍，仅在mmr模式下使用"
    )
    lambda_mult: float = Field(
        default=1,
        ge=0.0,
        le=1.0,
        description="MMR多样性参数：0=最大多样性，1=最大相关性，仅在mmr模式下使用"
    )

    # Embedding模型配置
    embed_model_base_url: Optional[str] = ''
    embed_model_api_key: Optional[str] = ''
    embed_model_name: str = ''

    # 重排序配置
    enable_rerank: bool = False
    rerank_model_base_url: Optional[str] = ''
    rerank_model_api_key: Optional[str] = ''
    rerank_model_name: Optional[str] = ''
    rerank_top_k: int = Field(default=5, ge=1, description="重排序后返回的文档数量")

    # 召回模式
    rag_recall_mode: str = "chunk"

    # RAG类型配置
    enable_naive_rag: bool = True
    enable_qa_rag: bool = False
    qa_size: int = Field(default=10, ge=1, description="QA RAG返回数量")

    # 图RAG配置
    enable_graph_rag: bool = False
    graph_rag_request: Optional[GraphitiDocumentRetrieverRequest] = None

    def get_effective_fetch_k(self) -> int:
        """获取有效的fetch_k值"""
        if self.search_type == "mmr":
            return self.fetch_k if self.fetch_k is not None else max(20, self.k * 3)
        return self.k

    def validate_search_params(self) -> bool:
        """验证搜索参数的有效性"""
        if self.search_type == "similarity_score_threshold" and self.score_threshold is None:
            raise ValueError(
                "search_type为similarity_score_threshold时，score_threshold不能为None")

        if self.search_type == "mmr" and self.fetch_k is not None and self.fetch_k < self.k:
            raise ValueError("MMR搜索中，fetch_k不能小于k")

        return True
    
class IndexDeleteRequest(BaseModel):
    index_name: str
    