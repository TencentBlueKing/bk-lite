import concurrent.futures
import json
import os
import re
import tempfile
import time

from celery import shared_task
from django.core.exceptions import SynchronousOnlyOperation
from django.db import close_old_connections, transaction
from django.utils import timezone
from langchain_core.messages import HumanMessage, SystemMessage
from tqdm import tqdm

from apps.core.logger import opspilot_logger as logger
from apps.opspilot.enum import DocumentStatus, KnowledgeTaskStatus
from apps.opspilot.metis.llm.chain.entity import BasicLLMRequest
from apps.opspilot.metis.llm.common.llm_client_factory import LLMClientFactory
from apps.opspilot.metis.llm.rag.naive_rag.pgvector.pgvector_rag import PgvectorRag
from apps.opspilot.metis.llm.rag.naive_rag_entity import DocumentMetadataUpdateRequest
from apps.opspilot.models import (
    Bot,
    BotWorkFlow,
    KnowledgeBase,
    KnowledgeDocument,
    KnowledgeGraph,
    KnowledgeTask,
    LLMModel,
    Memory,
    MemorySpace,
    MemoryWriteCache,
    QAPairs,
    WebPageKnowledge,
)
from apps.opspilot.services.knowledge_search_service import KnowledgeSearchService
from apps.opspilot.services.memory_write_buffer_service import (
    build_batch_content,
    build_memory_target_id,
    extract_memory_write_node_configs,
    normalize_write_batch_size,
    resolve_memory_target,
)
from apps.opspilot.services.workflow_attachment_service import cleanup_expired_workflow_attachments
from apps.opspilot.utils.chat_flow_utils.engine.factory import create_chat_flow_engine
from apps.opspilot.utils.chunk_helper import ChunkHelper
from apps.opspilot.utils.graph_utils import GraphUtils


def _run_in_native_thread(func, *args, **kwargs):
    def _execute(allow_async_unsafe=False):
        close_old_connections()
        previous_async_flag = os.environ.get("DJANGO_ALLOW_ASYNC_UNSAFE")
        if allow_async_unsafe:
            os.environ["DJANGO_ALLOW_ASYNC_UNSAFE"] = "true"

        try:
            return func(*args, **kwargs)
        finally:
            close_old_connections()
            if allow_async_unsafe:
                if previous_async_flag is None:
                    os.environ.pop("DJANGO_ALLOW_ASYNC_UNSAFE", None)
                else:
                    os.environ["DJANGO_ALLOW_ASYNC_UNSAFE"] = previous_async_flag

    with concurrent.futures.ThreadPoolExecutor(max_workers=1) as executor:
        try:
            future = executor.submit(_execute, False)
            return future.result()
        except SynchronousOnlyOperation:
            logger.warning("Fallback with DJANGO_ALLOW_ASYNC_UNSAFE for eventlet ORM task")
            future = executor.submit(_execute, True)
            return future.result()


def _build_memory_write_client(effective_model_id):
    if not effective_model_id:
        return None

    try:
        effective_model_id = int(effective_model_id)
    except (TypeError, ValueError):
        logger.warning(f"[MemoryWriteTask] 模型配置不是有效的 ID: model_id={effective_model_id}，直接处理")
        return None

    try:
        llm_model = LLMModel.objects.get(id=effective_model_id)
    except LLMModel.DoesNotExist:
        logger.warning(f"[MemoryWriteTask] 配置的模型不存在: model_id={effective_model_id}，直接处理")
        return None

    llm_request = BasicLLMRequest(
        openai_api_base=llm_model.openai_api_base,
        openai_api_key=llm_model.openai_api_key,
        model=llm_model.model_name,
        protocol_type=llm_model.protocol_type,
        vendor_type=llm_model.vendor.vendor_type if llm_model.vendor_id else "",
        temperature=0.3,
    )
    return LLMClientFactory.create_client(llm_request, disable_stream=True)


def _summarize_memory_batch_content(memory_space, batch_content: str, model_id=None) -> str:
    effective_model_id = model_id if model_id else memory_space.default_model
    client = _build_memory_write_client(effective_model_id)
    if not client:
        return batch_content

    write_rule = memory_space.write_rule.strip()
    summary_prompt = f"""你是一个记忆批处理助手。请将多条工作流输出整理为一份适合写入记忆的汇总内容。

## 输出要求
- 保留稳定、可复用、对后续对话有价值的信息
- 去除重复、噪音和临时执行细节
- 保持 Markdown 格式
- 只输出最终汇总内容，不要解释过程

## 写入规则
{write_rule or "未配置额外写入规则"}

## 待汇总内容
{batch_content}
"""

    try:
        response = client.invoke(
            [
                SystemMessage(content="你负责将批量工作流输出归纳为一份可写入长期记忆的 Markdown 内容。"),
                HumanMessage(content=summary_prompt),
            ]
        )
        summarized_content = response.content if hasattr(response, "content") else str(response)
        return summarized_content.strip() or batch_content
    except Exception as e:
        logger.error(f"[MemoryWriteBatchTask] 批量归纳失败: {e}，使用原始拼接内容", exc_info=True)
        return batch_content


def _resolve_org_display_name(organization_id) -> str:
    """组织记忆的展示名（owner_username）：优先组名，回退“组织-{id}”。

    与 LocalMemoryEngine.write 的直接写入路径保持一致，避免批量落库时 owner_username 为空，
    导致前端“管理组织”列（读 owner_username）显示空。
    """
    display = f"组织-{organization_id}"
    try:
        from apps.system_mgmt.models import Group

        group = Group.objects.filter(id=organization_id).first()
        if group:
            display = group.name
    except Exception:  # noqa: BLE001
        pass
    return display


def _flush_memory_write_cache_group(
    memory_space_id: int,
    title: str,
    model_id,
    workflow_id: int,
    node_id: str,
    memory_target_id: str,
    batch_size: int = None,
    force_flush: bool = False,
):
    cache_item_ids = []
    normalized_batch_size = normalize_write_batch_size(batch_size)

    with transaction.atomic():
        queryset = (
            MemoryWriteCache.objects.select_for_update()
            .filter(
                workflow_id=workflow_id,
                node_id=node_id,
                memory_target_id=memory_target_id,
                status=MemoryWriteCache.STATUS_PENDING,
            )
            .order_by("created_at", "id")
        )
        ready_items = list(queryset if force_flush else queryset[:normalized_batch_size])
        if not ready_items:
            return False
        if not force_flush and len(ready_items) < normalized_batch_size:
            return False

        cache_item_ids = [item.id for item in ready_items]
        MemoryWriteCache.objects.filter(id__in=cache_item_ids).update(status=MemoryWriteCache.STATUS_PROCESSING)

    try:
        cache_items = list(MemoryWriteCache.objects.filter(id__in=cache_item_ids).order_by("created_at", "id"))
        batch_content = build_batch_content(cache_items)
        if not batch_content:
            MemoryWriteCache.objects.filter(id__in=cache_item_ids).delete()
            return False

        memory_space = MemorySpace.objects.get(id=memory_space_id)
        summarized_content = _summarize_memory_batch_content(memory_space, batch_content, model_id=model_id)
        owner_username, owner_domain, organization_id = resolve_memory_target(memory_space, memory_target_id)
        # 团队记忆 owner_username 为空时补组名，保证前端“管理组织”列有值（与直接写入路径一致）
        if organization_id is not None and not owner_username:
            owner_username = _resolve_org_display_name(organization_id)

        process_memory_write(
            memory_space_id=memory_space_id,
            title=title,
            content=summarized_content,
            owner_username=owner_username,
            owner_domain=owner_domain,
            organization_id=organization_id,
            model_id=model_id,
            skip_write_rule=True,
        )
        MemoryWriteCache.objects.filter(id__in=cache_item_ids).delete()
        return True
    except Exception:
        if cache_item_ids:
            MemoryWriteCache.objects.filter(id__in=cache_item_ids).update(status=MemoryWriteCache.STATUS_PENDING)
        raise


