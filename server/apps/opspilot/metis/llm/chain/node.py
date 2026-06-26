import asyncio
import hashlib
import inspect
import json
import time
import uuid
from collections import Counter
from datetime import datetime
from typing import Any, Dict, List, Optional
from urllib.parse import parse_qs, urlparse

import json_repair
from deepagents import create_deep_agent
from langchain_core.callbacks import dispatch_custom_event
from langchain_core.messages import AIMessage, BaseMessage, HumanMessage, SystemMessage, ToolMessage
from langchain_core.runnables import RunnableConfig
from langchain_core.tools import StructuredTool
from langchain_mcp_adapters.client import MultiServerMCPClient
from langgraph.constants import END
from langgraph.graph import StateGraph
from langgraph.prebuilt import ToolNode
from pydantic import BaseModel as PydanticBaseModel
from pydantic import Field as PydanticField

from apps.core.logger import opspilot_logger as logger
from apps.opspilot.metis.llm.chain.compaction import CompactionConfig, compact_messages
from apps.opspilot.metis.llm.chain.entity import (
    BasicLLMRequest,
    DoneToolConfig,
    ExtraConfig,
    PrepareStepContext,
    PrepareStepResult,
    StopConditionContext,
    StopConditionResult,
    normalize_tool_calls,
)

# ---------------------------------------------------------------------------
# Facade re-exports (structural refactor, no behavior change).
#
# The langchain-openai monkey-patches and the K8s config-analysis report
# helpers were moved into dedicated submodules. They are re-exported here so
# that every existing ``from ...chain.node import X`` (and every test that
# patches ``apps.opspilot.metis.llm.chain.node.X``) keeps resolving exactly as
# before. Importing ``lc_patches`` also applies the monkey-patches as an import
# side effect, preserving the original import-time patching behavior of node.py.
# ---------------------------------------------------------------------------
from apps.opspilot.metis.llm.chain.k8s_report_tools import (  # noqa: E402,F401
    _build_config_analysis_report_total,
    _build_config_analysis_scan_range,
    _build_config_analysis_scope,
    _config_analysis_benefit_description,
    _config_analysis_fix_description,
    _config_analysis_risk_description,
    build_a2ui_report_contract,
    build_config_diff_report_payload,
    build_config_analysis_report_markdown,
    build_config_analysis_report_payload,
    build_post_tool_directives,
    build_repair_mode_choice_args,
    downgrade_config_analysis_next_step_hint,
    find_pending_k8s_analysis_choice,
    should_emit_config_analysis_report,
)
from apps.opspilot.metis.llm.chain.k8s_tool_gate import is_k8s_agent  # noqa: E402,F401
from apps.opspilot.metis.llm.chain.lc_patches import (  # noqa: E402,F401
    _REASONING_FIELD_NAMES,
    _patched_convert_delta_to_message_chunk,
    _patched_convert_dict_to_message,
    _patched_convert_message_to_dict,
    _patched_create_chat_result,
)
from apps.opspilot.metis.llm.chain.message_trim import trim_messages
from apps.opspilot.metis.llm.common.anthropic_capabilities import build_anthropic_runtime_capabilities, normalize_tool_choice_for_capabilities
from apps.opspilot.metis.llm.common.llm_client_factory import LLMClientFactory
from apps.opspilot.metis.llm.common.structured_output_parser import StructuredOutputParser
from apps.opspilot.metis.llm.rag.graph_rag.graphiti.graphiti_rag import GraphitiRAG
from apps.opspilot.metis.llm.rag.naive_rag.pgvector.pgvector_rag import PgvectorRag
from apps.opspilot.metis.llm.tools.tools_loader import ToolsLoader
from apps.opspilot.metis.utils.template_loader import TemplateLoader
from apps.opspilot.services.approval import wait_for_approval
from apps.opspilot.utils.execution_interrupt import is_interrupt_requested_async
from apps.opspilot.utils.rollback import execute_rollback, get_rollback_spec, take_snapshot
from apps.opspilot.utils.user_choice import wait_for_choice
from apps.opspilot.utils.verification import get_verification_spec, run_verification


