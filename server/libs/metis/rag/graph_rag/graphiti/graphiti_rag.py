from typing import List

from shapely import node
from langchain_core.documents import Document
from libs.metis.entity.rag.base.document_delete_request import DocumentDeleteRequest
from libs.metis.entity.rag.graphiti.document_ingest_request import GraphitiRagDocumentIngestRequest
from libs.metis.entity.rag.graphiti.document_retriever_request import DocumentRetrieverRequest
from libs.metis.entity.rag.graphiti.document_retriever_request import DocumentRetrieverRequest
from libs.metis.entity.rag.graphiti.rebuild_community_request import RebuildCommunityRequest
from libs.metis.rag.graph_rag.graphiti.metis_embedder import MetisEmbedder
from libs.metis.rag.graph_rag.graphiti.metis_embedder_config import MetisEmbedderConfig
from libs.metis.rag.graph_rag.graphiti.metis_raranker_config import MetisRerankerConfig
from libs.metis.rag.graph_rag.graphiti.metis_reranker_client import MetisRerankerClient
from libs.metis.summarize.summarize_manager import SummarizeManager
from tqdm import tqdm
from graphiti_core import Graphiti
from config.components.metis import METIS_NEO4J_URL,METIS_NEO4J_PASSWORD, METIS_NEO4J_USERNAME
from libs.graphiti_core.nodes import EpisodeType
from libs.metis.entity.rag.base.index_delete_request import IndexDeleteRequest
from libs.graphiti_core.llm_client import OpenAIClient, LLMConfig
from openai import AsyncOpenAI
from datetime import datetime, timezone


