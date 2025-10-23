from django.conf import settings

from apps.core.utils.loader import LanguageLoader
from apps.opspilot.models import GraphChunkMap, KnowledgeGraph
from apps.opspilot.utils.chunk_helper import ChunkHelper


class GraphUtils(ChunkHelper):
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
            return_data.extend([{"page_content": x["page_content"], "metadata": x["metadata"]} for x in res["documents"]])
        return return_data

    @classmethod
    def update_graph(cls, graph_obj, old_doc_list):
        new_doc_list = graph_obj.doc_list[:]
        if graph_obj.status == "failed":
            add_doc_list = new_doc_list[:]
            delete_doc_list = old_doc_list[:]
        else:
            add_doc_list = [i for i in new_doc_list if i not in old_doc_list]
            delete_doc_list = [i for i in old_doc_list if i not in new_doc_list]
        delete_docs = cls.get_documents(delete_doc_list, graph_obj.knowledge_base.knowledge_index_name())
        graph_map_list = dict(GraphChunkMap.objects.filter(knowledge_graph_id=graph_obj.id).values_list("chunk_id", "graph_id"))
        delete_chunk = [i["metadata"]["chunk_id"] for i in delete_docs]
        graph_list = [graph_id for chunk_id, graph_id in graph_map_list.items() if chunk_id in delete_chunk]
        if graph_list:
            try:
                cls.delete_graph_chunk(graph_list)
            except Exception as e:
                return {"result": False, "message": str(e)}
            GraphChunkMap.objects.filter(knowledge_graph_id=graph_obj.id, chunk_id__in=delete_chunk).delete()
        return cls.create_graph(graph_obj, add_doc_list)

    @classmethod
    def create_graph(cls, graph_obj: KnowledgeGraph, doc_list=None):
        if doc_list is None:
            doc_list = graph_obj.doc_list
        url = f"{settings.METIS_SERVER_URL}/api/graph_rag/ingest"
        embed_config = graph_obj.embed_model.decrypted_embed_config
        llm_config = graph_obj.llm_model.decrypted_llm_config
        rerank_config = graph_obj.rerank_model.decrypted_rerank_config_config
        docs = cls.get_documents(doc_list, graph_obj.knowledge_base.knowledge_index_name())
        kwargs = {
            "openai_api_key": llm_config["openai_api_key"],
            "openai_model": llm_config.get("model", graph_obj.llm_model.name),
            "openai_api_base": llm_config["openai_base_url"],
            "rerank_model_base_url": rerank_config["base_url"],
            "rerank_model_name": rerank_config.get("model", graph_obj.rerank_model.name),
            "rerank_model_api_key": rerank_config["api_key"] or " ",
            "group_id": f"graph-{graph_obj.id}",
            "rebuild_community": graph_obj.rebuild_community,
            "embed_model_base_url": embed_config["base_url"],
            "embed_model_api_key": embed_config["api_key"] or " ",
            "embed_model_name": embed_config.get("model", graph_obj.embed_model.name),
            "docs": docs,
        }
        try:
            res = cls.post_chat_server(kwargs, url, timeout=3600)
            if not res:
                loader = LanguageLoader(app="opspilot", default_lang="en")
                message = loader.get("error.graph_create_failed") or "Failed to create graph. Please check the server logs."
                return {"result": False, "message": message}
        except Exception as e:
            return {"result": False, "message": str(e)}
        data_list = [
            GraphChunkMap(graph_id=graph_id, chunk_id=chunk_id, knowledge_graph_id=graph_obj.id) for chunk_id, graph_id in res["result"].items()
        ]
        GraphChunkMap.objects.bulk_create(data_list, batch_size=100)
        return {"result": True}

    @classmethod
    def search_graph(cls, graph_obj: KnowledgeGraph, size=0, search_query=""):
        embed_config = graph_obj.embed_model.decrypted_embed_config
        rerank_config = graph_obj.rerank_model.decrypted_rerank_config_config
        kwargs = {
            "embed_model_base_url": embed_config["base_url"],
            "embed_model_api_key": embed_config["api_key"] or " ",
            "embed_model_name": embed_config.get("model", graph_obj.embed_model.name),
            "rerank_model_base_url": rerank_config["base_url"],
            "rerank_model_name": rerank_config.get("model", graph_obj.rerank_model.name),
            "rerank_model_api_key": rerank_config["api_key"] or " ",
            "size": size,
            "group_ids": [f"graph-{graph_obj.id}"],
            "search_query": search_query,
        }
        url = f"{settings.METIS_SERVER_URL}/api/graph_rag/search"
        try:
            res = cls.post_chat_server(kwargs, url)
            if not res:
                loader = LanguageLoader(app="opspilot", default_lang="en")
                message = loader.get("error.graph_search_failed") or "Failed to search graph. Please check the server logs."
                return {"result": False, "message": message}
        except Exception as e:
            return {"result": False, "message": str(e)}
        return {"result": True, "data": res["result"]}

    @classmethod
    def get_graph(cls, graph_id):
        """
        Retrieve a graph by its ID.
        """
        url = f"{settings.METIS_SERVER_URL}/api/graph_rag/list_index_documents"
        kwargs = {"group_ids": [f"graph-{graph_id}"]}
        try:
            res = cls.post_chat_server(kwargs, url)
            if not res:
                loader = LanguageLoader(app="opspilot", default_lang="en")
                message = loader.get("error.graph_search_failed") or "Failed to search graph. Please check the server logs."
                return {"result": False, "message": message}
        except Exception as e:
            return {"result": False, "message": str(e)}
        return_data = {"result": True, "data": res["result"]}
        return return_data

    @classmethod
    def delete_graph(cls, graph_obj: KnowledgeGraph):
        url = f"{settings.METIS_SERVER_URL}/api/graph_rag/delete_index"
        kwargs = {"group_id": f"graph-{graph_obj.id}"}
        res = cls.post_chat_server(kwargs, url)
        if not res or res.get("status", "fail") != "success":
            raise Exception("Failed to Delete graph")

    @classmethod
    def delete_graph_chunk(cls, chunk_ids):
        """
        Delete all chunks associated with a specific graph.
        """
        url = f"{settings.METIS_SERVER_URL}/api/graph_rag/delete_document"
        kwargs = {"uuids": chunk_ids}
        res = cls.post_chat_server(kwargs, url)
        if not res or res.get("status", "fail") != "success":
            raise Exception("Failed to Delete graph chunk")

    @classmethod
    def rebuild_graph_community(cls, graph_obj: KnowledgeGraph):
        url = f"{settings.METIS_SERVER_URL}/api/graph_rag/rebuild_community"
        embed_config = graph_obj.embed_model.decrypted_embed_config
        rerank_config = graph_obj.rerank_model.decrypted_rerank_config_config
        llm_config = graph_obj.llm_model.decrypted_llm_config
        kwargs = {
            "openai_api_key": llm_config["openai_api_key"],
            "openai_model": llm_config.get("model", graph_obj.llm_model.name),
            "openai_api_base": llm_config["openai_base_url"],
            "group_ids": [f"graph-{graph_obj.id}"],
            "embed_model_base_url": embed_config["base_url"],
            "embed_model_api_key": embed_config["api_key"] or " ",
            "embed_model_name": embed_config.get("model", graph_obj.embed_model.name),
            "rerank_model_base_url": rerank_config["base_url"],
            "rerank_model_name": rerank_config.get("model", graph_obj.rerank_model.name),
            "rerank_model_api_key": rerank_config["api_key"] or " ",
        }
        res = cls.post_chat_server(kwargs, url)
        if not res or res.get("status", "fail") != "success":
            return {"result": False}
        return {"result": True}
