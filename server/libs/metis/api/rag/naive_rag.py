from libs.metis.services.rag_service import RagService
from libs.metis.rag.naive_rag.elasticsearch.elasticsearch_rag import ElasticSearchRag
from libs.metis.loader.website_loader import WebSiteLoader
from libs.metis.loader.raw_loader import RawLoader
from libs.metis.entity.rag.base.index_delete_request import IndexDeleteRequest
from libs.metis.entity.rag.base.document_retriever_request import DocumentRetrieverRequest
from libs.metis.entity.rag.base.document_metadata_update_request import DocumentMetadataUpdateRequest
from libs.metis.entity.rag.base.document_list_request import DocumentListRequest
from libs.metis.entity.rag.base.document_delete_request import DocumentDeleteRequest
from libs.metis.entity.rag.base.document_count_request import DocumentCountRequest
import json as js
import tempfile
import time
import uuid

import logging
logger = logging.getLogger(__name__)


def naive_rag_test(body: DocumentRetrieverRequest):
    """
    测试RAG
    :param request:
    :param body:
    :return:
    """
    start_time = time.time()
    request_id = str(uuid.uuid4())[:8]
    logger.info(f"[{request_id}] RAG测试请求开始, 参数: {body.dict()}")
    rag = ElasticSearchRag()
    documents = rag.search(body)
    logger.info(
        f"[{request_id}] RAG测试请求成功, 耗时: {time.time() - start_time:.2f}秒, 返回文档数: {len(documents)}")
    return [doc.dict() for doc in documents]


async def count_index_document(body: DocumentCountRequest):
    request_id = str(uuid.uuid4())[:8]
    logger.info(f"[{request_id}] 计数索引文档请求, 索引: {body.index_name}")
    rag = ElasticSearchRag()
    count = rag.count_index_document(body)
    logger.info(f"[{request_id}] 计数索引文档请求成功, 文档数: {count}")
    return count


async def custom_content_ingest(content, chunk_mode,
                                knowledge_id, metadata={},
                                embed_model_base_url=None,
                                embed_model_api_key=None,
                                embed_model_name=None,
                                chunk_size=None, chunk_overlap=None,
                                semantic_chunk_model=None, semantic_chunk_model_base_url=None, semantic_chunk_model_api_key=None,
                                is_preview=False,
                                knowledge_base_id='unknown',
                                ):
    start_time = time.time()

    # 加载自定义内容
    loader = RawLoader(content)
    docs = loader.load()

    # 处理文档元数据
    docs = RagService.prepare_documents_metadata(docs,
                                                 is_preview=is_preview,
                                                 title="自定义内容",
                                                 knowledge_id=knowledge_id)
    # 执行文档分块
    chunker = RagService.get_chunker(chunk_mode, chunk_size, chunk_overlap,
                                     semantic_chunk_model=semantic_chunk_model,
                                     semantic_chunk_model_base_url=semantic_chunk_model_base_url,
                                     semantic_chunk_model_api_key=semantic_chunk_model_api_key)
    chunking_start_time = time.time()
    chunked_docs = chunker.chunk(docs)

    logger.debug(
        f"分块完成, 耗时: {time.time() - chunking_start_time:.2f}秒, 分块数: {len(chunked_docs)}")

    # 处理预览模式
    if is_preview:
        response_time = time.time() - start_time
        logger.info(
            f"自定义内容预览完成, 总耗时: {response_time:.2f}秒, 分块数: {len(chunked_docs)}")
        return RagService.serialize_documents(chunked_docs), len(chunked_docs)

    # 执行文档存储
    embedding_start_time = time.time()
    RagService.store_documents_to_es(
        chunked_docs=chunked_docs,
        knowledge_base_id=knowledge_base_id,
        embed_model_base_url=embed_model_base_url,
        embed_model_api_key=embed_model_api_key,
        embed_model_name=embed_model_name,
        metadata=metadata
    )
    logger.debug(
        f"存储到ES完成, 嵌入耗时: {time.time() - embedding_start_time:.2f}秒")

    response_time = time.time() - start_time
    logger.info(
        f"自定义内容导入请求完成, 总耗时: {response_time:.2f}秒, 分块数: {len(chunked_docs)}")
    return len(chunked_docs)


