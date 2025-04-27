import json as js
import tempfile
import traceback
import uuid
import time
from datetime import datetime

from langchain_openai import OpenAIEmbeddings
from sanic import Blueprint, json
from sanic.log import logger
from sanic_ext import validate
from loguru import logger
from src.chunk.fixed_size_chunk import FixedSizeChunk
from src.chunk.full_chunk import FullChunk
from src.chunk.recursive_chunk import RecursiveChunk
from src.chunk.semantic_chunk import SemanticChunk
from src.core.web.api_auth import auth
from src.loader.doc_loader import DocLoader
from src.loader.excel_loader import ExcelLoader
from src.loader.image_loader import ImageLoader
from src.loader.markdown_loader import MarkdownLoader
from src.loader.pdf_loader import PDFLoader
from src.loader.ppt_loader import PPTLoader
from src.loader.raw_loader import RawLoader
from src.loader.text_loader import TextLoader
from src.loader.website_loader import WebSiteLoader
from src.ocr.azure_ocr import AzureOCR
from src.ocr.olm_ocr import OlmOcr
from src.ocr.pp_ocr import PPOcr
from src.rag.native_rag.entity.elasticsearch_document_count_request import ElasticSearchDocumentCountRequest
from src.rag.native_rag.entity.elasticsearch_document_delete_request import ElasticSearchDocumentDeleteRequest
from src.rag.native_rag.entity.elasticsearch_document_list_request import ElasticSearchDocumentListRequest
from src.rag.native_rag.entity.elasticsearch_document_metadata_update_request import \
    ElasticsearchDocumentMetadataUpdateRequest
from src.rag.native_rag.entity.elasticsearch_index_delete_request import ElasticSearchIndexDeleteRequest
from src.rag.native_rag.entity.elasticsearch_retriever_request import ElasticSearchRetrieverRequest
from src.rag.native_rag.entity.elasticsearch_store_request import ElasticSearchStoreRequest
from src.rag.native_rag.rag.elasticsearch_rag import ElasticSearchRag

rag_api_router = Blueprint("rag", url_prefix="/rag")


def get_file_loader(file_path, file_extension, load_mode, request=None):
    """
    根据文件类型选择适当的加载器
    在内部初始化OCR，支持paddle_ocr、olm_ocr、azure_ocr
    """
    logger.debug(f"为文件 {file_path} (类型: {file_extension}) 初始化加载器")
    # 初始化OCR
    ocr = None
    ocr = load_ocr(ocr, request)
    if ocr:
        logger.debug(f"OCR类型: {type(ocr).__name__} 初始化成功")

    if file_extension in ['docx', 'doc']:
        return DocLoader(file_path, ocr, load_mode)
    elif file_extension in ['pptx', 'ppt']:
        return PPTLoader(file_path, load_mode)
    elif file_extension == 'txt':
        return TextLoader(file_path, load_mode)
    elif file_extension in ['jpg', 'png', 'jpeg']:
        return ImageLoader(file_path, ocr, load_mode)
    elif file_extension == 'pdf':
        return PDFLoader(file_path, ocr, load_mode)
    elif file_extension in ['xlsx', 'xls', 'csv']:
        return ExcelLoader(file_path, load_mode)
    elif file_extension in ['md']:
        return MarkdownLoader(file_path,load_mode)
    else:
        raise ValueError(f"不支持的文件类型: {file_extension}")


def load_ocr(ocr, request):
    ocr = None
    ocr_type = request.form.get('ocr_type')
    logger.debug(f"加载OCR服务，类型: {ocr_type}")

    if ocr_type == 'pp_ocr':
        logger.debug("初始化PP-OCR服务")
        ocr = PPOcr()

    if ocr_type == 'olm_ocr':
        base_url = request.form.get('olm_base_url')
        api_key = request.form.get('olm_api_key')
        model = request.form.get(
            'olm_model', "allenai/olmOCR-7B-0225-preview")
        logger.debug(f"初始化OLM-OCR服务，模型: {model}")
        ocr = OlmOcr(base_url=base_url, api_key=api_key, model=model)

    if ocr_type == 'azure_ocr':
        azure_endpoint = request.form.get('azure_endpoint')
        logger.debug(f"初始化Azure-OCR服务，endpoint: {azure_endpoint}")
        azure_api_key = request.form.get('azure_api_key')
        ocr = AzureOCR(api_key=azure_api_key, endpoint=azure_endpoint)

    return ocr


