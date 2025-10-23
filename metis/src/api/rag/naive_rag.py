import json as js
import tempfile
from typing import Dict, Any

from loguru import logger
from sanic import Blueprint, json
from sanic_ext import validate

from neco.llm.loader.raw_loader import RawLoader
from neco.llm.loader.website_loader import WebSiteLoader
from neco.sanic.auth.api_auth import auth
from src.core_settings import core_settings
from neco.llm.rag.naive_rag_entity import *
from neco.llm.rag.naive_rag.pgvector.pgvector_rag import PgvectorRag
from src.services.rag_service import RagService

naive_rag_api_router = Blueprint("naive_rag_api_router", url_prefix="/rag")

rag = PgvectorRag(core_settings.db_uri)


def _parse_common_ingest_params(request) -> Dict[str, Any]:
    """解析 ingest 接口的公共参数"""
    return {
        'is_preview': request.form.get('preview', 'false').lower() == 'true',
        'chunk_mode': request.form.get('chunk_mode'),
        'metadata': js.loads(request.form.get('metadata', '{}')),
        'knowledge_base_id': request.form.get('knowledge_base_id'),
        'embed_model_base_url': request.form.get('embed_model_base_url'),
        'embed_model_api_key': request.form.get('embed_model_api_key'),
        'embed_model_name': request.form.get('embed_model_name'),
        'knowledge_id': request.form.get('knowledge_id')
    }


def _process_documents_pipeline(docs, title, params, content_type, request):
    """
    统一的文档处理流水线

    Args:
        docs: 原始文档列表
        title: 文档标题
        params: 从 _parse_common_ingest_params 获取的参数字典
        content_type: 内容类型描述（用于日志）
        request: HTTP请求对象

    Returns:
        JSON响应
    """
    # 处理文档元数据
    docs = RagService.prepare_documents_metadata(
        docs,
        is_preview=params['is_preview'],
        title=title,
        knowledge_id=params['knowledge_id']
    )

    # 执行文档分块并记录日志
    chunked_docs = RagService.perform_chunking(
        docs, params['chunk_mode'], request, params['is_preview'], content_type
    )

    # 处理预览模式
    if params['is_preview']:
        return json({
            "status": "success",
            "message": "",
            "documents": RagService.serialize_documents(chunked_docs),
            "chunks_size": len(chunked_docs)
        })

    # 执行文档存储
    logger.debug(
        f"开始存储{content_type}{len(chunked_docs)}个文档分块，将自动添加created_time字段")
    RagService.store_documents_to_pg(
        chunked_docs=chunked_docs,
        knowledge_base_id=params['knowledge_base_id'],
        embed_model_base_url=params['embed_model_base_url'],
        embed_model_api_key=params['embed_model_api_key'],
        embed_model_name=params['embed_model_name'],
        metadata=params['metadata']
    )

    return json({"status": "success", "message": "", "chunks_size": len(chunked_docs)})


@naive_rag_api_router.post("/naive_rag_test")
@auth.login_required
@validate(json=DocumentRetrieverRequest)
def naive_rag_test(request, body: DocumentRetrieverRequest):
    documents = rag.search(body)
    return json({
        "status": "success",
        "message": "",
        "documents": [doc.model_dump() for doc in documents]
    })


@naive_rag_api_router.post("/count_index_document")
@auth.login_required
@validate(json=DocumentCountRequest)
async def count_index_document(request, body: DocumentCountRequest):
    count = rag.count_index_document(body)
    return json({"status": "success", "message": "", "count": count})


