import copy
import os
from typing import List
from venv import logger

import elasticsearch
import requests
from langchain_core.documents import Document
from langchain_elasticsearch import ElasticsearchRetriever
from langchain_elasticsearch import ElasticsearchStore
import logging
logger = logging.getLogger(__name__)

from libs.metis.embed.embed_builder import EmbedBuilder
from libs.metis.entity.rag.base.document_count_request import DocumentCountRequest
from libs.metis.entity.rag.base.document_delete_request import DocumentDeleteRequest
from libs.metis.entity.rag.base.document_ingest_request import DocumentIngestRequest
from libs.metis.entity.rag.base.document_list_request import DocumentListRequest
from libs.metis.entity.rag.base.document_metadata_update_request import DocumentMetadataUpdateRequest
from libs.metis.entity.rag.base.document_retriever_request import DocumentRetrieverRequest
from libs.metis.entity.rag.base.index_delete_request import IndexDeleteRequest
from libs.metis.rag.base_rag import BaseRag
from libs.metis.rag.naive_rag.elasticsearch.elasticsearch_query_builder import ElasticsearchQueryBuilder
from libs.metis.rerank.rerank_manager import ReRankManager
from config.components.metis import METIS_ELASTICSEARCH_URL,METIS_ELASTICSEARCH_PASSWORD