def get_chunker(chunk_mode, request=None):
    """
    根据分块模式返回相应的分块器
    """
    logger.debug(f"初始化分块器，模式: {chunk_mode}")
    if chunk_mode == 'fixed_size':
        chunk_size = int(request.form.get('chunk_size', 256))
        logger.debug(f"使用固定大小分块，大小: {chunk_size}")
        return FixedSizeChunk(chunk_size=chunk_size)

    elif chunk_mode == 'full':
        logger.debug("使用全文分块")
        return FullChunk()

    elif chunk_mode == 'recursive':
        chunk_size = int(request.form.get('chunk_size', 256))
        chunk_overlap = int(request.form.get('chunk_overlap', 128))
        logger.debug(f"使用递归分块，大小: {chunk_size}, 重叠: {chunk_overlap}")
        return RecursiveChunk(chunk_size=chunk_size, chunk_overlap=chunk_overlap)

    elif chunk_mode == 'semantic':
        semantic_chunk_model = request.form.get('semantic_chunk_model')
        semantic_chunk_model_base_url = request.form.get(
            'semantic_chunk_model_base_url')
        logger.debug(f"使用语义分块，模型: {semantic_chunk_model}, URL: {semantic_chunk_model_base_url}")
        semantic_chunk_model_api_key = request.form.get(
            'semantic_chunk_model_api_key')
        embeddings = OpenAIEmbeddings(
            model=semantic_chunk_model,
            api_key=semantic_chunk_model_api_key,
            base_url=semantic_chunk_model_base_url,
        )
        return SemanticChunk(embeddings)
    else:
        error_msg = f"不支持的分块模式: {chunk_mode}"
        logger.error(error_msg)
        raise ValueError(error_msg)


def process_documents(docs, knowledge_title, knowledge_id=None):
    """
    处理文档，添加元数据
    """
    logger.debug(f"处理文档元数据，标题: {knowledge_title}, ID: {knowledge_id}, 文档数量: {len(docs)}")
    for doc in docs:
        doc.metadata['knowledge_title'] = knowledge_title
        if knowledge_id:
            doc.metadata['knowledge_id'] = knowledge_id
        doc.metadata['chunk_id'] = str(uuid.uuid4())
    return docs


def serialize_documents(docs):
    """
    将文档序列化为JSON格式
    """
    logger.debug(f"序列化 {len(docs)} 个文档")
    serialized_docs = []
    for doc in docs:
        serialized_docs.append({
            "page_content": doc.page_content,
            "metadata": doc.metadata
        })
    return serialized_docs


@rag_api_router.post("/naive_rag_test")
@auth.login_required
@validate(json=ElasticSearchRetrieverRequest)
def naive_rag_test(request, body: ElasticSearchRetrieverRequest):
    """
    测试RAG
    :param request:
    :param body:
    :return:
    """
    start_time = time.time()
    request_id = str(uuid.uuid4())[:8]
    logger.info(f"[{request_id}] RAG测试请求开始, 参数: {body.dict()}")
    try:
        rag = ElasticSearchRag()
        documents = rag.search(body)
        logger.info(
            f"[{request_id}] RAG测试请求成功, 耗时: {time.time() - start_time:.2f}秒, 返回文档数: {len(documents)}")
        return json({"status": "success", "message": "", "documents": [doc.dict() for doc in documents]})
    except Exception as e:
        error_detail = traceback.format_exc()
        logger.error(f"[{request_id}] RAG测试请求失败: {str(e)}\n{error_detail}")
        return json({"status": "error", "message": str(e)})


@rag_api_router.post("/count_index_document")
@auth.login_required
@validate(json=ElasticSearchDocumentCountRequest)
async def count_index_document(request, body: ElasticSearchDocumentCountRequest):
    request_id = str(uuid.uuid4())[:8]
    logger.info(f"[{request_id}] 计数索引文档请求, 索引: {body.index_name}")
    try:
        rag = ElasticSearchRag()
        count = rag.count_index_document(body)
        logger.info(f"[{request_id}] 计数索引文档请求成功, 文档数: {count}")
        return json({"status": "success", "message": "", "count": count})
    except Exception as e:
        error_detail = traceback.format_exc()
        logger.error(f"[{request_id}] 计数索引文档请求失败: {str(e)}\n{error_detail}")
        return json({"status": "error", "message": str(e)})


