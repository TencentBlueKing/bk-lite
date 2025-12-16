import asyncio

from langchain_core.documents import Document
from loguru import logger

from apps.core.utils.loader import LanguageLoader
from apps.opspilot.metis.llm.rag.graph_rag.graphiti.graphiti_rag import GraphitiRAG
from apps.opspilot.metis.llm.rag.graph_rag_entity import (
    DocumentDeleteRequest,
    DocumentIngestRequest,
    DocumentRetrieverRequest,
    IndexDeleteRequest,
    RebuildCommunityRequest,
)
from apps.opspilot.models import GraphChunkMap, KnowledgeGraph
from apps.opspilot.utils.chunk_helper import ChunkHelper


class GraphUtils(ChunkHelper):
    @staticmethod
    def _run_async(coro):
        """运行异步协程的辅助方法，将异步方法转为同步调用"""
        try:
            # 尝试获取当前事件循环
            loop = asyncio.get_event_loop()
            if loop.is_running():
                # 事件循环已在运行，需要创建新的事件循环
                raise RuntimeError("Event loop is already running")
        except RuntimeError:
            # 没有事件循环或已在运行，创建新的
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            should_close = True
        else:
            # 使用现有事件循环
            should_close = False

        try:
            # 运行协程直到完成
            return loop.run_until_complete(coro)
        finally:
            # 只关闭我们创建的事件循环
            if should_close:
                # 给后台任务一点时间完成清理
                try:
                    pending = asyncio.all_tasks(loop)
                    for task in pending:
                        task.cancel()
                    # 运行事件循环直到所有任务被取消
                    loop.run_until_complete(asyncio.gather(
                        *pending, return_exceptions=True))
                except Exception:
                    pass
                finally:
                    loop.close()

    @classmethod
    def get_documents(cls, doc_list: list, index_name: str):
        """
        Convert a list of document IDs to a list of documents with metadata.
        """
        return_data = []
        for i in doc_list:
            res = cls.get_document_es_chunk(
                index_name,
                page=1,
                page_size=0,
                search_text="",
                metadata_filter={"is_doc": "1", "knowledge_id": str(i["id"])},
                get_count=False,
            )
            return_data.extend([{"page_content": x["page_content"],
                               "metadata": x["metadata"]} for x in res["documents"]])
        return return_data

    @classmethod
    def update_graph(cls, graph_obj, old_doc_list):
        new_doc_list = graph_obj.doc_list[:]
        if graph_obj.status == "failed":
            add_doc_list = new_doc_list[:]
            delete_doc_list = old_doc_list[:]
        else:
            add_doc_list = [i for i in new_doc_list if i not in old_doc_list]
            delete_doc_list = [
                i for i in old_doc_list if i not in new_doc_list]
        delete_docs = cls.get_documents(
            delete_doc_list, graph_obj.knowledge_base.knowledge_index_name())
        graph_map_list = dict(GraphChunkMap.objects.filter(
            knowledge_graph_id=graph_obj.id).values_list("chunk_id", "graph_id"))
        delete_chunk = [i["metadata"]["chunk_id"] for i in delete_docs]
        graph_list = [graph_id for chunk_id,
                      graph_id in graph_map_list.items() if chunk_id in delete_chunk]
        if graph_list:
            try:
                cls.delete_graph_chunk(graph_obj, graph_list)
            except Exception as e:
                return {"result": False, "message": str(e)}
            GraphChunkMap.objects.filter(
                knowledge_graph_id=graph_obj.id, chunk_id__in=delete_chunk).delete()
        return cls.create_graph(graph_obj, add_doc_list)

    @classmethod
    def create_graph(cls, graph_obj: KnowledgeGraph, doc_list=None):
        """创建图谱"""
        if doc_list is None:
            doc_list = graph_obj.doc_list

        embed_config = graph_obj.embed_model.decrypted_embed_config
        llm_config = graph_obj.llm_model.decrypted_llm_config
        rerank_config = graph_obj.rerank_model.decrypted_rerank_config_config
        docs = cls.get_documents(
            doc_list, graph_obj.knowledge_base.knowledge_index_name())

        # 将字典转换为 Document 对象
        doc_objects = [Document(
            page_content=doc["page_content"], metadata=doc["metadata"]) for doc in docs]

        # 构建请求对象
        request = DocumentIngestRequest(
            openai_api_key=llm_config["openai_api_key"],
            openai_model=llm_config.get("model", graph_obj.llm_model.name),
            openai_api_base=llm_config["openai_base_url"],
            rerank_model_base_url=rerank_config["base_url"],
            rerank_model_name=rerank_config.get(
                "model", graph_obj.rerank_model.name),
            rerank_model_api_key=rerank_config["api_key"] or " ",
            group_id=f"graph-{graph_obj.id}",
            rebuild_community=graph_obj.rebuild_community,
            embed_model_base_url=embed_config["base_url"],
            embed_model_api_key=embed_config["api_key"] or " ",
            embed_model_name=embed_config.get(
                "model", graph_obj.embed_model.name),
            docs=doc_objects,
        )

        try:
            rag = GraphitiRAG()
            res = asyncio.run(rag.ingest(request))

            if not res or "mapping" not in res:
                loader = LanguageLoader(app="opspilot", default_lang="en")
                message = loader.get(
                    "error.graph_create_failed") or "Failed to create graph. Please check the server logs."
                return {"result": False, "message": message}

            # 批量创建映射关系
            data_list = [
                GraphChunkMap(graph_id=graph_id, chunk_id=chunk_id, knowledge_graph_id=graph_obj.id) for chunk_id, graph_id in res["mapping"].items()
            ]
            GraphChunkMap.objects.bulk_create(data_list, batch_size=100)

            logger.info(
                f"图谱创建成功: 成功={res.get('success_count')}, 失败={res.get('failed_count')}, 总数={res.get('total_count')}")
            return {"result": True}

        except Exception as e:
            logger.error(f"创建图谱失败: {e}")
            return {"result": False, "message": str(e)}

    @classmethod
    def search_graph(cls, graph_obj: KnowledgeGraph, size=0, search_query=""):
        """搜索图谱"""
        embed_config = graph_obj.embed_model.decrypted_embed_config
        rerank_config = graph_obj.rerank_model.decrypted_rerank_config_config

        request = DocumentRetrieverRequest(
            embed_model_base_url=embed_config["base_url"],
            embed_model_api_key=embed_config["api_key"] or " ",
            embed_model_name=embed_config.get(
                "model", graph_obj.embed_model.name),
            rerank_model_base_url=rerank_config["base_url"],
            rerank_model_name=rerank_config.get(
                "model", graph_obj.rerank_model.name),
            rerank_model_api_key=rerank_config["api_key"] or " ",
            size=size,
            group_ids=[f"graph-{graph_obj.id}"],
            search_query=search_query,
        )

        try:
            rag = GraphitiRAG()
            res = cls._run_async(rag.search(request))

            if res is None:
                loader = LanguageLoader(app="opspilot", default_lang="en")
                message = loader.get(
                    "error.graph_search_failed") or "Failed to search graph. Please check the server logs."
                return {"result": False, "message": message}

            return {"result": True, "data": res}

        except Exception as e:
            logger.error(f"搜索图谱失败: {e}")
            return {"result": False, "message": str(e)}

    @classmethod
    def get_graph(cls, graph_id):
        """获取图谱文档列表"""
        request = DocumentRetrieverRequest(group_ids=[f"graph-{graph_id}"])

        try:
            rag = GraphitiRAG()
            res = cls._run_async(rag.list_index_document(request))

            if res is None:
                loader = LanguageLoader(app="opspilot", default_lang="en")
                message = loader.get(
                    "error.graph_search_failed") or "Failed to search graph. Please check the server logs."
                return {"result": False, "message": message}

            return {"result": True, "data": res}

        except Exception as e:
            logger.error(f"获取图谱失败: {e}")
            return {"result": False, "message": str(e)}

    @classmethod
    def delete_graph(cls, graph_obj: KnowledgeGraph):
        """删除图谱"""
        request = IndexDeleteRequest(group_id=f"graph-{graph_obj.id}")

        try:
            rag = GraphitiRAG()
            cls._run_async(rag.delete_index(request))
            logger.info(f"成功删除图谱: graph-{graph_obj.id}")
        except Exception as e:
            logger.error(f"删除图谱失败: {e}")
            raise Exception("Failed to Delete graph")

    @classmethod
    def delete_graph_chunk(cls, graph_obj: KnowledgeGraph, chunk_ids):
        """删除图谱分块"""
        request = DocumentDeleteRequest(
            group_id=f"graph-{graph_obj.id}",
            uuids=chunk_ids
        )

        try:
            rag = GraphitiRAG()
            cls._run_async(rag.delete_document(request))
            logger.info(f"成功删除图谱分块: {len(chunk_ids)}个")
        except Exception as e:
            logger.error(f"删除图谱分块失败: {e}")
            raise Exception("Failed to Delete graph chunk")

    @classmethod
    def rebuild_graph_community(cls, graph_obj: KnowledgeGraph):
        """重建图谱社区"""
        embed_config = graph_obj.embed_model.decrypted_embed_config
        rerank_config = graph_obj.rerank_model.decrypted_rerank_config_config
        llm_config = graph_obj.llm_model.decrypted_llm_config

        request = RebuildCommunityRequest(
            openai_api_key=llm_config["openai_api_key"],
            openai_model=llm_config.get("model", graph_obj.llm_model.name),
            openai_api_base=llm_config["openai_base_url"],
            group_ids=[f"graph-{graph_obj.id}"],
            embed_model_base_url=embed_config["base_url"],
            embed_model_api_key=embed_config["api_key"] or " ",
            embed_model_name=embed_config.get(
                "model", graph_obj.embed_model.name),
            rerank_model_base_url=rerank_config["base_url"],
            rerank_model_name=rerank_config.get(
                "model", graph_obj.rerank_model.name),
            rerank_model_api_key=rerank_config["api_key"] or " ",
        )

        try:
            rag = GraphitiRAG()
            cls._run_async(rag.rebuild_community(request))
            logger.info(f"成功重建图谱社区: graph-{graph_obj.id}")
            return {"result": True}
        except Exception as e:
            logger.error(f"重建图谱社区失败: {e}")
            return {"result": False}
