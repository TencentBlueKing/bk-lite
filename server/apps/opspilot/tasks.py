import json
import os
import time

import requests
from celery import shared_task
from django.conf import settings
from tqdm import tqdm

from apps.core.logger import opspilot_logger as logger
from apps.opspilot.enum import DocumentStatus
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
from apps.opspilot.utils.chat_server_helper import ChatServerHelper
from apps.opspilot.utils.chunk_helper import ChunkHelper
from apps.opspilot.utils.graph_utils import GraphUtils


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
        res, remote_docs = invoke_one_document(document_list[0], is_show)
        docs = [i["page_content"] for i in remote_docs][:10]
        return docs
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
            invoke_document_to_es(document=document, delete_qa_pairs=delete_qa_pairs)
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
    logger.info(f"document {document.name} progress: {document.train_progress}")
    keep_qa = not delete_qa_pairs
    KnowledgeSearchService.delete_es_content(document.knowledge_index_name(), document.id, document.name, keep_qa)
    res, knowledge_docs = invoke_one_document(document)
    if not res:
        document.train_status = DocumentStatus.ERROR
        document.save()
        return
    document.train_status = DocumentStatus.READY
    document.save()
    logger.info(f"document {document.name} progress: {document.train_progress}")


def invoke_one_document(document, is_show=False):
    source_invoke_format_map = {
        "file": format_file_invoke_kwargs,
        "manual": format_manual_invoke_kwargs,
        "web_page": format_web_page_invoke_kwargs,
    }
    remote_url_map = {
        "file": f"{settings.METIS_SERVER_URL}/api/rag/file_ingest",
        "web_page": f"{settings.METIS_SERVER_URL}/api/rag/website_ingest",
        "manual": f"{settings.METIS_SERVER_URL}/api/rag/custom_content_ingest",
    }
    knowledge_docs = []
    source_type = document.knowledge_source_type
    source_remote = remote_url_map[source_type]
    logger.info("Start handle {} knowledge: {}".format(source_type, document.name))
    form_data = format_invoke_kwargs(document, preview=is_show)
    source_data = source_invoke_format_map[source_type](document)
    res = {"status": "fail"}
    try:
        headers = ChatServerHelper.get_chat_server_header()
        # SSL验证配置 - 从环境变量读取
        ssl_verify = os.getenv("METIS_SSL_VERIFY", "false").lower() == "true"
        if source_type == "file":
            files = source_data.pop("file")
            response = requests.post(
                source_remote,
                headers=headers,
                data=form_data,
                files=files,
                verify=ssl_verify,
            )
        else:
            form_data.update(source_data)
            response = requests.post(source_remote, headers=headers, data=form_data, verify=ssl_verify)
        res = response.json()
        remote_docs = res.get("documents", [])
        document.chunk_size = res.get("chunks_size", 0)
        if not document.chunk_size:
            logger.error(f"获取不到文档，返回结果为： {res}")
        knowledge_docs.extend(remote_docs)
    except Exception as e:
        logger.exception(e)
    return res.get("status") == "success", knowledge_docs


def format_file_invoke_kwargs(document):
    knowledge = FileKnowledge.objects.filter(knowledge_document_id=document.id).first()
    return {
        "file": [
            (
                "file",
                (
                    knowledge.file.name,
                    knowledge.file.read(),
                    "application/octet-stream",
                ),
            )
        ]
    }


def format_manual_invoke_kwargs(document):
    knowledge = ManualKnowledge.objects.filter(knowledge_document_id=document.id).first()
    return {"content": document.name + knowledge.content}


def format_web_page_invoke_kwargs(document):
    knowledge = WebPageKnowledge.objects.filter(knowledge_document_id=document.id).first()
    return {"url": knowledge.url, "max_depth": knowledge.max_depth}


