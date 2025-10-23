import json
import os
from typing import Any, Dict, Optional

import requests
from django.conf import settings

from apps.core.logger import opspilot_logger as logger
from apps.opspilot.utils.chat_server_helper import ChatServerHelper


class ChunkHelper(ChatServerHelper):
    list_url = f"{settings.METIS_SERVER_URL}/api/rag/list_rag_document"
    generate_url = f"{settings.METIS_SERVER_URL}/api/rag/qa_pair_generate"
    del_url = f"{settings.METIS_SERVER_URL}/api/rag/delete_doc"
    create_url = f"{settings.METIS_SERVER_URL}/api/rag/custom_content_ingest"
    update_url = f"{settings.METIS_SERVER_URL}/api/rag/update_rag_document_metadata"
    generate_question_url = f"{settings.METIS_SERVER_URL}/api/rag/question_generation"
    generate_answer_url = f"{settings.METIS_SERVER_URL}/api/rag/answer_generation"

    @classmethod
    def create_qa_pairs_by_content(
        cls,
        content_list,
        embed_config,
        es_index,
        llm_setting,
        qa_pairs_obj,
        qa_count,
        question_prompt,
        answer_prompt,
        task_obj,
        only_question,
    ):
        success_count = 0
        q_kwargs = dict({"size": qa_count, "extra_prompt": question_prompt}, **llm_setting["question"])
        a_kwargs = dict({"extra_prompt": answer_prompt}, **llm_setting["answer"])
        for i in content_list:
            generate_count = cls.generate_qa(q_kwargs, a_kwargs, i, embed_config, es_index, qa_pairs_obj, only_question, task_obj)
            # res = cls.update_document_qa_pairs_count(es_index, generate_count, i["chunk_id"])
            # if not res:
            #     logger.error(f"Failed to update document QA pairs count for chunk_id ID: {i['chunk_id']}")
            success_count += generate_count
        return success_count

    @classmethod
    def get_document_es_chunk(
        cls,
        index_name,
        page: int = 1,
        page_size: int = 0,
        search_text: str = "",
        metadata_filter: Optional[Dict[str, Any]] = None,
        get_count: bool = True,
    ) -> Dict[str, Any]:
        if not metadata_filter:
            metadata_filter = {}
        query = {
            "index_name": index_name,
            "page": page,
            "metadata_filter": metadata_filter,
            "size": page_size,
            "query": search_text,
            "sort_field": "created_time",
            "sort_order": "asc",
        }
        res = cls.post_chat_server(query, cls.list_url)
        if not res:
            return {"count": 0, "documents": []}
        count_res = {"count": 0}
        if get_count:
            count_url = f"{settings.METIS_SERVER_URL}/api/rag/count_index_document"
            count_res = ChatServerHelper.post_chat_server(query, count_url)
        res["count"] = count_res.get("count", 0)
        return res

    @classmethod
    def delete_es_content(cls, doc_id, is_chunk=False, keep_qa=False):
        kwargs = {
            "chunk_ids": [str(doc_id)] if is_chunk else [],
            "knowledge_ids": [f"qa_pairs_id_{doc_id}"] if not is_chunk else [],
            "keep_qa": keep_qa,
        }
        try:
            ChatServerHelper.post_chat_server(kwargs, cls.del_url)
            return True
        except Exception as e:
            logger.exception(e)
            return False

    @classmethod
    def create_qa_pairs(cls, qa_paris, chunk_obj, index_name, embed_config, qa_pairs_id, task_obj):
        success_count = 0
        kwargs, metadata = cls.set_qa_pairs_params(embed_config, index_name, qa_pairs_id, chunk_obj)
        headers = cls.get_chat_server_header()
        # SSL验证配置 - 从环境变量读取
        ssl_verify = os.getenv("METIS_SSL_VERIFY", "false").lower() == "true"
        for i in qa_paris:
            params = dict(kwargs, **{"content": i["question"]})
            params["metadata"] = json.dumps(dict(metadata, **{"qa_question": i["question"], "qa_answer": i["answer"]}))
            response = requests.post(cls.create_url, headers=headers, data=params, verify=ssl_verify)
            try:
                res = response.json()
            except Exception as e:
                logger.exception(e)
                logger.error(response.text)
                continue
            if res.get("status", "fail") != "success":
                logger.exception(f"创建问答对失败: {res.get('message', '')}")
                continue
            success_count += 1
            task_obj.completed_count += 1
            task_obj.save()
        return success_count

    @classmethod
    def set_qa_pairs_params(cls, embed_config, index_name, qa_pairs_id, chunk_obj=None):
        if chunk_obj is None:
            chunk_obj = {}
        kwargs = {
            "knowledge_base_id": index_name,
            "knowledge_id": f"qa_pairs_id_{qa_pairs_id}",
            "embed_model_base_url": embed_config.get("base_url", ""),
            "embed_model_api_key": embed_config.get("api_key", "") or " ",
            "embed_model_name": embed_config.get("model", ""),
            "chunk_mode": "full",
            "chunk_size": 9999,
            "chunk_overlap": 128,
            "load_mode": "full",
            "semantic_chunk_model_base_url": [],
            "semantic_chunk_model_api_key": "",
            "semantic_chunk_model": "",
            "preview": "false",
        }
        metadata = {
            "enabled": "true",
            "base_chunk_id": chunk_obj.get("chunk_id", ""),
            "qa_pairs_id": str(qa_pairs_id),
            "is_doc": "0",
        }
        return kwargs, metadata

    @classmethod
    def create_one_qa_pairs(cls, embed_config, index_name, qa_pairs_id, question, answer, chunk_id=""):
        chunk_obj = {"chunk_id": chunk_id}
        kwargs, metadata = cls.set_qa_pairs_params(embed_config, index_name, qa_pairs_id, chunk_obj)
        metadata.update({"qa_question": question, "qa_answer": answer})
        params = dict(kwargs, **{"content": question, "metadata": json.dumps(metadata)})
        # SSL验证配置 - 从环境变量读取
        ssl_verify = os.getenv("METIS_SSL_VERIFY", "false").lower() == "true"
        res = requests.post(cls.create_url, headers=cls.get_chat_server_header(), data=params, verify=ssl_verify).json()
        if res.get("status", "fail") != "success":
            logger.exception(f"创建问答对失败: {res.get('message', '')}")
            return {"result": False}
        return {"result": True}

    @classmethod
    def update_qa_pairs(cls, chunk_id, question, answer):
        kwargs = {
            "knowledge_ids": [],
            "chunk_ids": [chunk_id],
            "metadata": {"qa_question": question, "qa_answer": answer},
        }
        res = ChatServerHelper.post_chat_server(kwargs, cls.update_url)
        return res

    @classmethod
    def get_qa_content(cls, document_id, es_index, page_size=0):
        res = cls.get_document_es_chunk(es_index, 1, page_size, metadata_filter={"knowledge_id": str(document_id)}, get_count=False)
        if res.get("status") != "success":
            raise Exception(f"Failed to get document chunk for document ID {document_id}.")
        return_data = []
        for i in res["documents"]:
            meta_data = i.get("metadata", {})
            if not meta_data:
                continue
            return_data.append(
                {
                    "chunk_id": meta_data["chunk_id"],
                    "content": i["page_content"],
                    "knowledge_id": meta_data["knowledge_id"],
                }
            )
        return return_data

    @classmethod
    def generate_question(cls, kwargs):
        ssl_verify = os.getenv("METIS_SSL_VERIFY", "false").lower() == "true"
        try:
            response = requests.post(cls.generate_question_url, headers=cls.get_chat_server_header(), json=kwargs, verify=ssl_verify)
            res = response.json()
            if res.get("status", "fail") != "success":
                raise Exception(res.get("message", "Failed to generate question."))
        except Exception as e:
            logger.exception(f"生成问题失败: {e}")
            return {"result": False, "data": []}
        return {"result": True, "data": res.get("message", [])}

    @classmethod
    def generate_answer(cls, kwargs):
        ssl_verify = os.getenv("METIS_SSL_VERIFY", "false").lower() == "true"
        try:
            response = requests.post(cls.generate_answer_url, headers=cls.get_chat_server_header(), json=kwargs, verify=ssl_verify)
            res = response.json()
            if res.get("status", "fail") != "success":
                raise Exception(res.get("message", "Failed to generate answer."))
        except Exception as e:
            logger.exception(f"生成答案失败: {e}")
            return {"result": False, "data": {}}
        return_data = res.get("message", {})
        return_data["question"] = kwargs["content"]
        return {"result": True, "data": return_data}

    @classmethod
    def create_document_qa_pairs(cls, content_list, embed_config, es_index, llm_setting, qa_pairs_obj, only_question, task_obj):
        success_count = 0
        q_kwargs = dict({"size": qa_pairs_obj.qa_count, "extra_prompt": qa_pairs_obj.question_prompt}, **llm_setting["question"])
        a_kwargs = dict({"extra_prompt": qa_pairs_obj.answer_prompt}, **llm_setting["answer"])
        for i in content_list:
            generate_count = cls.generate_qa(q_kwargs, a_kwargs, i, embed_config, es_index, qa_pairs_obj, only_question, task_obj)
            # res = cls.update_document_qa_pairs_count(es_index, generate_count, i["chunk_id"])
            # if not res:
            #     logger.error(f"Failed to update document QA pairs count for chunk_id ID: {i['chunk_id']}")
            success_count += generate_count
        return success_count

    @classmethod
    def generate_qa(cls, question_kwargs, answer_kwargs, chunk, embed_config, es_index, qa_pairs_obj, only_question, task_obj):
        success_count = 0
        question_res = cls.generate_question(dict(question_kwargs, **{"content": chunk["content"]}))
        if not question_res["result"]:
            logger.error(f"Failed to generate questions for content ID {chunk['chunk_id']}.")
            return 0
        for u in question_res["data"]:
            answer = ""
            if not only_question:
                res = cls.generate_answer(dict(answer_kwargs, **{"context": chunk["content"], "content": u["question"]}))
                if not res["result"]:
                    logger.error(f"Failed to generate answer for question {u['question']}.")
                    continue
                answer = res["data"].get("answer")
            cls.create_one_qa_pairs(
                embed_config,
                es_index,
                qa_pairs_obj.id,
                u["question"],
                answer,
                chunk["chunk_id"],
            )
            success_count += 1
            task_obj.completed_count += 1
            task_obj.save()
        return success_count

    @classmethod
    def update_qa_pairs_answer(cls, return_data, qa_pairs):
        if not return_data:
            return
        answer_llm = qa_pairs.answer_llm_model
        kwargs = {
            "extra_prompt": qa_pairs.answer_prompt,
            "openai_api_base": answer_llm.decrypted_llm_config["openai_base_url"],
            "openai_api_key": answer_llm.decrypted_llm_config["openai_api_key"],
            "model": answer_llm.decrypted_llm_config["model"] or answer_llm.name,
        }
        for i in return_data:
            res = cls.generate_answer(dict(kwargs, **{"context": i["content"], "content": i["question"]}))
            if not res["result"]:
                logger.error(f"Failed to generate answer for question {i['question']}.")
                continue
            answer = res["data"].get("answer")
            if not answer:
                continue
            cls.update_qa_pairs(i["id"], i["question"], answer)