async def website_ingest(
                         url,
                         knowledge_id='unknown', knowledge_base_id='unknown',
                         max_depth=1,
                         chunk_mode='full', is_preview=False, metadata={}):
    start_time = time.time()

    logger.info(
        f"网站内容导入请求开始, 知识库ID: {knowledge_base_id}, 知识ID: {knowledge_id}, URL: {url}, 最大深度: {max_depth}")

    # 加载网站内容
    loading_start_time = time.time()
    loader = WebSiteLoader(url, max_depth)
    docs = loader.load()
    logger.debug(
        f"网站内容加载完成, 耗时: {time.time() - loading_start_time:.2f}秒, 文档数: {len(docs)}")

    # 处理文档元数据
    docs = RagService.prepare_documents_metadata(docs,
                                                 is_preview=is_preview,
                                                 title=url,
                                                 knowledge_id=knowledge_id)

    # 执行文档分块并记录日志
    chunking_start_time = time.time()
    chunked_docs = RagService.perform_chunking(
        docs, chunk_mode, is_preview, "网站内容")
    logger.debug(
        f"网站内容分块完成, 耗时: {time.time() - chunking_start_time:.2f}秒, 分块数: {len(chunked_docs)}")

    # 处理预览模式
    if is_preview:
        response_time = time.time() - start_time
        logger.info(
            f"网站内容预览完成, 总耗时: {response_time:.2f}秒, 分块数: {len(chunked_docs)}")
        return RagService.serialize_documents(chunked_docs), len(chunked_docs)

    # 执行文档存储
    embedding_start_time = time.time()
    RagService.store_documents_to_es(
        chunked_docs=chunked_docs,
        knowledge_base_id=request.form.get('knowledge_base_id'),
        embed_model_base_url=request.form.get('embed_model_base_url'),
        embed_model_api_key=request.form.get('embed_model_api_key'),
        embed_model_name=request.form.get('embed_model_name'),
        metadata=metadata
    )
    logger.debug(
        f"网站内容存储到ES完成, 嵌入耗时: {time.time() - embedding_start_time:.2f}秒")

    response_time = time.time() - start_time
    logger.info(
        f"网站内容导入请求完成, 总耗时: {response_time:.2f}秒, 分块数: {len(chunked_docs)}")
    return len(chunked_docs)