@rag_api_router.post("/custom_content_ingest")
@auth.login_required
async def custom_content_ingest(request):
    start_time = time.time()
    request_id = str(uuid.uuid4())[:8]
    knowledge_id = request.form.get('knowledge_id', 'unknown')
    knowledge_base_id = request.form.get('knowledge_base_id', 'unknown')
    logger.info(f"[{request_id}] 自定义内容导入请求开始, 知识库ID: {knowledge_base_id}, 知识ID: {knowledge_id}")

    try:
        content = request.form.get('content')
        content_preview = content[:100] + '...' if len(content) > 100 else content
        chunk_mode = request.form.get('chunk_mode')
        is_preview = request.form.get('preview', 'false').lower() == 'true'
        metadata = js.loads(request.form.get('metadata', '{}'))

        logger.debug(f"[{request_id}] 内容预览: {content_preview}, 分块模式: {chunk_mode}, 预览模式: {is_preview}")

        # 加载自定义内容
        loader = RawLoader(content)
        docs = loader.load()
        logger.debug(f"[{request_id}] 加载内容完成, 文档数: {len(docs)}")

        # 处理文档元数据
        docs = prepare_documents_metadata(docs,
                                          is_preview=is_preview,
                                          title="自定义内容",
                                          knowledge_id=request.form.get('knowledge_id'))
        # 执行文档分块
        chunker = get_chunker(chunk_mode, request)
        chunking_start_time = time.time()
        chunked_docs = chunker.chunk(docs)
        logger.debug(
            f"[{request_id}] 分块完成, 耗时: {time.time() - chunking_start_time:.2f}秒, 分块数: {len(chunked_docs)}")

        # 处理预览模式
        if is_preview:
            response_time = time.time() - start_time
            logger.info(
                f"[{request_id}] 自定义内容预览完成, 总耗时: {response_time:.2f}秒, 分块数: {len(chunked_docs)}")
            return json({
                "status": "success",
                "message": "",
                "documents": serialize_documents(chunked_docs)
            })

        # 执行文档存储
        embedding_start_time = time.time()
        store_documents_to_es(
            chunked_docs=chunked_docs,
            knowledge_base_id=request.form.get('knowledge_base_id'),
            embed_model_base_url=request.form.get('embed_model_base_url'),
            embed_model_api_key=request.form.get('embed_model_api_key'),
            embed_model_name=request.form.get('embed_model_name'),
            metadata=metadata
        )
        logger.debug(f"[{request_id}] 存储到ES完成, 嵌入耗时: {time.time() - embedding_start_time:.2f}秒")

        response_time = time.time() - start_time
        logger.info(
            f"[{request_id}] 自定义内容导入请求完成, 总耗时: {response_time:.2f}秒, 分块数: {len(chunked_docs)}")
        return json({"status": "success", "message": "", "chunks_size": len(chunked_docs)})
    except Exception as e:
        error_detail = traceback.format_exc()
        response_time = time.time() - start_time
        logger.error(f"[{request_id}] 自定义内容处理错误, 耗时: {response_time:.2f}秒, 错误: {str(e)}\n{error_detail}")
        return json({"status": "error", "message": str(e)})


