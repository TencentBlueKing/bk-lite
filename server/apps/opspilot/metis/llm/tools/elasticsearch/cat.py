from langchain_core.runnables import RunnableConfig
from langchain_core.tools import tool

from apps.opspilot.metis.llm.tools.elasticsearch.connection import get_es_client
from apps.opspilot.metis.llm.tools.elasticsearch.utils import build_error_response, build_success_response


@tool()
def es_cat_indices(index: str = "*", config: RunnableConfig = None):
    """获取 Elasticsearch cat indices 结果（结构化）。"""
    try:
        client = get_es_client(config=config)
        return build_success_response(client.cat.indices(format="json", index=index), index=index)
    except Exception as e:
        return build_error_response(e)


@tool()
def es_cat_shards(index: str = "*", config: RunnableConfig = None):
    """获取 Elasticsearch cat shards 结果（结构化）。"""
    try:
        client = get_es_client(config=config)
        return build_success_response(client.cat.shards(format="json", index=index), index=index)
    except Exception as e:
        return build_error_response(e)


@tool()
def es_cat_nodes(config: RunnableConfig = None):
    """获取 Elasticsearch cat nodes 结果（结构化）。"""
    try:
        client = get_es_client(config=config)
        return build_success_response(client.cat.nodes(format="json"))
    except Exception as e:
        return build_error_response(e)


@tool()
def es_cat_aliases(name: str = "*", config: RunnableConfig = None):
    """获取 Elasticsearch cat aliases 结果（结构化）。"""
    try:
        client = get_es_client(config=config)
        return build_success_response(client.cat.aliases(format="json", name=name), name=name)
    except Exception as e:
        return build_error_response(e)


@tool()
def es_cat_allocation(config: RunnableConfig = None):
    """获取 Elasticsearch cat allocation 结果（结构化）。"""
    try:
        client = get_es_client(config=config)
        return build_success_response(client.cat.allocation(format="json"))
    except Exception as e:
        return build_error_response(e)


@tool()
def es_cat_recovery(index: str = "*", config: RunnableConfig = None):
    """获取 Elasticsearch cat recovery 结果（结构化）。"""
    try:
        client = get_es_client(config=config)
        return build_success_response(client.cat.recovery(format="json", index=index), index=index)
    except Exception as e:
        return build_error_response(e)
