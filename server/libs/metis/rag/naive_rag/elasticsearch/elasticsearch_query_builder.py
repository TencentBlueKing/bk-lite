from typing import Dict, List, Any

from langchain_openai import OpenAIEmbeddings

from libs.metis.embed.embed_builder import EmbedBuilder
from libs.metis.entity.rag.base.document_ingest_request import DocumentIngestRequest
from libs.metis.entity.rag.base.document_retriever_request import DocumentRetrieverRequest


class ElasticsearchQueryBuilder:
    @staticmethod
    def build_metadata_filter(metadata_filter: Dict) -> List[Dict]:
        filters = []
        for key, value in metadata_filter.items():
            if key.endswith('__exists'):
                filters.append({"exists": {"field": f"metadata.{key[:-8]}"}})
            elif key.endswith('__missing'):
                filters.append(
                    {"bool": {"must_not": {"exists": {"field": f"metadata.{key[:-9]}"}}}})
            elif key.endswith('__range'):
                range_key = key[:-7]
                if isinstance(value, dict) and 'gte' in value and 'lte' in value:
                    filters.append({"range": {f"metadata.{range_key}": {
                                   "gte": value['gte'], "lte": value['lte']}}})
                else:
                    raise ValueError(
                        f"Invalid range filter for key {key}: {value}")
            elif key.endswith('__in'):
                in_key = key[:-4]
                if isinstance(value, list):
                    filters.append({"terms": {f"metadata.{in_key}": value}})
                else:
                    raise ValueError(
                        f"Invalid in filter for key {key}: {value}")
            elif key.endswith('__not_in'):
                not_in_key = key[:-8]
                if isinstance(value, list):
                    filters.append(
                        {"bool": {"must_not": {"terms": {f"metadata.{not_in_key}": value}}}})
                else:
                    raise ValueError(
                        f"Invalid not_in filter for key {key}: {value}")
            elif key.endswith('__like'):
                like_key = key[:-6]
                if isinstance(value, str):
                    filters.append(
                        {"wildcard": {f"metadata.{like_key}": f"*{value}*"}})
                else:
                    raise ValueError(
                        f"Invalid like filter for key {key}: {value}")
            elif key.endswith('__not_like'):
                not_like_key = key[:-10]
                if isinstance(value, str):
                    filters.append(
                        {"bool": {"must_not": {"wildcard": {f"metadata.{not_like_key}": f"*{value}*"}}}})
                else:
                    raise ValueError(
                        f"Invalid not_like filter for key {key}: {value}")
            elif key.endswith('__is_null'):
                is_null_key = key[:-8]
                filters.append(
                    {"bool": {"must_not": {"exists": {"field": f"metadata.{is_null_key}"}}}})
            elif key.endswith('__is_not_null'):
                is_not_null_key = key[:-12]
                filters.append(
                    {"exists": {"field": f"metadata.{is_not_null_key}"}})
            elif key.endswith('__is_empty'):
                is_empty_key = key[:-9]
                filters.append(
                    {"bool": {"must_not": {"exists": {"field": f"metadata.{is_empty_key}"}}}})
            elif key.endswith('__is_not_empty'):
                is_not_empty_key = key[:-14]
                filters.append(
                    {"exists": {"field": f"metadata.{is_not_empty_key}"}})
            elif isinstance(value, (str, bool, int, float)):
                field_name = f"metadata.{key}"
                if isinstance(value, str):
                    field_name += ".keyword"
                filters.append({"term": {field_name: value}})
            else:
                raise ValueError(
                    f"Unsupported metadata filter type for key {key}: {type(value)}")
        return filters

    @staticmethod
    def build_text_query(req: DocumentIngestRequest) -> Dict:
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
    def build_vector_query(req: DocumentRetrieverRequest) -> Dict:
        if not req.enable_vector_search:
            return {}

        embedding = EmbedBuilder.get_embed(req.embed_model_base_url,
                                           req.embed_model_name,
                                           req.embed_model_api_key,
                                           req.embed_model_base_url)
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
    def _get_vector(req: DocumentRetrieverRequest, embedding: OpenAIEmbeddings) -> List[float]:
        return embedding.embed_query(req.search_query)

    @staticmethod
    def build_query(req: DocumentRetrieverRequest, size: int = None) -> Dict[str, Any]:
        query = {"size": size if size is not None else req.size}

        text_query = ElasticsearchQueryBuilder.build_text_query(req)
        if text_query:
            query["query"] = text_query

        vector_query = ElasticsearchQueryBuilder.build_vector_query(req)
        if vector_query:
            query.update(vector_query)

        return query
