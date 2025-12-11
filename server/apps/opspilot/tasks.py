import os
import tempfile
import time

from celery import shared_task
from tqdm import tqdm

from apps.core.logger import opspilot_logger as logger
from apps.opspilot.enum import DocumentStatus
from apps.opspilot.metis.llm.rag.naive_rag.pgvector.pgvector_rag import PgvectorRag
from apps.opspilot.models import (
    Bot,
    BotWorkFlow,
    FileKnowledge,
    KnowledgeBase,
    KnowledgeDocument,
    KnowledgeGraph,
    KnowledgeTask,
    LLMModel,
    ManualKnowledge,
    QAPairs,
    WebPageKnowledge,
)
from apps.opspilot.services.knowledge_search_service import KnowledgeSearchService
from apps.opspilot.utils.chat_flow_utils.engine.factory import create_chat_flow_engine
from apps.opspilot.utils.chunk_helper import ChunkHelper
from apps.opspilot.utils.graph_utils import GraphUtils


@shared_task
def general_embed(knowledge_document_id_list, username, domain="domain.com", delete_qa_pairs=False):
    logger.info(f"general_embed: {knowledge_document_id_list}")
    document_list = KnowledgeDocument.objects.filter(
        id__in=knowledge_document_id_list)
    general_embed_by_document_list(
        document_list, username=username, domain=domain, delete_qa_pairs=delete_qa_pairs)
    logger.info(f"knowledge training finished: {knowledge_document_id_list}")


@shared_task
def retrain_all(knowledge_base_id, username, domain, delete_qa_pairs):
    logger.info("Start retraining")
    document_list = KnowledgeDocument.objects.filter(
        knowledge_base_id=knowledge_base_id)
    document_list.update(train_status=DocumentStatus.CHUNKING)
    general_embed_by_document_list(
        document_list, username=username, domain=domain, delete_qa_pairs=delete_qa_pairs)


def general_embed_by_document_list(document_list, is_show=False, username="", domain="", delete_qa_pairs=False):
    if is_show:
        res, remote_docs = invoke_one_document(document_list[0], is_show)
        docs = [i["page_content"] for i in remote_docs][:10]
        return docs
    logger.info(f"document_list: {document_list}")
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
    )
    train_progress = round(float(1 / len(task_obj.knowledge_ids)) * 100, 2)
    for index, document in tqdm(enumerate(document_list)):
        try:
            invoke_document_to_es(
                document=document, delete_qa_pairs=delete_qa_pairs)
        except Exception as e:
            logger.exception(e)
        task_progress = task_obj.train_progress + train_progress
        task_obj.train_progress = round(task_progress, 2)
        task_obj.completed_count += 1
        if index < len(document_list) - 1:
            task_obj.name = document_list[index + 1].name
        task_obj.save()
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
    logger.info(
        f"document {document.name} progress: {document.train_progress}")
    keep_qa = not delete_qa_pairs
    KnowledgeSearchService.delete_es_content(
        document.knowledge_index_name(), document.id, document.name, keep_qa)
    res, knowledge_docs = invoke_one_document(document)
    if not res:
        document.train_status = DocumentStatus.ERROR
        document.save()
        return
    document.train_status = DocumentStatus.READY
    document.save()
    logger.info(
        f"document {document.name} progress: {document.train_progress}")


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

    try:
        if source_type == "file":
            res = _handle_file_ingest(document, params, rag)
        elif source_type == "manual":
            res = _handle_manual_ingest(document, params, rag)
        elif source_type == "web_page":
            res = _handle_webpage_ingest(document, params, rag)
        else:
            logger.error(f"不支持的文档类型: {source_type}")
            return False, []

        # 处理返回结果
        if is_show:
            knowledge_docs = res.get("documents", [])
        document.chunk_size = res.get("chunks_size", 0)

        if not document.chunk_size:
            logger.error(f"获取不到文档，返回结果为： {res}")

    except Exception as e:
        logger.exception(f"文档处理失败: {e}")
        res = {"status": "error", "message": str(e)}

    return res.get("status") == "success", knowledge_docs