class ElasticSearchRag(BaseRag):
    def __init__(self):
        self.es = elasticsearch.Elasticsearch(hosts=[METIS_ELASTICSEARCH_URL],
                                              basic_auth=("elastic", METIS_ELASTICSEARCH_PASSWORD))

    def update_metadata(self, req: DocumentMetadataUpdateRequest):
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
        self.es.update_by_query(
            index=req.index_name,
            body={**query, **update_script}
        )
        self.es.indices.refresh(index=req.index_name)

    def count_index_document(self, req: DocumentCountRequest):
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

    def delete_index(self, req: IndexDeleteRequest):
        self.es.indices.delete(index=req.index_name)

    def list_index_document(self, req: DocumentListRequest):
        # Build filter query for specific metadata
        metadata_filter = ElasticsearchQueryBuilder.build_metadata_filter(
            req.metadata_filter)

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

    def delete_document(self, req: DocumentDeleteRequest):
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

    def ingest(self, req: DocumentIngestRequest):

        if req.index_mode == 'overwrite' and self.es.indices.exists(index=req.index_name):
            self.es.indices.delete(index=req.index_name)

        embedding = EmbedBuilder.get_embed(req.embed_model_base_url,
                                           req.embed_model_name,
                                           req.embed_model_api_key,
                                           req.embed_model_base_url)
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
            if 'qa_answer' in doc.metadata.get('_source', {})['metadata']:
                doc.page_content += f"\n{doc.metadata['_source']['metadata']['qa_answer']}"
        return docs

    def _rerank_results(self, req: DocumentRetrieverRequest, search_result: List[Document]) -> List[Document]:
        """
        对搜索结果进行重排序处理
        """
        if not req.enable_rerank or not search_result:
            return search_result

        if req.rerank_model_base_url.startswith('local:'):
            logger.info(f"使用本地ReRank模型进行重排序: {req.rerank_model_base_url}")
            local_rerank_result = ReRankManager.rerank(req.rerank_model_base_url,
                                                       req.search_query, search_result)
            # 对local_rerank_result进行排序并获取topk
            top_k_search_result = []
            # Ensure rerank_ids and rerank_scores are available and have the same length
            if 'rerank_ids' in local_rerank_result and 'rerank_scores' in local_rerank_result and \
                    len(local_rerank_result['rerank_ids']) == len(local_rerank_result['rerank_scores']):

                top_rerank_ids = local_rerank_result['rerank_ids'][:req.rerank_top_k]

                for i in top_rerank_ids:
                    if 0 <= i < len(search_result):  # Check index bounds
                        doc = search_result[i]
                        # Ensure relevance_score can be set
                        if hasattr(doc, 'metadata'):
                            # Check if i is a valid index for rerank_scores
                            if 0 <= i < len(local_rerank_result['rerank_scores']):
                                doc.metadata['relevance_score'] = local_rerank_result['rerank_scores'][i]
                            else:
                                # Handle case where rerank_scores might not align, or set a default
                                # Or some other default/error indicator
                                doc.metadata['relevance_score'] = 0.0
                        top_k_search_result.append(doc)
                    else:
                        logger.warning(
                            f"Invalid index {i} from rerank_ids, skipping.")

            else:
                logger.warning(
                    "ReRank result format error or mismatch, skipping reranking.")
                return search_result  # Or handle error appropriately

            return top_k_search_result

        else:
            logger.info(f"使用远程ReRank模型进行重排序: {req.rerank_model_base_url}")
            headers = {
                "accept": "application/json", "Content-Type": "application/json",
                "Authorization": f"Bearer {req.rerank_model_api_key}"
            }

            rerank_content = [doc.page_content for doc in search_result]

            data = {
                "model": req.rerank_model_name,
                "query": req.search_query,
                "documents": rerank_content,
            }
            try:
                response = requests.post(
                    req.rerank_model_base_url, headers=headers, json=data, timeout=10)  # Added timeout
                response.raise_for_status()  # Raise an exception for HTTP errors
                rerank_api_result = response.json()

                if 'results' not in rerank_api_result:
                    logger.error(f"远程ReRank API响应格式错误: {rerank_api_result}")
                    return search_result  # Return original if reranking fails

                rerank_result_items = rerank_api_result['results']

                # 对rerank_result_items进行排序并获取topk
                # Ensure each item has 'relevance_score'
                valid_rerank_items = [
                    item for item in rerank_result_items if 'relevance_score' in item and 'index' in item]

                sorted_rerank_items = sorted(
                    valid_rerank_items, key=lambda x: x['relevance_score'], reverse=True)

                top_k_search_result = []
                for item in sorted_rerank_items[:req.rerank_top_k]:
                    original_index = item['index']
                    if 0 <= original_index < len(search_result):
                        doc = search_result[original_index]
                        if hasattr(doc, 'metadata'):
                            doc.metadata['relevance_score'] = item['relevance_score']
                        top_k_search_result.append(doc)
                    else:
                        logger.warning(
                            f"Invalid original_index {original_index} from rerank API, skipping.")

                return top_k_search_result

            except requests.exceptions.RequestException as e:
                logger.error(f"远程ReRank API请求失败: {e}")
                return search_result  # Return original if API call fails
            except (KeyError, TypeError) as e:
                logger.error(f"处理远程ReRank API响应时出错: {e}")
                return search_result  # Return original if response processing fails

    def search(self, req: DocumentRetrieverRequest) -> List[Document]:
        # 执行搜索
        search_result = []
        if req.enable_naive_rag is True:
            naive_rag_request = copy.deepcopy(req)
            naive_rag_request.metadata_filter['qa_answer__missing'] = True
            documents_retriever = ElasticsearchRetriever.from_es_params(
                index_name=req.index_name,
                body_func=lambda x: ElasticsearchQueryBuilder.build_query(
                    naive_rag_request),
                content_field="text",
                url=METIS_ELASTICSEARCH_URL,
                username="elastic",
                password=METIS_ELASTICSEARCH_PASSWORD,
            )
            rs = documents_retriever.invoke(req.search_query)
            rs = self._process_search_result(rs)
            search_result.extend(rs)
        if req.enable_qa_rag is True:
            qa_rag_request = copy.deepcopy(req)
            qa_rag_request.metadata_filter['qa_answer__exists'] = True
            documents_retriever = ElasticsearchRetriever.from_es_params(
                index_name=req.index_name,
                body_func=lambda x: ElasticsearchQueryBuilder.build_query(
                    qa_rag_request),
                content_field="text",
                url=METIS_ELASTICSEARCH_URL,
                username="elastic",
                password=METIS_ELASTICSEARCH_PASSWORD,
            )
            rs = documents_retriever.invoke(req.search_query)
            rs = self._process_search_result(rs)
            search_result.extend(rs)

        # 重排序处理
        search_result = self._rerank_results(req, search_result)
        search_result = [doc for doc in search_result if doc.metadata.get(
            # Consider relevance_score for threshold
            '_score', doc.metadata.get('relevance_score', 0)) >= (req.threshold / 10)]

        search_result = self.process_recall_stage(req, search_result)

        return search_result

    def process_recall_stage(self, req, search_result):
        if req.rag_recall_mode == 'chunk':
            return search_result

        if req.rag_recall_mode == 'segment':
            # 1. 根据chunk的segment_id进行去重
            segments_id_set = set()
            for doc in search_result:
                segment_id = doc.metadata['_source']['metadata']['segment_id']
                segments_id_set.add(segment_id)

            # 2. 去ElasticSearch中查找所有的segment_id内容，装载到字典中
            segment_id_dict = {}
            metadata_filter = [
                {
                    "terms": {
                        "metadata.segment_id.keyword": list(segments_id_set)
                    }
                }
            ]

            query = {
                "query": {
                    "bool": {
                        "filter": metadata_filter
                    }
                },
                "from": 0,
                "size": 10000,
                "_source": {"excludes": ["vector"]}  # Exclude the vector field
            }
            response = self.es.search(index=req.index_name, body=query)
            for hit in response['hits']['hits']:
                source = hit['_source']
                metadata = source.get('metadata', {})
                segment_id = metadata.get('segment_id')
                if segment_id not in segment_id_dict:
                    segment_id_dict[segment_id] = []
                segment_id_dict[segment_id].append(hit)  # 存储整个hit对象而不只是source

            # 3. 根据segment_id_dict的chunk_number，保留与原始搜索结果相同格式
            search_result = []

            # 按照segment_id分组处理
            for segment_id, hits in segment_id_dict.items():
                # 按chunk_number排序
                sorted_hits = sorted(hits, key=lambda x: int(
                    x['_source'].get('metadata', {}).get('chunk_number', 0)))

                # 将这个segment的所有chunk添加到结果中
                search_result.extend(sorted_hits)

        if req.rag_recall_mode == 'origin':
            # 1. 从搜索结果中提取所有相关的 knowledge_id
            knowledge_id_set = set()
            for doc in search_result:
                knowledge_id = doc.metadata['_source']['metadata'].get(
                    'knowledge_id')
                if knowledge_id:
                    knowledge_id_set.add(knowledge_id)

            if not knowledge_id_set:
                logger.warning("没有找到有效的 knowledge_id，返回原始搜索结果")
                return search_result

            # 2. 查询 Elasticsearch 获取所有包含这些 knowledge_id 的文档
            metadata_filter = [
                {
                    "terms": {
                        "metadata.knowledge_id.keyword": list(knowledge_id_set)
                    }
                }
            ]

            query = {
                "query": {
                    "bool": {
                        "filter": metadata_filter
                    }
                },
                "from": 0,
                "size": 10000,
                "_source": {"excludes": ["vector"]}
            }

            response = self.es.search(index=req.index_name, body=query)

            # 3. 按 knowledge_id 组织文档
            knowledge_docs = {}
            for hit in response['hits']['hits']:
                source = hit['_source']
                metadata = source.get('metadata', {})
                knowledge_id = metadata.get('knowledge_id')

                if not knowledge_id:
                    continue

                if knowledge_id not in knowledge_docs:
                    knowledge_docs[knowledge_id] = []

                knowledge_docs[knowledge_id].append(hit)  # 保存整个hit对象

            # 4. 返回所有匹配的文档，保持与原始搜索结果相同格式
            search_result = []
            for knowledge_id, hits in knowledge_docs.items():
                # 按segment_number排序
                sorted_hits = sorted(hits, key=lambda x: int(
                    x['_source'].get('metadata', {}).get('segment_number', 0)))

                # 将这个knowledge的所有文档添加到结果中
                search_result.extend(sorted_hits)

            logger.info(f"Origin 模式重组完成，共恢复 {len(search_result)} 份文档片段")

        # 5. 将ElasticSearch格式转换为Document格式
        docs_result = []
        for hit in search_result:
            doc = Document(page_content=source['text'], metadata=hit)
            docs_result.append(doc)

        return docs_result