@shared_task
def general_embed(knowledge_document_id_list, username, domain="domain.com", delete_qa_pairs=False):
    logger.info(f"general_embed: {knowledge_document_id_list}")
    document_list = KnowledgeDocument.objects.filter(id__in=knowledge_document_id_list)
    general_embed_by_document_list(document_list, username=username, domain=domain, delete_qa_pairs=delete_qa_pairs)
    logger.info(f"knowledge training finished: {knowledge_document_id_list}")


@shared_task
def retrain_all(knowledge_base_id, username, domain, delete_qa_pairs):
    logger.info("Start retraining")
    document_list = KnowledgeDocument.objects.filter(knowledge_base_id=knowledge_base_id)
    document_list.update(train_status=DocumentStatus.CHUNKING)
    general_embed_by_document_list(document_list, username=username, domain=domain, delete_qa_pairs=delete_qa_pairs)


def general_embed_by_document_list(document_list, is_show=False, username="", domain="", delete_qa_pairs=False):
    if is_show:
        res, remote_docs, _ = invoke_one_document(document_list[0], is_show)
        docs = [i["page_content"] for i in remote_docs][:10]
        return docs
    logger.info(f"document_list: {document_list}")
    # Prefetch related models and knowledge subtype records once to avoid N+1 queries
    # inside the per-document ingest loop (embed/ocr models + file/manual/web_page records).
    if hasattr(document_list, "select_related"):
        document_list = list(
            document_list.select_related(
                "knowledge_base",
                "knowledge_base__embed_model",
                "semantic_chunk_parse_embedding_model",
                "ocr_model",
            ).prefetch_related(
                "fileknowledge_set",
                "manualknowledge_set",
                "webpageknowledge_set",
            )
        )
    knowledge_base_id = document_list[0].knowledge_base_id
    knowledge_ids = [doc.id for doc in document_list]
    task_obj = KnowledgeTask.objects.create(
        created_by=username,
        domain=domain,
        knowledge_base_id=knowledge_base_id,
        task_name=document_list[0].name,
        knowledge_ids=knowledge_ids,
        train_progress=0,
        total_count=len(knowledge_ids),
        status=KnowledgeTaskStatus.RUNNING,
    )
    train_progress = round(float(1 / len(task_obj.knowledge_ids)) * 100, 2)
    has_failure = False
    total = len(document_list)
    for index, document in tqdm(enumerate(document_list)):
        success = True
        try:
            # invoke_document_to_es mutates and saves this same document object in place,
            # so document.train_status is already up to date without a refresh_from_db().
            invoke_document_to_es(document=document, delete_qa_pairs=delete_qa_pairs)
            if document.train_status == DocumentStatus.ERROR:
                success = False
                has_failure = True
        except Exception:
            logger.exception("Failed to invoke document to ES: document_id=%s", document.id)
            success = False
            has_failure = True
            document.train_status = DocumentStatus.ERROR
            document.error_message = "训练过程中发生异常"
            document.save()
        task_progress = task_obj.train_progress + train_progress
        task_obj.train_progress = round(task_progress, 2)
        if success:
            task_obj.completed_count += 1
        if index < total - 1:
            task_obj.name = document_list[index + 1].name
        task_obj.save()
    if has_failure:
        # Retain the tracking row so the failure stays visible to the frontend (get_my_tasks).
        task_obj.status = KnowledgeTaskStatus.FAILED
        task_obj.save()
        logger.warning(f"Knowledge training completed with failures. Task {task_obj.id} retained for tracking.")
    else:
        # Full success: delete the tracking row to keep get_my_tasks clean (no lingering
        # "success" rows). Failures are the only state we retain.
        task_obj.delete()
    return None


@shared_task
def invoke_document_to_es(document_id=0, document=None, delete_qa_pairs=False):
    if document_id:
        document = KnowledgeDocument.objects.filter(id=document_id).first()
    if not document:
        logger.error(f"document {document_id} not found")
        return
    document.train_status = DocumentStatus.CHUNKING
    document.chunk_size = 0
    document.save()
    logger.info(f"document {document.name} progress: {document.train_progress}")
    keep_qa = not delete_qa_pairs
    KnowledgeSearchService.delete_es_content(document.knowledge_index_name(), document.id, document.name, keep_qa)
    res, knowledge_docs, error_msg = invoke_one_document(document)
    if not res:
        document.train_status = DocumentStatus.ERROR
        document.error_message = error_msg
        document.save()
        return
    document.train_status = DocumentStatus.READY
    document.error_message = None
    document.save()
    logger.info(f"document {document.name} progress: {document.train_progress}")


def invoke_one_document(document, is_show=False):
    """处理文档并调用相应的摄取方法"""
    source_type = document.knowledge_source_type
    logger.info(f"Start handle {source_type} knowledge: {document.name}")

    # 准备通用参数
    params = _prepare_ingest_params(document, is_show)

    # 初始化 RAG 实例
    rag = PgvectorRag()

    res = {"status": "fail"}
    knowledge_docs = []
    error_msg = None

    try:
        if source_type == "file":
            res = _handle_file_ingest(document, params, rag)
        elif source_type == "manual":
            res = _handle_manual_ingest(document, params, rag)
        elif source_type == "web_page":
            res = _handle_webpage_ingest(document, params, rag)
        else:
            error_msg = f"不支持的文档类型: {source_type}"
            logger.error(error_msg)
            return False, [], error_msg

        # 处理返回结果
        if is_show:
            knowledge_docs = res.get("documents", [])
        document.chunk_size = res.get("chunks_size", 0)

        if not document.chunk_size:
            error_msg = f"获取不到文档，返回结果为： {res}"
            logger.error(error_msg)

    except Exception as e:
        error_msg = str(e)
        logger.exception(f"文档处理失败: {e}")
        res = {"status": "error", "message": error_msg}

    return res.get("status") == "success", knowledge_docs, error_msg


