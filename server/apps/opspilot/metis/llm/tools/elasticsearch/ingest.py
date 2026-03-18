from langchain_core.runnables import RunnableConfig
from langchain_core.tools import tool

from apps.opspilot.metis.llm.tools.elasticsearch.connection import get_es_client
from apps.opspilot.metis.llm.tools.elasticsearch.utils import build_error_response, build_success_response, require_confirm


@tool()
def es_get_pipeline(pipeline_id: str = None, config: RunnableConfig = None):
    """获取 Elasticsearch ingest pipeline。"""
    try:
        client = get_es_client(config=config)
        return build_success_response(client.ingest.get_pipeline(id=pipeline_id))
    except Exception as e:
        return build_error_response(e)


@tool()
def es_put_pipeline(pipeline_id: str, body: dict, config: RunnableConfig = None):
    """创建或更新 Elasticsearch ingest pipeline。"""
    try:
        client = get_es_client(config=config)
        return build_success_response(client.ingest.put_pipeline(id=pipeline_id, body=body), pipeline_id=pipeline_id)
    except Exception as e:
        return build_error_response(e)


@tool()
def es_delete_pipeline(pipeline_id: str, confirm: bool = False, config: RunnableConfig = None):
    """删除 Elasticsearch ingest pipeline，必须显式 confirm=True。"""
    confirm_error = require_confirm(confirm, "delete_pipeline")
    if confirm_error:
        return confirm_error
    try:
        client = get_es_client(config=config)
        return build_success_response(client.ingest.delete_pipeline(id=pipeline_id), pipeline_id=pipeline_id)
    except Exception as e:
        return build_error_response(e)


@tool()
def es_simulate_pipeline(body: dict, pipeline_id: str = None, config: RunnableConfig = None):
    """模拟执行 Elasticsearch ingest pipeline。"""
    try:
        client = get_es_client(config=config)
        return build_success_response(client.ingest.simulate(id=pipeline_id, body=body), pipeline_id=pipeline_id)
    except Exception as e:
        return build_error_response(e)