def format_invoke_kwargs(knowledge_document: KnowledgeDocument, preview=False):
    embed_config = {}
    semantic_embed_config = {}
    semantic_embed_model_name = ""
    if knowledge_document.knowledge_base.embed_model:
        embed_config = knowledge_document.knowledge_base.embed_model.decrypted_embed_config
        embed_config["model"] = embed_config.get("model", knowledge_document.knowledge_base.embed_model.name)
    if knowledge_document.semantic_chunk_parse_embedding_model:
        semantic_embed_config = knowledge_document.semantic_chunk_parse_embedding_model.decrypted_embed_config
        semantic_embed_model_name = knowledge_document.semantic_chunk_parse_embedding_model.name
    ocr_config = {}
    if knowledge_document.enable_ocr_parse:
        if knowledge_document.ocr_model.name == "AzureOCR":
            ocr_config = {
                "ocr_type": "azure_ocr",
                "azure_api_key": knowledge_document.ocr_model.ocr_config["api_key"] or " ",
                "azure_endpoint": knowledge_document.ocr_model.ocr_config["base_url"],
            }
        elif knowledge_document.ocr_model.name == "OlmOCR":
            ocr_config = {
                "ocr_type": "olm_ocr",
                "olm_base_url": knowledge_document.ocr_model.ocr_config["base_url"],
                "olm_api_key": knowledge_document.ocr_model.ocr_config["api_key"] or " ",
                "olm_model": knowledge_document.ocr_model.name,
            }
        else:
            ocr_config = {
                "ocr_type": "pp_ocr",
            }
    kwargs = {
        "knowledge_base_id": knowledge_document.knowledge_index_name(),
        "knowledge_id": str(knowledge_document.id),
        "embed_model_base_url": embed_config.get("base_url", ""),
        "embed_model_api_key": embed_config.get("api_key", "") or " ",
        "embed_model_name": embed_config.get("model", ""),
        "chunk_mode": knowledge_document.chunk_type,
        "chunk_size": knowledge_document.general_parse_chunk_size,
        "chunk_overlap": knowledge_document.general_parse_chunk_overlap,
        "load_mode": knowledge_document.mode,
        "semantic_chunk_model_base_url": [semantic_embed_config.get("base_url", "")] if semantic_embed_config.get("base_url", "") else [],
        "semantic_chunk_model_api_key": semantic_embed_config.get("api_key", "") or " ",
        "semantic_chunk_model": semantic_embed_config.get("model", semantic_embed_model_name),
        "preview": "true" if preview else "false",
        "metadata": json.dumps({"enabled": "true", "is_doc": "1", "qa_count": 0}),
    }
    kwargs.update(ocr_config)
    return kwargs


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
    embed_config["model"] = embed_config.get("model", knowledge_base.embed_model.name)
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
    graph_obj = KnowledgeGraph.objects.get(id=instance_id)
    graph_obj.status = "rebuilding"
    graph_obj.save()
    res = GraphUtils.rebuild_graph_community(graph_obj)
    if not res["result"]:
        logger.error("Failed to rebuild graph community")
    logger.info("Graph community rebuild completed for instance ID: {}".format(instance_id))
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
    url = f"{settings.METIS_SERVER_URL}/api/rag/custom_content_ingest"
    headers = ChatServerHelper.get_chat_server_header()
    kwargs = set_import_kwargs(knowledge_base)

    for qa_pairs in qa_pairs_list:
        qa_json = file_data[qa_pairs.name]
        kwargs["knowledge_id"] = f"qa_pairs_id_{qa_pairs.id}"
        success_count = _process_single_qa_pairs(qa_pairs, qa_json, kwargs, url, headers, task_obj)

        # 更新问答对数量和任务进度
        qa_pairs.status = "completed"
        qa_pairs.qa_count += success_count
        qa_pairs.generate_count += success_count
        qa_pairs.save()

        logger.info(f"批量创建问答对完成: {qa_pairs.name}, 总数: {len(qa_json)}, 成功: {success_count}")


