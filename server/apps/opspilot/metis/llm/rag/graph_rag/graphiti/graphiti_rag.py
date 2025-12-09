from typing import List, Optional, Union
from datetime import datetime, timezone
import asyncio

from langchain_core.documents import Document
from apps.opspilot.metis.llm.rag.graph_rag.graphiti.metis_embedder import MetisEmbedder
from apps.opspilot.metis.llm.rag.graph_rag.graphiti.metis_embedder_config import MetisEmbedderConfig
from apps.opspilot.metis.llm.rag.graph_rag.graphiti.metis_reranker_client import MetisRerankerClient
from apps.opspilot.metis.llm.rag.graph_rag.graphiti.metis_reranker_config import MetisRerankerConfig
from apps.opspilot.metis.llm.rag.graph_rag.graphiti.openai_client_patch import apply_openai_client_patch
from apps.opspilot.metis.llm.rag.graph_rag_entity import *
from tqdm import tqdm
from openai import AsyncOpenAI

from graphiti_core import Graphiti
from graphiti_core.nodes import EpisodeType
from graphiti_core.llm_client import OpenAIClient, LLMConfig

from loguru import logger
from graphiti_core.driver.falkordb_driver import FalkorDriver
import os


class GraphitiRAG:
    """Graphiti知识图谱RAG实现类"""
    LLM_TIMEOUT_SECONDS = 60 * 60 * 24

    def __init__(self):
        self.knowledge_graph_host = os.getenv("KNOWLEDGE_GRAPH_HOST")
        self.knowledge_graph_username = os.getenv("KNOWLEDGE_GRAPH_USERNAME")
        self.knowledge_graph_password = os.getenv("KNOWLEDGE_GRAPH_PASSWORD")
        self.knowledge_graph_port = os.getenv("KNOWLEDGE_GRAPH_PORT")
        # 应用OpenAI客户端兼容性补丁
        # 解决GraphitiCore使用Azure OpenAI特有API的问题
        apply_openai_client_patch()

    async def _safe_close_driver(self, graphiti: Graphiti):
        """
        安全关闭 Graphiti driver

        注意：由于 FalkorDriver 会在初始化时启动后台任务，
        我们简单地等待一小段时间让这些任务完成，而不是强制关闭连接。
        实际上，对于短期操作，不关闭连接让其自然回收可能更安全。
        """
        try:
            # 给后台索引构建任务足够时间完成
            await asyncio.sleep(0.3)
        except Exception as e:
            logger.debug(f"等待后台任务时出现警告: {e}")

        # 不主动关闭 driver，让 Redis 连接池自动管理
        # 这样可以避免 "Buffer is closed" 错误
        # driver 会在 graphiti 对象被垃圾回收时自动清理

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
        rerank_config: Optional[dict] = None,
        graph_database: str = None
    ) -> Graphiti:
        """创建完整配置的Graphiti实例

        Args:
            graph_database: 指定的graph数据库名称(必填)
        """
        if not graph_database:
            raise ValueError("graph_database 参数不能为空,必须指定知识库的 group_id")

        kwargs = {}

        if llm_config:
            kwargs['llm_client'] = self._create_llm_client(llm_config)

        if embed_config:
            kwargs['embedder'] = self._create_embed_client(embed_config)

        if rerank_config:
            kwargs['cross_encoder'] = self._create_rerank_client(rerank_config)

        logger.debug(f"创建Graphiti实例 - 使用database: {graph_database}")

        driver = FalkorDriver(
            host=self.knowledge_graph_host,
            username=self.knowledge_graph_username,
            password=self.knowledge_graph_password,
            port=self.knowledge_graph_port,
            database=graph_database
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
        """删除索引

        注意：在FalkorDB中,删除整个graph database的所有数据
        """
        logger.info(f"删除索引(graph database): group_id={req.group_id}")

        # 直接连接到要删除的graph database
        driver = FalkorDriver(
            host=self.knowledge_graph_host,
            username=self.knowledge_graph_username,
            password=self.knowledge_graph_password,
            port=self.knowledge_graph_port,
            database=req.group_id
        )
        graphiti = Graphiti(graph_driver=driver)

        try:
            # 删除graph中的所有节点和边
            await graphiti.driver.execute_query(
                """
                MATCH (n)
                DETACH DELETE n
                """
            )
            logger.info(f"成功清空graph database: {req.group_id}")
        except Exception as e:
            logger.warning(
                f"清空graph database失败(可能不存在): {req.group_id}, 错误: {e}")
        finally:
            await self._safe_close_driver(graphiti)

    async def list_index_document(self, req: DocumentRetrieverRequest):
        """列出索引文档（节点和边）"""
        logger.info(f"查询索引文档: group_ids={req.group_ids}")

        # FalkorDB 中每个 graph 是独立的，需要使用 group_id 作为 graph 名称
        if not req.group_ids or len(req.group_ids) == 0:
            raise ValueError("group_ids 参数不能为空")

        graph_name = req.group_ids[0]

        # 创建指定 graph 的 driver
        driver = FalkorDriver(
            host=self.knowledge_graph_host,
            username=self.knowledge_graph_username,
            password=self.knowledge_graph_password,
            port=self.knowledge_graph_port,
            database=graph_name
        )
        graphiti = Graphiti(graph_driver=driver)

        try:
            # 查询节点
            nodes_result, _, _ = await graphiti.driver.execute_query(
                """
                MATCH (n)
                RETURN n.name as name, n.uuid as uuid, n.fact as fact, n.summary as summary, 
                       id(n) as node_id, n.group_id as group_id, labels(n) as labels
                """
            )

            logger.debug(f"查询到 {len(nodes_result)} 个节点")
            if nodes_result:
                logger.debug(f"第一个节点示例: {nodes_result[0]}")

            # 查询边
            edges_result, _, _ = await graphiti.driver.execute_query(
                """
                MATCH (n)-[r]-(m)
                RETURN type(r) as relation_type, 
                       n.uuid as source_uuid, m.uuid as target_uuid,
                       n.name as source_name, m.name as target_name,
                       r.fact as fact, id(n) as source_id, id(m) as target_id
                """
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

            # 构建节点列表 - 在独立graph database模式下,使用graph_name作为group_id
            nodes = [
                {
                    'name': record.get('name'),
                    'uuid': record.get('uuid'),
                    # 如果没有group_id,使用graph名称
                    'group_id': record.get('group_id') or graph_name,
                    'node_id': record.get('node_id'),
                    "fact": record.get('fact'),
                    "summary": record.get('summary'),
                    "labels": record.get('labels', []),
                }
                for record in nodes_result
            ]

            result = {"nodes": nodes, "edges": edges}
            logger.info(f"查询完成: {len(nodes)} 个节点, {len(edges)} 条边")
            return result
        finally:
            # 等待后台任务完成
            await self._safe_close_driver(graphiti)

    async def delete_document(self, req: DocumentDeleteRequest):
        """删除文档"""
        logger.info(f"删除文档: group_id={req.group_id}, uuids={req.uuids}")

        # 使用group_id作为graph database名称
        driver = FalkorDriver(
            host=self.knowledge_graph_host,
            username=self.knowledge_graph_username,
            password=self.knowledge_graph_password,
            port=self.knowledge_graph_port,
            database=req.group_id
        )
        graphiti = Graphiti(graph_driver=driver)

        try:
            for uuid in req.uuids:
                await graphiti.remove_episode(episode_uuid=uuid)
        finally:
            await self._safe_close_driver(graphiti)

    async def setup_graph(self, graph_database: str):
        """设置图数据库索引和约束

        Args:
            graph_database: 要初始化的graph database名称
        """
        logger.info(f"设置图数据库索引和约束 - database: {graph_database}")

        driver = FalkorDriver(
            host=self.knowledge_graph_host,
            username=self.knowledge_graph_username,
            password=self.knowledge_graph_password,
            port=self.knowledge_graph_port,
            database=graph_database
        )
        graphiti = Graphiti(graph_driver=driver)

        try:
            await graphiti.build_indices_and_constraints()
        finally:
            await self._safe_close_driver(graphiti)

    async def build_communities(self, graphiti_instance: Graphiti, graph_database: str):
        """构建社区

        Args:
            graphiti_instance: Graphiti实例
            graph_database: graph database名称,用于日志记录

        注意：在独立graph database模式下,整个database就是一个知识库,
        因此不需要传group_ids参数进行过滤
        """
        logger.info(f"---------- 社区构建流程开始 ----------")
        logger.info(f"目标数据库: {graph_database}")

        # 检查图谱数据
        try:
            logger.info("正在检查图谱数据...")
            node_check, _, _ = await graphiti_instance.driver.execute_query(
                "MATCH (n) RETURN count(n) as count"
            )
            node_count = node_check[0]['count'] if node_check else 0

            edge_check, _, _ = await graphiti_instance.driver.execute_query(
                "MATCH ()-[r]->() RETURN count(r) as count"
            )
            edge_count = edge_check[0]['count'] if edge_check else 0

            logger.info(f"图谱统计 - 节点数: {node_count}, 边数: {edge_count}")

            if node_count == 0:
                logger.warning("警告: 图谱中没有节点,跳过社区构建")
                return

        except Exception as e:
            logger.error(f"检查图谱数据失败: {e}", exc_info=True)
            raise

        # 执行社区构建
        try:
            logger.info(f"正在为 {node_count} 个节点构建社区...")
            logger.debug("调用 graphiti_instance.build_communities()")

            result = await graphiti_instance.build_communities()

            logger.debug(f"build_communities 返回结果类型: {type(result)}")
            logger.info("社区构建调用完成")

            # 检查构建后的社区数量
            community_check, _, _ = await graphiti_instance.driver.execute_query(
                "MATCH (n:Community) RETURN count(n) as count"
            )
            community_count = community_check[0]['count'] if community_check else 0
            logger.info(f"社区构建结果 - 创建了 {community_count} 个社区")

        except Exception as e:
            logger.error(f"社区构建过程失败: {e}", exc_info=True)
            raise

        logger.info(f"---------- 社区构建流程完成 ----------")

    async def ingest(self, req: DocumentIngestRequest):
        """文档摄取"""
        logger.info(f"开始摄取文档: group_id={req.group_id}, 文档数量={len(req.docs)}")

        # 提取配置
        llm_config, embed_config, rerank_config = self._extract_configs_from_request(
            req)

        # 使用group_id作为graph database名称
        # 创建完整配置的Graphiti实例
        graphiti_instance = self._create_full_graphiti(
            llm_config, embed_config, rerank_config, graph_database=req.group_id)

        try:
            # 处理文档
            mapping = {}
            success_count = 0
            failed_count = 0

            for i, doc in enumerate(tqdm(req.docs, desc="处理文档")):
                try:
                    name = f"{doc.metadata['knowledge_title']}_{doc.metadata['knowledge_id']}_{doc.metadata['chunk_id']}"
                    logger.info(f"处理文档 {i + 1}/{len(req.docs)}: {name}")

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
                            f"已处理 {i + 1}/{len(req.docs)} 个文档，成功: {success_count}, 失败: {failed_count}")

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
                logger.info("---------- 文档摄取后重建社区 ----------")
                try:
                    await self.build_communities(graphiti_instance, req.group_id)
                except Exception as e:
                    logger.error(f"社区重建失败: {e}", exc_info=True)
                    # 社区重建失败不影响整体结果,继续返回摄取结果

            logger.info(f"文档摄取完成: 成功摄取{success_count}个文档，失败{failed_count}个文档")
            return {
                "mapping": mapping,
                "success_count": success_count,
                "failed_count": failed_count,
                "total_count": len(req.docs)
            }
        finally:
            # 确保关闭 driver 连接
            await self._safe_close_driver(graphiti_instance)

    async def rebuild_community(self, req: RebuildCommunityRequest):
        """重建社区"""
        logger.info("========== 开始重建图谱社区 ==========")
        logger.info(f"请求参数 - group_ids: {req.group_ids}")

        # 提取配置
        llm_config, embed_config, rerank_config = self._extract_configs_from_request(
            req)

        logger.info(
            f"配置信息 - LLM模型: {llm_config.get('model') if llm_config else 'None'}")
        logger.info(
            f"配置信息 - Embed模型: {embed_config.get('model_name') if embed_config else 'None'}")
        logger.info(
            f"配置信息 - Rerank模型: {rerank_config.get('model_name') if rerank_config else 'None'}")

        # 使用第一个group_id作为graph database名称
        if not req.group_ids or len(req.group_ids) == 0:
            logger.error("重建失败 - group_ids参数为空")
            raise ValueError("group_ids 参数不能为空")

        graph_database = req.group_ids[0]
        logger.info(f"目标数据库 - graph database: {graph_database}")

        # 创建完整配置的Graphiti实例
        logger.info("正在创建Graphiti实例...")
        graphiti_instance = self._create_full_graphiti(
            llm_config, embed_config, rerank_config, graph_database=graph_database)

        # 验证组件配置
        has_llm = hasattr(
            graphiti_instance, 'llm_client') and graphiti_instance.llm_client is not None
        has_embedder = hasattr(
            graphiti_instance, 'embedder') and graphiti_instance.embedder is not None
        has_reranker = hasattr(
            graphiti_instance, 'cross_encoder') and graphiti_instance.cross_encoder is not None

        logger.info(f"组件配置状态 - LLM客户端: {'已配置' if has_llm else '未配置'}, "
                    f"嵌入器: {'已配置' if has_embedder else '未配置'}, "
                    f"重排序器: {'已配置' if has_reranker else '未配置'}")

        if not has_llm:
            logger.warning("警告: LLM客户端未配置,社区构建可能失败")

        try:
            # 执行社区重建
            logger.info("开始执行社区构建...")
            await self.build_communities(graphiti_instance, graph_database)
            logger.info("========== 图谱社区重建完成 ==========")
        except Exception as e:
            logger.error("========== 图谱社区重建失败 ==========")
            logger.error(f"错误详情: {str(e)}", exc_info=True)
            raise
        finally:
            await self._safe_close_driver(graphiti_instance)

    async def search(self, req: DocumentRetrieverRequest) -> List[Document]:
        """搜索文档"""
        logger.info(
            f"开始搜索: query={req.search_query}, group_ids={req.group_ids}, size={req.size}")

        # 提取配置（搜索时不需要LLM客户端）
        _, embed_config, rerank_config = self._extract_configs_from_request(
            req)

        # 使用第一个group_id作为graph database名称
        # 注意: FalkorDB中每个group_id对应一个独立的graph database
        if not req.group_ids or len(req.group_ids) == 0:
            raise ValueError("group_ids 参数不能为空")

        graph_database = req.group_ids[0]
        logger.info(f"使用graph database: {graph_database}")

        # 创建Graphiti实例
        graphiti_instance = self._create_full_graphiti(
            embed_config=embed_config,
            rerank_config=rerank_config,
            graph_database=graph_database
        )

        try:
            # 在搜索前先检查图谱中是否有数据
            logger.debug(f"检查图谱数据 - database: {graph_database}")
            check_result, _, _ = await graphiti_instance.driver.execute_query(
                """
                MATCH (n)
                RETURN count(n) as node_count
                """
            )
            node_count = check_result[0]['node_count'] if check_result else 0
            logger.info(f"图谱database={graph_database}的节点数量: {node_count}")

            # 检查边的数量
            edge_check_result, _, _ = await graphiti_instance.driver.execute_query(
                """
                MATCH ()-[r]-()
                RETURN count(r) as edge_count
                """
            )
            edge_count = edge_check_result[0]['edge_count'] if edge_check_result else 0
            logger.info(f"图谱database={graph_database}的边数量: {edge_count}")

            # 执行搜索 - 注意：在独立graph中不需要传group_ids参数
            logger.debug(
                f"调用graphiti_instance.search - query: {req.search_query}, num_results: {req.size}")
            result = await graphiti_instance.search(
                query=req.search_query,
                num_results=req.size
            )
            logger.debug(
                f"graphiti_instance.search返回结果数量: {len(result) if result else 0}")

            # 如果结果为空,检查是否有向量索引
            if not result or len(result) == 0:
                logger.warning(f"搜索结果为空 - 检查向量索引")
                # 检查是否有边的嵌入向量
                vector_check_result, _, _ = await graphiti_instance.driver.execute_query(
                    """
                    MATCH ()-[r]-()
                    WHERE r.fact_embedding IS NOT NULL
                    RETURN count(r) as vector_count
                    LIMIT 10
                    """
                )
                vector_count = vector_check_result[0]['vector_count'] if vector_check_result else 0
                logger.warning(f"图谱中有嵌入向量的边数量: {vector_count}")

                # 抽样查看一些边的信息
                sample_edges_result, _, _ = await graphiti_instance.driver.execute_query(
                    """
                    MATCH (n)-[r]-(m)
                    RETURN type(r) as rel_type, r.fact as fact, 
                           r.fact_embedding IS NOT NULL as has_embedding,
                           n.name as source_name, m.name as target_name
                    LIMIT 5
                    """
                )
                logger.info(f"边样本信息: {sample_edges_result}")

            logger.debug(
                f"graphiti_instance.search返回结果数量: {len(result) if result else 0}")

            # 收集需要查询的节点UUID
            node_uid_set = set()
            for r in result:
                logger.debug(
                    f"搜索结果项: fact={r.fact}, name={r.name}, group_id={r.group_id}, source={r.source_node_uuid}, target={r.target_node_uuid}")
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
        finally:
            # 确保关闭 driver 连接
            await self._safe_close_driver(graphiti_instance)

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