def _prepare_ingest_params(document, is_preview=False):
    """准备摄取参数"""
    embed_config = {}
    semantic_embed_config = {}
    semantic_embed_model_name = ""

    if document.knowledge_base.embed_model:
        embed_config = {
            "base_url": document.knowledge_base.embed_model.base_url,
            "api_key": document.knowledge_base.embed_model.api_key,
            "model": document.knowledge_base.embed_model.model_name,
        }

    if document.semantic_chunk_parse_embedding_model:
        semantic_embed_config = {
            "base_url": document.semantic_chunk_parse_embedding_model.base_url,
            "api_key": document.semantic_chunk_parse_embedding_model.api_key,
            "model": document.semantic_chunk_parse_embedding_model.model_name,
        }
        semantic_embed_model_name = document.semantic_chunk_parse_embedding_model.model_name

    # OCR配置
    ocr_config = {}
    if document.enable_ocr_parse and document.ocr_model:
        runtime_ocr_config = document.ocr_model.runtime_ocr_config
        ocr_config = {
            "ocr_type": runtime_ocr_config.get("ocr_type", "olm_ocr"),
            "olm_base_url": runtime_ocr_config.get("base_url", ""),
            "olm_api_key": runtime_ocr_config.get("api_key") or " ",
            "olm_model": runtime_ocr_config.get("model", "olmOCR-7B-0225-preview"),
        }
        if runtime_ocr_config.get("ocr_type") == "azure_ocr":
            ocr_config["olm_base_url"] = runtime_ocr_config.get("endpoint", "")

    params = {
        "is_preview": is_preview,
        "knowledge_base_id": document.knowledge_index_name(),
        "knowledge_id": str(document.id),
        "embed_model_base_url": embed_config.get("base_url", ""),
        "embed_model_api_key": embed_config.get("api_key", "") or " ",
        "embed_model_name": embed_config.get("model", ""),
        "chunk_mode": document.chunk_type,
        "chunk_size": document.general_parse_chunk_size,
        "chunk_overlap": document.general_parse_chunk_overlap,
        "load_mode": document.mode,
        "semantic_chunk_model_base_url": semantic_embed_config.get("base_url", ""),
        "semantic_chunk_model_api_key": semantic_embed_config.get("api_key", "") or " ",
        "semantic_chunk_model": semantic_embed_config.get("model", semantic_embed_model_name),
        "metadata": {"enabled": "true", "is_doc": "1", "qa_count": 0},
    }
    params.update(ocr_config)

    return params


def _handle_file_ingest(document, params, rag):
    """处理文件类型的文档摄取"""
    # Use the prefetched reverse relation when available to avoid a per-document query.
    knowledge = next(iter(document.fileknowledge_set.all()), None)
    if not knowledge:
        raise ValueError(f"找不到文件知识记录: document_id={document.id}")

    # 创建临时文件
    file_extension = knowledge.file.name.split(".")[-1].lower() if "." in knowledge.file.name else ""
    with tempfile.NamedTemporaryFile(delete=False, suffix=f".{file_extension}") as temp_file:
        # 写入文件内容
        for chunk in knowledge.file.chunks():
            temp_file.write(chunk)
        temp_file.flush()
        temp_path = temp_file.name

    try:
        # 调用 RAG 的 file_ingest 方法
        result = rag.file_ingest(file_path=temp_path, file_name=knowledge.file.name, params=params)
        return result
    finally:
        # 清理临时文件
        if os.path.exists(temp_path):
            os.unlink(temp_path)


def _handle_manual_ingest(document, params, rag):
    """处理手动输入类型的文档摄取"""
    # Use the prefetched reverse relation when available to avoid a per-document query.
    knowledge = next(iter(document.manualknowledge_set.all()), None)
    if not knowledge:
        raise ValueError(f"找不到手动知识记录: document_id={document.id}")

    # 合并标题和内容
    content = document.name + knowledge.content

    # 调用 RAG 的 custom_content_ingest 方法
    result = rag.custom_content_ingest(content=content, params=params)
    return result


def _handle_webpage_ingest(document, params, rag):
    """处理网页类型的文档摄取"""
    # Use the prefetched reverse relation when available to avoid a per-document query.
    knowledge = next(iter(document.webpageknowledge_set.all()), None)
    if not knowledge:
        raise ValueError(f"找不到网页知识记录: document_id={document.id}")

    # 调用 RAG 的 website_ingest 方法
    result = rag.website_ingest(url=knowledge.url, max_depth=knowledge.max_depth, params=params)
    return result


@shared_task
def sync_web_page_knowledge(web_page_knowledge_id):
    """
    Sync web page knowledge by ID.
    """
    web_page = WebPageKnowledge.objects.filter(id=web_page_knowledge_id).first()
    if not web_page:
        logger.error(f"Web page knowledge {web_page_knowledge_id} not found.")
        return
    document_list = [web_page.knowledge_document]
    web_page.knowledge_document.train_status = DocumentStatus.CHUNKING
    web_page.last_run_time = timezone.now()
    web_page.save()
    web_page.knowledge_document.save()
    # If cleanup of old chunks fails we must NOT re-embed, otherwise we would leave stale or
    # duplicated chunks in the index (F074). Mark the document as errored and bail out.
    if not delete_and_update_old_data(web_page):
        document = web_page.knowledge_document
        document.train_status = DocumentStatus.ERROR
        document.error_message = "同步前清理旧数据失败，已跳过重新训练以避免重复分块"
        document.save()
        logger.error(
            "Skip re-embedding web page %s because old-data cleanup failed.",
            web_page_knowledge_id,
        )
        return
    general_embed_by_document_list(
        document_list,
        False,
        web_page.knowledge_document.created_by,
        web_page.knowledge_document.domain,
    )


def delete_and_update_old_data(web_page: WebPageKnowledge) -> bool:
    """Clean up old chunks/QA metadata before re-embedding a web page.

    Returns True when the destructive cleanup completed and it is safe to re-embed.
    The ES deletion is fatal: if it fails we return False so the caller can abort instead
    of producing duplicate/stale chunks. Failures of the non-destructive QA metadata refresh
    are logged but treated as recoverable.
    """
    index_name = web_page.knowledge_document.knowledge_index_name()
    knowledge_document_ids = [web_page.knowledge_document.id]
    # Destructive step: removing the previous chunks. A failure here is fatal.
    try:
        KnowledgeSearchService.delete_es_content(index_name=index_name, doc_id=knowledge_document_ids, keep_qa=True)
    except Exception:
        logger.exception("Failed to delete old ES content for web_page_id=%s", web_page.id)
        return False

    # Non-destructive step: detach QA pairs and refresh their metadata. Recoverable on failure.
    try:
        qa_pairs = QAPairs.objects.filter(document_id=web_page.knowledge_document.id)
        qa_pairs.update(document_id=0)
        qa_pairs_id = list(qa_pairs.values_list("id", flat=True))
        request = DocumentMetadataUpdateRequest(
            knowledge_ids=[f"qa_pairs_id_{i}" for i in qa_pairs_id],
            chunk_ids=[],
            metadata={"base_chunk_id": ""},
        )
        rag_client = PgvectorRag()
        rag_client.update_metadata(request)
    except Exception:
        logger.exception("Failed to refresh QA metadata for web_page_id=%s", web_page.id)
    return True


