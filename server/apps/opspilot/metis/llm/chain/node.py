from typing import Any, Dict, List, Optional
from urllib.parse import parse_qs, urlparse
import asyncio
import inspect
import json
import time
import uuid
from collections import Counter

import json_repair
import openai

# ---------------------------------------------------------------------------
# DeepSeek/Qwen thinking mode fix:
#
# Problem: Models like DeepSeek and Qwen return a `reasoning_content` field in
# their API responses. In multi-turn conversations (e.g. ReAct tool-calling
# loops), this field MUST be passed back with the assistant message. However
# langchain-openai's deserialization (_convert_dict_to_message) discards it,
# so on the next turn the field is missing and the model returns HTTP 400:
#   "The reasoning_content in the thinking mode must be passed back to the API."
#
# Fix: We monkey-patch BOTH directions:
#   1. Response → AIMessage: preserve reasoning_content in additional_kwargs
#   2. AIMessage → Request dict: inject reasoning_content back into the payload
# ---------------------------------------------------------------------------
import langchain_openai.chat_models.base as _lc_openai_base  # noqa: E402
from deepagents import create_deep_agent
from langchain_core.callbacks import dispatch_custom_event
from langchain_core.messages import AIMessage, AIMessageChunk, BaseMessage, HumanMessage, SystemMessage, ToolMessage
from langchain_core.runnables import RunnableConfig
from langchain_core.tools import StructuredTool
from langchain_mcp_adapters.client import MultiServerMCPClient
from langchain_openai.chat_models.base import BaseChatOpenAI as _BaseChatOpenAI
from langchain_openai.chat_models.base import _convert_delta_to_message_chunk as _original_convert_delta_to_message_chunk
from langchain_openai.chat_models.base import _convert_dict_to_message as _original_convert_dict_to_message
from langchain_openai.chat_models.base import _convert_message_to_dict as _original_convert_message_to_dict
from langgraph.constants import END
from langgraph.graph import StateGraph
from langgraph.prebuilt import ToolNode
from pydantic import BaseModel, Field as PydanticField
from apps.core.logger import opspilot_logger as logger
from apps.opspilot.metis.llm.chain.compaction import CompactionConfig, compact_messages
from apps.opspilot.metis.llm.chain.entity import BasicLLMRequest, DoneToolConfig, PrepareStepContext, PrepareStepResult, StopConditionContext, StopConditionResult
from apps.opspilot.metis.llm.chain.message_trim import trim_messages
from apps.opspilot.metis.llm.common.llm_client_factory import LLMClientFactory
from apps.opspilot.metis.llm.common.structured_output_parser import StructuredOutputParser
from apps.opspilot.metis.llm.rag.graph_rag.graphiti.graphiti_rag import GraphitiRAG
from apps.opspilot.metis.llm.rag.naive_rag.pgvector.pgvector_rag import PgvectorRag
from apps.opspilot.metis.llm.tools.tools_loader import ToolsLoader
from apps.opspilot.metis.utils.template_loader import TemplateLoader
from apps.opspilot.utils.execution_interrupt import is_interrupt_requested_async
from apps.opspilot.utils.approval import wait_for_approval
from apps.opspilot.utils.user_choice import wait_for_choice
from apps.opspilot.utils.rollback import get_rollback_spec, take_snapshot, execute_rollback
from apps.opspilot.utils.verification import get_verification_spec, run_verification


def _safe_log_preview(content: str, max_len: int = 200) -> str:
    """
    安全地截取日志预览内容，移除可能导致 Windows GBK 编码错误的字符（如 emoji）。
    
    Args:
        content: 原始内容
        max_len: 最大长度
    
    Returns:
        安全的日志预览字符串
    """
    if not content:
        return ""
    preview = str(content)[:max_len]
    # 移除非 ASCII 字符中可能导致 GBK 编码错误的字符（主要是 emoji）
    # 保留中文等常见字符，只移除 emoji 范围的字符
    return preview.encode('gbk', errors='replace').decode('gbk')


def normalize_messages_for_llm(messages: List[Any]) -> List[Any]:
    """
    规范化消息列表，确保兼容 Qwen 等对消息顺序有严格要求的模型。

    规则：
    1. 所有 SystemMessage 合并为一个，放在最前面
    2. 非 SystemMessage 保持原有顺序

    Args:
        messages: 原始消息列表

    Returns:
        规范化后的消息列表
    """
    if not messages:
        return messages

    system_contents = []
    non_system_messages = []

    for msg in messages:
        if isinstance(msg, SystemMessage):
            system_contents.append(msg.content)
        else:
            non_system_messages.append(msg)

    if system_contents:
        merged_system = SystemMessage(content="\n\n".join(system_contents))
        return [merged_system] + non_system_messages
    else:
        return non_system_messages


# --- Patch 1: Response deserialization (preserve reasoning_content) ----------

# Different providers use different field names for thinking/reasoning content:
#   - DeepSeek: "reasoning_content"
#   - Qwen: "reasoning"
# We normalize to "reasoning_content" in additional_kwargs for internal use.
_REASONING_FIELD_NAMES = ("reasoning_content", "reasoning")


def _patched_convert_dict_to_message(_dict, *args, **kwargs):
    """Preserve reasoning_content from provider response into AIMessage.additional_kwargs."""
    message = _original_convert_dict_to_message(_dict, *args, **kwargs)
    if isinstance(message, AIMessage):
        for field_name in _REASONING_FIELD_NAMES:
            if _dict.get(field_name):
                message.additional_kwargs["reasoning_content"] = _dict[field_name]
                break
    return message


_lc_openai_base._convert_dict_to_message = _patched_convert_dict_to_message


# --- Patch 3: _create_chat_result - capture reasoning_content from raw response ----

_original_create_chat_result = _BaseChatOpenAI._create_chat_result


def _patched_create_chat_result(self, response, generation_info=None):
    """Intercept _create_chat_result to extract reasoning_content from the raw response object."""
    # If response is an openai BaseModel, try to get reasoning content from the raw object
    reasoning_contents = {}
    if isinstance(response, openai.BaseModel) and hasattr(response, "choices"):
        for i, choice in enumerate(response.choices):
            msg = getattr(choice, "message", None)
            if msg is not None:
                rc = None
                for field_name in _REASONING_FIELD_NAMES:
                    rc = getattr(msg, field_name, None)
                    if rc:
                        reasoning_contents[i] = rc
                        break
                if not rc:
                    extras = getattr(msg, "model_extra", {}) or {}
                    for field_name in _REASONING_FIELD_NAMES:
                        if extras.get(field_name):
                            reasoning_contents[i] = extras[field_name]
                            break

    result = _original_create_chat_result(self, response, generation_info)

    # Inject reasoning_content into the AIMessage if we found it from raw response
    if reasoning_contents:
        for i, rc in reasoning_contents.items():
            if i < len(result.generations):
                gen_msg = result.generations[i].message
                if isinstance(gen_msg, AIMessage) and "reasoning_content" not in gen_msg.additional_kwargs:
                    gen_msg.additional_kwargs["reasoning_content"] = rc

    return result


_BaseChatOpenAI._create_chat_result = _patched_create_chat_result


# --- Patch 4: _convert_delta_to_message_chunk - preserve reasoning_content in streaming ---


def _patched_convert_delta_to_message_chunk(_dict, default_class, *args, **kwargs):
    """Preserve reasoning_content from streaming delta chunks."""
    chunk = _original_convert_delta_to_message_chunk(_dict, default_class, *args, **kwargs)
    if isinstance(chunk, AIMessageChunk):
        for field_name in _REASONING_FIELD_NAMES:
            if _dict.get(field_name):
                chunk.additional_kwargs["reasoning_content"] = _dict[field_name]
                break
    return chunk


_lc_openai_base._convert_delta_to_message_chunk = _patched_convert_delta_to_message_chunk


# --- Patch 2: Request serialization (inject reasoning_content back) ----------


def _patched_convert_message_to_dict(message, *args, **kwargs):
    """Inject reasoning_content from AIMessage.additional_kwargs into the API request payload."""
    result = _original_convert_message_to_dict(message, *args, **kwargs)
    if isinstance(message, AIMessage) and result.get("role") == "assistant" and "reasoning_content" in message.additional_kwargs:
        result["reasoning_content"] = message.additional_kwargs["reasoning_content"]
    return result


_lc_openai_base._convert_message_to_dict = _patched_convert_message_to_dict


