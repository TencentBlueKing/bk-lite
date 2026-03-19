from langchain_core.runnables import RunnableConfig
from langchain_core.tools import tool

from apps.opspilot.metis.llm.tools.elasticsearch.connection import get_es_client
from apps.opspilot.metis.llm.tools.elasticsearch.utils import build_error_response, build_success_response


@tool()
def es_get_alias(name: str = None, index: str = None, config: RunnableConfig = None):
    """获取 Elasticsearch alias 信息。"""
    try:
        client = get_es_client(config=config)
        return build_success_response(client.indices.get_alias(name=name, index=index))
    except Exception as e:
        return build_error_response(e)


@tool()
def es_alias_exists(name: str, index: str = None, config: RunnableConfig = None):
    """检查 alias 是否存在。"""
    try:
        client = get_es_client(config=config)
        return build_success_response({"name": name, "exists": client.indices.exists_alias(name=name, index=index)})
    except Exception as e:
        return build_error_response(e)


@tool()
def es_update_aliases(actions: list[dict], config: RunnableConfig = None):
    """批量更新 Elasticsearch aliases。"""
    try:
        client = get_es_client(config=config)
        return build_success_response(client.indices.update_aliases(body={"actions": actions}))
    except Exception as e:
        return build_error_response(e)