def _prepare_ingest_params(document, is_preview=False):
    """准备摄取参数"""
    embed_config = {}
    semantic_embed_config = {}
    semantic_embed_model_name = ""

    if document.knowledge_base.embed_model:
        embed_config = document.knowledge_base.embed_model.decrypted_embed_config
        embed_config["model"] = embed_config.get(
            "model", document.knowledge_base.embed_model.name)

    if document.semantic_chunk_parse_embedding_model:
        semantic_embed_config = document.semantic_chunk_parse_embedding_model.decrypted_embed_config
        semantic_embed_model_name = document.semantic_chunk_parse_embedding_model.name

    # OCR配置
    ocr_config = {}
    if document.enable_ocr_parse:
        if document.ocr_model.name == "AzureOCR":
            ocr_config = {
                "ocr_type": "azure_ocr",
                "azure_api_key": document.ocr_model.ocr_config["api_key"] or " ",
                "azure_endpoint": document.ocr_model.ocr_config["base_url"],
            }
        elif document.ocr_model.name == "OlmOCR":
            ocr_config = {
                "ocr_type": "olm_ocr",
                "olm_base_url": document.ocr_model.ocr_config["base_url"],
                "olm_api_key": document.ocr_model.ocr_config["api_key"] or " ",
                "olm_model": document.ocr_model.ocr_config.get("model", "olmOCR-7B-0225-preview"),
            }
        else:
            ocr_config = {
                "ocr_type": "pp_ocr",
            }

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
    knowledge = FileKnowledge.objects.filter(
        knowledge_document_id=document.id).first()
    if not knowledge:
        raise ValueError(f"找不到文件知识记录: document_id={document.id}")

    # 创建临时文件
    file_extension = knowledge.file.name.split(
        ".")[-1].lower() if "." in knowledge.file.name else ""
    with tempfile.NamedTemporaryFile(delete=False, suffix=f".{file_extension}") as temp_file:
        # 写入文件内容
        for chunk in knowledge.file.chunks():
            temp_file.write(chunk)
        temp_file.flush()
        temp_path = temp_file.name

    try:
        # 调用 RAG 的 file_ingest 方法
        result = rag.file_ingest(
            file_path=temp_path, file_name=knowledge.file.name, params=params)
        return result
    finally:
        # 清理临时文件
        if os.path.exists(temp_path):
            os.unlink(temp_path)


def _handle_manual_ingest(document, params, rag):
    """处理手动输入类型的文档摄取"""
    knowledge = ManualKnowledge.objects.filter(
        knowledge_document_id=document.id).first()
    if not knowledge:
        raise ValueError(f"找不到手动知识记录: document_id={document.id}")

    # 合并标题和内容
    content = document.name + knowledge.content

    # 调用 RAG 的 custom_content_ingest 方法
    result = rag.custom_content_ingest(content=content, params=params)
    return result


def _handle_webpage_ingest(document, params, rag):
    """处理网页类型的文档摄取"""
    knowledge = WebPageKnowledge.objects.filter(
        knowledge_document_id=document.id).first()
    if not knowledge:
        raise ValueError(f"找不到网页知识记录: document_id={document.id}")

    # 调用 RAG 的 website_ingest 方法
    result = rag.website_ingest(
        url=knowledge.url, max_depth=knowledge.max_depth, params=params)
    return result