@shared_task
def create_qa_pairs(qa_pairs_id_list, only_question, delete_old_qa_pairs=False):
    qa_pairs_list = QAPairs.objects.filter(id__in=qa_pairs_id_list)
    if not qa_pairs_list:
        logger.info(f"QAPairs with ID {qa_pairs_id_list} not found.")
        return
    knowledge_base = qa_pairs_list[0].knowledge_base
    question_llm = qa_pairs_list[0].llm_model
    answer_llm = qa_pairs_list[0].answer_llm_model
    username = qa_pairs_list[0].created_by
    task_obj = KnowledgeTask.objects.create(
        created_by=username,
        domain=qa_pairs_list[0].domain,
        knowledge_base_id=knowledge_base.id,
        task_name=qa_pairs_list[0].name,
        knowledge_ids=[doc for doc in qa_pairs_id_list],
        train_progress=0,
        is_qa_task=True,
        status=KnowledgeTaskStatus.RUNNING,
    )

    es_index = knowledge_base.knowledge_index_name()
    embed_config = {
        "base_url": knowledge_base.embed_model.base_url,
        "api_key": knowledge_base.embed_model.api_key,
        "model": knowledge_base.embed_model.model_name,
    }
    llm_setting = {
        "question": {
            "openai_api_base": question_llm.openai_api_base,
            "openai_api_key": question_llm.openai_api_key,
            "model": question_llm.model_name,
        },
        "answer": {
            "openai_api_base": answer_llm.openai_api_base,
            "openai_api_key": answer_llm.openai_api_key,
            "model": answer_llm.model_name,
        },
    }

    client = ChunkHelper()
    failure_count = 0
    for qa_pairs_obj in qa_pairs_list:
        # 修改状态为生成中
        try:
            task_obj.task_name = qa_pairs_obj.name
            task_obj.completed_count = 0
            task_obj.train_progress = 0
            qa_pairs_obj.status = "generating"
            qa_pairs_obj.save()
            content_list = client.get_qa_content(qa_pairs_obj.document_id, es_index)
            if delete_old_qa_pairs:
                ChunkHelper.delete_es_content(qa_pairs_obj.id)
            task_obj.total_count = len(content_list) * qa_pairs_obj.qa_count
            task_obj.save()
            success_count = client.create_document_qa_pairs(
                content_list,
                embed_config,
                es_index,
                llm_setting,
                qa_pairs_obj,
                only_question,
                task_obj,
            )
        except Exception:
            logger.exception("Failed to create QA pairs: qa_pairs_id=%s", qa_pairs_obj.id)
            failure_count += 1
            qa_pairs_obj.status = "failed"
            qa_pairs_obj.save()
        else:
            qa_pairs_obj.status = "completed"
            qa_pairs_obj.generate_count = success_count
            qa_pairs_obj.save()
    if failure_count:
        # Any failure: retain the tracking row so the failure stays visible (get_my_tasks /
        # get_qa_pairs_task_status). Only delete on full success.
        task_obj.status = KnowledgeTaskStatus.FAILED
        task_obj.save()
        logger.warning(f"QA pairs generation completed with {failure_count} failures. Task {task_obj.id} retained.")
    else:
        task_obj.delete()


@shared_task
def generate_answer(qa_pairs_id):
    qa_pairs = QAPairs.objects.get(id=qa_pairs_id)
    client = ChunkHelper()
    index_name = qa_pairs.knowledge_base.knowledge_index_name()
    return_data = get_chunk_and_question(client, index_name, qa_pairs)
    client.update_qa_pairs_answer(return_data, qa_pairs)


def get_chunk_and_question(client, index_name, qa_pairs):
    chunk_data = client.get_qa_content(qa_pairs.document_id, index_name)
    chunk_data_map = {i["chunk_id"]: i["content"] for i in chunk_data}
    metadata_filter = {"qa_pairs_id": str(qa_pairs.id)}
    res = client.get_document_es_chunk(index_name, page_size=0, metadata_filter=metadata_filter, get_count=False)
    return_data = [
        {
            "question": i["page_content"],
            "id": i["metadata"]["chunk_id"],
            "content": chunk_data_map.get(i["metadata"].get("base_chunk_id", ""), ""),
        }
        for i in res.get("documents", [])
        if not i["metadata"].get("qa_answer")
    ]
    return return_data


@shared_task
def rebuild_graph_community_by_instance(instance_id):
    def _execute():
        graph_obj = KnowledgeGraph.objects.get(id=instance_id)
        graph_obj.status = "rebuilding"
        graph_obj.save()
        res = GraphUtils.rebuild_graph_community(graph_obj)
        if not res["result"]:
            graph_obj.status = "failed"
            graph_obj.save()
            logger.error("Failed to rebuild graph community")
            return
        graph_obj.status = "completed"
        graph_obj.save()
        logger.info("Graph community rebuild completed for instance ID: {}".format(instance_id))

    return _run_in_native_thread(_execute)


@shared_task
def create_graph(instance_id):
    def _execute():
        logger.info("Start creating graph for instance ID: {}".format(instance_id))
        instance = KnowledgeGraph.objects.get(id=instance_id)
        instance.status = "training"
        instance.save()
        res = GraphUtils.create_graph(instance)
        if not res["result"]:
            instance.status = "failed"
            instance.save()
            logger.error("Failed to create graph: {}".format(res["message"]))
            return

        instance.status = "completed"
        instance.save()
        logger.info("Graph created completed: {}".format(instance.id))

    return _run_in_native_thread(_execute)


@shared_task
def update_graph(instance_id, old_doc_list):
    def _execute():
        logger.info("Start updating graph for instance ID: {}".format(instance_id))
        instance = KnowledgeGraph.objects.get(id=instance_id)
        instance.status = "training"
        instance.save()
        res = GraphUtils.update_graph(instance, old_doc_list)
        if not res["result"]:
            instance.status = "failed"
            instance.save()
            logger.error("Failed to update graph: {}".format(res["message"]))
            return

        instance.status = "completed"
        instance.save()
        logger.info("Graph updated completed: {}".format(instance.id))

    return _run_in_native_thread(_execute)


@shared_task
def create_qa_pairs_by_json(file_data, knowledge_base_id, username, domain):
    """
    通过JSON数据批量创建问答对

    Args:
        file_data: 包含问答对数据的JSON列表，每个元素包含instruction和output字段
        knowledge_base_id: 知识库ID
        username: 创建用户名
        domain: 域名
    """
    # 获取知识库对象
    knowledge_base = KnowledgeBase.objects.filter(id=knowledge_base_id).first()
    if not knowledge_base:
        return

    # 初始化任务和问答对对象
    task_obj, qa_pairs_list = _initialize_qa_task(file_data, knowledge_base_id, username, domain)

    # 批量处理问答对
    try:
        _process_qa_pairs_batch(qa_pairs_list, file_data, knowledge_base, task_obj)
    except Exception as e:
        logger.exception(f"批量创建问答对失败: {str(e)}")

    # 清理任务对象
    task_obj.delete()
    logger.info("批量创建问答对任务完成")


def _initialize_qa_task(file_data, knowledge_base_id, username, domain):
    """初始化任务和问答对对象"""
    task_name = list(file_data.keys())[0]
    qa_pairs_list = []
    qa_pairs_id_list = []

    # 创建问答对对象
    for qa_name in file_data.keys():
        qa_pairs = create_qa_pairs_task(knowledge_base_id, qa_name, username, domain)
        if qa_pairs.id not in qa_pairs_id_list:
            qa_pairs_list.append(qa_pairs)
            qa_pairs_id_list.append(qa_pairs.id)

    # 创建任务跟踪对象
    task_obj = KnowledgeTask.objects.create(
        created_by=username,
        domain=domain,
        knowledge_base_id=knowledge_base_id,
        task_name=task_name,
        knowledge_ids=qa_pairs_id_list,
        train_progress=0,
        is_qa_task=True,
    )

    return task_obj, qa_pairs_list


def _process_qa_pairs_batch(qa_pairs_list, file_data, knowledge_base, task_obj):
    """批量处理问答对数据"""
    # 准备基础参数
    base_params = _prepare_qa_ingest_params(knowledge_base)
    rag = PgvectorRag()

    for qa_pairs in qa_pairs_list:
        qa_json = file_data[qa_pairs.name]
        params = base_params.copy()
        params["knowledge_id"] = f"qa_pairs_id_{qa_pairs.id}"

        success_count = _process_single_qa_pairs(qa_pairs, qa_json, params, rag, task_obj)

        # 更新问答对数量和任务进度
        qa_pairs.status = "completed"
        qa_pairs.qa_count += success_count
        qa_pairs.generate_count += success_count
        qa_pairs.save()

        logger.info(f"批量创建问答对完成: {qa_pairs.name}, 总数: {len(qa_json)}, 成功: {success_count}")