@rag_api_router.post("/website_ingest")
@auth.login_required
async def website_ingest(request):
    start_time = time.time()
    request_id = str(uuid.uuid4())[:8]
    knowledge_id = request.form.get('knowledge_id', 'unknown')
    knowledge_base_id = request.form.get('knowledge_base_id', 'unknown')

    try:
        url = request.form.get('url')
        max_depth = int(request.form.get('max_depth', 1))
        chunk_mode = request.form.get('chunk_mode')
        is_preview = request.form.get('preview', 'false').lower() == 'true'
        metadata = js.loads(request.form.get('metadata', '{}'))

        logger.info(
            f"[{request_id}] 网站内容导入请求开始, 知识库ID: {knowledge_base_id}, 知识ID: {knowledge_id}, URL: {url}, 最大深度: {max_depth}")

        # 加载网站内容
        loading_start_time = time.time()
        loader = WebSiteLoader(url, max_depth)
        docs = loader.load()
        logger.debug(
            f"[{request_id}] 网站内容加载完成, 耗时: {time.time() - loading_start_time:.2f}秒, 文档数: {len(docs)}")

        # 处理文档元数据
        docs = prepare_documents_metadata(docs,
                                          is_preview=is_preview,
                                          title=url,
                                          knowledge_id=request.form.get('knowledge_id'))

        # 执行文档分块并记录日志
        chunking_start_time = time.time()
        chunked_docs = perform_chunking(
            docs, chunk_mode, request, is_preview, "网站内容")
        logger.debug(
            f"[{request_id}] 网站内容分块完成, 耗时: {time.time() - chunking_start_time:.2f}秒, 分块数: {len(chunked_docs)}")

        # 处理预览模式
        if is_preview:
            response_time = time.time() - start_time
            logger.info(f"[{request_id}] 网站内容预览完成, 总耗时: {response_time:.2f}秒, 分块数: {len(chunked_docs)}")
            return json({
                "status": "success",
                "message": "",
                "documents": serialize_documents(chunked_docs)
            })

        # 执行文档存储
        embedding_start_time = time.time()
        store_documents_to_es(
            chunked_docs=chunked_docs,
            knowledge_base_id=request.form.get('knowledge_base_id'),
            embed_model_base_url=request.form.get('embed_model_base_url'),
            embed_model_api_key=request.form.get('embed_model_api_key'),
            embed_model_name=request.form.get('embed_model_name'),
            metadata=metadata
        )
        logger.debug(f"[{request_id}] 网站内容存储到ES完成, 嵌入耗时: {time.time() - embedding_start_time:.2f}秒")

        response_time = time.time() - start_time
        logger.info(f"[{request_id}] 网站内容导入请求完成, 总耗时: {response_time:.2f}秒, 分块数: {len(chunked_docs)}")
        return json({"status": "success", "message": "", "chunks_size": len(chunked_docs)})
    except Exception as e:
        error_detail = traceback.format_exc()
        response_time = time.time() - start_time
        logger.error(f"[{request_id}] 网站内容处理错误, 耗时: {response_time:.2f}秒, 错误: {str(e)}\n{error_detail}")
        return json({"status": "error", "message": str(e)})


@rag_api_router.post("/file_ingest")
@auth.login_required
async def file_ingest(request):
    start_time = time.time()
    request_id = str(uuid.uuid4())[:8]

    file = request.files.get('file')
    file_size_mb = len(file.body) / (1024 * 1024)
    knowledge_id = request.form.get('knowledge_id', 'unknown')
    knowledge_base_id = request.form.get('knowledge_base_id', 'unknown')

    logger.info(
        f"[{request_id}] 文件导入请求开始, 知识库ID: {knowledge_base_id}, 知识ID: {knowledge_id}, 文件名: {file.name}, 文件大小: {file_size_mb:.2f} MB")

    allowed_types = ['docx', 'pptx', 'ppt', 'doc', 'txt',
                     'jpg', 'png', 'jpeg', 'pdf', 'csv', 'xlsx', 'xls', 'md']
    file_extension = file.name.split(
        '.')[-1].lower() if '.' in file.name else ''

    if file_extension not in allowed_types:
        logger.warn(f"[{request_id}] 不支持的文件类型: {file_extension}")
        return json({"status": "error", "message": f"不支持的文件类型。支持的类型: {', '.join(allowed_types)}"})

    is_preview = request.form.get('preview', 'false').lower() == 'true'
    chunk_mode = request.form.get('chunk_mode')
    metadata = js.loads(request.form.get('metadata', '{}'))
    load_mode = request.form.get('load_mode', 'full')

    logger.debug(f"[{request_id}] 文件处理模式: 分块模式={chunk_mode}, 预览模式={is_preview}")

    try:
        with tempfile.NamedTemporaryFile(delete=True, suffix=f'.{file_extension}') as temp_file:
            temp_file.write(file.body)
            temp_file.flush()
            temp_path = temp_file.name

            # 日志记录
            operation_type = "预览分块文件" if is_preview else "处理文件"
            logger.debug(f'[{request_id}] {operation_type}：{temp_path}')

            # 加载文件内容
            loading_start_time = time.time()
            loader = get_file_loader(temp_path, file_extension, load_mode, request)
            docs = loader.load()
            logger.debug(
                f"[{request_id}] 文件内容加载完成, 耗时: {time.time() - loading_start_time:.2f}秒, 文档数: {len(docs)}")

            # 处理文档元数据
            docs = prepare_documents_metadata(docs,
                                              is_preview=is_preview,
                                              title=file.name,
                                              knowledge_id=request.form.get('knowledge_id'))

            # 执行文档分块并记录日志
            chunking_start_time = time.time()
            chunked_docs = perform_chunking(
                docs, chunk_mode, request, is_preview, "文件内容")
            logger.debug(
                f"[{request_id}] 文件内容分块完成, 耗时: {time.time() - chunking_start_time:.2f}秒, 分块数: {len(chunked_docs)}")

            # 处理预览模式
            if is_preview:
                response_time = time.time() - start_time
                logger.info(
                    f"[{request_id}] 文件内容预览完成, 总耗时: {response_time:.2f}秒, 分块数: {len(chunked_docs)}")
                return json({
                    "status": "success",
                    "message": "",
                    "documents": serialize_documents(chunked_docs)
                })

            # 执行文档存储
            embedding_start_time = time.time()
            store_documents_to_es(
                chunked_docs=chunked_docs,
                knowledge_base_id=request.form.get('knowledge_base_id'),
                embed_model_base_url=request.form.get('embed_model_base_url'),
                embed_model_api_key=request.form.get('embed_model_api_key'),
                embed_model_name=request.form.get('embed_model_name'),
                metadata=metadata
            )
            logger.debug(f"[{request_id}] 文件内容存储到ES完成, 嵌入耗时: {time.time() - embedding_start_time:.2f}秒")

        response_time = time.time() - start_time
        logger.info(f"[{request_id}] 文件导入请求完成, 总耗时: {response_time:.2f}秒, 分块数: {len(chunked_docs)}")
        return json({"status": "success", "message": "", "chunks_size": len(chunked_docs)})
    except Exception as e:
        error_detail = traceback.format_exc()
        response_time = time.time() - start_time
        logger.error(f"[{request_id}] 文件处理错误, 耗时: {response_time:.2f}秒, 错误: {str(e)}\n{error_detail}")
        return json({"status": "error", "message": str(e)})