@shared_task
def sync_web_page_knowledge(web_page_knowledge_id):
    """
    Sync web page knowledge by ID.
    """
    web_page = WebPageKnowledge.objects.filter(
        id=web_page_knowledge_id).first()
    if not web_page:
        logger.error(f"Web page knowledge {web_page_knowledge_id} not found.")
        return
    document_list = [web_page.knowledge_document]
    web_page.knowledge_document.train_status = DocumentStatus.CHUNKING
    web_page.knowledge_document.save()
    general_embed_by_document_list(
        document_list,
        False,
        web_page.knowledge_document.created_by,
        web_page.knowledge_document.domain,
        True,
    )


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
    )

    es_index = knowledge_base.knowledge_index_name()
    embed_config = knowledge_base.embed_model.decrypted_embed_config
    embed_config["model"] = embed_config.get(
        "model", knowledge_base.embed_model.name)
    llm_setting = {
        "question": {
            "openai_api_base": question_llm.decrypted_llm_config["openai_base_url"],
            "openai_api_key": question_llm.decrypted_llm_config["openai_api_key"],
            "model": question_llm.decrypted_llm_config["model"] or question_llm.name,
        },
        "answer": {
            "openai_api_base": answer_llm.decrypted_llm_config["openai_base_url"],
            "openai_api_key": answer_llm.decrypted_llm_config["openai_api_key"],
            "model": answer_llm.decrypted_llm_config["model"] or answer_llm.name,
        },
    }

    client = ChunkHelper()
    for qa_pairs_obj in qa_pairs_list:
        # 修改状态为生成中
        try:
            task_obj.task_name = qa_pairs_obj.name
            task_obj.completed_count = 0
            task_obj.train_progress = 0
            qa_pairs_obj.status = "generating"
            qa_pairs_obj.save()
            content_list = client.get_qa_content(
                qa_pairs_obj.document_id, es_index)
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
        except Exception as e:
            logger.exception(e)
            qa_pairs_obj.status = "failed"
            qa_pairs_obj.save()
        else:
            qa_pairs_obj.status = "completed"
            qa_pairs_obj.generate_count = success_count
            qa_pairs_obj.save()
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
    res = client.get_document_es_chunk(
        index_name, page_size=0, metadata_filter=metadata_filter, get_count=False)
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
    graph_obj = KnowledgeGraph.objects.get(id=instance_id)
    graph_obj.status = "rebuilding"
    graph_obj.save()
    res = GraphUtils.rebuild_graph_community(graph_obj)
    if not res["result"]:
        logger.error("Failed to rebuild graph community")
    logger.info(
        "Graph community rebuild completed for instance ID: {}".format(instance_id))
    graph_obj.status = "completed"
    graph_obj.save()


@shared_task
def create_graph(instance_id):
    logger.info("Start creating graph for instance ID: {}".format(instance_id))
    instance = KnowledgeGraph.objects.get(id=instance_id)
    instance.status = "training"
    instance.save()
    res = GraphUtils.create_graph(instance)
    if not res["result"]:
        logger.error("Failed to create graph: {}".format(res["message"]))
    else:
        instance.status = "completed"
        instance.save()
        logger.info("Graph created completed: {}".format(instance.id))


@shared_task
def update_graph(instance_id, old_doc_list):
    logger.info("Start updating graph for instance ID: {}".format(instance_id))
    instance = KnowledgeGraph.objects.get(id=instance_id)
    instance.status = "training"
    instance.save()
    res = GraphUtils.update_graph(instance, old_doc_list)
    if not res["result"]:
        instance.status = "failed"
        instance.save()
        logger.error("Failed to update graph: {}".format(res["message"]))
    else:
        instance.status = "completed"
        instance.save()
        logger.info("Graph updated completed: {}".format(instance.id))


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
    task_obj, qa_pairs_list = _initialize_qa_task(
        file_data, knowledge_base_id, username, domain)

    # 批量处理问答对
    try:
        _process_qa_pairs_batch(qa_pairs_list, file_data,
                                knowledge_base, task_obj)
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
        qa_pairs = create_qa_pairs_task(
            knowledge_base_id, qa_name, username, domain)
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

        success_count = _process_single_qa_pairs(
            qa_pairs, qa_json, params, rag, task_obj)

        # 更新问答对数量和任务进度
        qa_pairs.status = "completed"
        qa_pairs.qa_count += success_count
        qa_pairs.generate_count += success_count
        qa_pairs.save()

        logger.info(
            f"批量创建问答对完成: {qa_pairs.name}, 总数: {len(qa_json)}, 成功: {success_count}")