def _prepare_qa_ingest_params(knowledge_base):
    """准备问答对摄取的基础参数"""
    embed_config = knowledge_base.embed_model

    return {
        "is_preview": False,
        "knowledge_base_id": knowledge_base.knowledge_index_name(),
        "knowledge_id": "0",
        "embed_model_base_url": embed_config.base_url,
        "embed_model_api_key": embed_config.api_key or " ",
        "embed_model_name": embed_config.model_name,
        "chunk_mode": "full",
        "chunk_size": 9999,
        "chunk_overlap": 128,
        "load_mode": "full",
        "semantic_chunk_model_base_url": "",
        "semantic_chunk_model_api_key": " ",
        "semantic_chunk_model": "",
    }


def _process_single_qa_pairs(qa_pairs, qa_json, params, rag, task_obj):
    """处理单个问答对集合"""
    base_metadata = {
        "enabled": "true",
        "base_chunk_id": "",
        "qa_pairs_id": str(qa_pairs.id),
        "is_doc": "0",
    }
    qa_pairs.status = "generating"
    qa_pairs.save()

    success_count = 0
    error_count = 0

    task_obj.task_name = qa_pairs.name
    task_obj.completed_count = 0
    task_obj.total_count = len(qa_json)
    task_obj.train_progress = 0
    task_obj.save()

    logger.info(f"开始处理问答对数据: {qa_pairs.name}")
    train_progress = round(float(1 / len(qa_json)) * 100, 4)
    task_progress = 0

    # First pass: attempt every item once without blocking the worker. Items that fail
    # the first attempt are queued for a single deferred retry pass (see F036) so we never
    # sleep inside the tight per-item loop.
    pending_retry = []
    for index, qa_item in enumerate(tqdm(qa_json)):
        result = _ingest_single_qa_item(qa_item, index, params, base_metadata, rag)
        if result is None:
            continue
        elif result:
            success_count += 1
        else:
            pending_retry.append((index, qa_item))

        # 每10个记录输出一次进度日志
        if (index + 1) % 10 == 0:
            logger.info(f"已处理 {index + 1}/{len(qa_json)} 个问答对，成功: {success_count}, 待重试: {len(pending_retry)}")

        task_progress += train_progress
        task_obj.train_progress = round(task_progress, 2)
        task_obj.completed_count += 1
        task_obj.save()

    # Second pass: retry the items that failed once, after a single bounded backoff. This
    # keeps the same per-item retry semantics without stalling the worker on every item.
    if pending_retry:
        logger.warning(f"{len(pending_retry)} 个问答对首次摄取失败，等待 {QA_INGEST_RETRY_DELAY}s 后统一重试")
        time.sleep(QA_INGEST_RETRY_DELAY)
        for index, qa_item in pending_retry:
            params_with_meta = _build_qa_item_params(qa_item, params, base_metadata)
            if params_with_meta is None:
                continue
            if _ingest_qa_once(qa_item["instruction"], params_with_meta, rag, index):
                logger.info(f"重试成功，索引: {index}")
                success_count += 1
            else:
                error_count += 1
                logger.error(f"创建问答对失败，索引: {index}")

    return success_count


# Backoff (seconds) applied once before the deferred QA retry pass instead of per item.
QA_INGEST_RETRY_DELAY = 5


def _build_qa_item_params(qa_item, base_params, base_metadata):
    """构建单个问答项的请求参数，跳过空 instruction 时返回 None。"""
    if not qa_item["instruction"]:
        return None
    params = base_params.copy()
    params["metadata"] = {
        **base_metadata,
        "qa_question": qa_item["instruction"],
        "qa_answer": qa_item["output"],
    }
    return params


def _ingest_qa_once(content, params, rag, index):
    """摄取单个问答对内容（单次尝试，不阻塞重试）。成功返回 True，失败返回 False。"""
    try:
        res = rag.custom_content_ingest(content=content, params=params)
        if res.get("status") != "success":
            logger.warning(f"摄取问答对失败，索引: {index}, 信息: {res.get('message', '')}")
            return False
        return True
    except Exception as e:
        logger.warning(f"摄取问答对异常，索引: {index}, 错误: {str(e)}")
        return False


def _ingest_single_qa_item(qa_item, index, base_params, base_metadata, rag):
    """处理单个问答项的首次摄取尝试。

    返回 None 表示跳过（空 instruction），True 表示成功，False 表示首次失败需重试。
    """
    params = _build_qa_item_params(qa_item, base_params, base_metadata)
    if params is None:
        logger.warning(f"跳过空instruction，索引: {index}")
        return None
    return _ingest_qa_once(qa_item["instruction"], params, rag, index)


def create_qa_pairs_task(knowledge_base_id, qa_name, username, domain):
    # 创建或获取问答对对象
    qa_pairs, created = QAPairs.objects.get_or_create(
        name=qa_name,
        knowledge_base_id=knowledge_base_id,
        document_id=0,
        created_by=username,
        domain=domain,
        create_type="import",
        status="pending",
    )
    logger.info(f"问答对对象{'创建' if created else '获取'}成功: {qa_pairs.name}")
    return qa_pairs


@shared_task
def create_qa_pairs_by_custom(qa_pairs_id, content_list):
    qa_pairs = QAPairs.objects.get(id=qa_pairs_id)
    es_index = qa_pairs.knowledge_base.knowledge_index_name()
    embed_config = {
        "base_url": qa_pairs.knowledge_base.embed_model.base_url,
        "api_key": qa_pairs.knowledge_base.embed_model.api_key,
        "model": qa_pairs.knowledge_base.embed_model.model_name,
    }
    chunk_obj = {}
    task_obj = KnowledgeTask.objects.create(
        created_by=qa_pairs.created_by,
        domain=qa_pairs.domain,
        knowledge_base_id=qa_pairs.knowledge_base_id,
        task_name=qa_pairs.name,
        knowledge_ids=[qa_pairs.id],
        train_progress=0,
        is_qa_task=True,
        total_count=len(content_list),
    )
    try:
        success_count = ChunkHelper.create_qa_pairs(content_list, chunk_obj, es_index, embed_config, qa_pairs_id, task_obj)
        qa_pairs.generate_count = success_count
        qa_pairs.status = "completed"
    except Exception:
        logger.exception("Failed to create QA pairs by custom: qa_pairs_id=%s", qa_pairs_id)
        qa_pairs.status = "failed"
    task_obj.delete()
    qa_pairs.save()


