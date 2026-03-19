from langchain_core.runnables import RunnableConfig
from langchain_core.tools import tool

from apps.opspilot.metis.llm.tools.elasticsearch.connection import get_es_client
from apps.opspilot.metis.llm.tools.elasticsearch.utils import build_error_response, build_success_response, require_confirm


@tool()
def es_get_snapshot_repositories(config: RunnableConfig = None):
    """获取 Elasticsearch snapshot repositories。"""
    try:
        client = get_es_client(config=config)
        return build_success_response(client.snapshot.get_repository())
    except Exception as e:
        return build_error_response(e)


@tool()
def es_create_snapshot_repository(repository: str, body: dict, config: RunnableConfig = None):
    """创建 Elasticsearch snapshot repository。"""
    try:
        client = get_es_client(config=config)
        return build_success_response(client.snapshot.create_repository(repository=repository, body=body), repository=repository)
    except Exception as e:
        return build_error_response(e)


@tool()
def es_get_snapshots(repository: str, snapshot: str = "*", config: RunnableConfig = None):
    """获取 Elasticsearch snapshots 列表。"""
    try:
        client = get_es_client(config=config)
        return build_success_response(client.snapshot.get(repository=repository, snapshot=snapshot), repository=repository)
    except Exception as e:
        return build_error_response(e)


@tool()
def es_create_snapshot(repository: str, snapshot: str, body: dict = None, config: RunnableConfig = None):
    """创建 Elasticsearch snapshot。"""
    try:
        client = get_es_client(config=config)
        return build_success_response(
            client.snapshot.create(repository=repository, snapshot=snapshot, body=body or {}), repository=repository, snapshot=snapshot
        )
    except Exception as e:
        return build_error_response(e)


@tool()
def es_restore_snapshot(repository: str, snapshot: str, body: dict = None, confirm: bool = False, config: RunnableConfig = None):
    """恢复 Elasticsearch snapshot，必须显式 confirm=True。"""
    confirm_error = require_confirm(confirm, "restore_snapshot")
    if confirm_error:
        return confirm_error
    try:
        client = get_es_client(config=config)
        return build_success_response(
            client.snapshot.restore(repository=repository, snapshot=snapshot, body=body or {}), repository=repository, snapshot=snapshot
        )
    except Exception as e:
        return build_error_response(e)