class BasicNode:
    def log(self, config: RunnableConfig, message: str):
        trace_id = config["configurable"]["trace_id"]
        logger.debug(f"[{trace_id}] {message}")

    def get_llm_client(self, request: BasicLLMRequest, disable_stream=False, isolated=False):
        """
        获取LLM客户端

        Args:
            request: LLM请求对象
            disable_stream: 是否禁用流式输出
            isolated: 是否创建独立客户端(不被LangGraph跟踪),用于内部调用如问题改写

        Returns:
            BaseChatModel客户端实例 (ChatOpenAI 或 ChatAnthropic)
        """
        return LLMClientFactory.create_client(request, disable_stream=disable_stream, isolated=isolated)

    def prompt_message_node(self, state: Dict[str, Any], config: RunnableConfig) -> Dict[str, Any]:
        system_message_prompt = TemplateLoader.render_template(
            "prompts/graph/base_node_system_message",
            {"user_system_message": config["configurable"]["graph_request"].system_message_prompt},
        )

        state["messages"].append(SystemMessage(content=system_message_prompt))

        return state

    def suggest_question_node(self, state: Dict[str, Any], config: RunnableConfig) -> Dict[str, Any]:
        if config["configurable"]["graph_request"].enable_suggest:
            suggest_question_prompt = TemplateLoader.render_template("prompts/graph/suggest_question_prompt", {})
            # 将建议问题提示合并到第一个 SystemMessage 中，避免某些模型要求 SystemMessage 必须在最前面
            if state["messages"] and isinstance(state["messages"][0], SystemMessage):
                state["messages"][0] = SystemMessage(content=state["messages"][0].content + "\n\n" + suggest_question_prompt)
            else:
                # 如果没有 SystemMessage，则插入到最前面
                state["messages"].insert(0, SystemMessage(content=suggest_question_prompt))
        return state

    def add_chat_history_node(self, state: Dict[str, Any], config: RunnableConfig) -> Dict[str, Any]:
        """添加聊天历史到消息列表"""
        if config["configurable"]["graph_request"].chat_history:
            for chat in config["configurable"]["graph_request"].chat_history:
                if chat.event == "user":
                    if chat.image_data:
                        # 构建多模态消息内容 (文本 + 多张图片)
                        content = []

                        # 添加文本部分
                        if chat.message:
                            content.append({"type": "text", "text": chat.message})
                        else:
                            content.append(
                                {
                                    "type": "text",
                                    "text": "describe the weather in this image",
                                }
                            )

                        # 添加图片列表 (chat.image_data 是列表)
                        for image_url in chat.image_data:
                            content.append({"type": "image_url", "image_url": {"url": image_url}})

                        state["messages"].append(HumanMessage(content=content))
                    else:
                        state["messages"].append(HumanMessage(content=chat.message))
                elif chat.event == "assistant":
                    state["messages"].append(AIMessage(content=chat.message))
        return state

    async def naive_rag_node(self, state: Dict[str, Any], config: RunnableConfig) -> Dict[str, Any]:
        naive_rag_request = config["configurable"]["graph_request"].naive_rag_request
        if len(naive_rag_request) == 0:
            return state

        # 智能知识路由选择
        selected_knowledge_ids = []
        if "km_info" in config["configurable"]:
            selected_knowledge_ids = self._select_knowledge_ids(config)

        rag_result = []
        all_img_docs = []  # 收集所有图片文档

        for rag_search_request in naive_rag_request:
            rag_search_request.search_query = config["configurable"]["graph_request"].graph_user_message

            if len(selected_knowledge_ids) != 0 and rag_search_request.index_name not in selected_knowledge_ids:
                logger.debug(f"智能知识路由判断:[{rag_search_request.index_name}]不适合当前问题,跳过检索")
                continue

            rag = PgvectorRag()
            naive_rag_search_result = rag.search(rag_search_request)

            rag_documents = []
            img_docs = []
            for doc in naive_rag_search_result:
                # 根据 is_doc 字段处理文档内容
                if getattr(doc, "metadata", {}).get("format") == "image":
                    img_docs.append(doc)
                    continue  # 图片不加入普通文档处理流程
                processed_doc = self._process_document_content(doc)
                rag_documents.append(processed_doc)

            rag_result.extend(rag_documents)
            all_img_docs.extend(img_docs)

            logger.info(f"文档中的图片数：{len(img_docs)}")
            if img_docs:
                logger.info(f"图片文档示例： {img_docs[0].page_content[:50] if img_docs[0].page_content else 'empty'}")

            # 执行图谱 RAG 检索
            if rag_search_request.enable_graph_rag:
                graph_results = await self._execute_graph_rag(rag_search_request, config)
                rag_result.extend(graph_results)

        # 准备模板数据
        template_data = self._prepare_template_data(rag_result, config)

        # 使用模板生成 RAG 消息
        rag_message = TemplateLoader.render_template("prompts/graph/naive_rag_node_prompt", template_data)

        # 如果有图片文档，将图片的OCR识别内容添加到rag_message
        if all_img_docs:
            # all_img_docs = all_img_docs[:10]
            img_text_content = self._extract_image_text_content(all_img_docs)
            if img_text_content:
                rag_message += f"\n\n=== 图片识别内容 ===\n{img_text_content}"

        logger.debug(f"RAG增强Prompt已生成，长度: {len(rag_message)}")

        # 添加文本 RAG 消息
        state["messages"].append(HumanMessage(content=rag_message))

        # 添加图片到消息（仅图片base64，不含文本内容）
        if all_img_docs:
            self._add_image_docs_to_messages(state, all_img_docs)

        return state

    def _select_knowledge_ids(self, config: RunnableConfig) -> list:
        """智能知识路由选择"""
        km_info = config["configurable"]["km_info"]

        # 创建临时请求对象用于知识路由
        km_request = BasicLLMRequest(
            model=config["configurable"]["km_route_llm_model"],
            openai_api_base=config["configurable"]["km_route_llm_api_base"],
            openai_api_key=config["configurable"]["km_route_llm_api_key"],
            temperature=0.01,
            user_message="",
        )

        # 使用模板生成知识路由选择prompt
        template_data = {"km_info": km_info, "user_message": config["configurable"]["graph_request"].user_message}
        selected_knowledge_prompt = TemplateLoader.render_template("prompts/graph/knowledge_route_selection_prompt", template_data)

        logger.debug(f"知识路由选择Prompt: {selected_knowledge_prompt}")
        # 使用原生OpenAI客户端调用,完全绕过LangGraph追踪
        response_content = LLMClientFactory.invoke_isolated(km_request, [{"role": "user", "content": selected_knowledge_prompt}])
        return json_repair.loads(response_content)

    async def _execute_graph_rag(self, rag_search_request, config: RunnableConfig) -> list:
        """执行图谱RAG检索并处理结果"""
        try:
            # 执行图谱检索
            graph_result = await self._perform_graph_search(rag_search_request, config)
            if not graph_result:
                logger.warning("GraphRAG检索结果为空")
                return []

            # 处理检索结果
            return self._process_graph_results(graph_result, rag_search_request.graph_rag_request.group_ids)

        except Exception as e:
            logger.error("GraphRAG检索处理异常: %r", e)
            return []

    async def _perform_graph_search(self, rag_search_request, config: RunnableConfig) -> list:
        """执行图谱搜索"""
        graphiti = GraphitiRAG()
        rag_search_request.graph_rag_request.search_query = rag_search_request.search_query
        graph_result = await graphiti.search(req=rag_search_request.graph_rag_request)

        logger.debug(f"GraphRAG模式检索知识库: {rag_search_request.graph_rag_request.group_ids}, 结果数量: {len(graph_result)}")
        return graph_result

    def _process_graph_results(self, graph_result: list, group_ids: list) -> list:
        """处理图谱检索结果"""
        seen_relations = set()
        summary_dict = {}  # 用于去重summary
        processed_results = []

        # 使用默认的group_id，避免在循环中重复获取
        default_group_id = group_ids[0] if group_ids else ""

        for graph_item in graph_result:
            # 处理关系事实
            relation_result = self._process_relation_fact(graph_item, seen_relations, default_group_id)
            if relation_result:
                processed_results.append(relation_result)

            # 收集summary信息
            self._collect_summary_info(graph_item, summary_dict)

        # 生成去重的summary结果
        summary_results = self._generate_summary_results(summary_dict, default_group_id)
        processed_results.extend(summary_results)

        return processed_results

    def _process_relation_fact(self, graph_item: dict, seen_relations: set, group_id: str):
        """处理单个关系事实"""
        source_node = graph_item.get("source_node", {})
        target_node = graph_item.get("target_node", {})
        source_name = source_node.get("name", "")
        target_name = target_node.get("name", "")
        fact = graph_item.get("fact", "")

        if not (fact and source_name and target_name):
            return None

        relation_content = f"关系事实: {source_name} - {fact} - {target_name}"
        if relation_content in seen_relations:
            return None

        seen_relations.add(relation_content)
        return self._create_relation_result_object(relation_content, source_name, target_name, group_id)

    def _collect_summary_info(self, graph_item: dict, summary_dict: dict):
        """收集并去重summary信息"""
        source_node = graph_item.get("source_node", {})
        target_node = graph_item.get("target_node", {})

        for node_data in [source_node, target_node]:
            node_name = node_data.get("name", "")
            node_summary = node_data.get("summary", "")

            if node_name and node_summary:
                if node_summary not in summary_dict:
                    summary_dict[node_summary] = set()
                summary_dict[node_summary].add(node_name)

    def _generate_summary_results(self, summary_dict: dict, group_id: str) -> list:
        """生成去重的summary结果"""
        summary_results = []
        for summary_content, associated_nodes in summary_dict.items():
            nodes_list = ", ".join(sorted(associated_nodes))
            summary_with_nodes = f"节点详情: 以下内容与节点 [{nodes_list}] 相关:\n{summary_content}"

            summary_result = self._create_summary_result_object(summary_with_nodes, nodes_list, group_id, summary_content)
            summary_results.append(summary_result)

        return summary_results

    def _create_relation_result_object(self, relation_content: str, source_name: str, target_name: str, group_id: str):
        """创建关系事实结果对象"""
        content_hash = hash(relation_content) % 100000

        class RelationResult:
            def __init__(self):
                self.page_content = relation_content
                self.metadata = {
                    "knowledge_title": f"图谱关系: {source_name} - {target_name}",
                    "knowledge_id": group_id,
                    "chunk_number": 1,
                    "chunk_id": f"relation_{content_hash}",
                    "segment_number": 1,
                    "segment_id": f"relation_{content_hash}",
                    "chunk_type": "Graph",
                }

        return RelationResult()

    def _create_summary_result_object(self, summary_with_nodes: str, nodes_list: str, group_id: str, summary_content: str):
        """创建summary结果对象"""
        content_hash = hash(summary_content) % 100000

        class SummaryResult:
            def __init__(self):
                self.page_content = summary_with_nodes
                self.metadata = {
                    "knowledge_title": f"图谱节点详情: {nodes_list}",
                    "knowledge_id": group_id,
                    "chunk_number": 1,
                    "chunk_id": f"summary_{content_hash}",
                    "segment_number": 1,
                    "segment_id": f"summary_{content_hash}",
                    "chunk_type": "Graph",
                }

        return SummaryResult()

    def _prepare_template_data(self, rag_result: list, config: RunnableConfig) -> dict:
        """准备模板渲染所需的数据"""
        # 转换RAG结果为模板友好的格式
        rag_results = []
        for r in rag_result:
            # 直接从metadata获取数据（PgvectorRag返回扁平结构）
            metadata = getattr(r, "metadata", {})
            rag_results.append(
                {
                    "title": metadata.get("knowledge_title", "N/A"),
                    "knowledge_id": metadata.get("knowledge_id", 0),
                    "chunk_number": metadata.get("chunk_number", 0),
                    "chunk_id": metadata.get("chunk_id", "N/A"),
                    "segment_number": metadata.get("segment_number", 0),
                    "segment_id": metadata.get("segment_id", "N/A"),
                    "content": r.page_content,
                    "chunk_type": metadata.get("chunk_type", "Document"),
                }
            )

        # 准备模板数据
        template_data = {
            "rag_results": rag_results,
            "enable_rag_source": config["configurable"].get("enable_rag_source", False),
            "enable_rag_strict_mode": config["configurable"].get("enable_rag_strict_mode", False),
        }

        return template_data

    def _process_document_content(self, doc):
        """
        根据 is_doc 字段处理文档内容

        Args:
            doc: 文档对象，包含 page_content 和 metadata

        Returns:
            处理后的文档对象
        """
        # 获取元数据
        metadata = getattr(doc, "metadata", {})
        is_doc = metadata.get("is_doc")

        logger.debug(f"处理文档内容 - is_doc: {is_doc}")

        if is_doc == "0":
            # QA类型：用 qa_question 和 qa_answer 组合替换 page_content
            qa_question = metadata.get("qa_question")
            qa_answer = metadata.get("qa_answer")

            if qa_question and qa_answer:
                doc.page_content = f"问题: {qa_question}\n答案: {qa_answer}"
                doc.metadata["knowledge_title"] = qa_question
            doc.metadata["chunk_type"] = "QA"
        elif is_doc == "1":
            # 文档类型：直接 append qa_answer
            qa_answer = metadata.get("qa_answer")
            if qa_answer:
                doc.page_content += f"\n{qa_answer}"
            doc.metadata["chunk_type"] = "Document"
        else:
            # 默认为文档类型
            doc.metadata["chunk_type"] = "Document"

        return doc

    def _extract_image_text_content(self, img_docs: List[Any]) -> str:
        """从图片文档中提取文本内容（OCR识别结果）

        Args:
            img_docs: 图片文档列表

        Returns:
            合并后的图片文本内容
        """
        text_parts = []
        for idx, doc in enumerate(img_docs, 1):
            page_content = getattr(doc, "page_content", "")
            if page_content:
                text_parts.append(f"[图片 {idx}]\n{page_content}")

        return "\n\n".join(text_parts) if text_parts else ""

    def _add_image_docs_to_messages(self, state: Dict[str, Any], img_docs: List[Any]) -> None:
        """将图片以ImageContentBlock形式添加到消息列表

        Args:
            state: 状态字典
            img_docs: 图片文档列表，每个文档的metadata包含format, page, image_base64字段
        """
        if not img_docs:
            return

        # 构建包含所有图片的多模态消息内容（仅图片，不含文本说明）
        content = []

        # 添加所有图片
        for idx, doc in enumerate(img_docs, 1):
            metadata = getattr(doc, "metadata", {})
            image_base64 = metadata.get("image_base64", "")
            page_number = metadata.get("page", "unknown")

            if not image_base64:
                logger.warning(f"图片文档 {idx} 缺少 image_base64 字段，跳过")
                continue

            # 添加图片URL（base64格式）- ImageContentBlock
            content.append({"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{image_base64}"}})

            logger.debug(f"添加图片 {idx}/{len(img_docs)} - 页码: {page_number}, base64长度: {len(image_base64)}")

        # 只有在至少有一张有效图片时才添加消息
        if content:
            state["messages"].append(HumanMessage(content=content))
            logger.info(f"已将 {len(content)} 张图片添加到消息中")
        else:
            logger.warning("所有图片文档都缺少有效的 image_base64，未添加图片消息")

    def _rewrite_query(self, request: BasicLLMRequest, config: RunnableConfig) -> str:
        """
        使用聊天历史上下文改写用户问题

        Args:
            request: 基础LLM请求对象
            config: 运行时配置

        Returns:
            改写后的问题字符串
        """
        try:
            # 准备模板数据
            template_data = {"user_message": request.user_message, "chat_history": request.chat_history}

            # 渲染问题改写prompt
            rewrite_prompt = TemplateLoader.render_template("prompts/graph/query_rewrite_prompt", template_data)

            # 使用原生OpenAI客户端调用,完全绕过LangGraph追踪
            response_content = LLMClientFactory.invoke_isolated(request, [HumanMessage(content=rewrite_prompt)])
            rewritten_query = response_content.strip()
            return rewritten_query

        except Exception as e:
            logger.error("问题改写过程中发生异常: %r", e)
            raise

    def user_message_node(self, state: Dict[str, Any], config: RunnableConfig) -> Dict[str, Any]:
        request = config["configurable"]["graph_request"]
        user_message = request.user_message
        trace_id = config["configurable"].get("trace_id", "unknown")
        logger.info(f"[{trace_id}] user_message_node 开始执行, original_user_message={user_message[:200]!r}")

        # 如果启用问题改写功能
        if config["configurable"]["graph_request"].enable_query_rewrite:
            try:
                rewritten_message = self._rewrite_query(request, config)
                if rewritten_message and rewritten_message.strip():
                    user_message = rewritten_message
                    self.log(config, f"问题改写完成: {request.user_message} -> {user_message}")
            except Exception as e:
                logger.warning("问题改写失败，使用原始问题: %r", e)
                user_message = request.user_message

        state["messages"].append(HumanMessage(content=user_message))
        request.graph_user_message = user_message
        logger.info(f"[{trace_id}] user_message_node 执行结束, appended_user_message={user_message[:200]!r}, message_count={len(state['messages'])}")
        return state

    def chat_node(self, state: Dict[str, Any], config: RunnableConfig) -> Dict[str, Any]:
        request = config["configurable"]["graph_request"]

        # 获取LLM客户端并调用
        llm = self.get_llm_client(request)
        result = llm.invoke(state["messages"])

        return {"messages": result}


