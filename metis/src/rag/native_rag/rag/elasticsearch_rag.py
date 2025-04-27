import os
from typing import List

import requests
from langchain_core.documents import Document
from langchain_elasticsearch import ElasticsearchRetriever
from langchain_openai import OpenAIEmbeddings

from src.embed.embed_builder import EmbedBuilder
from src.rag.native_rag.entity.elasticsearch_document_count_request import ElasticSearchDocumentCountRequest
from src.rag.native_rag.entity.elasticsearch_document_delete_request import ElasticSearchDocumentDeleteRequest
from src.rag.native_rag.entity.elasticsearch_document_list_request import ElasticSearchDocumentListRequest
from src.rag.native_rag.entity.elasticsearch_document_metadata_update_request import \
    ElasticsearchDocumentMetadataUpdateRequest
from src.rag.native_rag.entity.elasticsearch_index_delete_request import ElasticSearchIndexDeleteRequest
from src.rag.native_rag.entity.elasticsearch_retriever_request import ElasticSearchRetrieverRequest
from src.rag.native_rag.entity.elasticsearch_store_request import ElasticSearchStoreRequest
from src.rag.native_rag.utils.elasticsearch_query_builder import ElasticsearchQueryBuilder
from langchain_elasticsearch import ElasticsearchStore
import elasticsearch


