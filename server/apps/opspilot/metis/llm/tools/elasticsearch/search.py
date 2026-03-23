from langchain_core.runnables import RunnableConfig
from langchain_core.tools import tool

from apps.opspilot.metis.llm.tools.elasticsearch.connection import get_es_client
from apps.opspilot.metis.llm.tools.elasticsearch.utils import build_error_response, build_success_response


@tool()
def es_search(index: str, query: dict, size: int = 10, from_: int = 0, config: RunnableConfig = None):
    """执行 Elasticsearch 搜索查询。"""
    try:
        client = get_es_client(config=config)
        response = client.search(index=index, body={"query": query}, size=size, from_=from_)
        hits = response.get("hits", {})
        total = hits.get("total", {})
        total_value = total.get("value") if isinstance(total, dict) else total
        return build_success_response(
            {
                "took": response.get("took"),
                "timed_out": response.get("timed_out"),
                "total": total_value,
                "hits": hits.get("hits", []),
                "aggregations": response.get("aggregations"),
            },
            index=index,
        )
    except Exception as e:
        return build_error_response(e)


@tool()
def es_count(index: str, query: dict = None, config: RunnableConfig = None):
    """统计满足条件的文档数量。"""
    try:
        client = get_es_client(config=config)
        return build_success_response(client.count(index=index, body={"query": query or {"match_all": {}}}), index=index)
    except Exception as e:
        return build_error_response(e)


@tool()
def es_validate_query(index: str, query: dict, explain: bool = False, config: RunnableConfig = None):
    """校验 Elasticsearch 查询是否合法。"""
    try:
        client = get_es_client(config=config)
        return build_success_response(client.indices.validate_query(index=index, body={"query": query}, explain=explain), index=index)
    except Exception as e:
        return build_error_response(e)


@tool()
def es_multi_search(searches: list[dict], config: RunnableConfig = None):
    """执行 Elasticsearch msearch。"""
    try:
        client = get_es_client(config=config)
        return build_success_response(client.msearch(body=searches))
    except Exception as e:
        return build_error_response(e)


@tool()
def es_explain(index: str, doc_id: str, query: dict, config: RunnableConfig = None):
    """解释指定文档为何匹配查询。"""
    try:
        client = get_es_client(config=config)
        return build_success_response(client.explain(index=index, id=doc_id, body={"query": query}), index=index, doc_id=doc_id)
    except Exception as e:
        return build_error_response(e)


@tool()
def es_search_template(index: str, source: dict, params: dict = None, config: RunnableConfig = None):
    """执行 Elasticsearch search template。"""
    try:
        client = get_es_client(config=config)
        return build_success_response(client.search_template(index=index, body={"source": source, "params": params or {}}), index=index)
    except Exception as e:
        return build_error_response(e)


@tool()
def es_knn_search(index: str, knn: dict, source: list[str] = None, config: RunnableConfig = None):
    """执行 Elasticsearch kNN 搜索。"""
    try:
        client = get_es_client(config=config)
        return build_success_response(client.search(index=index, body={"knn": knn, "_source": source or True}), index=index)
    except Exception as e:
        return build_error_response(e)