@shared_task
def create_qa_pairs_by_chunk(qa_pairs_id, kwargs):
    """
    {
           "chunk_list": params["chunk_list"],
           "llm_model_id": params["llm_model_id"],
           "answer_llm_model_id": params["answer_llm_model_id"],
           "qa_count": params["qa_count"],
           "question_prompt": params["question_prompt"],
           "answer_prompt": params["answer_prompt"]
       }
    """
    qa_pairs_obj = QAPairs.objects.get(id=qa_pairs_id)
    qa_pairs_obj.status = "generating"
    qa_pairs_obj.save()
    content_list = [
        {
            "chunk_id": i["id"],
            "content": i["content"],
            "knowledge_id": qa_pairs_obj.document_id,
        }
        for i in kwargs["chunk_list"]
    ]
    question_llm = LLMModel.objects.filter(id=kwargs["llm_model_id"]).first()
    answer_llm = LLMModel.objects.filter(id=kwargs["answer_llm_model_id"]).first()
    llm_setting = {
        "question": {
            "openai_api_base": question_llm.openai_api_base,
            "openai_api_key": question_llm.openai_api_key,
            "model": question_llm.model_name,
        },
        "answer": {
            "openai_api_base": answer_llm.openai_api_base,
            "openai_api_key": answer_llm.openai_api_key,
            "model": answer_llm.model_name,
        },
    }
    es_index = qa_pairs_obj.knowledge_base.knowledge_index_name()
    embed_config = {
        "base_url": qa_pairs_obj.knowledge_base.embed_model.base_url,
        "api_key": qa_pairs_obj.knowledge_base.embed_model.api_key,
        "model": qa_pairs_obj.knowledge_base.embed_model.model_name,
    }
    client = ChunkHelper()
    task_obj = KnowledgeTask.objects.create(
        created_by=qa_pairs_obj.created_by,
        domain=qa_pairs_obj.domain,
        knowledge_base_id=qa_pairs_obj.knowledge_base_id,
        task_name=qa_pairs_obj.name,
        knowledge_ids=[qa_pairs_obj.id],
        train_progress=0,
        is_qa_task=True,
        total_count=len(content_list) * kwargs["qa_count"],
    )
    success_count = client.create_qa_pairs_by_content(
        content_list,
        embed_config,
        es_index,
        llm_setting,
        qa_pairs_obj,
        kwargs["qa_count"],
        kwargs["question_prompt"],
        kwargs["answer_prompt"],
        task_obj,
        kwargs["only_question"],
    )
    qa_pairs_obj.generate_count += success_count
    qa_pairs_obj.status = "completed"
    qa_pairs_obj.save()
    task_obj.delete()


@shared_task
def chat_flow_celery_task(bot_id, node_id, message):
    """ChatFlow周期性任务"""

    def _execute():
        logger.info(f"开始执行ChatFlow周期任务: bot_id={bot_id}, node_id={node_id}")
        bot_obj = Bot.objects.filter(id=bot_id, online=True).first()
        if not bot_obj:
            logger.error(f"Bot {bot_id} 不存在或已下线")
            return
        bot_chat_flow = BotWorkFlow.objects.filter(bot_id=bot_obj.id).first()
        if not bot_chat_flow:
            logger.error(f"Bot {bot_id} 没有配置ChatFlow")
            return
        try:
            engine = create_chat_flow_engine(bot_chat_flow, node_id)
            input_data = {
                "last_message": message,
                "user_id": bot_obj.created_by,
                "bot_id": bot_id,
                "node_id": node_id,
            }
            result = engine.execute(input_data)
            logger.info(f"ChatFlow周期任务执行完成: bot_id={bot_id}, node_id={node_id}, 执行结果为{result}")
        except Exception as e:
            logger.exception(f"ChatFlow周期任务执行失败: bot_id={bot_id}, node_id={node_id}, error={str(e)}")

    return _run_in_native_thread(_execute)


@shared_task
def chat_flow_test_execute_task(workflow_id, node_id, input_data, entry_type, execution_id):
    """ChatFlow测试异步任务"""

    def _execute():
        logger.info(f"开始执行ChatFlow测试异步任务: workflow_id={workflow_id}, node_id={node_id}, execution_id={execution_id}")
        workflow = BotWorkFlow.objects.filter(id=workflow_id).first()
        if not workflow:
            logger.error(f"ChatFlow测试异步任务失败: workflow_id={workflow_id} 不存在")
            return

        try:
            engine = create_chat_flow_engine(workflow, node_id, entry_type=entry_type, execution_id=execution_id)
            if entry_type:
                engine.entry_type = entry_type
            # 来自配置页"测试"的执行，标记 is_test，便于与真实对话执行区分
            engine.is_test = True
            engine.execute(input_data)
            logger.info(f"ChatFlow测试异步任务完成: workflow_id={workflow_id}, node_id={node_id}, execution_id={execution_id}")
        except Exception as e:
            logger.exception(f"ChatFlow测试异步任务失败: workflow_id={workflow_id}, node_id={node_id}, execution_id={execution_id}, error={str(e)}")

    return _run_in_native_thread(_execute)


@shared_task
def update_graph_task(current_count, all_count, task_id):
    def _execute():
        task_obj = KnowledgeTask.objects.filter(id=task_id).first()
        if not task_obj:
            return

        task_obj.completed_count = current_count
        train_progress = round(float(current_count / all_count) * 100, 2)
        task_obj.train_progress = train_progress
        task_obj.save()

    try:
        return _run_in_native_thread(_execute)
    except SynchronousOnlyOperation:
        logger.warning(
            "Skip update_graph_task progress update due to async context conflict: task_id=%s",
            task_id,
        )
        return


# ============================================================================
# 外部渠道消息处理任务（WeChat/DingTalk）
#
# 配置项：
#     max_retries: 最大重试次数，默认 3 次
#     default_retry_delay: 重试间隔（秒），默认 60 秒
#
#     如需调整，修改 @shared_task 装饰器参数：
#         @shared_task(bind=True, max_retries=5, default_retry_delay=120)
#
# 重试机制：
#     - 任务失败时自动重试，最多 max_retries 次
#     - 每次重试间隔 default_retry_delay 秒
#     - 失败时会清除消息去重标记，允许重新处理
#     - 所有重试耗尽后，消息将被丢弃（可通过 Celery 死信队列监控）
#
# 依赖：
#     - 两阶段去重：调用前需先调用 is_message_processed() 标记为 processing
#     - 成功后调用 mark_message_completed()
#     - 失败后调用 mark_message_failed()
# ============================================================================


def _get_bot_chat_flow(bot_id):
    """获取 Bot 的 ChatFlow 配置

    Args:
        bot_id: Bot ID

    Returns:
        BotWorkFlow 对象，如果不存在则返回 None
    """
    bot = Bot.objects.filter(id=bot_id, online=True).first()
    if not bot:
        return None
    return BotWorkFlow.objects.filter(bot_id=bot.id).first()


def _run_channel_message(task, handler_cls, bot_id, msg_id, message, sender_id, config, channel_label):
    """渠道消息处理的共享执行体（async_process_and_reply 风格）

    被企业微信 / 微信公众号等任务复用，差异仅在于 handler 类与日志前缀。

    两阶段去重：调用前已标记为 processing，成功后由 async_process_and_reply 内部
    标记 completed，失败时其内部已调用 mark_message_failed，这里仅负责触发 Celery 重试。

    Args:
        task: 绑定的 Celery 任务实例（用于 task.retry）
        handler_cls: ChatFlow 处理器类
        bot_id: Bot ID
        msg_id: 消息唯一标识
        message: 用户消息内容
        sender_id: 发送者 ID
        config: 渠道配置（包含 node_id 等）
        channel_label: 日志中使用的渠道名称
    """

    def _execute():
        handler = handler_cls(bot_id)
        try:
            bot_chat_flow = _get_bot_chat_flow(bot_id)
            if not bot_chat_flow:
                logger.error(f"{channel_label}消息处理失败：Bot {bot_id} 不存在或未配置 ChatFlow")
                handler.mark_message_failed(msg_id)
                return

            # 执行 ChatFlow 并发送回复
            handler.async_process_and_reply(bot_chat_flow, config, message, sender_id, msg_id)
            logger.info(f"{channel_label}消息处理成功: bot_id={bot_id}, msg_id={msg_id}")

        except Exception as e:
            logger.exception(f"{channel_label}消息处理失败: bot_id={bot_id}, msg_id={msg_id}, error={str(e)}")
            # async_process_and_reply 内部已调用 mark_message_failed
            # 触发 Celery 重试
            raise

    try:
        return _run_in_native_thread(_execute)
    except Exception as e:
        # Celery 重试
        raise task.retry(exc=e)