def _process_single_qa_pairs(qa_pairs, qa_json, kwargs, url, headers, task_obj):
    """处理单个问答对集合"""
    metadata = {"enabled": "true", "base_chunk_id": "", "qa_pairs_id": str(qa_pairs.id), "is_doc": "0"}
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
        result = _create_single_qa_item(qa_item, index, kwargs, metadata, url, headers)
        if result is None:
            continue
        elif result:
            success_count += 1
        else:
            error_count += 1
        # 每10个记录输出一次进度日志
        if (index + 1) % 10 == 0:
            logger.info(f"已处理 {index + 1}/{len(qa_json)} 个问答对，成功: {success_count}, 失败: {error_count}")
        task_progress += train_progress
        task_obj.train_progress = round(task_progress, 2)
        task_obj.completed_count += 1
        task_obj.save()
    return success_count


def _create_single_qa_item(qa_item, index, kwargs, metadata, url, headers):
    """创建单个问答项"""
    if not qa_item["instruction"]:
        logger.warning(f"跳过空instruction，索引: {index}")
        return None

    # 构建请求参数
    params = dict(kwargs, **{"content": qa_item["instruction"]})
    params["metadata"] = json.dumps(dict(metadata, **{"qa_question": qa_item["instruction"], "qa_answer": qa_item["output"]}))

    # 尝试创建问答对，带重试机制
    return _send_qa_request_with_retry(params, url, headers, index)


def _send_qa_request_with_retry(params, url, headers, index):
    """发送问答对创建请求，带重试机制"""
    # SSL验证配置 - 从环境变量读取
    ssl_verify = os.getenv("METIS_SSL_VERIFY", "false").lower() == "true"
    try:
        res = requests.post(url, headers=headers, data=params, verify=ssl_verify).json()
        if res.get("status") != "success":
            raise Exception(f"创建问答对失败: {res.get('message', '')}")
    except Exception as e:
        logger.warning(f"第一次请求失败，准备重试。索引: {index}, 错误: {str(e)}")
        # 重试机制：等待5秒后重试
        time.sleep(5)
        try:
            res = requests.post(url, headers=headers, data=params, verify=ssl_verify).json()
            if res.get("status") != "success":
                raise Exception(f"重试后仍然失败: {res.get('message', '')}")
            logger.info(f"重试成功，索引: {index}")
        except Exception as retry_e:
            logger.error(f"创建问答对失败，索引: {index}, 错误: {str(retry_e)}")
            if hasattr(retry_e, "response"):
                logger.error(f"响应内容: {retry_e.response}")
            return False
    return True


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


def set_import_kwargs(knowledge_base):
    embed_config = knowledge_base.embed_model.decrypted_embed_config
    kwargs = {
        "knowledge_base_id": knowledge_base.knowledge_index_name(),
        "knowledge_id": "0",
        "embed_model_base_url": embed_config.get("base_url", ""),
        "embed_model_api_key": embed_config.get("api_key", "") or " ",
        "embed_model_name": embed_config.get("model", knowledge_base.embed_model.name),
        "chunk_mode": "full",
        "chunk_size": 9999,
        "chunk_overlap": 128,
        "load_mode": "full",
        "semantic_chunk_model_base_url": [],
        "semantic_chunk_model_api_key": " ",
        "semantic_chunk_model": "",
        "preview": "false",
    }

    return kwargs


@shared_task
def create_qa_pairs_by_custom(qa_pairs_id, content_list):
    qa_pairs = QAPairs.objects.get(id=qa_pairs_id)
    es_index = qa_pairs.knowledge_base.knowledge_index_name()
    embed_config = qa_pairs.knowledge_base.embed_model.decrypted_embed_config
    embed_config["model"] = embed_config.get("model", qa_pairs.knowledge_base.embed_model.name)
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
    answer_llm = LLMModel.objects.filter(id=kwargs["answer_llm_model_id"]).first()
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
    embed_config["model"] = embed_config.get("model", qa_pairs_obj.knowledge_base.embed_model.name)
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
        logger.info(f"ChatFlow周期任务执行完成: bot_id={bot_id}, node_id={node_id}, 执行结果为{result}")
    except Exception as e:
        logger.error(f"ChatFlow周期任务执行失败: bot_id={bot_id}, node_id={node_id}, error={str(e)}")
