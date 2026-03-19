from langchain_core.runnables import RunnableConfig
from langchain_core.tools import tool

from apps.opspilot.metis.llm.tools.elasticsearch.connection import get_es_client
from apps.opspilot.metis.llm.tools.elasticsearch.utils import build_error_response, build_success_response


@tool()
def es_get_mapping(index: str, config: RunnableConfig = None):
    """获取 Elasticsearch 索引 mapping。"""
    try:
        client = get_es_client(config=config)
        return build_success_response(client.indices.get_mapping(index=index), index=index)
    except Exception as e:
        return build_error_response(e)


@tool()
def es_get_settings(index: str, config: RunnableConfig = None):
    """获取 Elasticsearch 索引 settings。"""
    try:
        client = get_es_client(config=config)
        return build_success_response(client.indices.get_settings(index=index), index=index)
    except Exception as e:
        return build_error_response(e)


@tool()
def es_put_mapping(index: str, body: dict, config: RunnableConfig = None):
    """更新 Elasticsearch 索引 mapping。"""
    try:
        client = get_es_client(config=config)
        return build_success_response(client.indices.put_mapping(index=index, body=body), index=index)
    except Exception as e:
        return build_error_response(e)


@tool()
def es_put_settings(index: str, body: dict, config: RunnableConfig = None):
    """更新 Elasticsearch 索引 settings。"""
    try:
        client = get_es_client(config=config)
        return build_success_response(client.indices.put_settings(index=index, body=body), index=index)
    except Exception as e:
        return build_error_response(e)


@tool()
def es_field_caps(index: str, fields: list[str], config: RunnableConfig = None):
    """获取 Elasticsearch 字段能力信息。"""
    try:
        client = get_es_client(config=config)
        return build_success_response(client.field_caps(index=index, fields=fields), index=index)
    except Exception as e:
        return build_error_response(e)
