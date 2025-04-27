from typing import Dict, List, Any

from langchain_openai import OpenAIEmbeddings

from src.rag.native_rag.entity.elasticsearch_retriever_request import ElasticSearchRetrieverRequest


class ElasticsearchQueryBuilder:
    @staticmethod
    def build_metadata_filter(metadata_filter: Dict) -> List[Dict]:
        filters = []
        for key, value in metadata_filter.items():
            if isinstance(value, (str, bool, int, float)):
                field_name = f"metadata.{key}"
                if isinstance(value, str):
                    field_name += ".keyword"
                filters.append({"term": {field_name: value}})
            else:
                raise ValueError(f"Unsupported metadata filter type for key {key}: {type(value)}")
        return filters

    @staticmethod
    def build_text_query(req: ElasticSearchRetrieverRequest) -> Dict:
        if not req.enable_term_search:
            return {}

        return {
            "bool": {
                "must": [{
                    "bool": {
                        "should": [
                            {
                                req.text_search_mode: {
                                    "metadata.knowledge_title": {
                                        "query": req.search_query,
                                        "boost": 2.0
                                    }
                                }
                            },
                            {
                                req.text_search_mode: {
                                    "text": {
                                        "query": req.search_query,
                                        "boost": 1.0
                                    }
                                }
                            }
                        ]
                    }
                }],
                "filter": ElasticsearchQueryBuilder.build_metadata_filter(req.metadata_filter),
                "boost": req.text_search_weight,
            }
        }

    @staticmethod
    def build_vector_query(req: ElasticSearchRetrieverRequest) -> Dict:
        if not req.enable_vector_search:
            return {}

        embedding = OpenAIEmbeddings(
            model=req.embed_model_name,
            api_key=req.embed_model_api_key,
            base_url=req.embed_model_base_url,
        )
        vector = ElasticsearchQueryBuilder._get_vector(req, embedding)

        return {
            "knn": {
                "field": "vector",
                "query_vector": vector,
                "k": req.rag_k,
                "filter": ElasticsearchQueryBuilder.build_metadata_filter(req.metadata_filter),
                "num_candidates": req.rag_num_candidates,
                "boost": req.vector_search_weight,
            }
        }

    @staticmethod
    def _get_vector(req: ElasticSearchRetrieverRequest, embedding: OpenAIEmbeddings) -> List[float]:
        return embedding.embed_query(req.search_query)

    @staticmethod
    def build_query(req: ElasticSearchRetrieverRequest, size: int = None) -> Dict[str, Any]:
        query = {"size": size if size is not None else req.size}

        text_query = ElasticsearchQueryBuilder.build_text_query(req)
        if text_query:
            query["query"] = text_query

        vector_query = ElasticsearchQueryBuilder.build_vector_query(req)
        if vector_query:
            query.update(vector_query)

        return query
