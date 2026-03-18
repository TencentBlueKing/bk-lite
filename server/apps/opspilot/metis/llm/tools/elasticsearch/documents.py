from langchain_core.runnables import RunnableConfig
from langchain_core.tools import tool

from apps.opspilot.metis.llm.tools.elasticsearch.connection import get_es_client
from apps.opspilot.metis.llm.tools.elasticsearch.utils import build_error_response, build_success_response, require_confirm


@tool()
def es_get_document(index: str, doc_id: str, config: RunnableConfig = None):
    """读取 Elasticsearch 单条文档。"""
    try:
        client = get_es_client(config=config)
        return build_success_response(client.get(index=index, id=doc_id), index=index, doc_id=doc_id)
    except Exception as e:
        return build_error_response(e, error_type="not_found")


@tool()
def es_index_document(index: str, document: dict, doc_id: str = None, refresh: bool = False, config: RunnableConfig = None):
    """写入 Elasticsearch 文档。"""
    try:
        client = get_es_client(config=config)
        return build_success_response(client.index(index=index, id=doc_id, body=document, refresh=refresh), index=index, doc_id=doc_id)
    except Exception as e:
        return build_error_response(e)


@tool()
def es_delete_document(index: str, doc_id: str, confirm: bool = False, refresh: bool = False, config: RunnableConfig = None):
    """删除 Elasticsearch 文档，必须显式 confirm=True。"""
    confirm_error = require_confirm(confirm, "delete_document")
    if confirm_error:
        return confirm_error
    try:
        client = get_es_client(config=config)
        return build_success_response(client.delete(index=index, id=doc_id, refresh=refresh), index=index, doc_id=doc_id)
    except Exception as e:
        return build_error_response(e)


@tool()
def es_update_document(index: str, doc_id: str, doc: dict, refresh: bool = False, config: RunnableConfig = None):
    """更新 Elasticsearch 文档。"""
    try:
        client = get_es_client(config=config)
        return build_success_response(client.update(index=index, id=doc_id, body={"doc": doc}, refresh=refresh), index=index, doc_id=doc_id)
    except Exception as e:
        return build_error_response(e)


@tool()
def es_multi_get(index: str, ids: list[str], config: RunnableConfig = None):
    """批量获取 Elasticsearch 文档。"""
    try:
        client = get_es_client(config=config)
        return build_success_response(client.mget(index=index, body={"ids": ids}), index=index)
    except Exception as e:
        return build_error_response(e)


@tool()
def es_bulk(operations: list[dict], confirm: bool = False, refresh: bool = False, config: RunnableConfig = None):
    """执行 Elasticsearch bulk 操作。"""
    confirm_error = require_confirm(confirm, "bulk")
    if confirm_error:
        return confirm_error
    try:
        client = get_es_client(config=config)
        return build_success_response(client.bulk(body=operations, refresh=refresh))
    except Exception as e:
        return build_error_response(e)