# 添加以下辅助函数，使代码更加模块化和易于维护

def prepare_documents_metadata(docs, is_preview, title, knowledge_id=None):
    """
    准备文档的元数据

    Args:
        docs: 文档列表
        is_preview: 是否为预览模式
        title: 文档标题
        knowledge_id: 知识库ID，预览模式下不需要

    Returns:
        处理后的文档列表
    """
    mode = "预览" if is_preview else "正式处理"
    logger.debug(f"准备文档元数据 [{mode}], 标题: {title}, 知识ID: {knowledge_id}, 文档数: {len(docs)}")
    if is_preview:
        return process_documents(docs, title)
    else:
        return process_documents(docs, title, knowledge_id)


def perform_chunking(docs, chunk_mode, request, is_preview, content_type):
    """
    执行文档分块并记录相关日志

    Args:
        docs: 文档列表
        chunk_mode: 分块模式
        request: HTTP请求对象
        is_preview: 是否为预览模式
        content_type: 内容类型

    Returns:
        分块后的文档列表
    """
    mode = "预览" if is_preview else "正式处理"
    logger.debug(f"{content_type}分块 [{mode}], 模式: {chunk_mode}, 文档数: {len(docs)}")

    chunker = get_chunker(chunk_mode, request)
    chunked_docs = chunker.chunk(docs)
    logger.debug(f"{content_type}分块完成, 输入文档: {len(docs)}, 输出分块: {len(chunked_docs)}")
    return chunked_docs


def store_documents_to_es(chunked_docs, knowledge_base_id, embed_model_base_url,
                          embed_model_api_key, embed_model_name, metadata={}):
    """
    将文档存储到ElasticSearch

    Args:
        chunked_docs: 分块后的文档
        knowledge_base_id: 知识库ID
        embed_model_base_url: 嵌入模型基础URL
        embed_model_api_key: 嵌入模型API密钥
        embed_model_name: 嵌入模型名称
        metadata: 额外的元数据
    """
    logger.debug(
        f"存储文档到ES, 知识库ID: {knowledge_base_id}, 模型名称: {embed_model_name}, 分块数: {len(chunked_docs)}")

    if metadata:
        logger.debug(f"应用额外元数据: {metadata}")
        for doc in chunked_docs:
            doc.metadata.update(metadata)

    elasticsearch_store_request = ElasticSearchStoreRequest(
        index_name=knowledge_base_id,
        docs=chunked_docs,
        embed_model_base_url=embed_model_base_url,
        embed_model_api_key=embed_model_api_key,
        embed_model_name=embed_model_name,
    )

    start_time = time.time()
    rag = ElasticSearchRag()
    rag.ingest(elasticsearch_store_request)
    elapsed_time = time.time() - start_time
    logger.debug(f"ES存储完成, 耗时: {elapsed_time:.2f}秒")