class GraphitiRAG():
    def __init__(self):
        pass

    async def delete_index(self, req: IndexDeleteRequest):
        graphiti = Graphiti(
            METIS_NEO4J_URL,
            METIS_NEO4J_USERNAME,
            METIS_NEO4J_PASSWORD,
        )
        await graphiti.driver.execute_query(
            f"""
            MATCH (n {{group_id: '{req.group_id}'}})
            DETACH DELETE n
            """
        )

    async def list_index_document(self, req: DocumentRetrieverRequest):
        graphiti = Graphiti(
            METIS_NEO4J_URL,
            METIS_NEO4J_USERNAME,
            METIS_NEO4J_PASSWORD,
        )
        # First get all nodes
        nodes_result = await graphiti.driver.execute_query(
            """
            MATCH (n) WHERE n.group_id IN $group_ids
            RETURN n.name as name, n.uuid as uuid, n.fact as fact, n.summary as summary, 
                   id(n) as node_id, n.group_id as group_id,
                   labels(n) as labels
            """,
            params={"group_ids": req.group_ids}
        )

        # Then get all relationships
        edges_result = await graphiti.driver.execute_query(
            """
            MATCH (n)-[r]-(m) 
            WHERE n.group_id IN $group_ids AND m.group_id IN $group_ids
            RETURN type(r) as relation_type, 
                   n.uuid as source_uuid, 
                   m.uuid as target_uuid,
                   n.name as source_name,
                   m.name as target_name,
                   r.fact as fact,
                   id(n) as source_id,
                   id(m) as target_id
            """,
            params={"group_ids": req.group_ids}
        )

        # Build edges list
        edges = []
        for edge_record in edges_result.records:
            edge = {
                'relation_type': edge_record['relation_type'],
                'source': edge_record['source_uuid'],
                'target': edge_record['target_uuid'],
                'source_name': edge_record['source_name'],
                'target_name': edge_record['target_name'],
                'source_id': edge_record['source_id'],
                'target_id': edge_record['target_id'],
                'fact': edge_record['fact']
            }
            edges.append(edge)

        nodes = []
        for record in nodes_result.records:
            doc = {
                'name': record['name'],
                'uuid': record['uuid'],
                'group_id': record['group_id'],
                'node_id': record['node_id'],
                "fact": record['fact'],
                "summary": record['summary'],
                "labels": record['labels'],
            }
            nodes.append(doc)
        rs = {
            "nodes": nodes,
            "edges": edges
        }
        return rs

    async def delete_document(self, req: DocumentDeleteRequest):
        graphiti = Graphiti(
            METIS_NEO4J_URL,
            METIS_NEO4J_USERNAME,
            METIS_NEO4J_PASSWORD,
        )
        for uuid in req.uuids:
            await graphiti.remove_episode(
                episode_uuid=uuid,
            )

    async def setup_graph(self):
        graphiti = Graphiti(
            METIS_NEO4J_URL,
            METIS_NEO4J_USERNAME,
            METIS_NEO4J_PASSWORD,
        )
        await graphiti.build_indices_and_constraints()

    async def build_communities(self, graphiti_instance: Graphiti, group_ids: List[str]):
        await graphiti_instance.build_communities(group_ids=group_ids)

    async def ingest(self, req: GraphitiRagDocumentIngestRequest):
        llm_client = AsyncOpenAI(
            api_key=req.openai_api_key,
            base_url=req.openai_api_base,
        )

        embed_client = MetisEmbedder(
            MetisEmbedderConfig(
                url=req.embed_model_base_url,
                model_name=req.embed_model_name,
                api_key=req.embed_model_api_key
            )
        )

        rerank_client = MetisRerankerClient(
            MetisRerankerConfig(
                url=req.rerank_model_base_url,
                model_name=req.rerank_model_name,
                api_key=req.rerank_model_api_key
            )
        )

        graphiti_instance = Graphiti(
            METIS_NEO4J_URL,
            METIS_NEO4J_USERNAME,
            METIS_NEO4J_PASSWORD,
            llm_client=OpenAIClient(
                client=llm_client,
                config=LLMConfig(
                    model=req.openai_model,
                    small_model=req.openai_model,
                ),
            ),
            embedder=embed_client,
            cross_encoder=rerank_client
        )

        mapping = {}
        for doc in tqdm(req.docs):

            name = f"{doc.metadata['knowledge_title']}_{doc.metadata['knowledge_id']}_{doc.metadata['chunk_id']}"
            episode = await graphiti_instance.add_episode(
                name=name,
                episode_body=doc.page_content,
                source=EpisodeType.text,
                source_description=doc.metadata['knowledge_title'],
                reference_time=datetime.now(timezone.utc),
                group_id=req.group_id,
            )
            mapping[doc.metadata['chunk_id']] = episode.episode.uuid

        if req.rebuild_community:
            await self.build_communities(graphiti_instance, [req.group_id])
        return mapping

    async def rebuild_community(self, req: RebuildCommunityRequest):
        llm_client = AsyncOpenAI(
            api_key=req.openai_api_key,
            base_url=req.openai_api_base,
        )

        embed_client = MetisEmbedder(
            MetisEmbedderConfig(
                url=req.embed_model_base_url,
                model_name=req.embed_model_name,
                api_key=req.embed_model_api_key
            )
        )

        rerank_client = MetisRerankerClient(
            MetisRerankerConfig(
                url=req.rerank_model_base_url,
                model_name=req.rerank_model_name,
                api_key=req.rerank_model_api_key
            )
        )

        graphiti_instance = Graphiti(
            METIS_NEO4J_URL,
            METIS_NEO4J_USERNAME,
            METIS_NEO4J_PASSWORD,
            llm_client=OpenAIClient(
                client=llm_client,
                config=LLMConfig(
                    model=req.openai_model,
                    small_model=req.openai_model,
                ),
            ),
            embedder=embed_client,
            cross_encoder=rerank_client
        )
        await self.build_communities(graphiti_instance, req.group_ids)

    async def search(self, req: DocumentRetrieverRequest) -> List[Document]:
        embed_client = MetisEmbedder(
            MetisEmbedderConfig(
                url=req.embed_model_base_url,
                model_name=req.embed_model_name,
                api_key=req.embed_model_api_key
            )
        )

        rerank_client = MetisRerankerClient(
            MetisRerankerConfig(
                url=req.rerank_model_base_url,
                model_name=req.rerank_model_name,
                api_key=req.rerank_model_api_key
            )
        )

        graphiti_instance = Graphiti(
            METIS_NEO4J_URL,
            METIS_NEO4J_USERNAME,
            METIS_NEO4J_PASSWORD,
            embedder=embed_client,
            cross_encoder=rerank_client
        )

        result = await graphiti_instance.search(
            query=req.search_query,
            num_results=req.size,
            group_ids=req.group_ids
        )

        node_uid_set = set()
        for r in result:
            node_uid_set.add(r.source_node_uuid)
            node_uid_set.add(r.target_node_uuid)

        # 查询neo4j中的节点信息
        node_info_map = {}
        if node_uid_set:
            node_uids = list(node_uid_set)
            node_result = await graphiti_instance.driver.execute_query(
                """
            MATCH (n) 
            WHERE n.uuid IN $node_uids
            RETURN n.uuid as uuid, n.name as name, n.fact as fact, n.summary as summary,labels(n) as labels
            """,
                params={"node_uids": node_uids}
            )

            for record in node_result.records:
                node_info_map[record['uuid']] = {
                    'name': record['name'],
                    'fact': record['fact'],
                    'summary': record['summary'],
                    'labels': record['labels']
                }

        docs = []
        for r in result:
            source_node_info = node_info_map.get(r.source_node_uuid, {})
            target_node_info = node_info_map.get(r.target_node_uuid, {})

            doc = {
                "fact": r.fact,
                "name": r.name,
                "group_id": r.group_id,
                "source_node": {
                    "uuid": r.source_node_uuid,
                    "name": source_node_info.get('name', ''),
                    "summary": source_node_info.get('summary', ''),
                    "labels": source_node_info.get('labels', [])
                },
                "target_node": {
                    "uuid": r.target_node_uuid,
                    "name": target_node_info.get('name', ''),
                    "summary": target_node_info.get('summary', ''),
                    "labels": target_node_info.get('labels', [])
                }
            }
            docs.append(doc)

        return docs