@shared_task(bind=True, max_retries=3, default_retry_delay=60)
def process_wechat_message(self, bot_id, msg_id, message, sender_id, config):
    """处理企业微信消息的 Celery 任务

    使用两阶段去重：
    - 调用前已标记为 processing
    - 成功后标记为 completed
    - 失败后清除标记并触发重试

    Args:
        bot_id: Bot ID
        msg_id: 消息唯一标识
        message: 用户消息内容
        sender_id: 发送者 ID
        config: 渠道配置（包含 node_id 等）
    """
    from apps.opspilot.utils.wechat_chat_flow_utils import WechatChatFlowUtils

    return _run_channel_message(self, WechatChatFlowUtils, bot_id, msg_id, message, sender_id, config, "微信")


@shared_task(bind=True, max_retries=3, default_retry_delay=60)
def process_dingtalk_message(self, bot_id, msg_id, text_content, sender_id, webhook_url, config):
    """处理钉钉消息的 Celery 任务

    使用两阶段去重：
    - 调用前已标记为 processing
    - 成功后标记为 completed
    - 失败后清除标记并触发重试

    Args:
        bot_id: Bot ID
        msg_id: 消息唯一标识
        text_content: 用户消息内容
        sender_id: 发送者 ID
        webhook_url: 钉钉 Webhook URL
        config: 渠道配置（包含 node_id 等）
    """
    from apps.opspilot.services.dingtalk_chat_flow_utils import DingTalkChatFlowUtils

    def _execute():
        handler = DingTalkChatFlowUtils(bot_id)
        try:
            bot_chat_flow = _get_bot_chat_flow(bot_id)
            if not bot_chat_flow:
                logger.error(f"钉钉消息处理失败：Bot {bot_id} 不存在或未配置 ChatFlow")
                handler.mark_message_failed(msg_id)
                return

            # 执行 ChatFlow
            node_id = config.get("node_id")
            reply_text = handler.execute_chatflow_with_message(bot_chat_flow, node_id, text_content, sender_id)

            # 发送回复
            if webhook_url and reply_text:
                markdown_content = {"title": "机器人回复", "text": reply_text}
                handler.send_message(webhook_url, "markdown", markdown_content)

            # 标记完成
            handler.mark_message_completed(msg_id)
            logger.info(f"钉钉消息处理成功: bot_id={bot_id}, msg_id={msg_id}")

        except Exception as e:
            logger.exception(f"钉钉消息处理失败: bot_id={bot_id}, msg_id={msg_id}, error={str(e)}")
            handler.mark_message_failed(msg_id)
            raise

    try:
        return _run_in_native_thread(_execute)
    except Exception as e:
        # Celery 重试
        raise self.retry(exc=e)


@shared_task(bind=True, max_retries=3, default_retry_delay=60)
def process_wechat_official_message(self, bot_id, msg_id, message, sender_id, config):
    """处理微信公众号消息的 Celery 任务

    使用两阶段去重：
    - 调用前已标记为 processing
    - 成功后标记为 completed
    - 失败后清除标记并触发重试

    Args:
        bot_id: Bot ID
        msg_id: 消息唯一标识
        message: 用户消息内容
        sender_id: 发送者 ID（OpenID）
        config: 渠道配置（包含 node_id, appid, secret 等）
    """
    from apps.opspilot.services.wechat_official_chat_flow_utils import WechatOfficialChatFlowUtils

    return _run_channel_message(self, WechatOfficialChatFlowUtils, bot_id, msg_id, message, sender_id, config, "微信公众号")


@shared_task
def process_memory_write_cache(
    memory_space_id: int,
    title: str,
    content: str,
    owner_username: str,
    owner_domain: str,
    organization_id: int = None,
    model_id: int = None,
    workflow_id: int = None,
    node_id: str = "",
    write_batch_size: int = None,
):
    if not content:
        return

    normalized_batch_size = normalize_write_batch_size(write_batch_size)

    if not workflow_id or not node_id:
        logger.warning("[MemoryWriteBatchTask] 缺少 workflow_id 或 node_id，回退为直接写入")
        process_memory_write(
            memory_space_id=memory_space_id,
            title=title,
            content=content,
            owner_username=owner_username,
            owner_domain=owner_domain,
            organization_id=organization_id,
            model_id=model_id,
        )
        return

    memory_target_id = build_memory_target_id(
        owner_username=owner_username,
        owner_domain=owner_domain,
        organization_id=organization_id,
    )
    workflow_id = int(workflow_id)

    try:
        close_old_connections()

        with transaction.atomic():
            MemoryWriteCache.objects.create(
                workflow_id=workflow_id,
                node_id=node_id,
                memory_target_id=memory_target_id,
                content=content,
            )

            ready_items = list(
                MemoryWriteCache.objects.select_for_update()
                .filter(
                    workflow_id=workflow_id,
                    node_id=node_id,
                    memory_target_id=memory_target_id,
                    status=MemoryWriteCache.STATUS_PENDING,
                )
                .order_by("created_at", "id")[:normalized_batch_size]
            )

            if len(ready_items) < normalized_batch_size:
                logger.info(
                    f"[MemoryWriteBatchTask] 缓存未达到阈值: workflow_id={workflow_id}, "
                    f"node_id={node_id}, target={memory_target_id}, current={len(ready_items)}, "
                    f"required={normalized_batch_size}"
                )
                return

        _flush_memory_write_cache_group(
            memory_space_id=memory_space_id,
            title=title,
            model_id=model_id,
            workflow_id=workflow_id,
            node_id=node_id,
            memory_target_id=memory_target_id,
            batch_size=normalized_batch_size,
        )
    except Exception as e:
        logger.error(
            f"[MemoryWriteBatchTask] 批量写入失败: workflow_id={workflow_id}, node_id={node_id}, target={memory_target_id}, error={e}",
            exc_info=True,
        )
        raise


@shared_task
def flush_memory_write_cache_for_node(
    workflow_id: int,
    node_id: str,
    memory_space_id: int,
    title: str = "",
    model_id: int = None,
):
    close_old_connections()
    target_ids = list(
        MemoryWriteCache.objects.filter(
            workflow_id=workflow_id,
            node_id=node_id,
            status=MemoryWriteCache.STATUS_PENDING,
        )
        .order_by("memory_target_id")
        .values_list("memory_target_id", flat=True)
        .distinct()
    )

    for memory_target_id in target_ids:
        _flush_memory_write_cache_group(
            memory_space_id=memory_space_id,
            title=title or f"自动记忆-{node_id}",
            model_id=model_id,
            workflow_id=int(workflow_id),
            node_id=node_id,
            memory_target_id=memory_target_id,
            force_flush=True,
        )


@shared_task
def flush_all_pending_memory_write_cache():
    close_old_connections()
    pending_pairs = list(MemoryWriteCache.objects.filter(status=MemoryWriteCache.STATUS_PENDING).values("workflow_id", "node_id").distinct())
    if not pending_pairs:
        return

    workflow_ids = {item["workflow_id"] for item in pending_pairs}
    workflow_map = BotWorkFlow.objects.filter(id__in=workflow_ids).in_bulk()
    node_configs_by_workflow = {}

    for pending_pair in pending_pairs:
        workflow_id = pending_pair["workflow_id"]
        workflow = workflow_map.get(workflow_id)
        if not workflow:
            continue

        node_configs = node_configs_by_workflow.setdefault(workflow_id, extract_memory_write_node_configs(workflow.flow_json))
        node_id = pending_pair["node_id"]
        config = node_configs.get(node_id) or {}
        memory_space_id = config.get("memorySpace") or config.get("memory_space_id")
        if not memory_space_id:
            continue
        flush_memory_write_cache_for_node(
            workflow_id=workflow_id,
            node_id=node_id,
            memory_space_id=memory_space_id,
            title=config.get("title", "") or f"自动记忆-{node_id}",
            model_id=config.get("llmModel"),
        )