def _safe_log_preview(content: str, max_len: int = 200) -> str:
    """
    安全地截取日志预览内容。

    使用 UTF-8（由日志 handler 负责编码），保留 emoji 与全部 Unicode 字符，
    仅做长度截断。

    Args:
        content: 原始内容
        max_len: 最大长度

    Returns:
        安全的日志预览字符串
    """
    if not content:
        return ""
    return str(content)[:max_len]


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
            # _select_knowledge_ids 内部走同步阻塞的 LLM HTTP 调用（invoke_isolated），
            # 在 async 节点中直接调用会阻塞事件循环，放入线程池执行。
            selected_knowledge_ids = await asyncio.to_thread(self._select_knowledge_ids, config)

        rag_result = []
        all_img_docs = []  # 收集所有图片文档

        for rag_search_request in naive_rag_request:
            rag_search_request.search_query = config["configurable"]["graph_request"].graph_user_message

            if len(selected_knowledge_ids) != 0 and rag_search_request.index_name not in selected_knowledge_ids:
                logger.debug(f"智能知识路由判断:[{rag_search_request.index_name}]不适合当前问题,跳过检索")
                continue

            rag = PgvectorRag()
            # PgvectorRag().search 为同步阻塞的向量库查询，async 节点中放入线程池避免阻塞事件循环。
            naive_rag_search_result = await asyncio.to_thread(rag.search, rag_search_request)

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
        content_hash = hashlib.md5(relation_content.encode("utf-8")).hexdigest()[:8]

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
        content_hash = hashlib.md5(summary_content.encode("utf-8")).hexdigest()[:8]

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

    @staticmethod
    def _is_k8s_tool_server(tool_server) -> bool:
        tool_url = (getattr(tool_server, "url", "") or "").strip().lower()
        return tool_url in {
            "langchain:kubernetes",
            "langchain:kubernetes_data_collection",
        }

    def _should_apply_first_turn_greeting_filter(self, request) -> bool:
        tool_servers = list(getattr(request, "tools_servers", []) or [])
        if not tool_servers:
            return False

        return all((getattr(server, "url", "") or "").startswith("langchain:") and self._is_k8s_tool_server(server) for server in tool_servers)

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

    async def setup(self, request: PydanticBaseModel):
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

        # 多实例强制选择配置（由 chat_service 注入 extra_config）
        _ec = ExtraConfig.from_raw(getattr(request, "extra_config", None))
        self._require_choice_before_tools = _ec.require_choice_before_tools
        self._multi_instance_options = _ec.multi_instance_options
        self._skill_package_capabilities = set(_ec.skill_package_capabilities or [])
        if self._require_choice_before_tools:
            logger.info(f"多实例强制选择已启用, options={self._multi_instance_options}")

    def _has_skill_package_capability(self, capability: str) -> bool:
        return capability in getattr(self, "_skill_package_capabilities", set())

    def _enable_config_analysis_report(self) -> bool:
        return self._has_skill_package_capability("config_analysis_report")

    def _enable_repair_diff_report(self) -> bool:
        return self._has_skill_package_capability("repair_diff_report")

    def _filter_basic_k8s_analysis_loop_calls(self, tool_calls: list, analysis_cache: dict) -> tuple[list, bool]:
        if self._enable_config_analysis_report() or self._enable_repair_diff_report():
            return tool_calls, False
        if not analysis_cache.get("deployments"):
            return tool_calls, False

        loop_prone_tools = {
            "request_user_choice",
            "analyze_deployment_configurations",
            "kubernetes_troubleshooting_guide",
        }
        filtered = [tc for tc in tool_calls if tc.get("name") not in loop_prone_tools]
        return filtered, len(filtered) != len(tool_calls)

    @staticmethod
    def _build_basic_k8s_analysis_done_message(response: AIMessage, analysis_cache: dict) -> AIMessage:
        content = str(getattr(response, "content", "") or "").strip()
        if not content:
            analyzed_count = len(analysis_cache.get("deployments") or [])
            cluster_name = analysis_cache.get("cluster_name") or "Kubernetes"
            content = (
                f"已完成 {cluster_name} 的基础配置检查，已分析 {analyzed_count} 个工作负载。"
                "当前未启用 Kubernetes Specialist 技能包，因此不进入结构化报告、修复方式选择或修复对比流程。"
                "请根据上方基础检查结果处理；如需专家报告和修复对比，请启用对应技能包后再测试。"
            )
        return AIMessage(content=content)

    def _sanitize_duplicate_config_analysis_text(self, response: AIMessage, analysis_cache: dict) -> AIMessage:
        if not self._enable_config_analysis_report() or not analysis_cache.get("deployments"):
            return response
        content = str(getattr(response, "content", "") or "")
        duplicate_markers = (
            "配置检查报告",
            "High Severity",
            "Medium Severity",
            "Low Severity",
            "高危问题",
            "中危问题",
            "低危问题",
            "修复建议",
        )
        marker_hits = sum(1 for marker in duplicate_markers if marker in content)
        if marker_hits < 2:
            return response

        sanitized = AIMessage(
            content="配置检查报告已通过上方结构化卡片展示，请查看卡片中的统计、风险分组和建议。",
            tool_calls=getattr(response, "tool_calls", None) or [],
            id=getattr(response, "id", None),
        )
        try:
            sanitized.response_metadata = getattr(response, "response_metadata", {}) or {}
            sanitized.usage_metadata = getattr(response, "usage_metadata", None)
        except Exception:
            pass
        return sanitized

    @staticmethod
    def _normalize_repair_group_by(group_by: str) -> str:
        value = str(group_by or "").strip().lower()
        if value in {"category", "target", "all"}:
            return value
        if "工作负载" in value or "目标" in value or "target" in value:
            return "target"
        if "类别" in value or "问题" in value or "category" in value:
            return "category"
        if "全部" in value or "一次性" in value or "直接展示" in value or "single" in value or "all" in value:
            return "all"
        return "target"

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

        class DoneToolInput(PydanticBaseModel):
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

        class ApprovalToolInput(PydanticBaseModel):
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
            except Exception as e:
                logger.warning(f"[approval_tool] 发射 approval_request 事件失败: {e}")

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
        """构建 request_user_choice 工具，供 LLM 需要向用户提问时调用"""
        from typing import List, Literal, Optional

        from langchain_core.tools import StructuredTool
        from pydantic import BaseModel as PydanticBaseModel
        from pydantic import Field as PydanticField

        class AskUserInput(PydanticBaseModel):
            question: str = PydanticField(description="完整的一句问句，具体、引用用户原话或当前上下文里的关键词。脱离上下文用户也能看懂。")
            question_type: Literal["single_select", "multi_select", "confirm", "text"] = PydanticField(
                description="single_select=N选1; multi_select=N选若干; confirm=是/否; text=开放式输入"
            )
            options: Optional[List[str]] = PydanticField(
                default=None,
                description="single_select/multi_select 必填，2~4项，每项不超40字符。confirm/text 必须为 None。",
            )

        async def _ask_user(
            question: str,
            question_type: str,
            options: Optional[List[str]] = None,
        ) -> str:
            from apps.opspilot.metis.llm.tools.common.user_choice_guard import validate_user_choice_options
            from apps.opspilot.metis.llm.tools.kubernetes.user_choice_guard import build_kubernetes_cluster_choice_guard

            configurable = getattr(_ask_user, "_configurable", {}) or {}
            guard = build_kubernetes_cluster_choice_guard(
                question=question,
                options=options,
                configurable=configurable,
            )
            guard_message = validate_user_choice_options(
                question_type=question_type,
                options=options,
                guard=guard,
            )
            if guard_message:
                logger.warning("[choice_tool] 已阻止不可信的用户选择请求: %s", guard_message)
                return guard_message

            choice_id = str(uuid.uuid4())[:8]
            execution_id = getattr(_ask_user, "_execution_id", "") or str(int(time.time() * 1000))
            node_id = getattr(_ask_user, "_node_id", "skill_test")

            # Convert to internal options format based on question_type
            if question_type == "confirm":
                options_data = [
                    {"key": "yes", "label": "是", "description": "", "recommended": False},
                    {"key": "no", "label": "否", "description": "", "recommended": False},
                ]
                multiple = False
            elif question_type == "text":
                # Text mode: no predefined options, user types freely
                options_data = []
                multiple = False
            else:
                # single_select / multi_select
                options_data = [{"key": opt, "label": opt, "description": "", "recommended": False} for opt in (options or [])]
                multiple = question_type == "multi_select"

            effective_min_select = 1 if not multiple else 1
            effective_max_select = 1 if not multiple else len(options_data)
            default_keys = [options_data[0]["key"]] if options_data else []

            choice_request_data = {
                "execution_id": execution_id,
                "node_id": node_id,
                "choice_id": choice_id,
                "a2ui": build_a2ui_report_contract(
                    component="user-choice",
                    event_name="user_choice_request",
                    actions=[{"key": "submit_choice", "label": "提交选择"}],
                ),
                "title": question,
                "description": "",
                "options": options_data,
                "multiple": multiple,
                "min_select": effective_min_select,
                "max_select": effective_max_select,
                "timeout_seconds": 120,
                "default_keys": default_keys,
                "display_hint": "text" if question_type == "text" else "auto",
            }

            try:
                dispatch_custom_event("user_choice_request", choice_request_data)
            except Exception:
                pass

            logger.info(f"[choice_tool] 提问已发射: question={question[:50]}, " f"type={question_type}, id={choice_id}")

            result = await wait_for_choice(
                execution_id=execution_id,
                node_id=node_id,
                choice_id=choice_id,
                options=options_data,
                default_keys=default_keys,
                timeout_seconds=120,
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

            # Build response text for LLM
            if question_type == "text":
                # For text mode, selected[0] is the raw user input
                answer_text = selected[0] if selected else ""
            elif question_type == "confirm":
                answer_text = "是" if "yes" in selected else "否"
            else:
                # single/multi select - selected keys ARE the labels
                answer_text = ", ".join(selected)

            if source == "user":
                return f"用户回答: {answer_text}。请根据用户的回答继续执行下一步操作，不要停止。"
            else:
                return f"用户未在规定时间内回答，已使用默认选项: {answer_text}。请根据默认值继续操作。"

        choice_tool = StructuredTool.from_function(
            coroutine=_ask_user,
            name="request_user_choice",
            description=(
                "向用户提一个澄清问题或让用户从选项中做出选择。\n"
                "【强制】任何需要用户做选择的场景都必须调用此工具，严禁用纯文本列出选项让用户打字回复。\n"
                "在调用之前，先确认你已经做完了所有自己能做的探索。\n\n"
                "━━━ 应当调用的场景 ━━━\n"
                "1. 存在多个目标/实例且用户未明确指定范围时（必须先通过搜索/查询工具确认有多个结果，再让用户选择。不能跳过查询直接问）\n"
                "2. 请求存在多种合理解读，选错会导致返工\n"
                "3. 需要只有用户掌握的信息（偏好、业务规则、场景背景）\n"
                "4. 任务完成后让用户选择下一步操作\n\n"
                "━━━ 禁止调用的场景 ━━━\n"
                "A. 自己能查到答案的不要问（用工具查）\n"
                "B. 用户原始消息里已经给过约束的不要再问\n"
                "C. 不确定的细节不影响最终结果的，自己做主\n"
                "D. 一次只问一个回合，不要连环追问（同一件事只问一次）\n"
                "E. 寒暄性、确认性的问题不要问（hello/你好 → 直接回复文本，不调任何工具）\n"
                "F. 第一步就让用户选集群/实例是不允许的，必须先用搜索工具确认目标位置\n"
                "G. 用户没有提出 K8s/技术操作需求时，不要主动问是否要做检查\n\n"
                "━━━ 参数选择 ━━━\n"
                "能让用户点按钮就别让用户打字。\n"
                "- single_select: N选1，options 2~4项\n"
                "- multi_select: N选若干\n"
                "- confirm: 是/否（options 设为 None）\n"
                "- text: 开放式输入（options 设为 None）\n\n"
                "question 必须是完整问句，脱离上下文也能看懂。选项必须来自实际查询结果，不得编造。"
            ),
            args_schema=AskUserInput,
        )
        choice_tool._request_choice_func = _ask_user
        return choice_tool

    def _build_diff_report_tool(self):
        """构建 report_config_diff 工具，供 LLM 将配置对比结果结构化输出给前端"""
        from typing import List, Literal

        from langchain_core.tools import StructuredTool
        from pydantic import BaseModel as PydanticBaseModel
        from pydantic import Field as PydanticField

        class DiffItem(PydanticBaseModel):
            workload_name: str = PydanticField(description="工作负载名称，如 nginx-deployment")
            workload_type: str = PydanticField(description="工作负载类型：Deployment/StatefulSet/DaemonSet")
            namespace: str = PydanticField(description="命名空间")
            severity: Literal["critical", "high", "warning", "info"] = PydanticField(description="严重程度: critical=严重/紧急, high=高危, warning=警告, info=提示")
            summary: str = PydanticField(description="问题概述，如 '缺少资源限制 | 使用latest标签'")
            before_yaml: str = PydanticField(description="修复前的 YAML 配置片段")
            after_yaml: str = PydanticField(description="修复后的推荐 YAML 配置片段")

        class DiffReportInput(PydanticBaseModel):
            title: str = PydanticField(description="报告标题，如 'K8S 工作负载配置修复对比'")
            cluster_name: str = PydanticField(description="集群名称")
            items: List[DiffItem] = PydanticField(description="各工作负载的对比项列表")

        async def _report_config_diff(title: str, cluster_name: str, items: List[dict]) -> str:
            import uuid

            from langchain_core.callbacks import dispatch_custom_event

            report_id = str(uuid.uuid4())[:8]

            report_data = build_config_diff_report_payload(title=title, cluster_name=cluster_name, items=items)
            report_data["report_id"] = report_id

            try:
                dispatch_custom_event("config_diff_report", report_data)
            except Exception as e:
                logger.warning(f"dispatch config_diff_report failed: {e}")

            return f"已生成配置修复对比报告（{len(items)} 个工作负载），用户可点击查看详细对比。"

        diff_tool = StructuredTool.from_function(
            coroutine=_report_config_diff,
            name="report_config_diff",
            description=(
                "将配置修复建议以左右对比视图展示给用户（仅在 generate_repair_report 无法覆盖时使用）。\n"
                "大多数场景请优先使用 generate_repair_report，它更高效且不容易遗漏。\n"
                "仅当 generate_repair_report 无法满足需求时，才用此工具手动构造对比。\n\n"
                "【禁止】\n"
                "- 不要和 generate_repair_report 同时使用\n"
                "- 不要多次调用生成多份报告\n"
                "- 不要只包含部分工作负载\n\n"
                "【参数说明】\n"
                "- items: 各工作负载的对比项列表，一次调用包含所有需修复的条目\n"
                "- before_yaml：基于分析结果构造当前有问题的配置片段\n"
                "- after_yaml：填写修复后的推荐配置"
            ),
            args_schema=DiffReportInput,
        )
        return diff_tool

    def _build_bulk_repair_tool(self, _analysis_cache: dict = None):  # noqa: C901
        """构建通用修复报告工具：LLM 生成内容，代码只负责聚合与渲染，不限定领域"""
        from typing import List

        from langchain_core.tools import StructuredTool
        from pydantic import BaseModel as PydanticBaseModel
        from pydantic import Field as PydanticField

        if _analysis_cache is None:
            _analysis_cache = {}

        class RepairItem(PydanticBaseModel):
            target_name: str = PydanticField(description="修复目标名称（如工作负载名、数据库表名、服务名）")
            namespace: str = PydanticField(default="", description="所属空间（如 K8s namespace）")
            target_type: str = PydanticField(default="", description="目标类型（如 Deployment、Table）")
            category: str = PydanticField(default="", description="问题类别（如 '资源配置'、'安全加固'）")
            severity: str = PydanticField(default="high", description="严重程度：critical/high/warning/info")
            summary: str = PydanticField(description="问题简述（必填，如'未配置资源限制'）")
            before: str = PydanticField(default="", description="当前有问题的配置（1-3行关键配置，如 'resources: {}'）")
            after: str = PydanticField(default="", description="修复后的配置（1-3行，如 'resources:\\n  limits:\\n    cpu: 500m'）")
            fix_command: str = PydanticField(default="", description="修复命令（如 kubectl patch deploy/x -n ns --type=strategic -p '{...}'）")

        class BulkRepairInput(PydanticBaseModel):
            title: str = PydanticField(default="K8S 配置修复对比", description="报告标题（如 'K8S 配置修复对比'、'MySQL 索引优化建议'）")
            context_name: str = PydanticField(default="", description="上下文名称（如集群名、数据库实例名）")
            items: List[RepairItem] = PydanticField(default=[], description="修复项列表（可选：留空则自动从分析结果生成）")
            target_names: List[str] = PydanticField(default=[], description="要包含的目标名称过滤列表（如 ['payment-gateway']）。留空=全部。当检查特定工作负载时必须填写，自动生成时会只保留这些目标。")
            expected_target_count: int = PydanticField(default=0, description="预期的修复目标数量（即分析报告中有问题的目标总数）。用于校验是否遗漏，必须填写真实数量。")
            group_by: str = PydanticField(
                default="target",
                description=("报告组织方式：\n" "- 'target': 按修复目标聚合（同一目标的多个问题合并为一条）\n" "- 'category': 按问题类别聚合（同一类别的多个目标合并为一条）\n" "- 'all': 全部合并为一条"),
            )

        async def _generate_repair_report(
            title: str, context_name: str, items: List[dict], group_by: str = "target", expected_target_count: int = 0, target_names: List[str] = None
        ) -> str:
            import uuid
            from itertools import groupby as _groupby

            from langchain_core.callbacks import dispatch_custom_event

            group_by = self._normalize_repair_group_by(group_by)

            # ========== 自动补全：如果 LLM 没传 items 或 items 不完整，从分析缓存生成 ==========
            def _auto_generate_items_from_cache() -> List[dict]:
                """从分析结果缓存中自动生成修复项"""
                cached = _analysis_cache.get("deployments", [])
                if not cached:
                    return []
                auto_items = []
                for dep in cached:
                    dep_name = dep.get("name", "")
                    dep_ns = dep.get("namespace", "")
                    issues = dep.get("issues", [])
                    config_analysis = dep.get("config_analysis", {})
                    containers = config_analysis.get("containers", [])

                    # 收集容器级别的 issues
                    container_issues = []
                    for c in containers:
                        container_issues.extend(c.get("issues", []))

                    all_issues = issues + container_issues
                    if not all_issues:
                        continue

                    # 为每个 issue 生成一个 repair item
                    for issue in all_issues:
                        category = _categorize_issue(issue)
                        severity = _severity_for_issue(issue)
                        fix_cmd = _fix_command_for_issue(issue, dep_name, dep_ns)
                        auto_items.append(
                            {
                                "target_name": dep_name,
                                "namespace": dep_ns,
                                "target_type": "Deployment",
                                "category": category,
                                "severity": severity,
                                "summary": issue,
                                "before": "",
                                "after": "",
                                "fix_command": fix_cmd,
                            }
                        )
                return auto_items

            def _categorize_issue(issue: str) -> str:
                """根据 issue 文本归类"""
                if "资源" in issue or "resource" in issue.lower():
                    return "资源配置"
                if "探针" in issue or "probe" in issue.lower() or "健康" in issue:
                    return "健康检查"
                if "latest" in issue or "标签" in issue or "镜像" in issue:
                    return "镜像管理"
                if "root" in issue or "安全" in issue or "security" in issue.lower():
                    return "安全加固"
                if "副本" in issue or "replica" in issue.lower() or "单点" in issue:
                    return "可靠性"
                return "配置优化"

            def _severity_for_issue(issue: str) -> str:
                """根据 issue 判断严重级别"""
                if "root" in issue or "安全" in issue:
                    return "critical"
                if "资源限制" in issue or "单副本" in issue or "单点" in issue:
                    return "high"
                if "探针" in issue or "latest" in issue:
                    return "warning"
                return "info"

            def _fix_command_for_issue(issue: str, name: str, ns: str) -> str:
                """根据 issue 生成修复命令"""
                base = f"kubectl patch deployment {name} -n {ns} --type=strategic"

                def _build_patch_command(patch: dict) -> str:
                    return f"{base} -p '{json.dumps(patch, separators=(',', ':'))}'"

                if "资源限制" in issue or "未设置资源限制" in issue:
                    return _build_patch_command(
                        {
                            "spec": {
                                "template": {
                                    "spec": {
                                        "containers": [
                                            {
                                                "name": name,
                                                "resources": {
                                                    "limits": {"cpu": "500m", "memory": "256Mi"},
                                                    "requests": {"cpu": "100m", "memory": "128Mi"},
                                                },
                                            }
                                        ]
                                    }
                                }
                            }
                        }
                    )
                if "资源请求" in issue or "未设置资源请求" in issue:
                    return _build_patch_command(
                        {
                            "spec": {
                                "template": {"spec": {"containers": [{"name": name, "resources": {"requests": {"cpu": "100m", "memory": "128Mi"}}}]}}
                            }
                        }
                    )
                if "存活探针" in issue:
                    return _build_patch_command(
                        {
                            "spec": {
                                "template": {
                                    "spec": {
                                        "containers": [
                                            {
                                                "name": name,
                                                "livenessProbe": {
                                                    "httpGet": {"path": "/healthz", "port": 8080},
                                                    "initialDelaySeconds": 30,
                                                    "periodSeconds": 10,
                                                },
                                            }
                                        ]
                                    }
                                }
                            }
                        }
                    )
                if "就绪探针" in issue:
                    return _build_patch_command(
                        {
                            "spec": {
                                "template": {
                                    "spec": {
                                        "containers": [
                                            {
                                                "name": name,
                                                "readinessProbe": {
                                                    "httpGet": {"path": "/ready", "port": 8080},
                                                    "initialDelaySeconds": 5,
                                                    "periodSeconds": 5,
                                                },
                                            }
                                        ]
                                    }
                                }
                            }
                        }
                    )
                if "latest" in issue:
                    return f"# 请手动更新镜像标签为具体版本\nkubectl set image deployment/{name} -n {ns} {name}=<image>:<specific-tag>"
                if "root" in issue or "安全" in issue:
                    return f'{base} -p \'{{"spec":{{"template":{{"spec":{{"securityContext":{{"runAsNonRoot":true,"runAsUser":1000}}}}}}}}}}\''
                if "单副本" in issue or "单点" in issue:
                    return f"kubectl scale deployment {name} -n {ns} --replicas=3"
                return f"# {issue}\n# 请根据实际情况手动修复"

            # ========== 合并逻辑：LLM 传的 items + 自动补全 ==========
            # 自动生成后由 target_names 过滤保证范围，不再用 expected_target_count 禁止自动生成
            if not items and _analysis_cache.get("deployments"):
                # items 为空，从缓存自动生成
                auto_items = _auto_generate_items_from_cache()
                if auto_items:
                    items = auto_items
                # 自动填充 context_name
                if not context_name and _analysis_cache.get("cluster_name"):
                    context_name = _analysis_cache["cluster_name"]
            elif items and expected_target_count > 1:
                # items 非空但不完整（多目标场景且数量不足），尝试补充
                actual_in_items = {
                    f"{it.get('namespace', '') if isinstance(it, dict) else ''}/{it.get('target_name', '') if isinstance(it, dict) else ''}"
                    for it in items
                }
                if len(actual_in_items) < expected_target_count:
                    auto_items = _auto_generate_items_from_cache()
                    if auto_items:
                        existing_keys = set()
                        for it in items:
                            d = it if isinstance(it, dict) else (it.dict() if hasattr(it, "dict") else it.model_dump())
                            existing_keys.add(f"{d.get('namespace', '')}/{d.get('target_name', '')}:{d.get('summary', '')}")
                        for ai in auto_items:
                            key = f"{ai['namespace']}/{ai['target_name']}:{ai['summary']}"
                            if key not in existing_keys:
                                items.append(ai)
                if not context_name and _analysis_cache.get("cluster_name"):
                    context_name = _analysis_cache["cluster_name"]
            else:
                # items 已提供 — 保持原样，仅填充 context_name
                if not context_name and _analysis_cache.get("cluster_name"):
                    context_name = _analysis_cache["cluster_name"]

            # ========== target_names 过滤：只保留指定目标的 items ==========
            if target_names:
                _target_set = {n.lower().strip() for n in target_names}
                items = [it for it in items if (it.get("target_name", "") if isinstance(it, dict) else "").lower().strip() in _target_set]

            # 标准化 severity（容忍中文、大小写差异）
            _severity_map = {
                "critical": "critical",
                "严重": "critical",
                "紧急": "critical",
                "high": "high",
                "高": "high",
                "高危": "high",
                "warning": "warning",
                "警告": "warning",
                "中": "warning",
                "info": "info",
                "提示": "info",
                "低": "info",
                "信息": "info",
            }

            raw_items = []
            for item in items:
                if isinstance(item, dict):
                    d = item
                else:
                    d = item.dict() if hasattr(item, "dict") else item.model_dump()
                # 标准化 severity
                raw_sev = d.get("severity", "info").lower().strip()
                d["severity"] = _severity_map.get(raw_sev, "warning")
                raw_items.append(d)

            # 软校验：记录覆盖率，但不阻断生成
            actual_targets = {f"{it.get('namespace', '')}/{it.get('target_name', '')}" for it in raw_items}
            _coverage_note = ""
            if expected_target_count > 0 and len(actual_targets) < expected_target_count:
                _coverage_note = f"（注意：本报告覆盖了 {len(actual_targets)}/{expected_target_count} 个有问题的目标）"

            if not raw_items:
                return "未提供任何修复项。"

            _severity_order = {"critical": 0, "high": 1, "warning": 2, "info": 3}

            def _extract_patch_body(fix_command: str) -> str:
                """从 kubectl patch 命令中提取 -p 后的 JSON 并转为可读 YAML"""
                if not fix_command:
                    return ""
                import re as _cmd_re

                # 用同类引号匹配：-p '...' (贪婪，因为 JSON 内无单引号)
                m = _cmd_re.search(r"""(?:-p|--patch)\s+'([^']+)'""", fix_command)
                if not m:
                    m = _cmd_re.search(r'''(?:-p|--patch)\s+"([^"]+)"''', fix_command)
                if not m:
                    return ""
                json_str = m.group(1).strip()
                try:
                    import json as _pj

                    obj = _pj.loads(json_str)
                    return _json_to_yaml(obj, indent=0)
                except Exception:
                    return json_str[:200]

            def _json_to_yaml(obj, indent=0) -> str:
                """将 JSON 对象转为简洁的 YAML 风格文本（仅展示叶子节点的关键配置）"""
                lines = []
                prefix = "  " * indent
                if isinstance(obj, dict):
                    for k, v in obj.items():
                        if isinstance(v, (dict, list)):
                            lines.append(f"{prefix}{k}:")
                            lines.append(_json_to_yaml(v, indent + 1))
                        else:
                            lines.append(f"{prefix}{k}: {v}")
                elif isinstance(obj, list):
                    for item in obj:
                        if isinstance(item, dict):
                            lines.append(f"{prefix}-")
                            lines.append(_json_to_yaml(item, indent + 1))
                        else:
                            lines.append(f"{prefix}- {item}")
                else:
                    lines.append(f"{prefix}{obj}")
                return "\n".join(lines)

            def _before_snippet_for_issue(issue: str) -> str:
                """根据 issue 类型生成有意义的 before 配置片段"""
                if "资源限制" in issue or "未设置资源限制" in issue:
                    return "resources: {}  # 未设置限制"
                if "资源请求" in issue or "未设置资源请求" in issue:
                    return "resources: {}  # 未设置请求"
                if "存活探针" in issue:
                    return "livenessProbe: null  # 未配置"
                if "就绪探针" in issue:
                    return "readinessProbe: null  # 未配置"
                if "latest" in issue:
                    return "image: xxx:latest  # 使用了 latest 标签"
                if "root" in issue:
                    return "securityContext: {}  # 未限制运行用户"
                if "单副本" in issue or "单点" in issue:
                    return "replicas: 1  # 单副本"
                return "# (当前配置存在问题)"

            def _after_snippet_for_issue(issue: str) -> str:
                """根据 issue 类型生成有意义的 after 配置片段"""
                if "资源限制" in issue or "未设置资源限制" in issue:
                    return "resources:\n  limits:\n    cpu: 500m\n    memory: 256Mi\n  requests:\n    cpu: 100m\n    memory: 128Mi"
                if "资源请求" in issue or "未设置资源请求" in issue:
                    return "resources:\n  requests:\n    cpu: 100m\n    memory: 128Mi"
                if "存活探针" in issue:
                    return "livenessProbe:\n  httpGet:\n    path: /healthz\n    port: 8080\n  initialDelaySeconds: 30\n  periodSeconds: 10"
                if "就绪探针" in issue:
                    return "readinessProbe:\n  httpGet:\n    path: /ready\n    port: 8080\n  initialDelaySeconds: 5\n  periodSeconds: 5"
                if "latest" in issue:
                    return "image: xxx:1.25.3  # 使用明确版本标签"
                if "root" in issue:
                    return "securityContext:\n  runAsNonRoot: true\n  runAsUser: 1000"
                if "单副本" in issue or "单点" in issue:
                    return "replicas: 3  # 多副本高可用"
                return "# (建议修复)"

            def _build_diff_pair(summary_text: str, before_val: str, after_val: str, fix_command: str):
                """构建一对 before/after 文本"""
                if before_val or after_val:
                    return (
                        f"# {summary_text}\n{before_val or '# (当前配置)'}",
                        f"# {summary_text}\n{after_val or '# (建议配置)'}",
                    )
                # 根据 issue 类型生成有意义的 before/after 片段
                before_snippet = _before_snippet_for_issue(summary_text)
                after_snippet = _after_snippet_for_issue(summary_text)
                return (
                    f"# {summary_text}\n{before_snippet}",
                    f"# {summary_text}\n{after_snippet}",
                )

            diff_items = []

            if group_by == "target":
                raw_items.sort(key=lambda x: (x.get("namespace", ""), x.get("target_name", "")))
                for key, group in _groupby(raw_items, key=lambda x: (x.get("namespace", ""), x.get("target_name", ""), x.get("target_type", ""))):
                    group_list = list(group)
                    ns, name, ttype = key
                    before_parts = []
                    after_parts = []
                    summaries = []
                    worst_severity = "info"
                    for it in group_list:
                        summary_text = it.get("summary", "")
                        before_val = it.get("before", "").strip()
                        after_val = it.get("after", "").strip()
                        fix_cmd = it.get("fix_command", "")
                        b_text, a_text = _build_diff_pair(summary_text, before_val, after_val, fix_cmd)
                        before_parts.append(b_text)
                        after_parts.append(a_text)
                        summaries.append(summary_text)
                        if _severity_order.get(it.get("severity"), 9) < _severity_order.get(worst_severity, 9):
                            worst_severity = it.get("severity", "info")
                    diff_items.append(
                        {
                            "workload_name": name,
                            "workload_type": ttype,
                            "namespace": ns,
                            "severity": worst_severity,
                            "summary": " | ".join(summaries),
                            "before_yaml": "\n\n".join(before_parts),
                            "after_yaml": "\n\n".join(after_parts),
                        }
                    )

            elif group_by == "category":
                raw_items.sort(key=lambda x: (_severity_order.get(x.get("severity"), 9), x.get("category", "")))
                for key, group in _groupby(raw_items, key=lambda x: (x.get("category", ""), x.get("severity", "info"))):
                    group_list = list(group)
                    category, severity = key
                    before_parts = []
                    after_parts = []
                    target_names = []
                    for it in group_list:
                        label = f"# {it.get('namespace', '')}/{it.get('target_name', '')}".rstrip("/")
                        if it.get("target_type"):
                            label += f" ({it['target_type']})"
                        before_val = it.get("before", "").strip()
                        after_val = it.get("after", "").strip()
                        summary_text = it.get("summary", "")
                        if before_val or after_val:
                            before_parts.append(f"{label}\n{before_val or '# (当前配置)'}")
                            after_parts.append(f"{label}\n{after_val or '# (建议配置)'}")
                        else:
                            before_parts.append(f"{label}\n{_before_snippet_for_issue(summary_text)}")
                            after_parts.append(f"{label}\n{_after_snippet_for_issue(summary_text)}")
                        target_names.append(it.get("target_name", ""))
                    diff_items.append(
                        {
                            "workload_name": ", ".join(target_names),
                            "workload_type": "Multiple",
                            "namespace": "-",
                            "severity": severity,
                            "summary": f"{category}（{len(group_list)} 个目标）" if category else f"修复项（{len(group_list)} 个目标）",
                            "before_yaml": "\n\n".join(before_parts),
                            "after_yaml": "\n\n".join(after_parts),
                        }
                    )

            else:
                before_parts = []
                after_parts = []
                categories = set()
                worst_severity = "info"
                raw_items.sort(key=lambda x: (x.get("namespace", ""), x.get("target_name", ""), _severity_order.get(x.get("severity"), 9)))
                for it in raw_items:
                    label = f"# {it.get('namespace', '')}/{it.get('target_name', '')} - {it.get('summary', '')}".replace("/ - ", " - ").replace(
                        "/- ", "- "
                    )
                    before_val = it.get("before", "").strip()
                    after_val = it.get("after", "").strip()
                    summary_text = it.get("summary", "")
                    if before_val or after_val:
                        before_parts.append(f"{label}\n{before_val or '# (当前配置)'}")
                        after_parts.append(f"{label}\n{after_val or '# (建议配置)'}")
                    else:
                        before_parts.append(f"{label}\n{_before_snippet_for_issue(summary_text)}")
                        after_parts.append(f"{label}\n{_after_snippet_for_issue(summary_text)}")
                    categories.add(it.get("category", "") or summary_text)
                    if _severity_order.get(it.get("severity"), 9) < _severity_order.get(worst_severity, 9):
                        worst_severity = it.get("severity", "info")
                unique_targets = {it.get("target_name", "") for it in raw_items}
                diff_items.append(
                    {
                        "workload_name": f"全部（{len(unique_targets)} 个目标）",
                        "workload_type": "All",
                        "namespace": "-",
                        "severity": worst_severity,
                        "summary": f"共 {len(raw_items)} 项修复：{' | '.join(sorted(categories))}",
                        "before_yaml": "\n\n".join(before_parts),
                        "after_yaml": "\n\n".join(after_parts),
                    }
                )

            report_data = build_config_diff_report_payload(title=title, cluster_name=context_name, items=diff_items)

            try:
                dispatch_custom_event("config_diff_report", report_data)
            except Exception as e:
                logger.warning(f"dispatch config_diff_report failed: {e}")

            def _get_patch_json_for_issue(issue: str) -> str:
                """根据 issue 类型返回紧凑的 patch JSON（多行格式，便于阅读）"""
                if "资源限制" in issue or "未设置资源限制" in issue:
                    return (
                        "{\n"
                        '  "spec":{"template":{"spec":{"containers":[{\n'
                        '    "name":"$dep",\n'
                        '    "resources":{"limits":{"cpu":"500m","memory":"256Mi"},\n'
                        '               "requests":{"cpu":"100m","memory":"128Mi"}}\n'
                        "  }]}}}\n"
                        "}"
                    )
                if "资源请求" in issue or "未设置资源请求" in issue:
                    return (
                        "{\n"
                        '  "spec":{"template":{"spec":{"containers":[{\n'
                        '    "name":"$dep",\n'
                        '    "resources":{"requests":{"cpu":"100m","memory":"128Mi"}}\n'
                        "  }]}}}\n"
                        "}"
                    )
                if "存活探针" in issue:
                    return (
                        "{\n"
                        '  "spec":{"template":{"spec":{"containers":[{\n'
                        '    "name":"$dep",\n'
                        '    "livenessProbe":{"httpGet":{"path":"/healthz","port":8080},\n'
                        '      "initialDelaySeconds":30,"periodSeconds":10}\n'
                        "  }]}}}\n"
                        "}"
                    )
                if "就绪探针" in issue:
                    return (
                        "{\n"
                        '  "spec":{"template":{"spec":{"containers":[{\n'
                        '    "name":"$dep",\n'
                        '    "readinessProbe":{"httpGet":{"path":"/ready","port":8080},\n'
                        '      "initialDelaySeconds":5,"periodSeconds":5}\n'
                        "  }]}}}\n"
                        "}"
                    )
                if "root" in issue or "安全" in issue:
                    return "{\n" '  "spec":{"template":{"spec":{\n' '    "securityContext":{"runAsNonRoot":true,"runAsUser":1000}\n' "  }}}\n" "}"
                return "{}"

            # 收集修复命令（按问题类型分组生成批量命令，避免 LLM 输出 token 超限）
            commands_by_issue: dict = {}  # issue_summary -> [(name, ns, cmd)]
            for it in raw_items:
                fix_cmd = it.get("fix_command", "")
                if not fix_cmd:
                    continue
                summary = it.get("summary", "")
                name = it.get("target_name", "")
                ns = it.get("namespace", "")
                commands_by_issue.setdefault(summary, []).append((name, ns, fix_cmd))

            commands_text = ""
            if commands_by_issue:
                commands_text_parts = []
                for issue_summary, cmd_list in commands_by_issue.items():
                    if len(cmd_list) == 1:
                        name, ns, cmd = cmd_list[0]
                        commands_text_parts.append(f"**{issue_summary}** ({ns}/{name})\n```bash\n{cmd}\n```")
                    else:
                        # 批量格式：如果命令模式相同（只是名字不同），用 for 循环
                        namespaces = {ns for _, ns, _ in cmd_list}
                        names = [name for name, _, _ in cmd_list]
                        if len(namespaces) == 1:
                            ns = namespaces.pop()
                            # 检查是否可用 scale 命令（简短）
                            sample_cmd = cmd_list[0][2]
                            if "kubectl scale" in sample_cmd:
                                commands_text_parts.append(
                                    f"**{issue_summary}** ({len(cmd_list)} 个工作负载)\n"
                                    f"```bash\nfor dep in {' '.join(names)}; do\n"
                                    f"  kubectl scale deployment $dep -n {ns} --replicas=3\n"
                                    f"done\n```"
                                )
                            elif "kubectl set image" in sample_cmd or "手动更新" in sample_cmd:
                                commands_text_parts.append(
                                    f"**{issue_summary}** ({len(cmd_list)} 个工作负载)\n"
                                    f"```bash\n# 请为以下工作负载更新镜像标签：\n"
                                    f"# {', '.join(names)}\n"
                                    f"# 示例：kubectl set image deployment/<name> -n {ns} <container>=<image>:<tag>\n```"
                                )
                            else:
                                # 用 PATCH 变量 + for 循环，避免超长单行
                                patch_json = _get_patch_json_for_issue(issue_summary)
                                commands_text_parts.append(
                                    f"**{issue_summary}** ({len(cmd_list)} 个工作负载)\n"
                                    f"```bash\n"
                                    f"PATCH='{patch_json}'\n\n"
                                    f"for dep in {' '.join(names)}; do\n"
                                    f"  kubectl patch deployment $dep -n {ns} \\\n"
                                    f'    --type=strategic -p "$PATCH"\n'
                                    f"done\n```"
                                )
                        else:
                            # 多个 namespace，用 PATCH 变量 + 逐条列出
                            patch_json = _get_patch_json_for_issue(issue_summary)
                            cmds_short = [f'kubectl patch deployment {n} -n {ns} \\\n  --type=strategic -p "$PATCH"' for n, ns, _ in cmd_list]
                            commands_text_parts.append(
                                f"**{issue_summary}** ({len(cmd_list)} 个工作负载)\n"
                                f"```bash\n"
                                f"PATCH='{patch_json}'\n\n" + "\n".join(cmds_short) + "\n```"
                            )
                commands_text = "\n\n".join(commands_text_parts)

            # dispatch 修复命令事件（直接渲染到前端，不经过 LLM 输出）
            if commands_text:
                try:
                    dispatch_custom_event(
                        "repair_commands",
                        {
                            "commands_id": str(uuid.uuid4())[:8],
                            "commands_markdown": commands_text,
                        },
                    )
                except Exception as e:
                    logger.warning(f"dispatch repair_commands failed: {e}")

            # 生成 .docx 报告并 dispatch 下载事件
            try:
                from apps.opspilot.metis.llm.tools.kubernetes.report_generator import generate_k8s_report_docx
                from apps.opspilot.services.generated_file_delivery_service import build_generated_file_download_event

                report_data_for_docx = {
                    "cluster_name": context_name,
                    "raw_items": raw_items,
                }
                docx_bytes = await asyncio.wait_for(
                    asyncio.to_thread(generate_k8s_report_docx, report_data_for_docx),
                    timeout=5,
                )
                filename = f"K8S配置检查报告_{context_name}_{datetime.now().strftime('%Y%m%d')}.docx"
                download_event = build_generated_file_download_event(
                    filename=filename,
                    content_bytes=docx_bytes,
                    mime_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
                )
                dispatch_custom_event("report_file_download", download_event)
            except asyncio.TimeoutError:
                logger.warning("generate docx report skipped: timeout")
            except Exception as e:
                logger.warning(f"generate docx report failed: {e}")

            result_parts = [f"已生成修复对比报告，共 {len(raw_items)} 项修复。{_coverage_note}"]
            if commands_text:
                result_parts.append("\n\n修复命令已直接展示给用户（通过界面卡片），你不需要再重复输出命令。" "\n只需简短告知用户：修复命令已在上方展示，请根据实际情况调整后执行。")
            else:
                result_parts.append("\n\n修复建议已在对比报告中展示。")

            return "".join(result_parts)

        bulk_repair_tool = StructuredTool.from_function(
            coroutine=_generate_repair_report,
            name="generate_repair_report",
            description=(
                "生成修复对比报告（通用工具，适用于任何领域）。\n\n"
                "【核心原则】报告只包含用户问的内容！\n"
                "- 用户问某个特定工作负载 → target_names=['工作负载名'] 必填\n"
                "- 用户问全部 → target_names 留空\n\n"
                "【调用规则】\n"
                "- items 可以留空，工具会自动从分析缓存生成，然后用 target_names 过滤\n"
                "- target_names 是范围过滤器，自动生成的内容会被过滤到只含这些目标\n"
                "- expected_target_count 填有问题的目标数量\n\n"
                "【如需自定义 items】\n"
                "- ⚠️ 只能调用一次！所有目标的所有问题放在同一个 items 数组中\n"
                "- fix_command：必填（如 kubectl patch deploy/x -n ns -p '{...}'）\n\n"
                "group_by: target=按目标聚合 / category=按类别聚合 / all=全部合一"
            ),
            args_schema=BulkRepairInput,
        )
        return bulk_repair_tool

    # ========== 使用 DeepAgent 实现 ==========
    #
    # 统一引擎入口：所有 agent 图（ReAct / Plan-Execute / ChatBot）均通过
    # build_deepagent_nodes 委托给 deepagents 的 create_deep_agent。
    # deepagents 原生提供规划（TodoListMiddleware）、虚拟文件系统、子代理、
    # 上下文压缩（SummarizationMiddleware）、Anthropic prompt 缓存、以及
    # 技能（SkillsMiddleware，SKILL.md 渐进式披露）能力。
    #
    # 在 deepagents 之上，本方法真实接入 BK-Lite 的四项能力：
    #   - tools / MCP：复用 setup() 已加载的 self.all_tools / self.tools
    #   - knowledge base：knowledge_retrieve 工具（agent 自主检索，见 _build_knowledge_retrieve_tool）
    #   - skills：把 SkillPackage 物化为 SKILL.md 写入 MinIO 对象存储 backend
    #   - approval：approval_config -> deepagents 原生 interrupt_on（HITL）
    #
    # 手写 ReAct 循环（build_react_nodes）暂时保留以兼容存量单测，但图层不再使用。

    # deepagents 内置工具名（规划/文件系统/子代理），用于 AG-UI 事件过滤与审批排除。
    DEEPAGENT_BUILTIN_TOOL_NAMES = frozenset(
        {
            "write_todos",
            "write_file",
            "read_file",
            "ls",
            "edit_file",
            "glob_search",
            "grep_search",
            "task",
        }
    )

    def _collect_deepagent_tools(self, graph_request) -> list:
        """汇总传给 deepagent 的业务工具：langchain + MCP（+ 知识库检索工具）。"""
        tools = list(self.all_tools or self.tools or [])
        kb_tool = self._build_knowledge_retrieve_tool(graph_request)
        if kb_tool is not None:
            tools.append(kb_tool)
        return tools

    def _build_knowledge_retrieve_tool(self, graph_request):
        """构建 agent 可调用的 knowledge_retrieve 工具（双模式中的“工具模式”）。

        基于 request.naive_rag_request（DocumentRetrieverRequest 列表）按需检索：
        每次调用用 agent 的 query 覆盖各请求的 search_query 再走 PgvectorRag。
        best-effort：无知识库配置或构建失败时返回 None，不影响主引擎。
        """
        naive_rag_request = list(getattr(graph_request, "naive_rag_request", None) or [])
        if not naive_rag_request:
            return None
        try:
            from types import SimpleNamespace

            from apps.opspilot.metis.llm.tools.knowledge_tool import build_knowledge_retrieve_tool
            from apps.opspilot.metis.llm.rag.naive_rag.pgvector.pgvector_rag import PgvectorRag

            # 用 DocumentRetrieverRequest 作为“知识库”载体；kwargs_map 不参与（search_fn 自带逻辑）
            knowledge_bases = []
            kwargs_map = {}
            for idx, req in enumerate(naive_rag_request):
                kb_id = str(getattr(req, "index_name", None) or f"kb_{idx}")
                knowledge_bases.append(SimpleNamespace(id=kb_id, name=kb_id, req=req))
                kwargs_map[kb_id] = {}

            def _search_fn(kb, query, kwargs, score_threshold=0, is_qa=False):
                req = kb.req
                try:
                    cloned = req.model_copy(update={"search_query": query})
                except Exception:
                    cloned = req
                    try:
                        cloned.search_query = query
                    except Exception:
                        pass
                results = PgvectorRag().search(cloned)
                return self._normalize_kb_results(results)

            return build_knowledge_retrieve_tool(knowledge_bases, kwargs_map, search_fn=_search_fn)
        except Exception as e:  # pragma: no cover - defensive
            logger.warning("knowledge_retrieve 工具构建失败，跳过: %r", e)
            return None

    @staticmethod
    def _normalize_kb_results(results) -> list:
        """把 PgvectorRag 返回结果规整成 knowledge_tool 期望的 dict 列表。"""
        normalized = []
        for item in results or []:
            meta = getattr(item, "metadata", None)
            if meta is None and isinstance(item, dict):
                meta = item.get("metadata", {})
            page = getattr(item, "page_content", None)
            if page is None and isinstance(item, dict):
                page = item.get("page_content") or item.get("content", "")
            normalized.append(
                {
                    "content": page or "",
                    "title": (meta or {}).get("title") or (meta or {}).get("source", ""),
                    "score": (meta or {}).get("score") or getattr(item, "score", 0),
                }
            )
        return normalized

    def _build_skill_backend_and_sources(self, graph_request):
        """把启用的 SkillPackage 物化为 SKILL.md 写入 MinIO，返回 (backend, sources)。

        sources 指向 backend 中存放各技能目录的父路径（"/skills/"），
        SkillsMiddleware 据此扫描 SKILL.md 的 frontmatter 并渐进式披露。
        best-effort：无技能或失败返回 (None, [])，不影响主引擎。
        """
        packages = self._resolve_skill_packages(graph_request)
        if not packages:
            return None, []
        try:
            from apps.opspilot.metis.llm.backends import MinIOBackend
            from apps.opspilot.services.skill_package.materializer import materialize_skill_package

            # 按 bot/用户做命名空间隔离，避免多租户串读
            user_id = getattr(graph_request, "user_id", "") or "shared"
            backend = MinIOBackend(bucket_name=self._skill_bucket_name(), prefix=f"opspilot-skills/{user_id}")
            for pkg in packages:
                try:
                    materialize_skill_package(pkg, backend)
                except Exception as me:  # 幂等：已存在/单包失败不影响其它技能
                    logger.debug("技能物化跳过(%s): %r", pkg.get("name") if isinstance(pkg, dict) else pkg, me)
            return backend, ["/skills/"]
        except Exception as e:  # pragma: no cover - defensive
            logger.warning("技能 backend 构建失败，跳过 skills: %r", e)
            return None, []

    @staticmethod
    def _skill_bucket_name() -> str:
        """技能文件所在的私有桶（沿用项目私有桶约定）。"""
        import os

        return os.getenv("OPSPILOT_SKILL_BUCKET", "munchkin-private")

    @staticmethod
    def _resolve_skill_packages(graph_request) -> list:
        """从 request.extra_config 解析本次启用的技能包（已 hydrate 的 dict 列表）。"""
        try:
            from apps.opspilot.services.skill_package.runtime import hydrate_skill_packages, normalize_skill_packages

            ec = ExtraConfig.from_raw(getattr(graph_request, "extra_config", None))
            raw = list(getattr(ec, "matched_skill_packages", None) or [])
            if not raw:
                return []
            return hydrate_skill_packages(normalize_skill_packages(raw))
        except Exception as e:  # pragma: no cover - defensive
            logger.debug("技能包解析失败: %r", e)
            return []

    def _build_interrupt_on(self, graph_request, tools) -> Optional[dict]:
        """approval_config -> deepagents interrupt_on（人工审批 HITL）。

        approval_config.tools 为空且启用 = 对所有业务工具审批（排除 deepagents 内置工具）。
        """
        approval = getattr(graph_request, "approval_config", None)
        if not approval or not getattr(approval, "enabled", False):
            return None
        named = list(getattr(approval, "tools", None) or [])
        if named:
            target_names = named
        else:
            target_names = [t.name for t in (tools or []) if getattr(t, "name", None) and t.name not in self.DEEPAGENT_BUILTIN_TOOL_NAMES]
        if not target_names:
            return None
        return {name: True for name in target_names}

    async def build_deepagent_nodes(
        self,
        graph_builder: StateGraph,
        composite_node_name: str = "deep_agent",
        additional_system_prompt: Optional[str] = None,
        next_node: str = END,
        tools_node: Optional[ToolNode] = None,
    ) -> str:
        """构建统一 DeepAgent 节点（所有 agent 图的执行引擎）。

        Args:
            graph_builder: StateGraph实例
            composite_node_name: 组合节点名称前缀
            additional_system_prompt: 附加系统提示词
            next_node: 下一个节点名称
            tools_node: 兼容签名（deepagent 自管工具，忽略）

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
            tools = self._collect_deepagent_tools(graph_request)
            backend, skill_sources = self._build_skill_backend_and_sources(graph_request)
            interrupt_on = self._build_interrupt_on(graph_request, tools)

            agent_kwargs: Dict[str, Any] = {
                "model": llm,
                "tools": tools,
                "system_prompt": final_system_prompt,
            }
            if backend is not None:
                agent_kwargs["backend"] = backend
            if skill_sources:
                agent_kwargs["skills"] = skill_sources
            if interrupt_on:
                agent_kwargs["interrupt_on"] = interrupt_on

            # 创建 DeepAgent (自动包含规划、文件系统、子代理、压缩与技能能力)
            deep_agent = create_deep_agent(**agent_kwargs)

            # DeepAgent 返回 CompiledStateGraph；提高递归限制以容纳复杂任务
            deep_config = {**config, "recursion_limit": 100}

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