@rag_api_router.post("/delete_index")
@validate(json=ElasticSearchIndexDeleteRequest)
@auth.login_required
async def delete_index(request, body: ElasticSearchIndexDeleteRequest):
    request_id = str(uuid.uuid4())[:8]
    logger.info(f"[{request_id}] 删除索引请求, 索引名: {body.index_name}")
    try:
        rag = ElasticSearchRag()
        start_time = time.time()
        rag.delete_index(body)
        elapsed_time = time.time() - start_time
        logger.info(f"[{request_id}] 删除索引成功, 耗时: {elapsed_time:.2f}秒")
        return json({"status": "success", "message": ""})
    except Exception as e:
        error_detail = traceback.format_exc()
        logger.error(f"[{request_id}] 删除索引失败: {str(e)}\n{error_detail}")
        return json({"status": "error", "message": str(e)})


@rag_api_router.post("/delete_doc")
@auth.login_required
@validate(json=ElasticSearchDocumentDeleteRequest)
async def delete_doc(request, body: ElasticSearchDocumentDeleteRequest):
    """
    删除文档
    :param request:
    :param body:
    :return:
    """
    request_id = str(uuid.uuid4())[:8]
    logger.info(f"[{request_id}] 删除文档请求, 索引名: {body.index_name}, 文档ID: {body.knowledge_id}")
    try:
        start_time = time.time()
        rag = ElasticSearchRag()
        rag.delete_document(body)
        elapsed_time = time.time() - start_time
        logger.info(f"[{request_id}] 删除文档成功, 耗时: {elapsed_time:.2f}秒")
        return json({"status": "success", "message": ""})
    except Exception as e:
        error_detail = traceback.format_exc()
        logger.error(f"[{request_id}] 删除文档失败: {str(e)}\n{error_detail}")
        return json({"status": "error", "message": str(e)})


@rag_api_router.post("/list_rag_document")
@auth.login_required
@validate(json=ElasticSearchDocumentListRequest)
async def list_rag_document(request, body: ElasticSearchDocumentListRequest):
    """
    查询RAG数据
    :param request:
    :param body:
    :return:
    """
    request_id = str(uuid.uuid4())[:8]
    logger.info(f"[{request_id}] 查询RAG文档列表请求, 索引名: {body.index_name}")
    try:
        start_time = time.time()
        rag = ElasticSearchRag()
        documents = rag.list_index_document(body)
        elapsed_time = time.time() - start_time
        logger.info(f"[{request_id}] 查询RAG文档列表成功, 耗时: {elapsed_time:.2f}秒, 文档数: {len(documents)}")
        return json({"status": "success", "message": "", "documents": [doc.dict() for doc in documents]})
    except Exception as e:
        error_detail = traceback.format_exc()
        logger.error(f"[{request_id}] 查询RAG文档列表失败: {str(e)}\n{error_detail}")
        return json({"status": "error", "message": str(e)})


@rag_api_router.post("/update_rag_document_metadata")
@auth.login_required
@validate(json=ElasticsearchDocumentMetadataUpdateRequest)
async def update_rag_document_metadata(request, body: ElasticsearchDocumentMetadataUpdateRequest):
    request_id = str(uuid.uuid4())[:8]
    logger.info(f"[{request_id}] 更新文档元数据请求, 索引名: {body.index_name}, 文档ID: {body.document_id}")
    try:
        start_time = time.time()
        rag = ElasticSearchRag()
        rag.update_metadata(body)
        elapsed_time = time.time() - start_time
        logger.info(f"[{request_id}] 更新文档元数据成功, 耗时: {elapsed_time:.2f}秒")
        return json({"status": "success", "message": "文档元数据更新成功"})
    except Exception as e:
        error_detail = traceback.format_exc()
        logger.error(f"[{request_id}] 更新文档元数据失败: {str(e)}\n{error_detail}")
        return json({"status": "error", "message": str(e)})