def _prepare_qa_ingest_params(knowledge_base):
    """准备问答对摄取的基础参数"""
    embed_config = knowledge_base.embed_model.decrypted_embed_config

    return {
        "is_preview": False,
        "knowledge_base_id": knowledge_base.knowledge_index_name(),
        "knowledge_id": "0",
        "embed_model_base_url": embed_config.get("base_url", ""),
        "embed_model_api_key": embed_config.get("api_key", "") or " ",
        "embed_model_name": embed_config.get("model", knowledge_base.embed_model.name),
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
    base_metadata = {"enabled": "true", "base_chunk_id": "",
                     "qa_pairs_id": str(qa_pairs.id), "is_doc": "0"}
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

    for index, qa_item in enumerate(tqdm(qa_json)):
        result = _create_single_qa_item(
            qa_item, index, params, base_metadata, rag)
        if result is None:
            continue
        elif result:
            success_count += 1
        else:
            error_count += 1

        # 每10个记录输出一次进度日志
        if (index + 1) % 10 == 0:
            logger.info(
                f"已处理 {index + 1}/{len(qa_json)} 个问答对，成功: {success_count}, 失败: {error_count}")

        task_progress += train_progress
        task_obj.train_progress = round(task_progress, 2)
        task_obj.completed_count += 1
        task_obj.save()

    return success_count


def _create_single_qa_item(qa_item, index, base_params, base_metadata, rag):
    """创建单个问答项"""
    if not qa_item["instruction"]:
        logger.warning(f"跳过空instruction，索引: {index}")
        return None

    # 构建请求参数
    params = base_params.copy()
    params["metadata"] = {
        **base_metadata, "qa_question": qa_item["instruction"], "qa_answer": qa_item["output"]}

    # 尝试创建问答对，带重试机制
    return _ingest_qa_with_retry(qa_item["instruction"], params, rag, index)


def _ingest_qa_with_retry(content, params, rag, index):
    """摄取问答对内容，带重试机制"""
    try:
        res = rag.custom_content_ingest(content=content, params=params)
        if res.get("status") != "success":
            raise Exception(f"创建问答对失败: {res.get('message', '')}")
        return True
    except Exception as e:
        logger.warning(f"第一次摄取失败，准备重试。索引: {index}, 错误: {str(e)}")
        # 重试机制：等待5秒后重试
        time.sleep(5)
        try:
            res = rag.custom_content_ingest(content=content, params=params)
            if res.get("status") != "success":
                raise Exception(f"重试后仍然失败: {res.get('message', '')}")
            logger.info(f"重试成功，索引: {index}")
            return True
        except Exception as retry_e:
            logger.error(f"创建问答对失败，索引: {index}, 错误: {str(retry_e)}")
            return False


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
    embed_config = qa_pairs.knowledge_base.embed_model.decrypted_embed_config
    embed_config["model"] = embed_config.get(
        "model", qa_pairs.knowledge_base.embed_model.name)
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
        success_count = ChunkHelper.create_qa_pairs(
            content_list, chunk_obj, es_index, embed_config, qa_pairs_id, task_obj)
        qa_pairs.generate_count = success_count
        qa_pairs.status = "completed"
    except Exception as e:
        logger.exception(e)
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
    answer_llm = LLMModel.objects.filter(
        id=kwargs["answer_llm_model_id"]).first()
    llm_setting = {
        "question": {
            "openai_api_base": question_llm.decrypted_llm_config["openai_base_url"],
            "openai_api_key": question_llm.decrypted_llm_config["openai_api_key"],
            "model": question_llm.decrypted_llm_config["model"] or question_llm.name,
        },
        "answer": {
            "openai_api_base": answer_llm.decrypted_llm_config["openai_base_url"],
            "openai_api_key": answer_llm.decrypted_llm_config["openai_api_key"],
            "model": answer_llm.decrypted_llm_config["model"] or answer_llm.name,
        },
    }
    es_index = qa_pairs_obj.knowledge_base.knowledge_index_name()
    embed_config = qa_pairs_obj.knowledge_base.embed_model.decrypted_embed_config
    embed_config["model"] = embed_config.get(
        "model", qa_pairs_obj.knowledge_base.embed_model.name)
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
        logger.info(
            f"ChatFlow周期任务执行完成: bot_id={bot_id}, node_id={node_id}, 执行结果为{result}")
    except Exception as e:
        logger.error(
            f"ChatFlow周期任务执行失败: bot_id={bot_id}, node_id={node_id}, error={str(e)}")