class ElasticSearchRag:
    def __init__(self):
        self.es = elasticsearch.Elasticsearch(hosts=[os.getenv('ELASTICSEARCH_URL')],
                                              basic_auth=("elastic", os.getenv('ELASTICSEARCH_PASSWORD')))

    def update_metadata(self, req: ElasticsearchDocumentMetadataUpdateRequest):
        """
        根据过滤条件更新文档的元数据

        Args:
            req: 包含索引名称、元数据过滤条件和新元数据的请求对象

        Returns:
            更新的文档数量
        """
        # 构建过滤条件
        metadata_filter = []
        for key, value in req.metadata_filter.items():
            # 检查值是否为逗号分隔的字符串
            if isinstance(value, str) and ',' in value:
                # 按逗号分割并去除空白
                values = [v.strip() for v in value.split(',')]
                metadata_filter.append(
                    {"terms": {f"metadata.{key}.keyword": values}}
                )
            else:
                metadata_filter.append(
                    {"term": {f"metadata.{key}.keyword": value}}
                )

        # 构建查询
        query = {
            "query": {
                "bool": {
                    "filter": metadata_filter
                }
            }
        }

        # 构建更新脚本
        script_parts = []
        for key, value in req.metadata.items():
            script_parts.append(f'ctx._source.metadata.{key} = params.{key}')

        update_script = {
            "script": {
                "source": "; ".join(script_parts),
                "params": req.metadata
            }
        }

        # 执行更新
        result = self.es.update_by_query(
            index=req.index_name,
            body={**query, **update_script}
        )
        self.es.indices.refresh(index=req.index_name)


    def count_index_document(self, req: ElasticSearchDocumentCountRequest):
        if not req.metadata_filter:
            # Count all documents in the index
            count = self.es.count(index=req.index_name)
            return count['count']

        # Build filter query for specific metadata
        metadata_filter = []
        for key, value in req.metadata_filter.items():
            metadata_filter.append(
                {"term": {f"metadata.{key}.keyword": value}})

        # Build the query with metadata filter
        query = {
            "query": {
                "bool": {
                    "filter": metadata_filter
                }
            }
        }

        # Add match_phrase query if req.query is not empty
        if req.query:
            if not query["query"]["bool"].get("must"):
                query["query"]["bool"]["must"] = []
                query["query"]["bool"]["must"].append({
                    "match_phrase": {
                        "text": req.query
                    }
                })

        count = self.es.count(index=req.index_name, body=query)
        return count['count']

    def delete_index(self, req: ElasticSearchIndexDeleteRequest):
        self.es.indices.delete(index=req.index_name)

    def list_index_document(self, req: ElasticSearchDocumentListRequest):
        # Build filter query for specific metadata
        metadata_filter = []
        for key, value in req.metadata_filter.items():
            metadata_filter.append(
                {"term": {f"metadata.{key}.keyword": value}}
            )

        # Calculate offset from page and size
        offset = (req.page - 1) * req.size if req.page > 0 else 0

        # Build the query
        query = {
            "query": {
                "bool": {
                    "filter": metadata_filter
                }
            },
            "from": offset,
            "size": req.size,
            "_source": {"excludes": ["vector"]}  # Exclude the vector field
        }

        # Add match_phrase query if req.query is not empty
        if req.query:
            if not query["query"]["bool"].get("must"):
                query["query"]["bool"]["must"] = []
                query["query"]["bool"]["must"].append({
                    "match_phrase": {
                        "text": req.query
                    }
                })

        # Execute the search query
        response = self.es.search(index=req.index_name, body=query)

        # Process and return the results
        documents = []
        for hit in response['hits']['hits']:
            source = hit['_source']
            metadata = source.get('metadata', {})
            documents.append(
                Document(page_content=source['text'], metadata=metadata))

        return documents

    def delete_document(self, req: ElasticSearchDocumentDeleteRequest):
        metadata_filter = []
        for key, value in req.metadata_filter.items():
            # Check if the value is a comma-separated string
            if isinstance(value, str) and ',' in value:
                # Split the value by comma and strip whitespace
                values = [v.strip() for v in value.split(',')]
                metadata_filter.append(
                    {"terms": {f"metadata.{key}.keyword": values}}
                )
            else:
                metadata_filter.append(
                    {"term": {f"metadata.{key}.keyword": value}}
                )

        query = {
            "query": {
                "bool": {
                    "filter": metadata_filter
                }
            }
        }

        self.es.delete_by_query(index=req.index_name, body=query)

    def ingest(self, req: ElasticSearchStoreRequest):

        if req.index_mode == 'overwrite' and self.es.indices.exists(index=req.index_name):
            self.es.indices.delete(index=req.index_name)

        if req.embed_model_base_url.startswith('local:'):
            embedding = EmbedBuilder.get_embed(req.embed_model_base_url)
        else:
            embedding = OpenAIEmbeddings(
                model=req.embed_model_name,
                api_key=req.embed_model_api_key,
                base_url=req.embed_model_base_url,
            )
        db = ElasticsearchStore.from_documents(
            req.docs, embedding=embedding,
            es_connection=self.es, index_name=req.index_name,
            bulk_kwargs={
                "chunk_size": req.chunk_size,
                "max_chunk_bytes": req.max_chunk_bytes
            }
        )
        db.client.indices.refresh(index=req.index_name)

    def _process_search_result(self, docs: List[Document]) -> List[Document]:
        for doc in docs:
            if 'vector' in doc.metadata.get('_source', {}):
                del doc.metadata['_source']['vector']
        return docs

    def search(self, req: ElasticSearchRetrieverRequest) -> List[Document]:
        # 构建检索器 (使用固定的size)
        documents_retriever = ElasticsearchRetriever.from_es_params(
            index_name=req.index_name,
            body_func=lambda x: ElasticsearchQueryBuilder.build_query(req),
            content_field="text",
            url=os.getenv('ELASTICSEARCH_URL'),
            username="elastic",
            password=os.getenv('ELASTICSEARCH_PASSWORD'),
        )

        # 执行搜索
        search_result = documents_retriever.invoke(req.search_query)
        search_result = self._process_search_result(search_result)

        # 重排序处理
        if req.enable_rerank and search_result:
            headers = {
                "accept": "application/json", "Content-Type": "application/json",
                "Authorization": f"Bearer {req.rerank_model_api_key}"
            }

            rerank_content = []
            for i in search_result:
                rerank_content.append(i.page_content)

            data = {
                "model": req.rerank_model_name,
                "query": req.search_query,
                "documents": rerank_content,
            }
            response = requests.post(
                req.rerank_model_base_url, headers=headers, json=data)

            rerank_result = response.json()['results']

            # 对rerank_result进行排序并获取topk
            sorted_rerank_result = sorted(
                enumerate(rerank_result), key=lambda x: x[1]['relevance_score'], reverse=True)
            top_k_indices = [i[0]
                             for i in sorted_rerank_result[:req.rerank_top_k]]

            top_k_search_result = []
            for index in top_k_indices:
                search_result[index].metadata['relevance_score'] = rerank_result[index]['relevance_score']
                top_k_search_result.append(search_result[index])

            search_result = top_k_search_result

        search_result = [doc for doc in search_result if doc.metadata.get(
            '_score', 0) >= req.threshold]
        return search_result
