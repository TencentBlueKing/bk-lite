from pydantic import BaseModel


class ElasticSearchRetrieverRequest(BaseModel):
    index_name: str
    search_query: str = ''
    metadata_filter: dict = {}
    size: int = 100
    threshold: float = 0.7
    enable_term_search: bool = True

    text_search_weight: float = 0.9
    text_search_mode: str = 'match'

    enable_vector_search: bool = True
    vector_search_weight: float = 0.1

    rag_k: int = 10
    rag_num_candidates: int = 1000
    enable_rerank: bool = False

    embed_model_base_url: str = ''
    embed_model_api_key: str = ''
    embed_model_name: str = ''

    rerank_model_base_url: str = ''
    rerank_model_api_key: str = ''
    rerank_model_name: str = ''
    rerank_top_k: int = 5
