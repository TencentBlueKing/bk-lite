from sanic import Blueprint, json
from sanic_ext import validate
from neco.sanic.auth.api_auth import auth
from neco.llm.rag.graph_rag_entity import *
from neco.llm.rag.graph_rag.graphiti.graphiti_rag import GraphitiRAG
from src.core_settings import core_settings

graph_rag_api_router = Blueprint(
    "graph_rag_api_router", url_prefix="/graph_rag")

rag = GraphitiRAG(
    core_settings.knowledge_graph_host, core_settings.knowledge_graph_username,
    core_settings.knowledge_graph_password, core_settings.knowledge_graph_port,
    core_settings.knowledge_graph_database
)


@graph_rag_api_router.post("/ingest")
@auth.login_required
@validate(json=DocumentIngestRequest)
async def ingest(request, body: DocumentIngestRequest):
    from loguru import logger
    import asyncio

    logger.info(f"接收到文档摄取请求: group_id={body.group_id}, 文档数量={len(body.docs)}")

    try:

        rs = await asyncio.wait_for(rag.ingest(body), timeout=60*60*24)
        logger.info(f"文档摄取请求完成: group_id={body.group_id}")
        return json({"status": "success", "result": rs})
    except asyncio.TimeoutError:
        logger.error(f"文档摄取超时: group_id={body.group_id}, 超时时间: 24小时")
        return json({
            "status": "error",
            "message": "文档摄取操作超时，请减少文档数量或联系管理员"
        }, status=408)
    except Exception as e:
        logger.error(f"文档摄取异常: group_id={body.group_id}, 错误: {e}")
        return json({
            "status": "error",
            "message": f"文档摄取失败: {str(e)}"
        }, status=500)


@graph_rag_api_router.post("/rebuild_community")
@auth.login_required
@validate(json=RebuildCommunityRequest)
async def rebuild_community(request, body: RebuildCommunityRequest):
    await rag.rebuild_community(body)
    return json({"status": "success"})


@graph_rag_api_router.post("/search")
@auth.login_required
@validate(json=DocumentRetrieverRequest)
async def search(request, body: DocumentRetrieverRequest):
    result = await rag.search(body)
    return json({"status": "success", "result": result})


@graph_rag_api_router.post("/list_index_documents")
@auth.login_required
@validate(json=DocumentRetrieverRequest)
async def list_index_documents(request, body: DocumentRetrieverRequest):
    result = await rag.list_index_document(body)
    return json({"status": "success", "result": result})


@graph_rag_api_router.post("/delete_document")
@auth.login_required
@validate(json=DocumentDeleteRequest)
async def delete_document(request, body: DocumentDeleteRequest):
    await rag.delete_document(body)
    return json({"status": "success"})


@graph_rag_api_router.post("/delete_index")
@auth.login_required
@validate(json=IndexDeleteRequest)
async def delete_index(request, body: IndexDeleteRequest):
    await rag.delete_index(body)
    return json({"status": "success"})
