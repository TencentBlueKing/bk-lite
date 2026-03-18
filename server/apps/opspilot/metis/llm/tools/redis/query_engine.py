from typing import List, Optional

import numpy as np
from langchain_core.runnables import RunnableConfig
from langchain_core.tools import tool
from redis.commands.search.field import VectorField
from redis.commands.search.query import Query
from redis.exceptions import RedisError

try:
    from redis.commands.search.index_definition import IndexDefinition
except ImportError:
    from redis.commands.search.indexDefinition import IndexDefinition

from apps.opspilot.metis.llm.tools.redis.connection import get_redis_connection
from apps.opspilot.metis.llm.tools.redis.utils import build_error_response, build_success_response


@tool()
def redis_get_indexes(config: RunnableConfig = None):
    """获取 Redis 当前已有的搜索索引列表。"""
    try:
        client = get_redis_connection(config=config)
        return build_success_response(client.execute_command("FT._LIST"))
    except RedisError as e:
        return build_error_response(e, error_type="unsupported_feature")


@tool()
def redis_get_index_info(index_name: str, config: RunnableConfig = None):
    """获取指定 Redis 搜索索引的详细信息。"""
    try:
        client = get_redis_connection(config=config)
        return build_success_response(client.ft(index_name).info())
    except RedisError as e:
        return build_error_response(e, error_type="unsupported_feature")


@tool()
def redis_get_indexed_keys_number(index_name: str, config: RunnableConfig = None):
    """获取指定 Redis 搜索索引已索引的 key 数量。"""
    try:
        client = get_redis_connection(config=config)
        total = client.ft(index_name).search(Query("*")).total
        return build_success_response({"index_name": index_name, "total": total})
    except RedisError as e:
        return build_error_response(e, error_type="unsupported_feature")


@tool()
def redis_create_vector_index_hash(
    index_name: str = "vector_index",
    prefix: str = "doc:",
    vector_field: str = "vector",
    dim: int = 1536,
    distance_metric: str = "COSINE",
    config: RunnableConfig = None,
):
    """为 Redis hash 创建 HNSW 向量索引。"""
    try:
        client = get_redis_connection(config=config)
        index_def = IndexDefinition(prefix=[prefix])
        schema = VectorField(vector_field, "HNSW", {"TYPE": "FLOAT32", "DIM": dim, "DISTANCE_METRIC": distance_metric})
        client.ft(index_name).create_index([schema], definition=index_def)
        return build_success_response({"index_name": index_name, "created": True})
    except RedisError as e:
        return build_error_response(e, error_type="unsupported_feature")


@tool()
def redis_vector_search_hash(
    query_vector: List[float],
    index_name: str = "vector_index",
    vector_field: str = "vector",
    k: int = 5,
    return_fields: Optional[List[str]] = None,
    config: RunnableConfig = None,
):
    """对 Redis hash 向量索引执行 KNN 搜索。"""
    try:
        client = get_redis_connection(config=config)
        vector_blob = np.array(query_vector, dtype=np.float32).tobytes()
        query = (
            Query(f"*=>[KNN {k} @{vector_field} $vec_param AS score]")
            .sort_by("score")
            .paging(0, k)
            .return_fields("id", "score", *(return_fields or []))
            .dialect(2)
        )
        results = client.ft(index_name).search(query, query_params={"vec_param": vector_blob})
        return build_success_response([doc.__dict__ for doc in results.docs])
    except RedisError as e:
        return build_error_response(e, error_type="unsupported_feature")


@tool()
def redis_hybrid_search(
    query_vector: List[float],
    filter_expression: str = "*",
    index_name: str = "vector_index",
    vector_field: str = "vector",
    k: int = 5,
    return_fields: Optional[List[str]] = None,
    config: RunnableConfig = None,
):
    """执行 Redis 混合检索：过滤表达式 + KNN 向量搜索。"""
    try:
        client = get_redis_connection(config=config)
        vector_blob = np.array(query_vector, dtype=np.float32).tobytes()
        query = (
            Query(f"({filter_expression})=>[KNN {k} @{vector_field} $vec_param AS score]")
            .sort_by("score")
            .paging(0, k)
            .return_fields("id", "score", *(return_fields or []))
            .dialect(2)
        )
        results = client.ft(index_name).search(query, query_params={"vec_param": vector_blob})
        return build_success_response([doc.__dict__ for doc in results.docs])
    except RedisError as e:
        return build_error_response(e, error_type="unsupported_feature")