@naive_rag_api_router.post("/custom_content_ingest")
@auth.login_required
async def custom_content_ingest(request):
    """自定义内容摄取接口"""
    content = request.form.get('content')
    params = _parse_common_ingest_params(request)

    # 加载自定义内容
    loader = RawLoader(content)
    docs = loader.load()

    # 对于自定义内容，如果不是预览模式，需要手动处理分块
    if not params['is_preview']:
        # 处理文档元数据
        docs = RagService.prepare_documents_metadata(
            docs,
            is_preview=params['is_preview'],
            title="自定义内容",
            knowledge_id=params['knowledge_id']
        )

        # 执行文档分块
        chunker = RagService.get_chunker(params['chunk_mode'], request)
        chunked_docs = chunker.chunk(docs)

        # 执行文档存储
        logger.debug(
            f"开始存储{len(chunked_docs)}个文档分块，将自动添加created_time字段以支持时间排序")
        RagService.store_documents_to_pg(
            chunked_docs=chunked_docs,
            knowledge_base_id=params['knowledge_base_id'],
            embed_model_base_url=params['embed_model_base_url'],
            embed_model_api_key=params['embed_model_api_key'],
            embed_model_name=params['embed_model_name'],
            metadata=params['metadata']
        )
        return json({"status": "success", "message": "", "chunks_size": len(chunked_docs)})
    else:
        # 预览模式使用统一流水线
        return _process_documents_pipeline(docs, "自定义内容", params, "自定义内容", request)


@naive_rag_api_router.post("/website_ingest")
@auth.login_required
async def website_ingest(request):
    """网站内容摄取接口"""
    url = request.form.get('url')
    max_depth = int(request.form.get('max_depth', 1))
    params = _parse_common_ingest_params(request)

    # 加载网站内容
    loader = WebSiteLoader(url, max_depth)
    docs = loader.load()

    # 使用统一的文档处理流水线
    return _process_documents_pipeline(docs, url, params, "网站内容", request)


@naive_rag_api_router.post("/file_ingest")
@auth.login_required
async def file_ingest(request):
    """文件内容摄取接口"""
    file = request.files.get('file')
    params = _parse_common_ingest_params(request)

    # 文件类型验证
    allowed_types = ['docx', 'pptx', 'ppt', 'doc', 'txt',
                     'jpg', 'png', 'jpeg', 'pdf', 'csv', 'xlsx', 'xls', 'md']

    file_extension = file.name.split(
        '.')[-1].lower() if '.' in file.name else ''
    if file_extension not in allowed_types:
        return json({
            "status": "error",
            "message": f"不支持的文件类型。支持的类型: {', '.join(allowed_types)}"
        })

    load_mode = request.form.get('load_mode', 'full')

    with tempfile.NamedTemporaryFile(delete=True, suffix=f'.{file_extension}') as temp_file:
        temp_file.write(file.body)
        temp_file.flush()
        temp_path = temp_file.name

        # 加载文件内容
        loader = RagService.get_file_loader(
            temp_path, file_extension, load_mode, request)
        docs = loader.load()

        # 使用统一的文档处理流水线
        return _process_documents_pipeline(docs, file.name, params, "文件内容", request)


@naive_rag_api_router.post("/delete_index")
@validate(json=IndexDeleteRequest)
@auth.login_required
async def delete_index(request, body: IndexDeleteRequest):
    rag.delete_index(body)
    return json({"status": "success", "message": ""})


@naive_rag_api_router.post("/delete_doc")
@auth.login_required
@validate(json=DocumentDeleteRequest)
async def delete_doc(request, body: DocumentDeleteRequest):
    rag.delete_document(body)
    return json({"status": "success", "message": ""})


@naive_rag_api_router.post("/list_rag_document")
@auth.login_required
@validate(json=DocumentListRequest)
async def list_rag_document(request, body: DocumentListRequest):
    documents = rag.list_index_document(body)
    return json({"status": "success", "message": "", "documents": [doc.dict() for doc in documents]})


@naive_rag_api_router.post("/update_rag_document_metadata")
@auth.login_required
@validate(json=DocumentMetadataUpdateRequest)
async def update_rag_document_metadata(request, body: DocumentMetadataUpdateRequest):
    rag.update_metadata(body)
    return json({"status": "success", "message": "文档元数据更新成功"})