@shared_task
def process_memory_write(
    memory_space_id: int,
    title: str,
    content: str,
    owner_username: str,
    owner_domain: str,
    organization_id: int = None,
    model_id: int = None,
    skip_write_rule: bool = False,
):
    """异步写入记忆条目，每个用户/组织在每个记忆空间只有一条记忆

    核心逻辑：
    - 个人记忆：按 owner_username + owner_domain + memory_space_id 查找唯一记忆
    - 组织记忆：按 organization_id + memory_space_id 查找唯一记忆
    - 找到则合并内容，未找到则创建新记忆

    Args:
        model_id: 可选，用于覆盖记忆空间的默认模型（workflow 节点级别配置）
        skip_write_rule: 为 True 时跳过 write_rule 规范化，用于批量归纳后的单次写入
    """
    is_org_memory = organization_id is not None
    try:
        close_old_connections()

        # 获取记忆空间配置
        memory_space = MemorySpace.objects.get(id=memory_space_id)
        write_rule = memory_space.write_rule
        # 优先使用传入的 model_id（workflow 节点配置），否则使用记忆空间的默认模型
        effective_model_id = model_id if model_id else memory_space.default_model
        # Step 1: 查找该实体的现有记忆（每个用户/组织只有一条）
        if is_org_memory:
            existing_memory = Memory.objects.filter(
                memory_space_id=memory_space_id,
                organization_id=organization_id,
            ).first()
        else:
            existing_memory = Memory.objects.filter(
                memory_space_id=memory_space_id,
                owner_username=owner_username,
                owner_domain=owner_domain,
                organization_id__isnull=True,
            ).first()

        # 如果没有配置模型，直接创建或追加内容
        if not effective_model_id:
            if existing_memory:
                # 简单追加内容
                existing_memory.content = f"{existing_memory.content}\n\n---\n\n{content}"
                existing_memory.updated_by = owner_username
                existing_memory.save()
            else:
                Memory.objects.create(
                    memory_space_id=memory_space_id,
                    title=title,
                    content=content,
                    owner_username=owner_username,
                    owner_domain=owner_domain,
                    organization_id=organization_id,
                    created_by=owner_username,
                    updated_by=owner_username,
                )
            return

        client = _build_memory_write_client(effective_model_id)
        if not client:
            if existing_memory:
                existing_memory.content = f"{existing_memory.content}\n\n---\n\n{content}"
                existing_memory.updated_by = owner_username
                existing_memory.save()
            else:
                Memory.objects.create(
                    memory_space_id=memory_space_id,
                    title=title,
                    content=content,
                    owner_username=owner_username,
                    owner_domain=owner_domain,
                    organization_id=organization_id,
                    created_by=owner_username,
                    updated_by=owner_username,
                )
            return

        # Step 2: 使用 write_rule 规范化新内容（如果配置了）
        processed_content = content
        if write_rule and not skip_write_rule:
            try:
                messages = [
                    SystemMessage(content=write_rule),
                    HumanMessage(content=content),
                ]
                response = client.invoke(messages)
                processed_content = response.content if hasattr(response, "content") else str(response)
            except Exception as e:
                logger.error(f"[MemoryWriteTask] 规范化失败: {e}，使用原始内容", exc_info=True)

        # Step 3: 如果没有现有记忆，直接创建
        if not existing_memory:
            Memory.objects.create(
                memory_space_id=memory_space_id,
                title=title,
                content=processed_content,
                owner_username=owner_username,
                owner_domain=owner_domain,
                organization_id=organization_id,
                created_by=owner_username,
                updated_by=owner_username,
            )
            return

        # Step 4: 有现有记忆，使用 LLM 智能合并
        merge_prompt = f"""你是一个记忆管理助手。请将新内容与现有记忆智能合并。

## 现有记忆
标题: {existing_memory.title}
内容:
{existing_memory.content}

## 新内容
{processed_content}

## 合并规则（重要！）
你必须将新内容与旧内容**智能合并**，而不是简单替换：
- **保留旧内容中仍然有效的信息**
- **追加新内容中的新信息**
- **如果新旧信息冲突，以新内容为准**（如用户说"我现在喜欢咖啡"覆盖"我喜欢茶"）
- **去除重复信息**，保持内容简洁
- **保持 Markdown 格式**，条目清晰

## 输出格式
请严格按以下 JSON 格式输出，不要输出其他内容：
```json
{{
    "title": "合并后的记忆标题",
    "content": "合并后的完整记忆内容"
}}
```

## 示例
假设现有记忆：
- 标题: 用户饮食偏好
- 内容: "喜欢川菜，不吃香菜"

新内容: "我也喜欢粤式早茶"

正确的合并结果：
```json
{{
    "title": "用户饮食偏好",
    "content": "- 喜欢川菜\\n- 喜欢粤式早茶\\n- 不吃香菜"
}}
```

错误的做法（直接替换）：
```json
{{
    "title": "用户饮食偏好",
    "content": "我也喜欢粤式早茶"
}}
```"""

        try:
            messages = [
                SystemMessage(content="你是一个记忆管理助手，负责智能合并新旧记忆内容。请严格按照 JSON 格式输出。"),
                HumanMessage(content=merge_prompt),
            ]
            response = client.invoke(messages)
            merge_text = response.content if hasattr(response, "content") else str(response)

            # 解析 JSON 响应
            json_match = re.search(r"```json\s*(.*?)\s*```", merge_text, re.DOTALL)
            if json_match:
                json_str = json_match.group(1)
            else:
                json_str = merge_text.strip()
                json_str = re.sub(r"^```\w*\s*", "", json_str)
                json_str = re.sub(r"\s*```$", "", json_str)

            merge_result = json.loads(json_str)
            merged_title = merge_result.get("title", existing_memory.title)
            merged_content = merge_result.get("content", processed_content)

            # 更新现有记忆
            existing_memory.title = merged_title
            existing_memory.content = merged_content
            existing_memory.updated_by = owner_username
            existing_memory.save()

        except json.JSONDecodeError as e:
            logger.error(f"[MemoryWriteTask] JSON 解析失败: {e}，简单追加内容")
            existing_memory.content = f"{existing_memory.content}\n\n---\n\n{processed_content}"
            existing_memory.updated_by = owner_username
            existing_memory.save()
        except Exception as e:
            logger.error(f"[MemoryWriteTask] LLM 合并失败: {e}，简单追加内容", exc_info=True)
            existing_memory.content = f"{existing_memory.content}\n\n---\n\n{processed_content}"
            existing_memory.updated_by = owner_username
            existing_memory.save()

    except MemorySpace.DoesNotExist:
        logger.error(f"[MemoryWriteTask] 记忆空间不存在: space_id={memory_space_id}")
        raise
    except Exception as e:
        logger.error(f"[MemoryWriteTask] 记忆写入失败: {e}", exc_info=True)
        raise


@shared_task
def cleanup_expired_workflow_attachments_task():
    deleted_count = cleanup_expired_workflow_attachments(retention_days=3)
    logger.info("清理过期工作流附件完成: deleted_count=%s", deleted_count)
    return deleted_count
