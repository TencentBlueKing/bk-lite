from langchain_core.runnables import RunnableConfig
from langchain_core.tools import tool

from apps.opspilot.metis.llm.tools.elasticsearch.connection import get_es_client
from apps.opspilot.metis.llm.tools.elasticsearch.utils import build_error_response, build_success_response, require_confirm


@tool()
def es_list_indices(config: RunnableConfig = None):
    """列出 Elasticsearch 索引。"""
    try:
        client = get_es_client(config=config)
        return build_success_response(client.indices.get_alias(index="*"))
    except Exception as e:
        return build_error_response(e)


@tool()
def es_get_index(index: str, config: RunnableConfig = None):
    """获取指定索引的详细信息。"""
    try:
        client = get_es_client(config=config)
        return build_success_response(client.indices.get(index=index), index=index)
    except Exception as e:
        return build_error_response(e, error_type="not_found")


@tool()
def es_index_exists(index: str, config: RunnableConfig = None):
    """检查指定索引是否存在。"""
    try:
        client = get_es_client(config=config)
        return build_success_response({"index": index, "exists": client.indices.exists(index=index)})
    except Exception as e:
        return build_error_response(e)


@tool()
def es_create_index(index: str, body: dict = None, config: RunnableConfig = None):
    """创建 Elasticsearch 索引。"""
    try:
        client = get_es_client(config=config)
        return build_success_response(client.indices.create(index=index, body=body or {}), index=index)
    except Exception as e:
        return build_error_response(e)


@tool()
def es_delete_index(index: str, confirm: bool = False, config: RunnableConfig = None):
    """删除 Elasticsearch 索引，必须显式 confirm=True。"""
    confirm_error = require_confirm(confirm, "delete_index")
    if confirm_error:
        return confirm_error
    try:
        client = get_es_client(config=config)
        return build_success_response(client.indices.delete(index=index), index=index)
    except Exception as e:
        return build_error_response(e)


@tool()
def es_open_index(index: str, config: RunnableConfig = None):
    """打开已关闭的 Elasticsearch 索引。"""
    try:
        client = get_es_client(config=config)
        return build_success_response(client.indices.open(index=index), index=index)
    except Exception as e:
        return build_error_response(e)


@tool()
def es_close_index(index: str, confirm: bool = False, config: RunnableConfig = None):
    """关闭 Elasticsearch 索引，必须显式 confirm=True。"""
    confirm_error = require_confirm(confirm, "close_index")
    if confirm_error:
        return confirm_error
    try:
        client = get_es_client(config=config)
        return build_success_response(client.indices.close(index=index), index=index)
    except Exception as e:
        return build_error_response(e)


@tool()
def es_refresh_index(index: str, config: RunnableConfig = None):
    """刷新 Elasticsearch 索引。"""
    try:
        client = get_es_client(config=config)
        return build_success_response(client.indices.refresh(index=index), index=index)
    except Exception as e:
        return build_error_response(e)


@tool()
def es_forcemerge_index(index: str, max_num_segments: int = 1, confirm: bool = False, config: RunnableConfig = None):
    """对 Elasticsearch 索引执行 force merge。"""
    confirm_error = require_confirm(confirm, "forcemerge_index")
    if confirm_error:
        return confirm_error
    try:
        client = get_es_client(config=config)
        return build_success_response(client.indices.forcemerge(index=index, max_num_segments=max_num_segments), index=index)
    except Exception as e:
        return build_error_response(e)


@tool()
def es_index_stats(index: str, config: RunnableConfig = None):
    """获取 Elasticsearch 索引统计信息。"""
    try:
        client = get_es_client(config=config)
        return build_success_response(client.indices.stats(index=index), index=index)
    except Exception as e:
        return build_error_response(e)