async def file_ingest(file,
                      knowledge_id='unknown', knowledge_base_id='unknown',
                      embed_model_base_url=None,
                      embed_model_api_key=None,
                      embed_model_name=None,
                      is_preview=False,
                      chunk_mode='full',
                        chunk_size=256, chunk_overlap=128,
                        semantic_chunk_model=None, semantic_chunk_model_base_url=None, semantic_chunk_model_api_key=None,
                      metadata={}, load_mode='full',
                      ocr_type=None, olm_base_url=None, olm_api_key=None, olm_model=None, azure_base_url=None, azure_api_key=None):
    start_time = time.time()
    file_size_mb = len(file.body) / (1024 * 1024)

    logger.info(
        f"文件导入请求开始, 知识库ID: {knowledge_base_id}, 知识ID: {knowledge_id}, 文件名: {file.name}, 文件大小: {file_size_mb:.2f} MB")

    file_extension = file.name.split(
        '.')[-1].lower() if '.' in file.name else ''

    logger.debug(
        f"文件处理模式: 分块模式={chunk_mode}, 预览模式={is_preview}")

    with tempfile.NamedTemporaryFile(delete=True, suffix=f'.{file_extension}') as temp_file:
        temp_file.write(file.body)
        temp_file.flush()
        temp_path = temp_file.name

        # 日志记录
        operation_type = "预览分块文件" if is_preview else "处理文件"
        logger.debug(f'{operation_type}：{temp_path}')

        # 加载文件内容
        loading_start_time = time.time()
        loader = RagService.get_file_loader(
            temp_path, file_extension, load_mode, ocr_type=ocr_type,
            olm_base_url=olm_base_url, olm_api_key=olm_api_key, olm_model=olm_model,
            azure_base_url=azure_base_url, azure_api_key=azure_api_key)
        docs = loader.load()
        logger.debug(
            f"文件内容加载完成, 耗时: {time.time() - loading_start_time:.2f}秒, 文档数: {len(docs)}")

        # 处理文档元数据
        docs = RagService.prepare_documents_metadata(docs,
                                                     is_preview=is_preview,
                                                     title=file.name,
                                                     knowledge_id=knowledge_id)

        # 执行文档分块并记录日志
        chunking_start_time = time.time()
        chunked_docs = RagService.perform_chunking(
            docs, chunk_mode, is_preview, chunk_size, chunk_overlap, semantic_chunk_model, semantic_chunk_model_base_url, semantic_chunk_model_api_key
        logger.debug(
            f"文件内容分块完成, 耗时: {time.time() - chunking_start_time:.2f}秒, 分块数: {len(chunked_docs)}")

        # 处理预览模式
        if is_preview:
            response_time=time.time() - start_time
            logger.info(
                f"文件内容预览完成, 总耗时: {response_time:.2f}秒, 分块数: {len(chunked_docs)}")
            return RagService.serialize_documents(chunked_docs), len(chunked_docs)

        # 执行文档存储
        embedding_start_time=time.time()
        RagService.store_documents_to_es(
            chunked_docs=chunked_docs,
            knowledge_base_id=knowledge_base_id,
            embed_model_base_url=embed_model_base_url,
            embed_model_api_key=embed_model_api_key,
            embed_model_name=embed_model_name,
            metadata=metadata
        )
        logger.debug(
            f"文件内容存储到ES完成, 嵌入耗时: {time.time() - embedding_start_time:.2f}秒")

    response_time=time.time() - start_time
    logger.info(
        f"文件导入请求完成, 总耗时: {response_time:.2f}秒, 分块数: {len(chunked_docs)}")
    return len(chunked_docs)


async def delete_index(body: IndexDeleteRequest):
    logger.info(f"删除索引请求, 索引名: {body.index_name}")
    rag=ElasticSearchRag()
    start_time=time.time()
    rag.delete_index(body)
    elapsed_time=time.time() - start_time
    logger.info(f"删除索引成功, 耗时: {elapsed_time:.2f}秒")
    return json({"status": "success", "message": ""})


async def delete_doc(body: DocumentDeleteRequest):
    """
    删除文档
    :param request:
    :param body:
    :return:
    """
    logger.info(
        f"删除文档请求, 索引名: {body.index_name}, 过滤条件: {body.metadata_filter}")
    start_time=time.time()
    rag=ElasticSearchRag()
    rag.delete_document(body)
    elapsed_time=time.time() - start_time
    logger.info(f"删除文档成功, 耗时: {elapsed_time:.2f}秒")


async def list_rag_document(body: DocumentListRequest):
    """
    查询RAG数据
    :param request:
    :param body:
    :return:
    """
    logger.info(f"查询RAG文档列表请求, 索引名: {body.index_name}")
    start_time=time.time()
    rag=ElasticSearchRag()
    documents=rag.list_index_document(body)
    elapsed_time=time.time() - start_time
    logger.info(
        f"查询RAG文档列表成功, 耗时: {elapsed_time:.2f}秒, 文档数: {len(documents)}")
    return [doc.dict() for doc in documents]})


async def update_rag_document_metadata(body: DocumentMetadataUpdateRequest):
    logger.info(
        f"更新文档元数据请求, 索引名: {body.index_name}, 过滤条件: {body.metadata_filter}")
    start_time = time.time()
    rag = ElasticSearchRag()
    rag.update_metadata(body)
    elapsed_time = time.time() - start_time
    logger.info(f"更新文档元数据成功, 耗时: {elapsed_time:.2f}秒")
