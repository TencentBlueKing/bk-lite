from typing import Any, Dict, Optional

from langchain_core.documents import Document

from apps.core.logger import opspilot_logger as logger
from apps.opspilot.metis.llm.rag.enhance.qa_generation import QAGeneration
from apps.opspilot.metis.llm.rag.naive_rag.pgvector.pgvector_rag import PgvectorRag
from apps.opspilot.metis.llm.rag.naive_rag_entity import (
    DocumentCountRequest,
    DocumentDeleteRequest,
    DocumentIngestRequest,
    DocumentListRequest,
    DocumentMetadataUpdateRequest,
)
from apps.opspilot.metis.llm.rag.rag_enhance_entity import AnswerGenerateRequest, QuestionGenerateRequest
from apps.opspilot.utils.chat_server_helper import ChatServerHelper


class ChunkHelper(ChatServerHelper):
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
        """使用 PgvectorRag 直接查询文档列表

        Args:
            index_name: 索引名称
            page: 页码
            page_size: 每页大小
            search_text: 搜索文本
            metadata_filter: 元数据过滤条件
            get_count: 是否获取总数

        Returns:
            Dict[str, Any]: 包含文档列表和总数的字典
        """
        if not metadata_filter:
            metadata_filter = {}

        rag_client = PgvectorRag()

        # 构建 DocumentListRequest 对象
        request = DocumentListRequest(
            index_name=index_name,
            page=page,
            size=page_size,
            metadata_filter=metadata_filter,
            query=search_text,
            sort_field="created_time",
            sort_order="asc",
        )

        # 调用 list_index_document 方法
        documents = rag_client.list_index_document(request)

        # 转换 Document 对象为字典格式
        document_list = []
        for doc in documents:
            document_list.append(
                {
                    "page_content": doc.page_content,
                    "metadata": doc.metadata,
                }
            )

        # 获取文档总数
        count = 0
        if get_count:
            count_request = DocumentCountRequest(
                index_name=index_name,
                metadata_filter=metadata_filter,
                query=search_text,
            )
            count = rag_client.count_index_document(count_request)

        return {
            "status": "success",
            "count": count,
            "documents": document_list,
        }

    @classmethod
    def delete_es_content(cls, doc_id, is_chunk=False, keep_qa=False):
        """删除 ES 内容

        Args:
            doc_id: 文档ID或chunk ID
            is_chunk: 是否为chunk
            keep_qa: 是否保留问答对
        """
        rag_client = PgvectorRag()
        request = DocumentDeleteRequest(
            chunk_ids=[str(doc_id)] if is_chunk else [],
            knowledge_ids=[f"qa_pairs_id_{doc_id}"] if not is_chunk else [],
            keep_qa=keep_qa,
        )
        try:
            rag_client.delete_document(request)
            return True
        except Exception as e:
            logger.exception(e)
            return False

    @classmethod
    def create_qa_pairs(cls, qa_paris, chunk_obj, index_name, embed_config, qa_pairs_id, task_obj):
        """创建问答对

        Args:
            qa_paris: 问答对列表
            chunk_obj: chunk 对象
            index_name: 索引名称
            embed_config: 嵌入模型配置
            qa_pairs_id: 问答对ID
            task_obj: 任务对象
        """
        success_count = 0
        rag_client = PgvectorRag()

        # 构建元数据
        base_metadata = {
            "enabled": "true",
            "base_chunk_id": chunk_obj.get("chunk_id", ""),
            "qa_pairs_id": str(qa_pairs_id),
            "is_doc": "0",
            "knowledge_id": f"qa_pairs_id_{qa_pairs_id}",
        }

        for qa in qa_paris:
            try:
                # 为每个问答对创建 Document
                metadata = dict(
                    base_metadata,
                    **{
                        "qa_question": qa["question"],
                        "qa_answer": qa["answer"],
                        "chunk_id": f"qa_{qa_pairs_id}_{success_count}",
                    },
                )

                doc = Document(
                    page_content=qa["question"],
                    metadata=metadata,
                )

                # 构建 ingest 请求
                request = DocumentIngestRequest(
                    embed_model_base_url=embed_config.get("base_url", ""),
                    embed_model_api_key=embed_config.get("api_key", "") or " ",
                    embed_model_name=embed_config.get("model", ""),
                    index_name=index_name,
                    index_mode="append",
                    docs=[doc],
                )

                rag_client.ingest(request)
                success_count += 1
                task_obj.completed_count += 1
                task_obj.save()

            except Exception as e:
                logger.exception(f"创建问答对失败: {e}")
                continue

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
        """创建单个问答对

        Args:
            embed_config: 嵌入模型配置
            index_name: 索引名称
            qa_pairs_id: 问答对ID
            question: 问题
            answer: 答案
            chunk_id: chunk ID
        """
        rag_client = PgvectorRag()

        # 构建元数据
        metadata = {
            "enabled": "true",
            "base_chunk_id": chunk_id,
            "qa_pairs_id": str(qa_pairs_id),
            "is_doc": "0",
            "knowledge_id": f"qa_pairs_id_{qa_pairs_id}",
            "qa_question": question,
            "qa_answer": answer,
            "chunk_id": f"qa_{qa_pairs_id}_{chunk_id or 'single'}",
        }

        # 创建 Document
        doc = Document(
            page_content=question,
            metadata=metadata,
        )

        # 构建 ingest 请求
        request = DocumentIngestRequest(
            embed_model_base_url=embed_config.get("base_url", ""),
            embed_model_api_key=embed_config.get("api_key", "") or " ",
            embed_model_name=embed_config.get("model", ""),
            index_name=index_name,
            index_mode="append",
            docs=[doc],
        )

        try:
            rag_client.ingest(request)
            return {"result": True}
        except Exception as e:
            logger.exception(f"创建问答对失败: {e}")
            return {"result": False}

    @classmethod
    def update_qa_pairs(cls, chunk_id, question, answer):
        """更新问答对

        Args:
            chunk_id: chunk ID
            question: 问题
            answer: 答案
        """
        rag_client = PgvectorRag()
        request = DocumentMetadataUpdateRequest(
            knowledge_ids=[],
            chunk_ids=[chunk_id],
            metadata={"qa_question": question, "qa_answer": answer},
        )
        try:
            rag_client.update_metadata(request)
            return {"status": "success"}
        except Exception as e:
            logger.exception(e)
            return {"status": "fail", "message": str(e)}

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
        """生成问题

        Args:
            kwargs: 包含 content, size, extra_prompt, openai_api_base, openai_api_key, model 等参数
        """
        try:
            request = QuestionGenerateRequest(
                content=kwargs["content"],
                size=kwargs.get("size", 5),
                extra_prompt=kwargs.get("extra_prompt", ""),
                openai_api_base=kwargs.get("openai_api_base", "https://api.openai.com"),
                openai_api_key=kwargs.get("openai_api_key", ""),
                model=kwargs.get("model", "gpt-4o"),
            )
            result = QAGeneration.generate_question(request)
            return {"result": True, "data": result}
        except Exception as e:
            logger.exception(f"生成问题失败: {e}")
            return {"result": False, "data": []}

    @classmethod
    def generate_answer(cls, kwargs):
        """生成答案

        Args:
            kwargs: 包含 context, content, extra_prompt, openai_api_base, openai_api_key, model 等参数
        """
        try:
            request = AnswerGenerateRequest(
                context=kwargs["context"],
                content=kwargs["content"],
                extra_prompt=kwargs.get("extra_prompt", ""),
                openai_api_base=kwargs.get("openai_api_base", "https://api.openai.com"),
                openai_api_key=kwargs.get("openai_api_key", ""),
                model=kwargs.get("model", "gpt-4o"),
            )
            result = QAGeneration.generate_answer(request)
            result["question"] = kwargs["content"]
            return {"result": True, "data": result}
        except Exception as e:
            logger.exception(f"生成答案失败: {e}")
            return {"result": False, "data": {}}

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
