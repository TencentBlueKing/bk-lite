from typing import List, Optional, Union
from datetime import datetime, timezone

from langchain_core.documents import Document
from neco.llm.rag.graph_rag.graphiti.metis_embedder import MetisEmbedder
from neco.llm.rag.graph_rag.graphiti.metis_embedder_config import MetisEmbedderConfig
from neco.llm.rag.graph_rag.graphiti.metis_reranker_client import MetisRerankerClient
from neco.llm.rag.graph_rag.graphiti.metis_reranker_config import MetisRerankerConfig
from neco.llm.rag.graph_rag.graphiti.openai_client_patch import apply_openai_client_patch
from neco.llm.rag.graph_rag_entity import *
from tqdm import tqdm
from openai import AsyncOpenAI

from graphiti_core import Graphiti
from graphiti_core.nodes import EpisodeType
from graphiti_core.llm_client import OpenAIClient, LLMConfig

from neco.core.utils.timing_decorator import timeit
from loguru import logger
from graphiti_core.driver.falkordb_driver import FalkorDriver


class GraphitiRAG:
    """Graphiti知识图谱RAG实现类"""
    LLM_TIMEOUT_SECONDS = 60*60*24

    def __init__(self, knowledge_graph_host, knowledge_graph_username,
                 knowledge_graph_password, knowledge_graph_port,
                 knowledge_graph_database):
        self.knowledge_graph_host = knowledge_graph_host
        self.knowledge_graph_username = knowledge_graph_username
        self.knowledge_graph_password = knowledge_graph_password
        self.knowledge_graph_port = knowledge_graph_port
        self.knowledge_graph_database = knowledge_graph_database

        # 应用OpenAI客户端兼容性补丁
        # 解决GraphitiCore使用Azure OpenAI特有API的问题
        apply_openai_client_patch()

    def _create_basic_graphiti(self) -> Graphiti:
        """创建基础的Graphiti实例（不包含LLM客户端）"""
        driver = FalkorDriver(
            host=self.knowledge_graph_host,
            username=self.knowledge_graph_username,
            password=self.knowledge_graph_password,
            port=self.knowledge_graph_port,
            database=self.knowledge_graph_database
        )
        return Graphiti(graph_driver=driver)

    def _create_embed_client(self, embed_config: dict) -> MetisEmbedder:
        """创建嵌入客户端"""
        return MetisEmbedder(
            MetisEmbedderConfig(
                url=embed_config['url'],
                model_name=embed_config['model_name'],
                api_key=embed_config['api_key']
            )
        )

    def _create_rerank_client(self, rerank_config: dict) -> MetisRerankerClient:
        """创建重排序客户端"""
        return MetisRerankerClient(
            MetisRerankerConfig(
                url=rerank_config['url'],
                model_name=rerank_config['model_name'],
                api_key=rerank_config['api_key']
            )
        )

    def _create_llm_client(self, llm_config: dict) -> OpenAIClient:
        """创建LLM客户端"""
        async_openai = AsyncOpenAI(
            api_key=llm_config['api_key'],
            base_url=llm_config['base_url'],
            timeout=self.LLM_TIMEOUT_SECONDS  # 使用类变量避免硬编码
        )
        return OpenAIClient(
            client=async_openai,
            config=LLMConfig(
                model=llm_config['model'],
                small_model=llm_config['model'],
            ),
        )

    def _create_full_graphiti(
        self,
        llm_config: Optional[dict] = None,
        embed_config: Optional[dict] = None,
        rerank_config: Optional[dict] = None
    ) -> Graphiti:
        """创建完整配置的Graphiti实例"""
        kwargs = {}

        if llm_config:
            kwargs['llm_client'] = self._create_llm_client(llm_config)

        if embed_config:
            kwargs['embedder'] = self._create_embed_client(embed_config)

        if rerank_config:
            kwargs['cross_encoder'] = self._create_rerank_client(rerank_config)

        driver = FalkorDriver(
            host=self.knowledge_graph_host,
            username=self.knowledge_graph_username,
            password=self.knowledge_graph_password,
            port=self.knowledge_graph_port,
            database=self.knowledge_graph_database
        )
        kwargs['graph_driver'] = driver
        return Graphiti(**kwargs)

    def _extract_configs_from_request(
        self,
        req: Union[DocumentIngestRequest,
                   DocumentRetrieverRequest, RebuildCommunityRequest]
    ) -> tuple[Optional[dict], Optional[dict], Optional[dict]]:
        """从请求对象中提取配置信息"""
        llm_config = None
        embed_config = None
        rerank_config = None

        # 提取LLM配置（如果存在）
        if hasattr(req, 'openai_api_key') and req.openai_api_key:
            llm_config = {
                'api_key': req.openai_api_key,
                'base_url': req.openai_api_base,
                'model': req.openai_model
            }

        # 提取嵌入模型配置（如果存在）
        if hasattr(req, 'embed_model_base_url') and req.embed_model_base_url:
            embed_config = {
                'url': req.embed_model_base_url,
                'model_name': req.embed_model_name,
                'api_key': req.embed_model_api_key
            }

        # 提取重排序模型配置（如果存在）
        if hasattr(req, 'rerank_model_base_url') and req.rerank_model_base_url:
            rerank_config = {
                'url': req.rerank_model_base_url,
                'model_name': req.rerank_model_name,
                'api_key': req.rerank_model_api_key
            }

        return llm_config, embed_config, rerank_config

    async def delete_index(self, req: IndexDeleteRequest):
        """删除索引"""
        logger.info(f"删除索引: group_id={req.group_id}")
        graphiti = self._create_basic_graphiti()
        await graphiti.driver.execute_query(
            f"""
            MATCH (n {{group_id: '{req.group_id}'}})
            DETACH DELETE n
            """
        )

    async def list_index_document(self, req: DocumentRetrieverRequest):
        """列出索引文档（节点和边）"""
        logger.info(f"查询索引文档: group_ids={req.group_ids}")
        graphiti = self._create_basic_graphiti()

        # 查询节点
        nodes_result, _, _ = await graphiti.driver.execute_query(
            """
            MATCH (n) WHERE n.group_id IN $group_ids
            RETURN n.name as name, n.uuid as uuid, n.fact as fact, n.summary as summary, 
                   id(n) as node_id, n.group_id as group_id, labels(n) as labels
            """,
            group_ids=req.group_ids
        )

        # 查询边
        edges_result, _, _ = await graphiti.driver.execute_query(
            """
            MATCH (n)-[r]-(m) 
            WHERE n.group_id IN $group_ids AND m.group_id IN $group_ids
            RETURN type(r) as relation_type, 
                   n.uuid as source_uuid, m.uuid as target_uuid,
                   n.name as source_name, m.name as target_name,
                   r.fact as fact, id(n) as source_id, id(m) as target_id
            """,
            group_ids=req.group_ids
        )

        # 构建边列表
        edges = [
            {
                'relation_type': record['relation_type'],
                'source': record['source_uuid'],
                'target': record['target_uuid'],
                'source_name': record['source_name'],
                'target_name': record['target_name'],
                'source_id': record['source_id'],
                'target_id': record['target_id'],
                'fact': record['fact']
            }
            for record in edges_result
        ]

        # 构建节点列表
        nodes = [
            {
                'name': record['name'],
                'uuid': record['uuid'],
                'group_id': record['group_id'],
                'node_id': record['node_id'],
                "fact": record['fact'],
                "summary": record['summary'],
                "labels": record['labels'],
            }
            for record in nodes_result
        ]

        return {"nodes": nodes, "edges": edges}

    async def delete_document(self, req: DocumentDeleteRequest):
        """删除文档"""
        logger.info(f"删除文档: uuids={req.uuids}")
        graphiti = self._create_basic_graphiti()
        for uuid in req.uuids:
            await graphiti.remove_episode(episode_uuid=uuid)

    async def setup_graph(self):
        """设置图数据库索引和约束"""
        logger.info("设置图数据库索引和约束")
        graphiti = self._create_basic_graphiti()
        await graphiti.build_indices_and_constraints()

    @timeit("community_building")
    async def build_communities(self, graphiti_instance: Graphiti, group_ids: List[str]):
        """构建社区"""
        logger.info(f"构建社区: group_ids={group_ids}")
        await graphiti_instance.build_communities(group_ids=group_ids)

    @timeit("document_ingest")
    async def ingest(self, req: DocumentIngestRequest):
        """文档摄取"""
        logger.info(f"开始摄取文档: group_id={req.group_id}, 文档数量={len(req.docs)}")

        # 提取配置
        llm_config, embed_config, rerank_config = self._extract_configs_from_request(
            req)

        # 创建完整配置的Graphiti实例
        graphiti_instance = self._create_full_graphiti(
            llm_config, embed_config, rerank_config)

        # 处理文档
        mapping = {}
        success_count = 0
        failed_count = 0

        for i, doc in enumerate(tqdm(req.docs, desc="处理文档")):
            try:
                name = f"{doc.metadata['knowledge_title']}_{doc.metadata['knowledge_id']}_{doc.metadata['chunk_id']}"
                logger.info(f"处理文档 {i+1}/{len(req.docs)}: {name}")

                episode = await graphiti_instance.add_episode(
                    name=name,
                    episode_body=doc.page_content,
                    source=EpisodeType.text,
                    source_description=doc.metadata['knowledge_title'],
                    reference_time=datetime.now(timezone.utc),
                    group_id=req.group_id,
                )
                mapping[doc.metadata['chunk_id']] = episode.episode.uuid
                success_count += 1

                # 每处理10个文档输出一次进度
                if (i + 1) % 10 == 0:
                    logger.info(
                        f"已处理 {i+1}/{len(req.docs)} 个文档，成功: {success_count}, 失败: {failed_count}")

            except Exception as e:
                failed_count += 1
                logger.error(f"处理文档失败 {name}: {e}")
                # 添加更详细的调试信息
                logger.error(f"文档内容长度: {len(doc.page_content)}")
                logger.error(f"文档内容前500字符: {doc.page_content[:500]}...")
                logger.error(f"文档元数据: {doc.metadata}")
                # 继续处理下一个文档，不中断整个流程

        # 可选：重建社区
        if req.rebuild_community:
            logger.info("开始重建社区...")
            try:
                await self.build_communities(graphiti_instance, [req.group_id])
                logger.info("社区重建完成")
            except Exception as e:
                logger.error(f"社区重建失败: {e}")
                # 社区重建失败不影响整体结果

        logger.info(f"文档摄取完成: 成功摄取{success_count}个文档，失败{failed_count}个文档")
        return {
            "mapping": mapping,
            "success_count": success_count,
            "failed_count": failed_count,
            "total_count": len(req.docs)
        }

    @timeit("community_rebuild")
    async def rebuild_community(self, req: RebuildCommunityRequest):
        """重建社区"""
        logger.info(f"重建社区: group_ids={req.group_ids}")

        # 提取配置
        llm_config, embed_config, rerank_config = self._extract_configs_from_request(
            req)

        # 创建完整配置的Graphiti实例
        graphiti_instance = self._create_full_graphiti(
            llm_config, embed_config, rerank_config)
        await self.build_communities(graphiti_instance, req.group_ids)
        logger.info("社区重建完成")

    @timeit("document_search")
    async def search(self, req: DocumentRetrieverRequest) -> List[Document]:
        """搜索文档"""
        logger.info(
            f"开始搜索: query={req.search_query}, group_ids={req.group_ids}, size={req.size}")

        # 提取配置（搜索时不需要LLM客户端）
        _, embed_config, rerank_config = self._extract_configs_from_request(
            req)

        # 创建Graphiti实例
        graphiti_instance = self._create_full_graphiti(
            embed_config=embed_config,
            rerank_config=rerank_config
        )

        # 执行搜索
        result = await graphiti_instance.search(
            query=req.search_query,
            num_results=req.size,
            group_ids=req.group_ids
        )

        # 收集需要查询的节点UUID
        node_uid_set = set()
        for r in result:
            node_uid_set.add(r.source_node_uuid)
            node_uid_set.add(r.target_node_uuid)

        # 查询节点信息
        node_info_map = {}
        if node_uid_set:
            node_uids = list(node_uid_set)
            logger.info(f"查询节点信息: node_uids数量={len(node_uids)}")
            node_result, _, _ = await graphiti_instance.driver.execute_query(
                """
                MATCH (n) 
                WHERE n.uuid IN $node_uids
                RETURN n.uuid as uuid, n.name as name, n.fact as fact, 
                       n.summary as summary, labels(n) as labels
                """,
                node_uids=node_uids
            )

            node_info_map = {
                record['uuid']: {
                    'name': record['name'],
                    'fact': record['fact'],
                    'summary': record['summary'],
                    'labels': record['labels']
                }
                for record in node_result
            }
            logger.info(f"查询到节点信息: 节点数量={len(node_info_map)}")

        # 构建结果文档
        docs = [
            self._build_search_result_doc(r, node_info_map)
            for r in result
        ]

        logger.info(f"搜索完成: 找到{len(docs)}个相关文档")
        return docs

    def _build_node_info(self, node_uuid: str, node_info_map: dict) -> dict:
        """构建节点信息字典"""
        node_info = node_info_map.get(node_uuid, {})
        return {
            "uuid": node_uuid,
            "name": node_info.get('name', ''),
            "summary": node_info.get('summary', ''),
            "labels": node_info.get('labels', [])
        }

    def _build_search_result_doc(self, result_item, node_info_map: dict) -> dict:
        """构建搜索结果文档"""
        return {
            "fact": result_item.fact,
            "name": result_item.name,
            "group_id": result_item.group_id,
            "source_node": self._build_node_info(result_item.source_node_uuid, node_info_map),
            "target_node": self._build_node_info(result_item.target_node_uuid, node_info_map)
        }
