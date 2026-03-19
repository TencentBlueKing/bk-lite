from langchain_core.runnables import RunnableConfig
from langchain_core.tools import tool

from apps.opspilot.metis.llm.tools.elasticsearch.connection import get_es_client
from apps.opspilot.metis.llm.tools.elasticsearch.utils import build_error_response, build_success_response


@tool()
def es_ping(config: RunnableConfig = None):
    """检查 Elasticsearch 连通性。"""
    try:
        client = get_es_client(config=config)
        return build_success_response({"pong": client.ping()})
    except Exception as e:
        return build_error_response(e, error_type="connection_error")


@tool()
def es_info(config: RunnableConfig = None):
    """获取 Elasticsearch 基础信息。"""
    try:
        client = get_es_client(config=config)
        return build_success_response(client.info())
    except Exception as e:
        return build_error_response(e)


@tool()
def es_cluster_health(index: str = None, config: RunnableConfig = None):
    """获取 Elasticsearch 集群健康状态。"""
    try:
        client = get_es_client(config=config)
        if index:
            return build_success_response(client.cluster.health(index=index), index=index)
        return build_success_response(client.cluster.health())
    except Exception as e:
        return build_error_response(e)


@tool()
def es_cluster_stats(config: RunnableConfig = None):
    """获取 Elasticsearch 集群统计信息。"""
    try:
        client = get_es_client(config=config)
        return build_success_response(client.cluster.stats())
    except Exception as e:
        return build_error_response(e)


@tool()
def es_nodes_info(config: RunnableConfig = None):
    """获取 Elasticsearch 节点信息。"""
    try:
        client = get_es_client(config=config)
        return build_success_response(client.nodes.info())
    except Exception as e:
        return build_error_response(e)


@tool()
def es_nodes_stats(config: RunnableConfig = None):
    """获取 Elasticsearch 节点统计信息。"""
    try:
        client = get_es_client(config=config)
        return build_success_response(client.nodes.stats())
    except Exception as e:
        return build_error_response(e)