class ToolsNodes(BasicNode):
    def __init__(self) -> None:
        self.tools = []
        self.mcp_client = None
        self.mcp_config = {}
        self.tools_prompt_tokens = 0
        self.tools_completions_tokens = 0
        # 动态工具选择相关
        self.all_tools = []  # 全量工具池
        self.active_tools = []  # 当前激活的工具
        self.tool_catalog = {}  # {category_name: [tool_name, ...]}
        self.tool_catalog_descriptions = {}  # {category_name: description}
        self._category_tool_map = {}  # {category_name: [StructuredTool, ...]}
        self._dynamic_mode = False  # 是否启用动态工具选择模式
        # done tool 相关
        self.done_tool_config = None  # DoneToolConfig，由外部设置

    def get_tools_description(self) -> str:
        # 动态模式下 self.tools 被清空，使用 all_tools 获取完整工具描述
        source = self.all_tools if self.all_tools else self.tools
        if source:
            tools_info = ""
            for tool in source:
                tools_info += f"{tool.name}: {tool.description}\n"
            return tools_info
        return ""

    @staticmethod
    def _resolve_remote_transport(server_url: str, transport: str = "") -> str:
        """解析远程 MCP 传输协议（仅 HTTP/HTTPS）"""
        explicit_transport = (transport or "").strip().lower()
        if explicit_transport in {"sse", "streamable_http"}:
            return explicit_transport

        parsed_url = urlparse(server_url or "")
        query_dict = parse_qs(parsed_url.query)
        query_transport = (query_dict.get("transport", [""])[0] or "").strip().lower()
        if query_transport in {"sse", "streamable_http"}:
            return query_transport

        normalized_path = (parsed_url.path or "").rstrip("/").lower()
        if normalized_path.endswith("/sse"):
            return "sse"
        if normalized_path.endswith("/mcp") or normalized_path.endswith("/streamable_http"):
            return "streamable_http"

        return "sse"

    async def call_with_structured_output(self, llm, user_message: str, pydantic_model):
        """
        通用结构化输出调用方法

        Args:
            llm: LangChain LLM实例
            user_message: 用户消息内容
            pydantic_model: 目标Pydantic模型类

        Returns:
            解析后的Pydantic模型实例
        """
        parser = StructuredOutputParser(llm)
        return await parser.parse_with_structured_output(user_message, pydantic_model)

    async def setup(self, request: BaseModel):
        """初始化工具节点"""
        # 初始化LLM客户端和结构化输出解析器
        self.llm = self.get_llm_client(request)
        self.structured_output_parser = StructuredOutputParser(self.llm)

        # 初始化MCP客户端配置
        for server in request.tools_servers:
            if server.url.startswith("langchain:"):
                continue

            if server.url.startswith("stdio-mcp:"):
                # stdio-mcp:name
                self.mcp_config[server.name] = {"command": server.command, "args": server.args, "transport": "stdio"}
            else:
                self.mcp_config[server.name] = {
                    "url": server.url,
                    "transport": self._resolve_remote_transport(server.url, getattr(server, "transport", "")),
                }
            if server.enable_auth:
                self.mcp_config[server.name]["headers"] = {"Authorization": server.auth_token}

        if self.mcp_config:
            self.mcp_client = MultiServerMCPClient(self.mcp_config)
            try:
                self.tools = await self.mcp_client.get_tools()
                logger.debug(f"成功加载 MCP 工具，共 {len(self.tools)} 个")
            except Exception as e:
                logger.error(f"MCP 工具加载失败: {e}。将继续使用其他可用工具。")
                # MCP 加载失败时不中断，继续加载其他工具（如 LangChain 工具）

        # 初始化LangChain工具
        for server in request.tools_servers:
            if server.url.startswith("langchain:"):
                try:
                    langchain_tools = ToolsLoader.load_tools(server.url, server.extra_tools_prompt, server.extra_param_prompt)
                    self.tools.extend(langchain_tools)
                    # 按类别记录工具映射
                    category_name = server.url.replace("langchain:", "")
                    self._category_tool_map[category_name] = langchain_tools
                    self.tool_catalog[category_name] = [t.name for t in langchain_tools]
                    # 描述取第一个工具的 description 前 100 字符或 server.extra_tools_prompt
                    desc = server.extra_tools_prompt or (langchain_tools[0].description[:100] if langchain_tools else "")
                    self.tool_catalog_descriptions[category_name] = desc
                except Exception as e:
                    logger.error(f"LangChain 工具加载失败 ({server.url}): {e}。将继续使用其他可用工具。")

        # MCP 工具也记录到 catalog
        if self.mcp_config:
            # 收集所有已被 LangChain 类别归属的工具名
            categorized_names = {name for tools_list in self._category_tool_map.values() for name in [t.name for t in tools_list]}
            # MCP 工具 = self.tools 中未被 LangChain 归类的部分
            mcp_tools_ungrouped = [t for t in self.tools if t.name not in categorized_names]
            # 按 MCP server 名逐个分配（工具名前缀匹配或均分到对应 server）
            # 注: MultiServerMCPClient 返回的工具不携带 server 来源，此处按顺序尝试匹配
            mcp_server_names = [s.name for s in request.tools_servers if not s.url.startswith("langchain:")]
            if len(mcp_server_names) == 1:
                # 单 MCP server: 全部归入
                server_name = mcp_server_names[0]
                server_cfg = next((s for s in request.tools_servers if s.name == server_name), None)
                if mcp_tools_ungrouped:
                    self._category_tool_map[server_name] = mcp_tools_ungrouped
                    self.tool_catalog[server_name] = [t.name for t in mcp_tools_ungrouped]
                    desc = (server_cfg.extra_tools_prompt if server_cfg else "") or f"MCP tools from {server_name}"
                    self.tool_catalog_descriptions[server_name] = desc
            elif len(mcp_server_names) > 1 and mcp_tools_ungrouped:
                # 多 MCP server: 无法精确归属，统一归入 "mcp_tools" 类别
                self._category_tool_map["mcp_tools"] = mcp_tools_ungrouped
                self.tool_catalog["mcp_tools"] = [t.name for t in mcp_tools_ungrouped]
                self.tool_catalog_descriptions["mcp_tools"] = f"MCP tools ({len(mcp_tools_ungrouped)} tools from {len(mcp_server_names)} servers)"

        # 全量工具池
        self.all_tools = list(self.tools)

        # 动态工具选择：根据阈值决定是否启用
        tool_pool_config = getattr(request, "tool_pool_config", None)
        if tool_pool_config and tool_pool_config.enabled and len(self.all_tools) > tool_pool_config.auto_activate_threshold:
            self._dynamic_mode = True
            self.active_tools = []  # 初始不激活任何工具
            self.tools = []  # 清空 self.tools，由 build_react_nodes 使用 active_tools + meta-tool
            logger.info(f"动态工具选择已启用: 共 {len(self.all_tools)} 个工具函数, " f"{len(self.tool_catalog)} 个类别, 阈值={tool_pool_config.auto_activate_threshold}")
        else:
            self._dynamic_mode = False
            self.active_tools = list(self.all_tools)
            logger.info(f"动态工具选择未启用: 共 {len(self.all_tools)} 个工具函数，全部激活")

        # done tool 配置
        self.done_tool_config = getattr(request, "done_tool_config", None)

    def _build_activate_tools_meta_tool(self):
        """构建 activate_tools meta-tool，供 LLM 按需激活工具类别"""
        # 构建工具目录描述
        catalog_lines = []
        for category, tool_names in self.tool_catalog.items():
            desc = self.tool_catalog_descriptions.get(category, "")
            catalog_lines.append(f"- {category}: {desc} (包含 {len(tool_names)} 个工具)")
        catalog_text = "\n".join(catalog_lines)

        # 闭包引用
        category_tool_map = self._category_tool_map
        active_tools = self.active_tools

        def activate_tools(categories: str) -> str:
            """激活指定类别的工具，使其可用于后续调用。

            Args:
                categories: 逗号分隔的类别名称列表，如 "kubernetes,mysql"
            """
            category_list = [c.strip() for c in categories.split(",") if c.strip()]
            activated = []
            already_active = []
            not_found = []

            for cat in category_list:
                if cat not in category_tool_map:
                    not_found.append(cat)
                    continue
                cat_tools = category_tool_map[cat]
                # 检查是否已激活
                active_names = {t.name for t in active_tools}
                new_tools = [t for t in cat_tools if t.name not in active_names]
                if new_tools:
                    active_tools.extend(new_tools)
                    activated.append(f"{cat} ({len(new_tools)} 个工具)")
                else:
                    already_active.append(cat)

            parts = []
            if activated:
                parts.append(f"已激活: {', '.join(activated)}")
            if already_active:
                parts.append(f"已存在: {', '.join(already_active)}")
            if not_found:
                parts.append(f"未找到: {', '.join(not_found)}")

            active_names_now = [t.name for t in active_tools]
            parts.append(f"当前可用工具: {active_names_now}")
            return "; ".join(parts)

        tool_description = f"激活工具类别，使对应工具可用于后续操作。输入逗号分隔的类别名称。\n\n" f"可用工具类别:\n{catalog_text}\n\n" f'示例: activate_tools(categories="kubernetes,mysql")'

        meta_tool = StructuredTool.from_function(
            func=activate_tools,
            name="activate_tools",
            description=tool_description,
        )
        return meta_tool

    def _build_done_tool(self, done_cfg=None):
        """构建 done tool 用于显式终止 ReAct 循环并返回结构化结果"""
        if done_cfg is None:
            done_cfg = DoneToolConfig()
        if not done_cfg.enabled:
            return None

        class DoneToolInput(BaseModel):
            result: str = PydanticField(description="任务的最终结构化结果（JSON 字符串）")

        def _done_func(result: str) -> str:
            # 实际不会执行，should_continue 会拦截
            return result

        done_tool = StructuredTool.from_function(
            func=_done_func,
            name=done_cfg.tool_name,
            description=done_cfg.description,
            args_schema=DoneToolInput,
        )
        return done_tool

    def _build_approval_tool(self):
        """构建 request_human_approval 工具，供 LLM 在判断操作高危时主动调用"""
        class ApprovalToolInput(BaseModel):
            action: str = PydanticField(description="即将执行的操作描述，包括工具名和关键参数")
            reason: str = PydanticField(description="为什么需要人工审批（风险说明）")
            risk_level: str = PydanticField(default="medium", description="风险等级: low / medium / high / critical")

        async def _request_approval(action: str, reason: str, risk_level: str = "medium") -> str:
            # 从 RunnableConfig 中获取上下文信息（通过闭包不可行，工具执行时由 ToolNode 调用）
            # 使用唯一标识作为 tool_call_id 的替代
            request_id = str(uuid.uuid4())[:8]
            # 从当前执行上下文获取 execution_id
            # 注意：ToolNode 执行工具时不传 config，所以用模块级的上下文
            execution_id = getattr(_request_approval, "_execution_id", "") or str(int(time.time() * 1000))
            node_id = getattr(_request_approval, "_node_id", "skill_test")

            approval_request_data = {
                "execution_id": execution_id,
                "node_id": node_id,
                "tool_call_id": f"approval_{request_id}",
                "tool_name": action,
                "tool_args": {"reason": reason, "risk_level": risk_level},
                "timeout_seconds": 300,
            }
            try:
                dispatch_custom_event("approval_request", approval_request_data)
            except Exception:
                pass

            logger.info(f"[approval_tool] 审批请求已发射: action={action}, risk={risk_level}, id={request_id}")

            decision_info = await wait_for_approval(
                execution_id=execution_id,
                node_id=node_id,
                tool_call_id=f"approval_{request_id}",
                timeout_seconds=300,
                poll_interval=1.0,
                trigger_type="interactive",
                unattended_strategy="skip",
                timeout_fallback="deny",
            )

            decision = decision_info["decision"]
            dec_reason = decision_info.get("reason", "")
            logger.info(f"[approval_tool] 审批决策: decision={decision}, reason={dec_reason}")

            if decision == "approve":
                return f"已批准。你现在可以继续执行操作: {action}"
            else:
                return f"操作被拒绝: {action}。原因: {dec_reason}" if dec_reason else f"操作被拒绝: {action}。请告知用户操作未被批准。"

        approval_tool = StructuredTool.from_function(
            coroutine=_request_approval,
            name="request_human_approval",
            description=("当你判断即将执行的操作具有较高风险（如修改系统配置、删除数据、重启服务等），" "应先调用此工具请求人工审批。描述你要做什么以及为什么需要审批。" "收到审批结果后，根据结果决定是否继续执行实际操作。"),
            args_schema=ApprovalToolInput,
        )
        # 存储执行上下文的引用，在 build_react_nodes 中设置
        approval_tool._request_approval_func = _request_approval
        return approval_tool

    def _build_choice_tool(self):
        """构建 request_user_choice 工具，供 LLM 需要用户从多个选项中选择时调用"""
        class ChoiceOption(BaseModel):
            key: str = PydanticField(description="选项唯一标识，将返回给你")
            label: str = PydanticField(description="选项显示文本")
            description: str = PydanticField(default="", description="选项详细描述（可选）")
            recommended: bool = PydanticField(default=False, description="是否为推荐选项")

        class ChoiceToolInput(BaseModel):
            title: str = PydanticField(description="选择标题，如'请选择要查询的表'")
            options: List[ChoiceOption] = PydanticField(description="可选项列表，至少2个")
            description: str = PydanticField(default="", description="补充说明（可选）")
            multiple: bool = PydanticField(default=False, description="是否允许多选")
            min_select: int = PydanticField(default=1, description="最少选择数量（多选时有效）")
            max_select: int = PydanticField(default=0, description="最多选择数量（多选时有效，0表示不限制）")
            timeout_seconds: int = PydanticField(default=60, description="等待用户选择的超时时间（秒），超时后使用默认选项")
            default_keys: List[str] = PydanticField(
                default_factory=list,
                description="超时时的默认选项 key 列表（可选，不填则使用第一个或推荐选项）",
            )

        async def _request_choice(
            title: str,
            options: List[ChoiceOption],
            description: str = "",
            multiple: bool = False,
            min_select: int = 1,
            max_select: int = 0,
            timeout_seconds: int = 60,
            default_keys: List[str] = None,
        ) -> str:
            choice_id = str(uuid.uuid4())[:8]
            execution_id = getattr(_request_choice, "_execution_id", "") or str(int(time.time() * 1000))
            node_id = getattr(_request_choice, "_node_id", "skill_test")

            options_data = [opt.model_dump() for opt in options]
            default_keys = default_keys or []

            # Calculate effective min/max select
            effective_min_select = min_select if multiple else 1
            effective_max_select = max_select if max_select > 0 else (len(options) if multiple else 1)

            # If no default_keys, use recommended options or first option
            if not default_keys:
                recommended_keys = [opt["key"] for opt in options_data if opt.get("recommended")]
                if recommended_keys:
                    if effective_max_select > 0:
                        default_keys = recommended_keys[:effective_max_select]
                    else:
                        default_keys = recommended_keys
                elif options_data:
                    default_keys = [options_data[0]["key"]]

            choice_request_data = {
                "execution_id": execution_id,
                "node_id": node_id,
                "choice_id": choice_id,
                "title": title,
                "description": description,
                "options": options_data,
                "multiple": multiple,
                "min_select": effective_min_select,
                "max_select": effective_max_select,
                "timeout_seconds": timeout_seconds,
                "default_keys": default_keys,
                "display_hint": "auto",
            }

            try:
                dispatch_custom_event("user_choice_request", choice_request_data)
            except Exception:
                pass

            logger.info(f"[choice_tool] 选择请求已发射: title={title}, " f"options={len(options)}, id={choice_id}, timeout={timeout_seconds}s")

            result = await wait_for_choice(
                execution_id=execution_id,
                node_id=node_id,
                choice_id=choice_id,
                options=options_data,
                default_keys=default_keys,
                timeout_seconds=timeout_seconds,
                poll_interval=1.0,
                trigger_type="interactive",
            )

            selected = result["selected"]
            source = result["source"]

            # Dispatch result event to notify frontend
            try:
                dispatch_custom_event(
                    "user_choice_result",
                    {
                        "execution_id": execution_id,
                        "node_id": node_id,
                        "choice_id": choice_id,
                        "selected": selected,
                        "source": source,
                    },
                )
            except Exception:
                pass

            # 构建返回给 LLM 的文本
            selected_labels = [opt["label"] for opt in options_data if opt["key"] in selected]

            if source == "user":
                return f"用户选择了: {', '.join(selected_labels)} (keys: {selected})。请根据用户的选择继续执行下一步操作，不要停止。"
            elif source == "timeout":
                return f"用户未在规定时间内选择，已使用默认选项: " f"{', '.join(selected_labels)} (keys: {selected})。请根据默认选项继续执行下一步操作，不要停止。"
            else:
                return f"自动选择: {', '.join(selected_labels)} (keys: {selected})。请继续执行下一步操作，不要停止。"

        choice_tool = StructuredTool.from_function(
            coroutine=_request_choice,
            name="request_user_choice",
            description=("当你需要用户从多个选项中选择时调用此工具。" "例如：用户请求查询多个表但一次只能查一个，需要用户选择；" "或者有多种执行方案需要用户决定。" "提供清晰的选项列表，等待用户选择后继续。"),
            args_schema=ChoiceToolInput,
        )
        choice_tool._request_choice_func = _request_choice
        return choice_tool

    async def build_tools_node(self) -> ToolNode:
        """构建工具节点"""
        try:
            if self.tools:
                tool_node = ToolNode(self.tools, handle_tool_errors=True)
                logger.debug(f"成功构建工具节点，包含 {len(self.tools)} 个工具")
                return tool_node
            else:
                logger.debug("未找到可用工具，返回空工具节点")
                return ToolNode([])
        except Exception as e:
            logger.error("构建工具节点失败: %r", e)
            return ToolNode([])

    # ========== 使用 LangGraph 标准 ReAct Agent 实现 ==========

    async def build_react_nodes(  # noqa: C901
        self,
        graph_builder: StateGraph,
        composite_node_name: str = "react_agent",
        additional_system_prompt: Optional[str] = None,
        next_node: str = END,
        tools_node: Optional[ToolNode] = None,
        agent_name: Optional[str] = None,
    ) -> str:
        """构建 ReAct Agent 节点组合

        使用 bind_tools + ToolNode + 条件边的方式构建 ReAct 循环，
        使工具调用事件能够被外层 astream_events 捕获。

        Args:
            graph_builder: StateGraph 实例
            composite_node_name: 节点名称前缀
            additional_system_prompt: 附加系统提示词
            next_node: ReAct 循环结束后转到的下一个节点名称（默认 END）
            tools_node: 工具节点（可选，默认使用 self.tools）

        Returns:
            入口节点名称（wrapper 节点，用于连接外部边）
        """
        # 节点名称
        agent_node_name = f"{composite_node_name}_agent"
        tools_node_name = f"{composite_node_name}_tools"
        wrapper_node_name = f"{composite_node_name}_wrapper"

        # 保存引用供闭包使用
        tools = self.tools
        get_llm_client = self.get_llm_client
        step_counter = {"count": 0}  # 步数计数器（闭包可变引用）
        token_counter = {"total": 0}  # 累计 token 计数器
        start_time = {"value": None}  # 总超时起始时间（首步时初始化）
        # 反思追踪器
        reflection_tracker = {
            "consecutive_failures": 0,  # 连续失败计数
            "tool_call_history": [],  # 最近的工具调用名称列表
        }
        # 动态工具选择相关
        dynamic_mode = self._dynamic_mode
        active_tools_ref = self.active_tools  # 可变列表引用
        meta_tool = self._build_activate_tools_meta_tool() if dynamic_mode else None
        # done tool 结构化终止
        done_tool_instance = self._build_done_tool(self.done_tool_config)
        done_tool_name = self.done_tool_config.tool_name if (self.done_tool_config and self.done_tool_config.enabled) else None
        # 人工审批工具（LLM 自主判断高危操作时调用）
        approval_tool_instance = self._build_approval_tool() if (self.all_tools or self.tools) else None
        # 用户选择工具（LLM 需要用户从多个选项中选择时调用）
        choice_tool_instance = self._build_choice_tool() if (self.all_tools or self.tools) else None
        # 选择后续行追踪（防止 LLM 在 request_user_choice 后停止）
        choice_continuation = {"retried_at_step": -1}

        # ========== 步骤进度发射辅助 ==========
        def _emit_step_progress(max_steps: int, status: str, description: str = "", tool_name: str = None, step_elapsed: float = 0.0):
            """发射 agent_step_progress 自定义事件"""
            total_elapsed = (time.monotonic() - start_time["value"]) if start_time["value"] else 0.0
            try:
                dispatch_custom_event(
                    "agent_step_progress",
                    {
                        "agent_name": agent_name,
                        "step": step_counter["count"],
                        "max_steps": max_steps,
                        "status": status,
                        "description": description,
                        "tool_name": tool_name,
                        "elapsed_seconds": round(step_elapsed, 2),
                        "total_elapsed_seconds": round(total_elapsed, 2),
                    },
                )
            except Exception:
                pass  # 非关键路径，不阻断执行

        # ========== Agent 节点：调用 LLM 并决定是否使用工具 ==========
        async def agent_node(state: Dict[str, Any], config: RunnableConfig) -> Dict[str, Any]:
            """Agent 节点 - 调用绑定工具的 LLM"""
            graph_request = config["configurable"]["graph_request"]
            trace_id = config["configurable"].get("trace_id", "unknown")

            # 设置审批工具的执行上下文
            if approval_tool_instance:
                func = approval_tool_instance._request_approval_func
                func._execution_id = config["configurable"].get("execution_id", "")
                func._node_id = config["configurable"].get("node_id", "skill_test")

            # 设置选择工具的执行上下文
            if choice_tool_instance:
                func = choice_tool_instance._request_choice_func
                func._execution_id = config["configurable"].get("execution_id", "")
                func._node_id = config["configurable"].get("node_id", "skill_test")

            # 构建系统提示
            # 动态工具模式下，构建 activate_tools 使用说明
            dynamic_tool_instruction = ""
            if dynamic_mode and meta_tool:
                catalog_lines = []
                for category, tool_names in self.tool_catalog.items():
                    desc = self.tool_catalog_descriptions.get(category, "")
                    catalog_lines.append(f"- {category}: {desc} (包含 {len(tool_names)} 个工具)")
                catalog_text = "\n".join(catalog_lines)
                dynamic_tool_instruction = (
                    "【铁律：必须先激活工具才能执行任何操作】\n\n"
                    "你当前没有直接可用的操作工具。你必须先调用 activate_tools 工具来激活需要的工具类别，"
                    "然后才能使用对应的具体工具完成用户的请求。\n\n"
                    "可用的工具类别:\n"
                    f"{catalog_text}\n\n"
                    '使用方式: 根据用户的请求，判断需要哪些类别的工具，立即调用 activate_tools(categories="类别名1,类别名2") 来激活它们。\n'
                    "激活后，你就可以使用该类别下的具体工具来完成用户的请求。\n\n"
                    "⚠️ 重要: \n"
                    "- 不要告诉用户你无法执行操作，你拥有工具能力，只需要先激活对应类别\n"
                    "- 不要直接回答用户的问题，必须先调用 activate_tools 激活工具，再使用具体工具获取真实数据\n"
                    "- 收到用户请求后的第一个动作必须是调用 activate_tools\n"
                )

            final_system_prompt = TemplateLoader.render_template(
                "prompts/graph/react_agent_system_message",
                {
                    "user_system_message": graph_request.system_message_prompt,
                    "additional_system_prompt": additional_system_prompt or "",
                    "dynamic_tool_instruction": dynamic_tool_instruction,
                    "has_approval_tool": approval_tool_instance is not None,
                },
            )

            # 准备消息列表
            messages = state.get("messages", [])

            # 如果消息中没有系统提示，添加一个
            if not any(isinstance(m, SystemMessage) for m in messages):
                messages = [SystemMessage(content=final_system_prompt)] + list(messages)

            # 消息裁剪：在 compaction 之前执行轻量级裁剪（截断过长消息、清理早期图片）
            trim_cfg = graph_request.message_trim_config
            if trim_cfg.enabled and (tools or dynamic_mode):
                messages = trim_messages(messages, trim_cfg, model_name=graph_request.model)

            # 上下文 Compaction：检测 token 是否超限，自动压缩历史消息
            if graph_request.compaction_enabled and (tools or dynamic_mode):
                compaction_config = CompactionConfig(
                    enabled=graph_request.compaction_enabled,
                    max_token_threshold=graph_request.compaction_max_token_threshold,
                    keep_recent_messages=graph_request.compaction_keep_recent_messages,
                    summary_max_tokens=graph_request.compaction_summary_max_tokens,
                )
                # 使用 isolated LLM 生成摘要（不被 LangGraph 流捕获）
                compaction_llm = get_llm_client(graph_request, disable_stream=True, isolated=True)
                messages = await compact_messages(
                    messages=messages,
                    llm=compaction_llm,
                    config=compaction_config,
                    model_name=graph_request.model,
                )

            # ========== prepareStep 钩子：每步前允许修改 tools/messages ==========
            step_counter["count"] += 1

            # 发射步骤开始进度事件
            _emit_step_progress(graph_request.max_steps, "running", description=f"步骤 {step_counter['count']} 开始")

            # ========== 中断检查：每步开始时检查是否被请求中断 ==========
            execution_id = config["configurable"].get("execution_id", "")
            if execution_id and await is_interrupt_requested_async(execution_id):
                logger.info(f"[{trace_id}] agent_node 检测到中断请求 (step={step_counter['count']})")
                _emit_step_progress(graph_request.max_steps, "interrupted", description="任务已被中断")
                return {"messages": [AIMessage(content="任务已被中断。")]}

            # ========== 总超时检查 ==========
            timeout_cfg = graph_request.timeout_config
            if timeout_cfg.enabled:
                if start_time["value"] is None:
                    start_time["value"] = time.monotonic()
                elif timeout_cfg.total_timeout_seconds > 0:
                    elapsed = time.monotonic() - start_time["value"]
                    if elapsed >= timeout_cfg.total_timeout_seconds:
                        logger.warning(
                            f"[{trace_id}] agent_node 总超时 (step={step_counter['count']}, "
                            f"elapsed={elapsed:.1f}s >= {timeout_cfg.total_timeout_seconds}s)"
                        )
                        _emit_step_progress(graph_request.max_steps, "timeout", description=f"任务已超时（{elapsed:.0f}s）")
                        return {"messages": [AIMessage(content=f"任务已超时（已运行 {elapsed:.0f} 秒）。基于已有信息，以下是当前进展的总结。")]}

            # 本轮使用的工具（动态模式下从 active_tools 取，并附加 meta-tool）
            if dynamic_mode:
                current_tools = list(active_tools_ref) + ([meta_tool] if meta_tool else [])
            else:
                current_tools = list(tools)
            # 附加 done tool（如果启用）
            if done_tool_instance:
                current_tools = current_tools + [done_tool_instance]
            # 附加审批工具
            if approval_tool_instance:
                current_tools = current_tools + [approval_tool_instance]
            # 附加选择工具
            if choice_tool_instance:
                current_tools = current_tools + [choice_tool_instance]

            logger.info(
                f"[{trace_id}] ReAct agent_node 准备调用 LLM, model={graph_request.model!r}, "
                f"bound_tool_count={len(current_tools)}, bound_tool_names={[tool.name for tool in current_tools]}, "
                f"message_count={len(messages)}, message_types={[type(m).__name__ for m in messages]}, "
                f"last_message_preview={str(getattr(messages[-1], 'content', ''))[:200]!r}"
            )

            extra_system_prompt_override = None

            if graph_request.prepare_step_hooks:
                ctx = PrepareStepContext(
                    step_number=step_counter["count"],
                    messages=messages,
                    tools=current_tools,
                    model=graph_request.model,
                )
                for hook in graph_request.prepare_step_hooks:
                    try:
                        if inspect.iscoroutinefunction(hook):
                            result = await hook(ctx)
                        else:
                            result = hook(ctx)

                        if isinstance(result, PrepareStepResult):
                            if result.stop:
                                logger.info(f"[{trace_id}] prepareStep 钩子请求终止循环 (step={step_counter['count']})")
                                return {"messages": [AIMessage(content=result.metadata.get("stop_message", "任务已被 prepareStep 钩子终止"))]}
                            if result.messages is not None:
                                messages = result.messages
                            if result.tools is not None:
                                current_tools = result.tools
                            if result.additional_system_prompt is not None:
                                extra_system_prompt_override = result.additional_system_prompt
                            ctx.metadata.update(result.metadata)
                    except Exception as e:
                        logger.warning(f"[{trace_id}] prepareStep 钩子执行失败: {e}")

            if extra_system_prompt_override is not None:
                step_system_prompt = TemplateLoader.render_template(
                    "prompts/graph/react_agent_system_message",
                    {
                        "user_system_message": graph_request.system_message_prompt,
                        "additional_system_prompt": extra_system_prompt_override,
                        "dynamic_tool_instruction": dynamic_tool_instruction,
                        "has_approval_tool": approval_tool_instance is not None,
                    },
                )
                if messages and isinstance(messages[0], SystemMessage):
                    messages = [SystemMessage(content=step_system_prompt)] + list(messages[1:])
                else:
                    messages = [SystemMessage(content=step_system_prompt)] + list(messages)

            # ========== 循环内反思：检测连续失败或重复调用 ==========
            reflection_cfg = graph_request.reflection_config
            if reflection_cfg.enabled and step_counter["count"] > 1:
                trigger_reflection = False
                reflection_reason = ""

                # 条件 1: 连续失败超过阈值
                if reflection_tracker["consecutive_failures"] >= reflection_cfg.consecutive_failures_threshold:
                    trigger_reflection = True
                    reflection_reason = f"连续 {reflection_tracker['consecutive_failures']} 次工具调用失败"

                # 条件 2: 重复调用检测
                if not trigger_reflection:
                    history = reflection_tracker["tool_call_history"]
                    window = history[-reflection_cfg.repetition_window :] if len(history) >= reflection_cfg.repetition_window else history
                    if window:
                        counts = Counter(window)
                        most_common_name, most_common_count = counts.most_common(1)[0]
                        if most_common_count >= reflection_cfg.repetition_threshold:
                            trigger_reflection = True
                            reflection_reason = f"工具 '{most_common_name}' 在最近 {len(window)} 次调用中被重复调用 {most_common_count} 次"

                if trigger_reflection:
                    reflection_prompt = TemplateLoader.render_template(
                        "prompts/graph/reflection_prompt",
                        {"reason": reflection_reason, "step_number": step_counter["count"]},
                    )
                    messages = list(messages) + [HumanMessage(content=reflection_prompt)]
                    logger.info(f"[{trace_id}] 触发循环内反思 (step={step_counter['count']}): {reflection_reason}")
                    # 重置追踪器，给 agent 一次"重新来过"的机会
                    reflection_tracker["consecutive_failures"] = 0
                    reflection_tracker["tool_call_history"] = []

            # ========== Token 预算软阈值：注入 wrap-up 提示 ==========
            if (
                graph_request.max_tokens_budget > 0
                and graph_request.soft_budget_ratio < 1.0
                and token_counter["total"] >= graph_request.max_tokens_budget * graph_request.soft_budget_ratio
                and token_counter["total"] < graph_request.max_tokens_budget
            ):
                used_pct = int(token_counter["total"] / graph_request.max_tokens_budget * 100)
                wrapup_prompt = TemplateLoader.render_template(
                    "prompts/graph/budget_wrapup_prompt",
                    {
                        "step_number": step_counter["count"],
                        "used_percent": used_pct,
                        "used_tokens": token_counter["total"],
                        "total_budget": graph_request.max_tokens_budget,
                    },
                )
                messages = list(messages) + [HumanMessage(content=wrapup_prompt)]
                logger.info(f"[{trace_id}] Token 预算软阈值触发 wrap-up (step={step_counter['count']}, {used_pct}%)")

            # ========== 选择后续行预处理：检测 request_user_choice 结果并注入提示 ==========
            # 策略：检查最近一条 AIMessage 是否调用了 request_user_choice。
            # 如果是，说明当前步骤紧跟用户选择，需要强制 LLM 继续调用工具。
            _has_pending_choice = False
            if choice_tool_instance:
                for _rmsg in reversed(messages):
                    _msg_type = getattr(_rmsg, "type", "")
                    if _msg_type == "ai":
                        _tool_calls = getattr(_rmsg, "tool_calls", []) or []
                        for _tc in _tool_calls:
                            if isinstance(_tc, dict) and _tc.get("name") == "request_user_choice":
                                _has_pending_choice = True
                        break  # 只检查最近一条 AIMessage

                if _has_pending_choice:
                    messages = list(messages) + [SystemMessage(content="[系统] 用户已完成选择，请基于选择结果调用下一个工具继续执行任务。")]
                    logger.info(f"[{trace_id}] agent_node: 最近 AIMessage 调用了 request_user_choice，" f"注入续行提示 (step={step_counter['count']})")

            # 获取 LLM 并绑定工具
            llm = get_llm_client(graph_request)
            if current_tools:
                # toolChoice 控制
                tool_choice_cfg = getattr(graph_request, "tool_choice_config", None)
                bind_kwargs = {}

                # 动态模式下，如果尚未激活任何工具，强制 LLM 必须调用 activate_tools
                # 但如果上一条消息是审批工具的拒绝结果，不强制（允许 LLM 直接回复用户）
                if dynamic_mode and not active_tools_ref:
                    last_msg = messages[-1] if messages else None
                    last_is_approval_reject = (
                        last_msg is not None and hasattr(last_msg, "content") and isinstance(last_msg.content, str) and "操作被拒绝" in last_msg.content
                    )
                    if not last_is_approval_reject:
                        bind_kwargs["tool_choice"] = "any"
                        logger.info(f"[{trace_id}] 动态模式: 尚未激活工具，强制 tool_choice='any' 以触发 activate_tools")
                elif tool_choice_cfg and tool_choice_cfg.mode != "auto":
                    # 检查是否在生效步骤范围内
                    in_scope = tool_choice_cfg.apply_on_steps is None or step_counter["count"] in tool_choice_cfg.apply_on_steps
                    if in_scope:
                        if tool_choice_cfg.mode == "none":
                            bind_kwargs["tool_choice"] = "none"
                        elif tool_choice_cfg.mode == "any":
                            bind_kwargs["tool_choice"] = "any"
                        elif tool_choice_cfg.mode == "specific" and tool_choice_cfg.tool_name:
                            bind_kwargs["tool_choice"] = tool_choice_cfg.tool_name
                # 选择后续行：用户刚完成 request_user_choice，强制 LLM 必须调用工具
                if _has_pending_choice and "tool_choice" not in bind_kwargs:
                    bind_kwargs["tool_choice"] = "any"
                    logger.info(f"[{trace_id}] 选择后续行: 用户刚完成 request_user_choice，" f"强制 tool_choice='any' (step={step_counter['count']})")
                
                # Thinking 模式兼容性处理：
                # DeepSeek V4 和 Qwen 在 thinking 模式下只支持 tool_choice="auto" 或 "none"，
                # 不支持 "any"/"required"/specific tool。检测 thinking 模式并转换。
                if bind_kwargs.get("tool_choice") in ("any", "required"):
                    extra_body = getattr(llm, 'extra_body', None) or {}
                    # DeepSeek: extra_body.thinking.type == "enabled"
                    # Qwen: extra_body.enable_thinking == True
                    deepseek_thinking = extra_body.get("thinking", {}).get("type") == "enabled"
                    qwen_thinking = extra_body.get("enable_thinking") is True
                    is_thinking_enabled = deepseek_thinking or qwen_thinking
                    if is_thinking_enabled:
                        bind_kwargs["tool_choice"] = "auto"

                llm_with_tools = llm.bind_tools(current_tools, **bind_kwargs)
            else:
                llm_with_tools = llm

            # 规范化消息列表，确保兼容 Qwen 等对消息顺序有严格要求的模型
            messages = normalize_messages_for_llm(messages)

            # 调用 LLM（带超时保护）
            try:
                llm_timeout = timeout_cfg.llm_timeout_seconds if (timeout_cfg.enabled and timeout_cfg.llm_timeout_seconds > 0) else None
                if llm_timeout:
                    response = await asyncio.wait_for(llm_with_tools.ainvoke(messages), timeout=llm_timeout)
                else:
                    response = await llm_with_tools.ainvoke(messages)
            except asyncio.TimeoutError:
                logger.warning(f"[{trace_id}] ReAct agent_node LLM 调用超时 ({timeout_cfg.llm_timeout_seconds}s)")
                return {"messages": [AIMessage(content=f"LLM 调用超时（{timeout_cfg.llm_timeout_seconds}s），请稍后重试或简化问题。")]}
            except Exception as e:
                logger.exception(f"[{trace_id}] ReAct agent_node 调用 LLM 异常: {e}")
                raise

            if response is None:
                logger.warning(f"[{trace_id}] ReAct agent_node 收到空响应: response=None")
                return {"messages": []}

            tool_calls = getattr(response, "tool_calls", None) or []

            # ========== done tool 拦截：在 agent_node 中直接处理，避免进入 tools_node ==========
            if done_tool_name and tool_calls:
                for tc in tool_calls:
                    if tc.get("name") == done_tool_name:
                        done_result = tc.get("args", {}).get("result", "")
                        try:
                            parsed = json.loads(done_result) if isinstance(done_result, str) else done_result
                        except (ValueError, TypeError):
                            parsed = done_result
                        structured_output = json.dumps(parsed, ensure_ascii=False) if not isinstance(parsed, str) else parsed
                        logger.info(f"[{trace_id}] agent_node 检测到 done tool 调用，返回结构化结果, " f"result_preview={str(structured_output)[:200]!r}")
                        # 返回无 tool_calls 的 AIMessage，should_continue 会自然终止
                        _emit_step_progress(graph_request.max_steps, "completed", description="任务完成（done tool）")
                        return {"messages": [AIMessage(content=structured_output)]}

            # 累计 token 统计
            usage_metadata = getattr(response, "usage_metadata", None) or {}
            if isinstance(usage_metadata, dict):
                token_counter["total"] += usage_metadata.get("total_tokens", 0)

            logger.info(
                f"[{trace_id}] ReAct agent_node 返回: message_type={type(response).__name__}, "
                f"tool_call_count={len(tool_calls)}, content_preview={_safe_log_preview(str(getattr(response, 'content', '')))!r}"
            )

            if tool_calls:
                logger.info(f"[{trace_id}] ReAct agent_node tool_calls: {tool_calls}")
                # 重置续行标记
                choice_continuation["retried_at_step"] = -1
            else:
                # ========== 选择后强制续行（安全网）==========
                # 正常情况下，预调用阶段的 tool_choice="any" 已强制 LLM 调用工具。
                # 此处作为二次保底：若仍无 tool_calls 且刚执行过 request_user_choice，再重试一次。
                current_step = step_counter["count"]
                already_retried = choice_continuation["retried_at_step"] == current_step

                if _has_pending_choice and not already_retried:
                    choice_continuation["retried_at_step"] = current_step
                    nudge_msg = SystemMessage(content="[系统] 用户已完成选择，请根据选择结果调用下一个工具继续执行。")
                    logger.info(f"[{trace_id}] agent_node: request_user_choice 后 LLM 未调用工具（预调用 tool_choice=any 未生效），" f"二次重试 (step={current_step})")
                    retry_messages = list(messages) + [response, nudge_msg]
                    try:
                        # Thinking 模式兼容：检测并转换 tool_choice
                        retry_tool_choice = "any"
                        extra_body = getattr(llm, 'extra_body', None) or {}
                        # DeepSeek: extra_body.thinking.type == "enabled"
                        # Qwen: extra_body.enable_thinking == True
                        deepseek_thinking = extra_body.get("thinking", {}).get("type") == "enabled"
                        qwen_thinking = extra_body.get("enable_thinking") is True
                        if deepseek_thinking or qwen_thinking:
                            retry_tool_choice = "auto"
                            logger.info(f"[{trace_id}] 二次重试: Thinking 模式，tool_choice 'any' -> 'auto'")
                        
                        forced_llm = llm.bind_tools(current_tools, tool_choice=retry_tool_choice)
                        if llm_timeout:
                            response = await asyncio.wait_for(forced_llm.ainvoke(retry_messages), timeout=llm_timeout)
                        else:
                            response = await forced_llm.ainvoke(retry_messages)
                        tool_calls = getattr(response, "tool_calls", None) or []
                        if tool_calls:
                            logger.info(f"[{trace_id}] agent_node: 续行二次重试成功，tool_calls: {tool_calls}")
                            return {"messages": [nudge_msg, response]}
                        else:
                            logger.warning(f"[{trace_id}] agent_node: 续行二次重试后仍无 tool_calls")
                    except Exception as e:
                        logger.warning(f"[{trace_id}] agent_node: 续行二次重试失败: {e}")

                # LLM 未调用工具 → 循环即将自然结束
                _emit_step_progress(graph_request.max_steps, "completed", description="任务完成")

            return {"messages": [response]}

        # ========== 工具节点：执行工具调用 ==========
        # 工具节点必须包含全量工具（因为激活后的工具都可能被调用）
        if dynamic_mode:
            all_tools_for_node = list(self.all_tools) + ([meta_tool] if meta_tool else [])
        else:
            all_tools_for_node = list(tools)
        # done tool 也加入 ToolNode（虽然 should_continue 会拦截，但保持一致性）
        if done_tool_instance:
            all_tools_for_node = all_tools_for_node + [done_tool_instance]
        # 审批工具加入 ToolNode
        if approval_tool_instance:
            all_tools_for_node = all_tools_for_node + [approval_tool_instance]
        # 选择工具加入 ToolNode
        if choice_tool_instance:
            all_tools_for_node = all_tools_for_node + [choice_tool_instance]
        tool_node = tools_node if tools_node else ToolNode(all_tools_for_node, handle_tool_errors=True)

        async def logged_tool_node(state: Dict[str, Any], config: RunnableConfig) -> Dict[str, Any]:
            """带日志和自适应重试的工具节点包装器。"""
            trace_id = config["configurable"].get("trace_id", "unknown")
            graph_request = config["configurable"]["graph_request"]
            retry_cfg = graph_request.retry_config

            messages = state.get("messages", [])
            last_message = messages[-1] if messages else None
            tool_calls = getattr(last_message, "tool_calls", None) or []
            logger.info(f"[{trace_id}] ReAct tools_node 开始执行, tool_call_count={len(tool_calls)}, tool_calls={tool_calls}")

            # ========== 中断检查：工具执行前检查是否被请求中断 ==========
            execution_id = config["configurable"].get("execution_id", "")
            if execution_id and await is_interrupt_requested_async(execution_id):
                logger.info(f"[{trace_id}] logged_tool_node 检测到中断请求，跳过工具执行")
                # 返回空 ToolMessage 以满足 LangGraph 对 tool_call_id 配对的要求
                interrupted_msgs = []
                for tc in tool_calls:
                    tc_id = tc.get("id", "") if isinstance(tc, dict) else getattr(tc, "id", "")
                    interrupted_msgs.append(ToolMessage(content="[执行已中断]", tool_call_id=tc_id))
                return {"messages": interrupted_msgs}

            # ========== 操作前快照（回滚用）==========
            rollback_cfg = graph_request.rollback_config
            snapshots: Dict[str, str] = {}  # tool_call_id -> snapshot_result
            rollback_specs: Dict[str, Any] = {}  # tool_call_id -> ToolRollbackSpec
            if rollback_cfg.enabled and tool_calls:
                all_tools_for_snapshot = list(self.tools) + (list(self.all_tools) if hasattr(self, "all_tools") else [])
                for tc in tool_calls:
                    tc_id = tc.get("id", "") if isinstance(tc, dict) else getattr(tc, "id", "")
                    tc_name = tc.get("name", "") if isinstance(tc, dict) else getattr(tc, "name", "")
                    tc_args = tc.get("args", {}) if isinstance(tc, dict) else getattr(tc, "args", {})

                    # 查找工具实例
                    tool_inst = None
                    for t in all_tools_for_snapshot:
                        if getattr(t, "name", "") == tc_name:
                            tool_inst = t
                            break

                    rb_spec = get_rollback_spec(tc_name, tool_inst, rollback_cfg)
                    if rb_spec and rb_spec.strategy != "none":
                        rollback_specs[tc_id] = rb_spec
                        snapshot = await take_snapshot(
                            spec=rb_spec,
                            action_tool_name=tc_name,
                            action_tool_args=tc_args,
                            available_tools=all_tools_for_snapshot,
                            runnable_config=config,
                        )
                        if snapshot:
                            snapshots[tc_id] = snapshot
                            logger.info(f"[{trace_id}] 快照完成: tool={tc_name}, tc_id={tc_id}")

            # ========== 工具执行（带单步超时保护）==========
            timeout_cfg = graph_request.timeout_config
            step_timeout = timeout_cfg.step_timeout_seconds if (timeout_cfg.enabled and timeout_cfg.step_timeout_seconds > 0) else None

            # 发射工具执行开始事件
            tool_names = [tc.get("name", "") if isinstance(tc, dict) else getattr(tc, "name", "") for tc in tool_calls]
            _emit_step_progress(
                graph_request.max_steps,
                "tool_executing",
                description=f"执行工具: {', '.join(tool_names)}",
                tool_name=tool_names[0] if tool_names else None,
            )

            try:
                if step_timeout:
                    result = await asyncio.wait_for(tool_node.ainvoke(state, config=config), timeout=step_timeout)
                else:
                    result = await tool_node.ainvoke(state, config=config)
            except asyncio.TimeoutError:
                logger.warning(f"[{trace_id}] logged_tool_node 工具执行超时 ({step_timeout}s)")
                # 返回超时错误 ToolMessage
                timeout_msgs = []
                for tc in tool_calls:
                    tc_id = tc.get("id", "") if isinstance(tc, dict) else getattr(tc, "id", "")
                    timeout_msgs.append(ToolMessage(content=f"Error: 工具执行超时 ({step_timeout}s)", tool_call_id=tc_id))
                return {"messages": timeout_msgs}
            result_messages = result.get("messages", []) if isinstance(result, dict) else []

            # ========== 自适应重试：检测工具错误并重试 ==========
            if retry_cfg.enabled and result_messages:
                retried_any = False
                for idx, msg in enumerate(result_messages):
                    if not isinstance(msg, ToolMessage):
                        continue
                    content_str = str(getattr(msg, "content", ""))
                    # 检查是否为错误响应（ToolNode handle_tool_errors 将异常写入 content）
                    is_error = content_str.startswith("Error:") or content_str.startswith("Traceback")
                    if not is_error:
                        # 关键词匹配仅对短内容生效（长内容通常是正常工具结果，可能误匹配）
                        if len(content_str) < 500:
                            content_lower = content_str.lower()
                            is_error = any(kw in content_lower for kw in retry_cfg.retry_on_error_keywords)
                    # 跳过 meta-tool（activate_tools）的重试
                    if is_error and meta_tool:
                        tool_call_id = getattr(msg, "tool_call_id", "")
                        # 检查该 tool_call_id 对应的是否为 activate_tools
                        for tc in tool_calls:
                            tc_id = tc.get("id", "") if isinstance(tc, dict) else getattr(tc, "id", "")
                            tc_name = tc.get("name", "") if isinstance(tc, dict) else getattr(tc, "name", "")
                            if tc_id == tool_call_id and tc_name == meta_tool.name:
                                is_error = False
                                break
                    # 跳过审批工具的重试
                    if is_error and approval_tool_instance:
                        tool_call_id = getattr(msg, "tool_call_id", "")
                        for tc in tool_calls:
                            tc_id = tc.get("id", "") if isinstance(tc, dict) else getattr(tc, "id", "")
                            tc_name = tc.get("name", "") if isinstance(tc, dict) else getattr(tc, "name", "")
                            if tc_id == tool_call_id and tc_name == "request_human_approval":
                                is_error = False
                                break

                    if is_error and retry_cfg.max_retries_per_tool > 0:
                        tool_call_id = getattr(msg, "tool_call_id", "")
                        for attempt in range(1, retry_cfg.max_retries_per_tool + 1):
                            wait_time = retry_cfg.backoff_seconds * (2 ** (attempt - 1))
                            logger.info(
                                f"[{trace_id}] 工具重试 (attempt={attempt}/{retry_cfg.max_retries_per_tool}, "
                                f"tool_call_id={tool_call_id}, wait={wait_time}s): {content_str[:100]}"
                            )
                            await asyncio.sleep(wait_time)

                            retry_result = await tool_node.ainvoke(state, config=config)
                            retry_messages = retry_result.get("messages", []) if isinstance(retry_result, dict) else []

                            # 找到对应 tool_call_id 的结果
                            retry_msg = None
                            for rm in retry_messages:
                                if isinstance(rm, ToolMessage) and getattr(rm, "tool_call_id", "") == tool_call_id:
                                    retry_msg = rm
                                    break

                            if retry_msg:
                                retry_content = str(getattr(retry_msg, "content", ""))
                                retry_is_error = retry_content.startswith("Error:") or retry_content.startswith("Traceback")
                                if not retry_is_error:
                                    retry_content_lower = retry_content.lower()
                                    retry_is_error = any(kw in retry_content_lower for kw in retry_cfg.retry_on_error_keywords)

                                if not retry_is_error:
                                    # 重试成功，替换结果
                                    result_messages[idx] = retry_msg
                                    retried_any = True
                                    logger.info(f"[{trace_id}] 工具重试成功 (attempt={attempt}, tool_call_id={tool_call_id})")
                                    break
                        else:
                            logger.warning(f"[{trace_id}] 工具重试耗尽 (tool_call_id={tool_call_id})，保留原始错误")

                if retried_any:
                    result = {"messages": result_messages}

            # ========== 反思追踪：记录工具执行结果 ==========
            has_failure = False
            for msg in result_messages:
                if isinstance(msg, ToolMessage):
                    content_str = str(getattr(msg, "content", ""))
                    is_error = content_str.startswith("Error:") or content_str.startswith("Traceback")
                    if not is_error:
                        content_lower = content_str.lower()
                        is_error = any(kw in content_lower for kw in ["error", "failed", "exception"])
                    if is_error:
                        has_failure = True

            if has_failure:
                reflection_tracker["consecutive_failures"] += 1
            else:
                reflection_tracker["consecutive_failures"] = 0

            # 记录工具调用名称
            for tc in tool_calls:
                if isinstance(tc, dict):
                    reflection_tracker["tool_call_history"].append(tc.get("name", ""))
                else:
                    reflection_tracker["tool_call_history"].append(getattr(tc, "name", ""))

            logger.info(
                f"[{trace_id}] ReAct tools_node 执行结束, result_message_count={len(result_messages)}, "
                f"result_types={[type(msg).__name__ for msg in result_messages]}"
            )

            # ========== 构建 tool_call 信息映射（验证和回滚共用）==========
            tc_info_map = {}
            for tc in tool_calls:
                tc_id = tc.get("id", "") if isinstance(tc, dict) else getattr(tc, "id", "")
                tc_name = tc.get("name", "") if isinstance(tc, dict) else getattr(tc, "name", "")
                tc_args = tc.get("args", {}) if isinstance(tc, dict) else getattr(tc, "args", {})
                tc_info_map[tc_id] = (tc_name, tc_args)

            all_available_tools = list(self.tools) + (list(self.all_tools) if hasattr(self, "all_tools") else [])

            # ========== 执行后验证 ==========
            verify_cfg = graph_request.verification_config
            if verify_cfg.enabled and result_messages:
                verification_msgs = []
                for msg in result_messages:
                    if not isinstance(msg, ToolMessage):
                        continue
                    tc_id = getattr(msg, "tool_call_id", "")
                    if tc_id not in tc_info_map:
                        continue

                    tc_name, tc_args = tc_info_map[tc_id]
                    content_str = str(getattr(msg, "content", ""))

                    # 跳过错误结果（不验证失败的工具调用）
                    is_error = content_str.startswith("Error:") or content_str.startswith("Traceback")
                    if is_error:
                        continue

                    # 查找工具实例
                    tool_instance = None
                    for t in all_available_tools:
                        if getattr(t, "name", "") == tc_name:
                            tool_instance = t
                            break

                    # 获取验证规格
                    spec = get_verification_spec(tc_name, tool_instance, verify_cfg)
                    if not spec:
                        continue

                    logger.info(f"[{trace_id}] 触发执行后验证: action={tc_name}, verify={spec.verify_tool}")

                    # 发射验证事件
                    try:
                        dispatch_custom_event(
                            "verification_started",
                            {
                                "action_tool": tc_name,
                                "verify_tool": spec.verify_tool,
                                "description": spec.description,
                            },
                        )
                    except Exception:
                        pass

                    # 执行验证
                    verify_result = await run_verification(
                        spec=spec,
                        action_tool_name=tc_name,
                        action_tool_args=tc_args,
                        action_tool_result=content_str,
                        available_tools=all_available_tools,
                        config=verify_cfg,
                        runnable_config=config,
                    )

                    # 构建验证结果 ToolMessage（追加到结果中让 LLM 看到）
                    verify_content = (
                        f"[执行后验证] 操作: {tc_name}\n"
                        f"验证工具: {verify_result['verify_tool']}\n"
                        f"验证说明: {spec.description}\n"
                        f"验证结果:\n{verify_result['verify_result']}\n"
                        f"请根据以上验证结果判断操作 {tc_name} 是否真正生效。"
                    )
                    # 使用相同的 tool_call_id 不行（会冲突），需要让 LLM 通过上下文关联
                    # 改为追加为 HumanMessage 或 SystemMessage（不是 ToolMessage）
                    verification_msgs.append(SystemMessage(content=verify_content))

                    try:
                        dispatch_custom_event(
                            "verification_completed",
                            {
                                "action_tool": tc_name,
                                "verify_tool": verify_result["verify_tool"],
                                "attempts": verify_result["attempts"],
                                "verify_result_preview": str(verify_result["verify_result"])[:500],
                            },
                        )
                    except Exception:
                        pass

                if verification_msgs:
                    result_messages = result.get("messages", []) if isinstance(result, dict) else []
                    result_messages.extend(verification_msgs)
                    result = {"messages": result_messages}

            # ========== 操作回滚（验证失败时触发）==========
            if rollback_cfg.enabled and rollback_specs:
                rollback_msgs = []

                for tc_id, rb_spec in rollback_specs.items():
                    if tc_id not in tc_info_map:
                        continue
                    tc_name, tc_args = tc_info_map[tc_id]
                    snapshot = snapshots.get(tc_id)

                    # 构建回滚上下文 SystemMessage（始终注入，让 LLM 知道可以回滚）
                    if rb_spec.strategy == "auto" and rollback_cfg.auto_rollback_on_verify_fail:
                        # 自动回滚：直接执行
                        logger.info(f"[{trace_id}] 自动回滚触发: action={tc_name}, strategy=auto")

                        try:
                            dispatch_custom_event(
                                "rollback_started",
                                {
                                    "action_tool": tc_name,
                                    "rollback_tool": rb_spec.rollback_tool,
                                    "strategy": "auto",
                                },
                            )
                        except Exception:
                            pass

                        rb_result = await execute_rollback(
                            spec=rb_spec,
                            action_tool_name=tc_name,
                            action_tool_args=tc_args,
                            snapshot_result=snapshot,
                            available_tools=all_available_tools,
                            runnable_config=config,
                        )

                        rb_content = (
                            f"[操作回滚] 操作: {tc_name}\n"
                            f"回滚工具: {rb_result['rollback_tool'] or 'N/A'}\n"
                            f"回滚结果: {'成功' if rb_result['rolled_back'] else '失败'}\n"
                            f"详情:\n{rb_result['rollback_result'][:1000]}\n"
                        )
                        rollback_msgs.append(SystemMessage(content=rb_content))

                        try:
                            dispatch_custom_event(
                                "rollback_completed",
                                {
                                    "action_tool": tc_name,
                                    "rollback_tool": rb_result["rollback_tool"],
                                    "rolled_back": rb_result["rolled_back"],
                                    "strategy": "auto",
                                },
                            )
                        except Exception:
                            pass

                    elif rb_spec.strategy == "prompt":
                        # 提示模式：注入上下文让 LLM 决定是否回滚
                        prompt_content = f"[回滚可用] 操作: {tc_name}\n" f"如果上述验证结果表明操作未生效或产生了负面影响，你可以执行回滚。\n"
                        if rb_spec.rollback_tool:
                            prompt_content += f"回滚工具: {rb_spec.rollback_tool}\n"
                        if snapshot:
                            prompt_content += f"操作前快照:\n{snapshot[:800]}\n"
                        if rb_spec.description:
                            prompt_content += f"说明: {rb_spec.description}\n"
                        rollback_msgs.append(SystemMessage(content=prompt_content))

                if rollback_msgs:
                    result_messages = result.get("messages", []) if isinstance(result, dict) else []
                    result_messages.extend(rollback_msgs)
                    result = {"messages": result_messages}

            return result

        # ========== 条件函数：判断是否继续调用工具 ==========
        def should_continue(state: Dict[str, Any], config: RunnableConfig) -> str:
            """判断是否需要继续执行工具调用（支持可配置停止条件链）"""
            messages = state.get("messages", [])
            if not messages:
                return "end"

            last_message = messages[-1]

            # 如果 LLM 没有发起工具调用，自然结束
            if not (hasattr(last_message, "tool_calls") and last_message.tool_calls):
                logger.info(
                    "ReAct should_continue: 未检测到 tool_calls，结束循环, "
                    f"last_message_type={type(last_message).__name__}, content_preview={_safe_log_preview(str(getattr(last_message, 'content', '')))!r}"
                )
                return "end"

            # ========== stopWhen 条件链评估 ==========
            graph_request = config["configurable"]["graph_request"]

            # 内置条件 1: 最大步数
            if graph_request.max_steps > 0 and step_counter["count"] >= graph_request.max_steps:
                logger.warning(f"ReAct should_continue: 达到最大步数限制 ({step_counter['count']}/{graph_request.max_steps})，强制终止")
                return "end"

            # 内置条件 2: token 预算
            if graph_request.max_tokens_budget > 0 and token_counter["total"] >= graph_request.max_tokens_budget:
                logger.warning(f"ReAct should_continue: 达到 token 预算上限 ({token_counter['total']}/{graph_request.max_tokens_budget})，强制终止")
                return "end"

            # 自定义条件链
            if graph_request.stop_when_conditions:
                ctx = StopConditionContext(
                    step_number=step_counter["count"],
                    total_tokens=token_counter["total"],
                    messages=messages,
                    last_tool_calls=getattr(last_message, "tool_calls", []),
                )
                for condition in graph_request.stop_when_conditions:
                    try:
                        result = condition(ctx)
                        if isinstance(result, StopConditionResult) and result.should_stop:
                            logger.warning(f"ReAct should_continue: 自定义条件触发停止 — {result.reason}")
                            return "end"
                    except Exception as e:
                        logger.warning(f"ReAct should_continue: 自定义条件执行失败: {e}")

            logger.info(f"ReAct should_continue: 检测到 tool_calls，进入 tools 节点 (step={step_counter['count']}): {last_message.tool_calls}")
            return "continue"

        # ========== Wrapper 节点：入口点，兼容现有 API ==========
        async def wrapper_node(state: Dict[str, Any], config: RunnableConfig) -> Dict[str, Any]:
            """Wrapper 节点 - 入口点，直接透传状态"""
            # 不做任何处理，只是作为入口点
            return {}

        # ========== 添加节点到图 ==========
        graph_builder.add_node(wrapper_node_name, wrapper_node)
        graph_builder.add_node(agent_node_name, agent_node)
        graph_builder.add_node(tools_node_name, logged_tool_node)

        # ========== 添加边 ==========
        # wrapper -> agent
        graph_builder.add_edge(wrapper_node_name, agent_node_name)

        # agent -> 条件边 (tools 或 next_node)
        # 当 ReAct 循环完成时，转到 next_node（可以是 END 或其他节点）
        graph_builder.add_conditional_edges(
            agent_node_name,
            should_continue,
            {
                "continue": tools_node_name,
                "end": next_node,  # 使用传入的 next_node 而不是硬编码 END
            },
        )

        # tools -> agent (循环)
        graph_builder.add_edge(tools_node_name, agent_node_name)

        logger.debug(f"构建 ReAct 节点组合完成: {wrapper_node_name} -> {agent_node_name} <-> {tools_node_name} -> {next_node}")

        return wrapper_node_name

    async def invoke_react_for_candidate(
        self, user_message: str, messages: List[BaseMessage], config: RunnableConfig, system_prompt: str
    ) -> AIMessage:
        """通用的 ReAct 候选生成方法

        Args:
            user_message: 用户消息
            messages: 上下文消息列表
            config: 运行配置
            system_prompt: 系统提示词

        Returns:
            生成的 AI 消息
        """
        try:
            # 创建临时状态图来使用可复用的 ReAct 节点组合
            temp_graph_builder = StateGraph(dict)

            # 使用可复用的 ReAct 节点组合构建图
            react_entry_node = await self.build_react_nodes(
                graph_builder=temp_graph_builder, composite_node_name="temp_react_candidate", additional_system_prompt=system_prompt, next_node=END
            )

            # 设置起始节点
            # 注意：不需要额外添加 wrapper → END 的边，因为 build_react_nodes
            # 已经通过 next_node 参数设置了 ReAct 循环结束后的去向
            temp_graph_builder.set_entry_point(react_entry_node)

            # 编译临时图
            temp_graph = temp_graph_builder.compile()

            # 调用 ReAct 节点
            # result = await temp_graph.ainvoke({"messages": messages[-3:] if len(messages) > 3 else messages}, config=config)
            result = await temp_graph.ainvoke(
                {"messages": messages[-3:] if len(messages) > 3 else messages}, config={**config, "recursion_limit": 100}
            )

            # 提取最后的 AI 消息
            result_messages = result.get("messages", [])
            if isinstance(result_messages, list):
                for msg in reversed(result_messages):
                    if isinstance(msg, AIMessage):
                        return msg
            elif isinstance(result_messages, AIMessage):
                return result_messages

            # 如果没有找到 AI 消息，返回默认响应
            return AIMessage(content=f"正在分析问题: {user_message}")

        except Exception as e:
            logger.warning("ReAct 调用失败: %r，使用降级方案", e)
            return AIMessage(content=f"正在重新分析这个问题: {user_message}，寻找更好的解决方案...", tool_calls=[])

    def _get_current_tools(self, tools_node: Optional[ToolNode]) -> list:
        """获取当前可用的工具列表"""
        if tools_node and hasattr(tools_node, "tools"):
            return tools_node.tools
        return self.tools

    # ========== 使用 DeepAgent 实现 ==========

    async def build_deepagent_nodes(
        self,
        graph_builder: StateGraph,
        composite_node_name: str = "deep_agent",
        additional_system_prompt: Optional[str] = None,
        next_node: str = END,
        tools_node: Optional[ToolNode] = None,
    ) -> str:
        """构建DeepAgent节点

        DeepAgent 自动提供规划、文件系统工具和子代理能力

        Args:
            graph_builder: StateGraph实例
            composite_node_name: 组合节点名称前缀
            additional_system_prompt: 附加系统提示词
            next_node: 下一个节点名称
            tools_node: 可选的工具节点

        Returns:
            DeepAgent包装节点名称
        """
        deep_wrapper_name = f"{composite_node_name}_wrapper"

        async def deep_wrapper_node(state: Dict[str, Any], config: RunnableConfig) -> Dict[str, Any]:
            """DeepAgent 包装节点 - 返回完整消息列表以支持实时 SSE 流式输出"""
            graph_request = config["configurable"]["graph_request"]

            # 创建系统提示
            final_system_prompt = TemplateLoader.render_template(
                "prompts/graph/deepagent_system_message",
                {"user_system_message": graph_request.system_message_prompt, "additional_system_prompt": additional_system_prompt or ""},
            )

            llm = self.get_llm_client(graph_request)

            # 创建 DeepAgent (自动包含规划、文件系统工具和子代理能力)
            deep_agent = create_deep_agent(model=llm, tools=self.tools, system_prompt=final_system_prompt, debug=True)

            # DeepAgent返回的是CompiledStateGraph,需要调用它
            # 增加递归限制以允许复杂任务完成
            deep_config = {**config, "recursion_limit": 100}  # DeepAgent 需要更高的递归限制

            result = await deep_agent.ainvoke({"messages": state["messages"]}, config=deep_config)

            # 获取完整的消息列表
            final_messages = result.get("messages", [])
            if not final_messages:
                return {"messages": [AIMessage(content="DeepAgent 未返回任何消息")]}

            # 过滤掉输入消息，只保留 DeepAgent 新增的消息
            input_message_count = len(state.get("messages", []))
            new_messages = final_messages[input_message_count:]

            if not new_messages:
                return {"messages": [AIMessage(content="DeepAgent 未产生新的响应")]}

            # 直接返回新消息列表，让 agui_stream 逐个处理
            # 这样可以实时发送：工具调用 -> 工具结果 -> 最终响应
            return {"messages": new_messages}

        graph_builder.add_node(deep_wrapper_name, deep_wrapper_node)
        return deep_wrapper_name
