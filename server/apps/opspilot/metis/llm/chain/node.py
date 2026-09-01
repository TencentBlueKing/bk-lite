import asyncio
import hashlib
import json
import uuid
from datetime import datetime
from typing import Any, Dict, List, Optional
from urllib.parse import parse_qs, urlparse

import json_repair
from deepagents import create_deep_agent
from langchain_core.callbacks import adispatch_custom_event, dispatch_custom_event
from langchain_core.messages import AIMessage, AIMessageChunk, BaseMessage, HumanMessage, SystemMessage, ToolMessage
from langchain_core.runnables import RunnableConfig
from langchain_core.tools import StructuredTool
from langchain_mcp_adapters.client import MultiServerMCPClient
from langgraph.constants import END
from langgraph.graph import StateGraph
from langgraph.prebuilt import ToolNode
from pydantic import BaseModel as PydanticBaseModel
from pydantic import Field as PydanticField

from apps.core.logger import opspilot_logger as logger
from apps.opspilot.metis.llm.chain.approval_tools import ApprovalToolsMixin, _build_approval_tool, _build_choice_tool  # noqa: E402,F401
from apps.opspilot.metis.llm.chain.deepagent_assembly import (  # noqa: E402,F401
    DeepAgentAssemblyMixin,
    _append_planned_execution_step_prompt,
    _build_deep_agent_kwargs,
    _build_interrupt_on,
    _build_legacy_deep_agent_middleware,
    _build_lightweight_system_prompt,
    _build_planned_execution_runtime_middleware,
    _build_planned_execution_tool_visibility,
    _plan_is_skills_only,
    _planned_step_already_answered,
    _planned_tool_step_guidance,
    _should_use_lightweight_after_empty_plan,
    _should_use_lightweight_direct_reply,
    _skill_only_step_guidance,
    _skill_package_script_lines,
)
from apps.opspilot.metis.llm.chain.entity import BasicLLMRequest, DoneToolConfig, ExtraConfig

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
    RENDERER_REGISTRY,
    _build_config_analysis_report_total,
    _build_config_analysis_scan_range,
    _build_config_analysis_scope,
    _config_analysis_benefit_description,
    _config_analysis_fix_description,
    _config_analysis_risk_description,
    build_a2ui_report_contract,
    build_config_analysis_report_markdown,
    build_config_analysis_report_payload,
    build_post_tool_directives,
    build_repair_mode_choice_args,
    downgrade_config_analysis_next_step_hint,
    find_completed_k8s_analysis_choice,
    find_pending_k8s_analysis_choice,
    get_renderer,
    should_emit_config_analysis_report,
)
from apps.opspilot.metis.llm.chain.k8s_tool_gate import is_k8s_agent  # noqa: E402,F401
from apps.opspilot.metis.llm.chain.knowledge_tools import (  # noqa: E402,F401
    KnowledgeToolsMixin,
    _build_knowledge_retrieve_tool,
    _normalize_kb_results,
)
from apps.opspilot.metis.llm.chain.lc_patches import (  # noqa: E402,F401
    _REASONING_FIELD_NAMES,
    _patched_convert_delta_to_message_chunk,
    _patched_convert_dict_to_message,
    _patched_convert_message_to_dict,
    _patched_create_chat_result,
    _patched_get_request_payload,
    merge_openai_payload_system_messages,
)
from apps.opspilot.metis.llm.chain.prepare_llm_context import prepare_messages_for_llm
from apps.opspilot.metis.llm.chain.skill_sandbox import (  # noqa: E402,F401
    SkillSandboxMixin,
    _build_skill_backend_and_sources,
    _cleanup_sandbox,
    _discover_sandbox_path,
    _ensure_skill_deps,
    _load_skill_package_runtime_params,
    _make_lazy_skill_deps_callback,
    _resolve_skill_packages,
    _sandbox_env,
    _skill_bucket_name,
    _skill_sandbox_base,
)
from apps.opspilot.metis.llm.common.llm_client_factory import LLMClientFactory
from apps.opspilot.metis.llm.common.structured_output_parser import StructuredOutputParser
from apps.opspilot.metis.llm.common.token_usage import TokenUsageAccumulator
from apps.opspilot.metis.llm.middleware.planned_execution_limits import ask_limit_continue, detect_limit_kind
from apps.opspilot.metis.llm.middleware.tool_runtime import (
    PLANNED_EXECUTION_ALWAYS_ON_BUSINESS_TOOLS,
    PLANNED_EXECUTION_ALWAYS_VISIBLE_FS_TOOLS,
    PLANNED_EXECUTION_HIDDEN_DEEPAGENT_TOOLS,
    is_progressive_tools_enabled,
)

# from apps.opspilot.metis.llm.rag.naive_rag.pgvector.pgvector_rag import PgvectorRag  # 暂时禁用,master 合并后文件被删除
from apps.opspilot.metis.llm.tools.tools_loader import ToolsLoader

# master 删除的 RAG 模块(占位,后续用 lazy import 避免启动失败)
try:
    from apps.opspilot.metis.llm.rag.naive_rag.pgvector.pgvector_rag import PgvectorRag
except ImportError:
    PgvectorRag = None
from apps.opspilot.metis.utils.template_loader import TemplateLoader


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


def _image_urls(value) -> List[str]:
    return [url for url in (value or []) if url]


def human_message_with_images(text: str, image_urls) -> HumanMessage:
    """当前轮或历史用户话：有图则拼多模态；无文本时不再塞天气示例句。"""
    urls = _image_urls(image_urls)
    if not urls:
        return HumanMessage(content=text or "")
    content: List[dict] = []
    if str(text or "").strip():
        content.append({"type": "text", "text": text})
    for url in urls:
        content.append({"type": "image_url", "image_url": {"url": url}})
    return HumanMessage(content=content)


def _request_current_image_urls(request) -> List[str]:
    extra = ExtraConfig.from_raw(getattr(request, "extra_config", None))
    return _image_urls(extra.current_image_data)


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


def without_system_messages(messages: List[Any]) -> List[Any]:
    """Drop SystemMessage so DeepAgent 的 system_prompt 成为唯一 system。

    图前置节点已写入 SystemMessage；create_deep_agent(system_prompt=...) 会再注入一条，
    部分网关会因此返回 400 “System message must be at the beginning.”
    """
    return [message for message in (messages or []) if not isinstance(message, SystemMessage)]


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

    async def _prepare_messages_for_llm(self, messages, graph_request, *, tools=None):
        if graph_request is None:
            return list(messages or [])
        isolated_llm = self.get_llm_client(graph_request, disable_stream=True, isolated=True)
        return await prepare_messages_for_llm(
            list(messages or []),
            request=graph_request,
            isolated_llm=isolated_llm,
            tools=tools,
        )

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
                event = str(getattr(chat, "event", "") or "").strip().lower()
                if event == "user":
                    state["messages"].append(human_message_with_images(chat.message, chat.image_data))
                elif event in {"assistant", "bot"}:
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

            if PgvectorRag is None:
                # master 删除 pgvector_rag 模块,降级跳过
                logger.warning("[naive_rag] PgvectorRag 模块不可用,跳过")
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
        """执行图谱搜索(GraphRAG 模块上游已删除,降级返回空)"""
        try:
            from apps.opspilot.metis.llm.rag.graph_rag.graphiti.graphiti_rag import GraphitiRAG

            graphiti = GraphitiRAG()
            rag_search_request.graph_rag_request.search_query = rag_search_request.search_query
            graph_result = await graphiti.search(req=rag_search_request.graph_rag_request)
            logger.debug(f"GraphRAG模式检索知识库: {rag_search_request.graph_rag_request.group_ids}, 结果数量: {len(graph_result)}")
            return graph_result
        except ImportError:
            logger.warning("[GraphRAG] graphiti_rag 模块不可用,降级返回空列表")
            return []

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
        preview = _safe_log_preview(user_message, max_len=20)
        logger.info(
            "[%s] user_message_node 开始执行, original_user_message(len=%s, preview=%r)",
            trace_id,
            len(user_message or ""),
            preview,
        )

        # 如果启用问题改写功能
        if config["configurable"]["graph_request"].enable_query_rewrite:
            try:
                rewritten_message = self._rewrite_query(request, config)
                if rewritten_message and rewritten_message.strip():
                    user_message = rewritten_message
                    self.log(
                        config,
                        f"问题改写完成: {_safe_log_preview(request.user_message, 20)!r} -> {_safe_log_preview(user_message, 20)!r}",
                    )
            except Exception as e:
                logger.warning("问题改写失败，使用原始问题: %r", e)
                user_message = request.user_message

        state["messages"].append(human_message_with_images(user_message, _request_current_image_urls(request)))
        request.graph_user_message = user_message
        logger.info(
            "[%s] user_message_node 执行结束, appended_user_message(len=%s, preview=%r), message_count=%s",
            trace_id,
            len(user_message or ""),
            _safe_log_preview(user_message, 20),
            len(state["messages"]),
        )
        return state

    def chat_node(self, state: Dict[str, Any], config: RunnableConfig) -> Dict[str, Any]:
        request = config["configurable"]["graph_request"]

        # 获取LLM客户端并调用
        llm = self.get_llm_client(request)
        result = llm.invoke(state["messages"])

        return {"messages": result}


class ToolsNodes(
    BasicNode,
    ApprovalToolsMixin,
    KnowledgeToolsMixin,
    SkillSandboxMixin,
    DeepAgentAssemblyMixin,
):
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
        self._extra_config = _ec
        self._require_choice_before_tools = _ec.require_choice_before_tools
        self._multi_instance_options = _ec.multi_instance_options
        self._skill_package_capabilities = set(_ec.skill_package_capabilities or [])
        logger.debug(
            "ToolsNodes extra_config keys=%s, capabilities=%s",
            list((getattr(request, "extra_config", None) or {}).keys()),
            self._skill_package_capabilities,
        )
        if self._require_choice_before_tools:
            logger.info(f"多实例强制选择已启用, options={self._multi_instance_options}")

    def _has_skill_package_capability(self, capability: str) -> bool:
        return capability in getattr(self, "_skill_package_capabilities", set())

    def _enabled_report_capabilities(self) -> set[str]:
        """已启用的 report 类 capability 集合(由 skill 包声明 ∩ 渲染器注册表)。

        任何 report 能力的判断都从这里走,避免在多处硬编码 capability 名。
        """
        return set(RENDERER_REGISTRY.keys()) & getattr(self, "_skill_package_capabilities", set())

    def _has_report_capability(self, capability: str) -> bool:
        return capability in self._enabled_report_capabilities()

    def _enable_config_analysis_report(self) -> bool:
        # 保留旧名以兼容现有调用点;真值从统一的 capability 集合里查
        return self._has_report_capability("config_analysis_report")

    def _enable_repair_diff_report(self) -> bool:
        return self._has_report_capability("repair_diff_report")

    def _stable_report_id(self, capability: str, config: RunnableConfig = None) -> Optional[str]:
        """同一执行内复用报告 ID，避免重复追加相同卡片。"""
        configurable = config.get("configurable", {}) if isinstance(config, dict) else {}
        execution_id = configurable.get("execution_id") if isinstance(configurable, dict) else None
        if not execution_id:
            execution_id = getattr(getattr(self, "_extra_config", None), "execution_id", None)
        return f"{capability}_{execution_id}" if execution_id else None

    def _emit_report_event(
        self,
        capability: str,
        parsed: Any,
        event_dispatcher=None,
        config: RunnableConfig = None,
    ) -> Optional[str]:
        """通过 registry 渲染 + dispatch 一个 report 类 AG-UI 事件。

        流程:
        1. 检查 capability 是否在 skill 包声明中(否则直接跳过)
        2. 查 RENDERER_REGISTRY 拿渲染器
        3. 渲染器吃 parsed,产出 payload(None 表示"本轮跳过")
        4. dispatch_custom_event(capability, payload)

        event_dispatcher: 可选的 async 回调(capability, payload) -> awaitable。
        默认走同步 dispatch_custom_event(deepagent 包装节点不在 langchain
        runnable 回调树里时会缺 parent run id,需要传一个 adispatch_custom_event
        并把 config 传进去的回调)。

        返回生成的 report_id(payload 上的)以便调用方引用,失败返回 None。
        事件名 = capability 名,前后端/技能包能力名三者一致。
        """
        if not self._has_report_capability(capability):
            return None
        renderer = get_renderer(capability)
        if renderer is None:
            return None
        # package 上下文:matched_skill_packages 的第一个(若存在),渲染器用它做
        # cluster_name 兜底;主数据来源仍是 parsed 里的 cluster_name/title。
        ec = getattr(self, "_extra_config", None)
        matched = list(getattr(ec, "matched_skill_packages", None) or []) if ec else []
        package_ctx = matched[0] if matched else {}
        payload = renderer(parsed, package_ctx)
        if not payload:
            return None
        stable_report_id = self._stable_report_id(capability, config)
        if stable_report_id:
            payload["report_id"] = stable_report_id
        if event_dispatcher is not None:
            # async 路径:deep_wrapper_node 传入的 adispatch_custom_event 回调。
            # 已有 running loop 时不能 fire-and-forget：包装节点可能立刻返回，
            # ensure_future 任务会被取消，表现为有工具结果但前端收不到卡片。
            try:
                import asyncio as _asyncio

                coro = event_dispatcher(capability, payload)
                try:
                    loop = _asyncio.get_running_loop()
                except RuntimeError:
                    # 同步上下文里没运行 loop,把 coroutine 跑到底
                    _asyncio.run(coro)
                else:
                    pending = getattr(self, "_pending_async_report_emits", None)
                    if not isinstance(pending, list):
                        pending = []
                        self._pending_async_report_emits = pending
                    pending.append(loop.create_task(coro))
            except Exception as e:
                logger.warning(f"dispatch {capability} (async) failed: {e}")
                return None
        else:
            try:
                dispatch_custom_event(capability, payload, config=config)
            except Exception as e:
                logger.warning(f"dispatch {capability} failed: {e}")
                return None
        return payload.get("report_id")

    async def _aflush_pending_report_emits(self) -> None:
        """等待 `_emit_report_event` 在 running loop 下挂起的异步派发任务。"""
        pending = getattr(self, "_pending_async_report_emits", None) or []
        self._pending_async_report_emits = []
        if not pending:
            return
        import asyncio as _asyncio

        await _asyncio.gather(*pending, return_exceptions=True)

    async def _aemit_report_event(
        self,
        capability: str,
        parsed: Any,
        config: RunnableConfig,
    ) -> Optional[str]:
        """在异步 Runnable 工具内部派发报告事件，保留父 run 上下文。"""
        if not self._has_report_capability(capability):
            return None
        renderer = get_renderer(capability)
        if renderer is None:
            return None
        ec = getattr(self, "_extra_config", None)
        matched = list(getattr(ec, "matched_skill_packages", None) or []) if ec else []
        payload = renderer(parsed, matched[0] if matched else {})
        if not payload:
            return None
        stable_report_id = self._stable_report_id(capability, config)
        if stable_report_id:
            payload["report_id"] = stable_report_id

        from langchain_core.callbacks import adispatch_custom_event

        await adispatch_custom_event(capability, payload, config=config)
        return payload.get("report_id")

    def _post_process_tool_results(
        self,
        new_messages: list,
        skill_id: int = None,
        event_dispatcher=None,
    ) -> None:
        """deepagent 返回后扫一遍新消息,对映射的 tool 结果触发 report 渲染。

        解决"普通工具(非 Pydantic/StructuredTool)返回值也想结构化展示"的场景:
        LLM 调 analyze_deployment_configurations → ToolMessage.content 是 JSON 字符串,
        后处理器按 tool name 命中 TOOL_RESULT_TO_CAPABILITY,自动 dispatch 报告事件。

        同一 capability 多次触发(LLM 分 namespace 多次调分析工具)会被合并:
        - issues_detail 串接
        - total / problematic / healthy 累加
        - cluster_name 优先用唯一值,多 namespace 时改成 cluster_names 列表
        渲染器拿到的还是单份 parsed,无需自己处理多份。

        不在映射里的 tool 静默跳过。renderer 返 None(数据无效)也静默。

        前端保留模型正文，并在收到本方法派发的完成事件后追加结构化卡片。
        """
        from langchain_core.messages import ToolMessage

        from apps.opspilot.metis.llm.chain.k8s_report_tools import TOOL_RESULT_TO_CAPABILITY, merge_analysis_results

        # 按 capability 累计:同一 capability 多次工具调用,合并成一次 emit
        accumulated: Dict[str, List[Any]] = {}

        for message in new_messages:
            if not isinstance(message, ToolMessage):
                continue
            tool_name = getattr(message, "name", "") or ""
            capability = TOOL_RESULT_TO_CAPABILITY.get(tool_name)
            if not capability:
                continue
            try:
                content = message.content
                if isinstance(content, str):
                    parsed = json.loads(content)
                elif isinstance(content, list):
                    # 偶发:content 是 list[dict](langchain 0.2+ 行为)
                    parsed = content[0] if content and isinstance(content[0], dict) else {"content": content}
                else:
                    parsed = content
            except (json.JSONDecodeError, TypeError, IndexError) as e:
                logger.debug(f"skip {tool_name} post-process (parse failed): {e}")
                continue
            if isinstance(parsed, dict) and parsed.get("_report_emitted_capability") == capability:
                continue
            accumulated.setdefault(capability, []).append(parsed)

        # 每个 capability 合并后 emit 一次(而不是 N 张卡片)
        for capability, parsed_list in accumulated.items():
            if not parsed_list:
                continue
            merged = merge_analysis_results(parsed_list) if len(parsed_list) > 1 else parsed_list[0]
            self._emit_report_event(capability, merged, event_dispatcher=event_dispatcher)

    def _filter_basic_k8s_analysis_loop_calls(self, tool_calls: list, analysis_cache: dict) -> tuple[list, bool]:
        if self._enable_config_analysis_report() and self._enable_repair_diff_report():
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
        if value in {"category", "target", "scope", "severity", "all"}:
            return value
        if value == "namespace" or "空间" in value or "namespace" in value or "schema" in value:
            return "scope"
        if "等级" in value or "severity" in value or "高危" in value or "风险" in value:
            return "severity"
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
            # 走统一的 registry 路径:capability 名 = 事件名,渲染器构造 payload。
            # 不再这里手写 dispatch,新增 report 类型只需 register_renderer()。
            parsed = {"title": title, "cluster_name": cluster_name, "items": items}
            report_id = self._emit_report_event("repair_diff_report", parsed)

            if not report_id:
                # capability 未启用或渲染器返回 None,不阻塞流程
                return f"已收到 {len(items)} 个工作负载的修复对比数据,但当前技能包未声明 repair_diff_report 能力,跳过报告推送。"

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
                description=(
                    "报告组织方式：\n" "- 'scope': 按所属空间聚合\n" "- 'severity': 按风险等级聚合\n" "- 'all': 全部合并为一条\n" "兼容旧值：'target' 按目标聚合，'category' 按问题类别聚合"
                ),
            )

        async def _generate_repair_report(
            title: str,
            context_name: str,
            items: List[dict],
            group_by: str = "target",
            expected_target_count: int = 0,
            target_names: List[str] = None,
            config: RunnableConfig = None,
        ) -> str:
            import uuid
            from itertools import groupby as _groupby

            from langchain_core.callbacks import adispatch_custom_event

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

            elif group_by == "scope":
                from apps.opspilot.metis.llm.chain.repair_report_identity import count_distinct_repair_targets

                raw_items.sort(key=lambda x: (x.get("namespace", ""), x.get("target_name", "")))
                for namespace, group in _groupby(raw_items, key=lambda x: x.get("namespace", "")):
                    group_list = list(group)
                    before_parts = []
                    after_parts = []
                    categories = set()
                    worst_severity = "info"
                    for it in group_list:
                        label = f"# {it.get('target_name', '')} ({it.get('target_type', '')})".rstrip(" ()")
                        summary_text = it.get("summary", "")
                        before_val = it.get("before", "").strip()
                        after_val = it.get("after", "").strip()
                        before_parts.append(f"{label}\n{before_val or _before_snippet_for_issue(summary_text)}")
                        after_parts.append(f"{label}\n{after_val or _after_snippet_for_issue(summary_text)}")
                        categories.add(it.get("category", "") or summary_text)
                        if _severity_order.get(it.get("severity"), 9) < _severity_order.get(worst_severity, 9):
                            worst_severity = it.get("severity", "info")
                    target_count = count_distinct_repair_targets(group_list)
                    display_namespace = namespace or "未指定空间"
                    diff_items.append(
                        {
                            "workload_name": f"{display_namespace}（{target_count} 个目标）",
                            "workload_type": "Scope",
                            "namespace": namespace or "-",
                            "severity": worst_severity,
                            "summary": f"共 {len(group_list)} 项修复：{' | '.join(sorted(categories))}",
                            "before_yaml": "\n\n".join(before_parts),
                            "after_yaml": "\n\n".join(after_parts),
                        }
                    )

            elif group_by == "severity":
                from apps.opspilot.metis.llm.chain.repair_report_identity import count_distinct_repair_targets

                severity_labels = {"critical": "严重", "high": "高危", "warning": "中危", "info": "低危"}
                raw_items.sort(key=lambda x: (_severity_order.get(x.get("severity"), 9), x.get("namespace", ""), x.get("target_name", "")))
                for severity, group in _groupby(raw_items, key=lambda x: x.get("severity", "info")):
                    group_list = list(group)
                    before_parts = []
                    after_parts = []
                    categories = set()
                    for it in group_list:
                        label = f"# {it.get('namespace', '')}/{it.get('target_name', '')}".replace("#/", "# ")
                        summary_text = it.get("summary", "")
                        before_val = it.get("before", "").strip()
                        after_val = it.get("after", "").strip()
                        before_parts.append(f"{label}\n{before_val or _before_snippet_for_issue(summary_text)}")
                        after_parts.append(f"{label}\n{after_val or _after_snippet_for_issue(summary_text)}")
                        categories.add(it.get("category", "") or summary_text)
                    target_count = count_distinct_repair_targets(group_list)
                    diff_items.append(
                        {
                            "workload_name": f"{severity_labels.get(severity, severity)}（{target_count} 个目标）",
                            "workload_type": "Severity",
                            "namespace": "-",
                            "severity": severity,
                            "summary": f"共 {len(group_list)} 项修复：{' | '.join(sorted(categories))}",
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
                from apps.opspilot.metis.llm.chain.repair_report_identity import count_distinct_repair_targets

                target_count = count_distinct_repair_targets(raw_items)
                diff_items.append(
                    {
                        "workload_name": f"全部（{target_count} 个目标）",
                        "workload_type": "All",
                        "namespace": "-",
                        "severity": worst_severity,
                        "summary": f"共 {len(raw_items)} 项修复：{' | '.join(sorted(categories))}",
                        "before_yaml": "\n\n".join(before_parts),
                        "after_yaml": "\n\n".join(after_parts),
                    }
                )

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
                    await adispatch_custom_event(
                        "repair_commands",
                        {
                            "commands_id": str(uuid.uuid4())[:8],
                            "commands_markdown": commands_text,
                        },
                        config=config,
                    )
                except Exception as e:
                    logger.warning(f"dispatch repair_commands failed: {e}")

            # 修复对比与 repair_commands / docx 同路 await 派发（避免后处理丢事件），
            # 但仍受 repair_diff_report capability 门禁约束：未声明能力时不推对比卡。
            emitted_diff_capability = None
            if diff_items:
                if not self._enable_repair_diff_report():
                    logger.warning(
                        "skip repair_diff_report: capability not enabled (items=%s)",
                        len(diff_items),
                    )
                else:
                    try:
                        from apps.opspilot.metis.llm.chain.report_renderers.k8s import render_repair_diff_report

                        diff_payload = render_repair_diff_report(
                            {
                                "title": title,
                                "cluster_name": context_name,
                                "items": diff_items,
                            },
                            {},
                        )
                        if diff_payload:
                            stable_report_id = self._stable_report_id("repair_diff_report", config)
                            if stable_report_id:
                                diff_payload["report_id"] = stable_report_id
                            await adispatch_custom_event("repair_diff_report", diff_payload, config=config)
                            emitted_diff_capability = "repair_diff_report"
                            logger.info(
                                "dispatched repair_diff_report report_id=%s items=%s",
                                diff_payload.get("report_id"),
                                len(diff_items),
                            )
                        else:
                            logger.warning(
                                "repair_diff_report renderer returned empty payload; items=%s",
                                len(diff_items),
                            )
                    except Exception as e:
                        logger.warning(f"dispatch repair_diff_report failed: {e}")

            # 生成 .docx 报告并 dispatch 下载事件
            try:
                from apps.opspilot.metis.llm.tools.kubernetes.report_generator import generate_k8s_report_docx
                from apps.opspilot.services.generated_file_delivery_service import build_generated_file_download_event

                report_data_for_docx = {
                    "cluster_name": context_name,
                    "raw_items": raw_items,
                }
                # DOCX 是双 capability 修复闭环的正式产物，不能因机器负载或
                # 报告条目较多超过固定 5 秒就静默丢弃。生成过程不依赖外部
                # 服务，放在线程中等待完成即可，且不会阻塞事件循环。
                docx_bytes = await asyncio.to_thread(generate_k8s_report_docx, report_data_for_docx)
                filename = f"K8S配置检查报告_{context_name}_{datetime.now().strftime('%Y%m%d')}.docx"
                download_event = build_generated_file_download_event(
                    filename=filename,
                    content_bytes=docx_bytes,
                    mime_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
                )
                await adispatch_custom_event("report_file_download", download_event, config=config)
            except Exception as e:
                logger.warning(f"generate docx report failed: {e}")

            result_parts = [f"已生成修复对比报告，共 {len(raw_items)} 项修复。{_coverage_note}"]
            if commands_text:
                result_parts.append("\n\n修复命令已直接展示给用户（通过界面卡片），你不需要再重复输出命令。" "\n只需简短告知用户：修复命令已在上方展示，请根据实际情况调整后执行。")
            else:
                result_parts.append("\n\n修复建议已在对比报告中展示。")

            payload = {
                "message": "".join(result_parts),
                "title": title,
                "cluster_name": context_name,
                "items": diff_items,
            }
            if emitted_diff_capability:
                payload["_report_emitted_capability"] = emitted_diff_capability
            return json.dumps(payload, ensure_ascii=False)

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

        # 配置分析后的选择与修复报告属于后端确定性状态机，不向模型暴露。
        # 双 capability 门禁、动态选项和报告派发统一由
        # _run_pending_k8s_repair_workflow 执行，避免模型改写选项或打乱顺序。
        return tools

    async def _run_pending_k8s_repair_workflow(
        self,
        messages: list,
        config: RunnableConfig,
        *,
        output_messages: list | None = None,
    ) -> bool:
        """模型漏调选择工具时，确定性完成“选择 → 修复对比”闭环。

        output_messages: 若提供，写入合成 ToolMessage，避免同轮分步循环重复提问。
        """
        if not (self._enable_config_analysis_report() and self._enable_repair_diff_report()):
            return False

        completed_choice = find_completed_k8s_analysis_choice(messages)
        analysis = completed_choice[0] if completed_choice else find_pending_k8s_analysis_choice(messages)
        if not analysis:
            return False

        choice_tool = self._build_choice_tool()
        configurable = (config or {}).get("configurable", {})
        choice_func = getattr(choice_tool, "_request_choice_func", None)
        if choice_func is not None:
            choice_func._configurable = configurable
            choice_func._execution_id = configurable.get("execution_id", "")
            choice_func._node_id = configurable.get("node_id") or "skill_test"

        if completed_choice:
            choice_result = completed_choice[1]
        else:
            choice_result = await choice_tool.ainvoke(build_repair_mode_choice_args(analysis), config=config)
            if output_messages is not None:
                output_messages.append(
                    ToolMessage(
                        name="request_user_choice",
                        tool_call_id=f"deterministic-choice-{uuid.uuid4().hex[:8]}",
                        content=str(choice_result or ""),
                    )
                )
        group_by = self._normalize_repair_group_by(str(choice_result or ""))

        from apps.opspilot.metis.llm.tools.kubernetes.analysis import _take_cached_k8s_analysis_details

        configurable = (config or {}).get("configurable", {})
        deployments = analysis.get("_deployments_full") or _take_cached_k8s_analysis_details(configurable.get("execution_id", "")) or []
        analysis_cache = {
            "deployments": deployments if isinstance(deployments, list) else [],
            "cluster_name": analysis.get("cluster_name") or "Kubernetes",
        }
        repair_tool = self._build_bulk_repair_tool(analysis_cache)
        repair_result = await repair_tool.ainvoke(
            {
                "title": "K8S 配置修复对比",
                "context_name": analysis_cache["cluster_name"],
                "items": [],
                "target_names": [],
                "expected_target_count": int(analysis.get("problematic") or 0),
                "group_by": group_by,
            },
            config=config,
        )
        if output_messages is not None:
            output_messages.append(
                ToolMessage(
                    name="generate_repair_report",
                    tool_call_id=f"deterministic-repair-{uuid.uuid4().hex[:8]}",
                    content=str(repair_result or ""),
                )
            )
        try:
            parsed_repair = json.loads(repair_result) if isinstance(repair_result, str) else repair_result
        except (json.JSONDecodeError, TypeError):
            parsed_repair = None
        if isinstance(parsed_repair, dict) and parsed_repair.get("items") and parsed_repair.get("_report_emitted_capability") != "repair_diff_report":
            await self._aemit_report_event("repair_diff_report", parsed_repair, config=config)
        return True

    @staticmethod
    def _is_unsupported_stream_usage_error(exc: BaseException) -> bool:
        text = str(exc).casefold()
        return "stream_options" in text or "include_usage" in text

    @staticmethod
    def _lightweight_chunk_text(chunk) -> str:
        piece = getattr(chunk, "content", None)
        if isinstance(piece, str):
            return piece
        if isinstance(piece, list):
            parts = []
            for block in piece:
                if isinstance(block, str):
                    parts.append(block)
                elif isinstance(block, dict) and block.get("type") == "text":
                    parts.append(str(block.get("text") or ""))
            return "".join(parts)
        return ""

    @staticmethod
    def _merge_lightweight_stream_response(merged: AIMessage | None, content_parts: list[str]) -> AIMessage:
        if merged is None:
            return AIMessage(content="".join(content_parts))
        if str(merged.content or "").strip() or not content_parts:
            return merged
        return AIMessage(
            content="".join(content_parts),
            additional_kwargs=getattr(merged, "additional_kwargs", {}) or {},
            response_metadata=getattr(merged, "response_metadata", {}) or {},
            usage_metadata=getattr(merged, "usage_metadata", None),
        )

    async def _astream_lightweight_reply(self, astream, light_messages, config) -> AIMessage:
        """流式直答：合并 chunk 以免终包 usage 被正文覆盖；优先带 include_usage。"""

        async def _consume(stream) -> tuple[AIMessage | None, list[str]]:
            content_parts: list[str] = []
            merged: AIMessage | None = None
            async for chunk in stream:
                text = self._lightweight_chunk_text(chunk)
                if text:
                    content_parts.append(text)
                if isinstance(chunk, AIMessageChunk):
                    merged = chunk if merged is None else merged + chunk
                elif isinstance(chunk, AIMessage) and not isinstance(merged, AIMessageChunk):
                    merged = chunk
            return merged, content_parts

        try:
            merged, content_parts = await _consume(astream(light_messages, config=config, stream_usage=True))
            return self._merge_lightweight_stream_response(merged, content_parts)
        except TypeError:
            merged, content_parts = await _consume(astream(light_messages, config=config))
            return self._merge_lightweight_stream_response(merged, content_parts)
        except Exception as exc:
            if not self._is_unsupported_stream_usage_error(exc):
                raise
            merged, content_parts = await _consume(astream(light_messages, config=config))
            return self._merge_lightweight_stream_response(merged, content_parts)

    async def _invoke_lightweight_direct_reply(
        self,
        *,
        llm,
        light_system: str,
        original_messages: list,
        config: dict,
        token_usage_accumulator,
        sandbox_dir: Optional[str] = None,
        log_reason: str = "",
    ) -> dict:
        from apps.opspilot.metis.llm.common.llm_error_diagnostics import (
            classify_llm_error,
            format_llm_empty_response_log,
            format_llm_failure_log,
            summarize_llm_endpoint,
        )

        graph_request = (config or {}).get("configurable", {}).get("graph_request")
        endpoint = summarize_llm_endpoint(graph_request)
        logger.info(
            "DeepAgent 轻量直答: %s system_prompt_len=%s model=%s api_base=%s",
            log_reason or "direct",
            len(light_system),
            endpoint.get("model") or "-",
            endpoint.get("api_base") or "-",
        )
        try:
            # Qwen 等网关要求：仅允许一条 system，且必须在 messages[0]。
            # 图前置节点已写入 SystemMessage，再前置 light_system 会变成
            # [system, system, user...]，触发 400 "System message must be at the beginning."
            light_messages = normalize_messages_for_llm([SystemMessage(content=light_system), *list(original_messages or [])])
            light_messages = await self._prepare_messages_for_llm(light_messages, graph_request)
            response: AIMessage | None = None
            astream = getattr(llm, "astream", None)
            if callable(astream):
                response = await self._astream_lightweight_reply(astream, light_messages, config)
            else:
                response = await llm.ainvoke(light_messages, config=config)
                if not isinstance(response, AIMessage):
                    response = AIMessage(content=str(getattr(response, "content", "") or ""))
            if not str(getattr(response, "content", "") or "").strip():
                logger.warning(
                    format_llm_empty_response_log(
                        stage="lightweight_direct_reply",
                        endpoint=endpoint,
                        extra=f"reason={log_reason or 'direct'}",
                    )
                )
            if isinstance(token_usage_accumulator, TokenUsageAccumulator):
                token_usage_accumulator.middleware_tracking = True
                token_usage_accumulator.add(None, response, visible_tools=[])
            return {"messages": [response]}
        except Exception as exc:
            classification = classify_llm_error(exc)
            logger.exception(
                format_llm_failure_log(
                    stage="lightweight_direct_reply",
                    classification=classification,
                    endpoint=endpoint,
                )
            )
            raise
        finally:
            if sandbox_dir:
                self._cleanup_sandbox(sandbox_dir)

    async def build_deepagent_nodes(  # noqa: C901
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
            # 惰性导入：避免 apps.opspilot.metis.llm.agent.__init__ → deep_agent → node 循环依赖
            from apps.opspilot.metis.llm.agent.tool_execution_planner import (
                TOOL_FAILURE_AUTHZ,
                TOOL_FAILURE_CONFIG,
                TOOL_FAILURE_INTERNAL,
                USE_SKILLS_TOOL_NAME,
                CompletedExecutionStep,
                ToolExecutionPlan,
                ToolExecutionPlanner,
                ToolPlanningError,
                classify_tool_failure_kind,
                drop_k8s_followup_steps_after_unresolved_target,
                is_context_size_error,
                is_non_replanable_tool_failure,
                is_tool_result_failure,
                merge_replanned_pending_steps,
            )
            from apps.opspilot.metis.llm.tools.kubernetes.data_collection import k8s_target_lookup_exhausted_from_messages

            graph_request = config["configurable"]["graph_request"]

            # 创建系统提示
            final_system_prompt = TemplateLoader.render_template(
                "prompts/graph/deepagent_system_message",
                {"user_system_message": graph_request.system_message_prompt, "additional_system_prompt": additional_system_prompt or ""},
            )

            llm = self.get_llm_client(graph_request)
            if getattr(graph_request, "max_model_calls", 0) == 1:
                prepared = await self._prepare_messages_for_llm(
                    normalize_messages_for_llm([SystemMessage(content=final_system_prompt), *list(state.get("messages") or [])]),
                    graph_request,
                )
                response = await llm.ainvoke(
                    prepared,
                    config=config,
                )
                return {"messages": [response]}
            tools = self._collect_deepagent_tools(graph_request)
            registered_tools = list(tools)
            original_messages = list(state.get("messages") or [])
            collected_output_messages: List[BaseMessage] = []
            skill_packages = self._resolve_skill_packages(graph_request)
            has_skill_packages = bool(skill_packages)
            # 渐进路径推迟沙箱物化：空计划寒暄不应为技能包付 DeepAgent/FS 税。
            backend, skill_sources, sandbox_dir = None, [], None
            interrupt_on = self._build_interrupt_on(graph_request, tools)
            token_usage_accumulator = config["configurable"].get("token_usage_accumulator")

            # 无业务工具、无技能包：跳过规划器与 DeepAgent 内置 FS/execute 工具，直接短 system 回答。
            if self._should_use_lightweight_direct_reply(
                registered_tools,
                ["/skills/"] if has_skill_packages else [],
            ):
                light_system = self._build_lightweight_system_prompt(getattr(graph_request, "system_message_prompt", "") or "")
                if additional_system_prompt:
                    light_system = f"{light_system}\n\n{additional_system_prompt}"
                return await self._invoke_lightweight_direct_reply(
                    llm=llm,
                    light_system=light_system,
                    original_messages=original_messages,
                    config=config,
                    token_usage_accumulator=token_usage_accumulator,
                    log_reason="tools=0, skills=0",
                )

            # 紧急关闭：回退全量 Schema + 单次 DeepAgent 调用
            if not is_progressive_tools_enabled():
                backend, skill_sources, sandbox_dir = self._build_skill_backend_and_sources(graph_request)
                agent_kwargs = self._build_deep_agent_kwargs(
                    llm=llm,
                    registered_tools=registered_tools,
                    final_system_prompt=final_system_prompt,
                    runtime_middleware=self._build_legacy_deep_agent_middleware(token_usage_accumulator, graph_request),
                    backend=backend,
                    skill_sources=skill_sources,
                    interrupt_on=interrupt_on,
                )
                deep_agent = create_deep_agent(**agent_kwargs)
                ec = getattr(self, "_extra_config", None)
                matched_packages = list(getattr(ec, "matched_skill_packages", None) or []) if ec else []
                deep_config = {
                    **config,
                    "recursion_limit": 100,
                    "configurable": {
                        **config.get("configurable", {}),
                        "enabled_report_capabilities": sorted(self._enabled_report_capabilities()),
                        "report_package_context": matched_packages[0] if matched_packages else {},
                    },
                }
                try:
                    deep_input_messages = await self._prepare_messages_for_llm(
                        without_system_messages(original_messages),
                        graph_request,
                        tools=registered_tools,
                    )
                    result = await deep_agent.ainvoke({"messages": deep_input_messages}, config=deep_config)
                except Exception as _await_exc:
                    try:
                        err_prompt = (
                            f"上一轮工具执行失败(异常 {type(_await_exc).__name__}:"
                            f" {str(_await_exc)[:800]}),请用中文告诉用户失败原因,"
                            "并给出可执行的替代方案(例如改用白名单内的命令 uvx / python -m,"
                            "或换其他可用工具)。不要再尝试调同样的命令。"
                        )
                        fallback_messages = await self._prepare_messages_for_llm(
                            original_messages + [HumanMessage(content=err_prompt)],
                            graph_request,
                        )
                        fallback_response = await llm.ainvoke(fallback_messages, config=config)
                        fallback_text = str(getattr(fallback_response, "content", "") or "").strip()
                        if not fallback_text:
                            fallback_text = (
                                f"工具执行失败:{type(_await_exc).__name__}: {str(_await_exc)[:400]}\n" "请尝试改用白名单内的等效命令(uvx / python -m 等)或换其他工具。"
                            )
                        return {"messages": [AIMessage(content=fallback_text)]}
                    except Exception:
                        return {
                            "messages": [
                                AIMessage(
                                    content=(
                                        f"工具执行失败:{type(_await_exc).__name__}: {str(_await_exc)[:400]}\n" "请尝试改用白名单内的等效命令(uvx / python -m 等)或换其他工具。"
                                    )
                                )
                            ]
                        }
                finally:
                    if sandbox_dir:
                        self._cleanup_sandbox(sandbox_dir)

                final_messages = result.get("messages", [])
                if not final_messages:
                    return {"messages": [AIMessage(content="DeepAgent 未返回任何消息")]}
                new_messages = final_messages[len(deep_input_messages) :]
                if not new_messages:
                    return {"messages": [AIMessage(content="DeepAgent 未产生新的响应")]}
                try:

                    async def _emit_via_async_config_legacy(capability: str, payload: dict):
                        await adispatch_custom_event(capability, payload, config=config)

                    self._post_process_tool_results(
                        new_messages,
                        skill_id=getattr(graph_request, "skill_id", None),
                        event_dispatcher=_emit_via_async_config_legacy,
                    )
                    await self._aflush_pending_report_emits()
                    await self._run_pending_k8s_repair_workflow(
                        final_messages,
                        config,
                        output_messages=new_messages,
                    )
                except Exception:
                    raise
                return {"messages": new_messages}

            planner_llm = self.get_llm_client(graph_request, disable_stream=True, isolated=True)
            planner = ToolExecutionPlanner(
                planner_llm,
                accumulator=(token_usage_accumulator if isinstance(token_usage_accumulator, TokenUsageAccumulator) else None),
            )

            planning_question = str(getattr(graph_request, "user_message", "") or getattr(graph_request, "graph_user_message", "") or "").strip()
            if not planning_question:
                for message in reversed(original_messages):
                    if isinstance(message, HumanMessage):
                        planning_question = str(message.content or "").strip()
                        break

            async def _emit_planned_execution_status(phase: str, **payload: Any) -> None:
                """规划阶段心跳：让前端显示「正在规划」而非长时间空白。"""
                try:
                    await adispatch_custom_event(
                        "planned_execution_status",
                        {"phase": phase, **payload},
                        config=config,
                    )
                except Exception as emit_exc:
                    logger.debug("规划状态事件派发跳过: %s (%s)", phase, emit_exc)

            await _emit_planned_execution_status("planning")
            try:
                plan = await planner.plan(
                    planning_question,
                    tools,
                    skill_packages=skill_packages,
                    config=config,
                    agent_system_prompt=str(getattr(graph_request, "system_message_prompt", "") or ""),
                )
            except Exception as planning_exc:
                # 规划失败时保持零工具可见，仍允许模型直接回答，绝不退回全量工具。
                logger.exception(
                    "DeepAgent 工具执行规划失败，将以零工具模式回答: %s",
                    planning_exc,
                )
                plan = ToolExecutionPlan(goal=planning_question, steps=[])
                await _emit_planned_execution_status("idle", reason="planning_failed")
            else:
                await _emit_planned_execution_status(
                    "planned",
                    step_count=len(plan.steps),
                    goal=str(plan.goal or "")[:200],
                )

            planned_tool_names = list(dict.fromkeys(tool_name for step in plan.steps for tool_name in step.tools))
            logger.info(
                "DeepAgent 工具执行计划: goal=%s, registered_tool_count=%s, skill_count=%s, " "planned_tools=%s, steps=%s",
                plan.goal,
                len(registered_tools),
                len(skill_packages),
                planned_tool_names,
                [
                    {
                        "objective": step.objective,
                        "tools": step.tools,
                    }
                    for step in plan.steps
                ],
            )

            # 空计划（含已启用技能包的寒暄）：跳过 DeepAgent/FS，轻量直答。
            if self._should_use_lightweight_after_empty_plan(plan):
                await _emit_planned_execution_status("idle", reason="empty_plan")
                light_system = self._build_lightweight_system_prompt(
                    getattr(graph_request, "system_message_prompt", "") or "",
                    skills_available=has_skill_packages,
                )
                if additional_system_prompt:
                    light_system = f"{light_system}\n\n{additional_system_prompt}"
                return await self._invoke_lightweight_direct_reply(
                    llm=llm,
                    light_system=light_system,
                    original_messages=original_messages,
                    config=config,
                    token_usage_accumulator=token_usage_accumulator,
                    sandbox_dir=sandbox_dir,
                    log_reason=f"empty_plan, skills={len(skill_packages)}",
                )

            def _plan_needs_skill_runtime(candidate_plan) -> bool:
                return any(USE_SKILLS_TOOL_NAME in (step.tools or []) for step in (getattr(candidate_plan, "steps", None) or []))

            needs_skill_runtime = has_skill_packages and _plan_needs_skill_runtime(plan)
            if needs_skill_runtime:
                backend, skill_sources, sandbox_dir = self._build_skill_backend_and_sources(graph_request)

            skills_only_plan = bool(skill_sources) and self._plan_is_skills_only(plan)
            active_tools = []
            always_visible, hidden_tools = self._build_planned_execution_tool_visibility(
                skill_sources=skill_sources,
                skills_only_plan=skills_only_plan,
                registered_tools=registered_tools,
            )
            # 无技能运行时时用短 system，避免 deepagent 技能/沙箱长文案挤爆小上下文模型。
            if not skill_sources:
                final_system_prompt = TemplateLoader.render_template(
                    "prompts/graph/base_node_system_message",
                    {"user_system_message": graph_request.system_message_prompt},
                )
                if additional_system_prompt:
                    final_system_prompt = f"{final_system_prompt}\n\n{additional_system_prompt}"
            runtime_middleware, visibility_middleware, limit_middleware, skill_guard = self._build_planned_execution_runtime_middleware(
                registered_tools=registered_tools,
                active_tools=active_tools,
                always_visible=always_visible,
                hidden_tools=hidden_tools,
                skills_only_plan=skills_only_plan,
                graph_request=graph_request,
                token_usage_accumulator=token_usage_accumulator,
            )
            final_system_prompt = self._append_planned_execution_step_prompt(final_system_prompt)

            def _build_deep_agent():
                return create_deep_agent(
                    **self._build_deep_agent_kwargs(
                        llm=llm,
                        registered_tools=registered_tools,
                        final_system_prompt=final_system_prompt,
                        runtime_middleware=runtime_middleware,
                        backend=backend,
                        skill_sources=skill_sources,
                        interrupt_on=interrupt_on,
                    )
                )

            deep_agent = _build_deep_agent()

            def _ensure_skill_runtime_for_plan(candidate_plan) -> None:
                """重规划若新挂上技能运行时，补物化沙箱并重建 DeepAgent。"""
                nonlocal backend, skill_sources, sandbox_dir, deep_agent, always_visible, final_system_prompt
                if not has_skill_packages or not _plan_needs_skill_runtime(candidate_plan):
                    return
                if skill_sources:
                    return
                backend, skill_sources, sandbox_dir = self._build_skill_backend_and_sources(graph_request)
                if skill_sources:
                    skills_only = self._plan_is_skills_only(candidate_plan)
                    skill_guard.enabled = skills_only
                    if skills_only:
                        always_visible -= set(PLANNED_EXECUTION_ALWAYS_VISIBLE_FS_TOOLS)
                        always_visible.add("execute")
                        visibility_middleware._hidden_tools = frozenset(
                            name for name in PLANNED_EXECUTION_HIDDEN_DEEPAGENT_TOOLS if name != "execute"
                        )
                    else:
                        always_visible |= set(PLANNED_EXECUTION_ALWAYS_VISIBLE_FS_TOOLS)
                        always_visible.discard("execute")
                        visibility_middleware._hidden_tools = frozenset(PLANNED_EXECUTION_HIDDEN_DEEPAGENT_TOOLS)
                    visibility_middleware._always_visible_tools = frozenset(always_visible)
                    # 技能运行时启用后切回完整 deepagent system（含技能说明）。
                    final_system_prompt = self._append_planned_execution_step_prompt(
                        TemplateLoader.render_template(
                            "prompts/graph/deepagent_system_message",
                            {
                                "user_system_message": graph_request.system_message_prompt,
                                "additional_system_prompt": additional_system_prompt or "",
                            },
                        )
                    )
                    deep_agent = _build_deep_agent()

            # DeepAgent 返回 CompiledStateGraph；提高递归限制以容纳复杂任务
            ec = getattr(self, "_extra_config", None)
            matched_packages = list(getattr(ec, "matched_skill_packages", None) or []) if ec else []
            deep_config = {
                **config,
                "recursion_limit": 100,
                "configurable": {
                    **config.get("configurable", {}),
                    "enabled_report_capabilities": sorted(self._enabled_report_capabilities()),
                    "report_package_context": matched_packages[0] if matched_packages else {},
                },
            }

            tool_by_name = {str(getattr(tool, "name", "") or ""): tool for tool in tools if str(getattr(tool, "name", "") or "")}

            def _internal_message(content: str) -> HumanMessage:
                return HumanMessage(
                    content=content,
                    additional_kwargs={"opspilot_planned_execution": True},
                )

            def _step_failure(messages: List[BaseMessage]) -> str:
                for message in reversed(messages):
                    if not isinstance(message, ToolMessage):
                        continue
                    status = str(getattr(message, "status", "") or "").lower()
                    content = message.content
                    # 技能脚本失败带 [OPSPILOT_SKILL_RESULT]，不算 is_tool_result_failure，
                    # 但仍按与业务工具同一套分型收口凭据/配置/实现异常。
                    if is_non_replanable_tool_failure(content, status) or is_tool_result_failure(content, status):
                        tool_name = str(getattr(message, "name", "") or "未知工具")
                        return f"工具 {tool_name} 执行失败: {str(content)[:800]}"
                return ""

            def _compact_agent_state_with_summaries(*, overflow: bool = False) -> Dict[str, Any]:
                """用步骤摘要替换完整工具历史，避免 8K 窗口在后续步再次撑爆。"""
                summary_lines = [f"- {item.objective}: {item.result[:400]}" for item in completed_steps]
                if overflow:
                    header = "【上下文压缩】前序步骤因模型上下文窗口不足已跳过或截断。" "以下为已完成步骤摘要，请仅基于摘要与用户问题继续，不要重复已完成步骤。\n"
                else:
                    header = "【步骤摘要】以下为已完成步骤摘要，请仅基于摘要与用户问题继续，不要重复已完成步骤。\n"
                summary = _internal_message(header + ("\n".join(summary_lines) if summary_lines else "无"))
                return {"messages": without_system_messages(original_messages) + [summary]}

            def _step_summary(messages: List[BaseMessage]) -> str:
                for message in reversed(messages):
                    if isinstance(message, AIMessage):
                        text = str(message.content or "").strip()
                        if text:
                            return text[:1200]
                for message in reversed(messages):
                    if isinstance(message, ToolMessage):
                        return str(message.content or "")[:1200]
                return "步骤已完成"

            def _resolve_step_tools(step_tool_names: List[str]) -> list:
                selected = [tool_by_name[name] for name in step_tool_names if name in tool_by_name]
                selected_names = {getattr(tool, "name", "") for tool in selected}
                for name in PLANNED_EXECUTION_ALWAYS_ON_BUSINESS_TOOLS:
                    if name in tool_by_name and name not in selected_names:
                        selected.append(tool_by_name[name])
                return selected

            async def _emit_step_boundary(event_name: str, payload: dict) -> None:
                try:
                    await adispatch_custom_event(event_name, payload, config=config)
                except Exception as emit_exc:
                    # 单测直接调 wrapper 时缺少 parent run id，属预期；真实 astream_events 路径可发出。
                    logger.debug("分步边界事件派发跳过: %s (%s)", event_name, emit_exc)

            def _collect_output_messages(messages: List[BaseMessage]) -> None:
                """步间压缩会丢弃完整工具历史；对外返回需单独累积每步产出。"""
                for message in messages:
                    if isinstance(message, HumanMessage) and message.additional_kwargs.get("opspilot_planned_execution"):
                        continue
                    collected_output_messages.append(message)

            async def _maybe_run_repair_workflow() -> None:
                """分析步结束后立刻推进选择/修复，避免等最终总结时用户已以为流程中断。"""
                repair_history = list(original_messages) + list(collected_output_messages)
                await self._run_pending_k8s_repair_workflow(
                    repair_history,
                    config,
                    output_messages=collected_output_messages,
                )

            try:
                completed_steps: List[CompletedExecutionStep] = []
                pending_steps = list(plan.steps)
                agent_state: Dict[str, Any] = {"messages": without_system_messages(original_messages)}
                replan_count = 0
                total_steps = len(plan.steps)

                while pending_steps:
                    step = pending_steps.pop(0)
                    step_index = len(completed_steps) + 1
                    active_tools[:] = _resolve_step_tools(step.tools)
                    visibility_middleware.include_always_visible = True
                    visible_names = [getattr(tool, "name", "") for tool in active_tools]
                    await _emit_step_boundary(
                        "planned_execution_step",
                        {
                            "phase": "start",
                            "step_index": step_index,
                            "total_steps": total_steps,
                            "objective": step.objective,
                            "tools": visible_names,
                        },
                    )
                    limit_middleware.reset_step_continues()
                    step_guidance = ""
                    if skills_only_plan or (
                        USE_SKILLS_TOOL_NAME in (step.tools or []) and not any(t != USE_SKILLS_TOOL_NAME for t in (step.tools or []))
                    ):
                        step_guidance = "\n" + self._skill_only_step_guidance(skill_packages)
                    else:
                        step_guidance = "\n" + self._planned_tool_step_guidance()
                    step_message = _internal_message(
                        f"执行计划当前步骤：{step.objective}\n"
                        f"本步骤计划工具：{', '.join(step.tools) or '无'}。\n"
                        f"本步骤当前可见工具：{', '.join(visible_names) or '无'} "
                        f"（含文件/交互等常驻工具）。\n"
                        "只完成本步骤；取得足够证据后立即结束，不要处理后续步骤。"
                        f"{step_guidance}"
                    )
                    step_payload = {
                        **agent_state,
                        "messages": list(agent_state.get("messages") or []) + [step_message],
                    }
                    step_finished = False
                    replanned = False

                    async def _replan_remaining(failure_text: str, extra_messages: List[BaseMessage] | None = None) -> None:
                        nonlocal pending_steps, total_steps, replan_count, replanned, step_finished, agent_state
                        leftover_steps = list(pending_steps)
                        replan_count += 1
                        await _emit_planned_execution_status("replanning", replan_count=replan_count)
                        replacement = await planner.plan(
                            planning_question,
                            tools,
                            completed_steps=completed_steps,
                            failure=failure_text,
                            skill_packages=skill_packages,
                            config=config,
                            agent_system_prompt=str(getattr(graph_request, "system_message_prompt", "") or ""),
                        )
                        _ensure_skill_runtime_for_plan(replacement)
                        pending_steps = merge_replanned_pending_steps(replacement.steps, leftover_steps)
                        completed_steps.append(
                            CompletedExecutionStep(
                                objective=step.objective,
                                result=_step_summary(extra_messages or []) or failure_text[:400],
                            )
                        )
                        await _emit_step_boundary(
                            "planned_execution_step",
                            {
                                "phase": "end",
                                "step_index": step_index,
                                "total_steps": total_steps,
                                "objective": step.objective,
                                "tools": list(step.tools),
                                "status": "failed",
                                "error": failure_text[:800],
                            },
                        )
                        total_steps = len(completed_steps) + len(pending_steps)
                        await _emit_planned_execution_status(
                            "planned",
                            step_count=total_steps,
                            replan_count=replan_count,
                        )
                        logger.warning(
                            "DeepAgent 当前步骤已重规划并保留未覆盖后续步: count=%s, failure=%s, steps=%s",
                            replan_count,
                            failure_text,
                            [item.objective for item in pending_steps],
                        )
                        agent_state = _compact_agent_state_with_summaries(overflow=False)
                        replanned = True
                        step_finished = True

                    def _non_replanable_status(failure_text: str) -> str:
                        kind = classify_tool_failure_kind(failure_text)
                        if kind == TOOL_FAILURE_AUTHZ:
                            return "failed_permission"
                        if kind == TOOL_FAILURE_CONFIG:
                            return "failed_config"
                        if kind == TOOL_FAILURE_INTERNAL:
                            return "failed_internal"
                        return "failed_auth"

                    async def _abort_unrecoverable_step(failure_text: str, extra_messages: List[BaseMessage] | None = None) -> None:
                        nonlocal agent_state, step_finished
                        logger.warning(
                            "DeepAgent 步骤因凭据/权限/配置失败，跳过重规划并收口: %s",
                            failure_text[:400],
                        )
                        completed_steps.append(
                            CompletedExecutionStep(
                                objective=step.objective,
                                result=_step_summary(extra_messages or []) or failure_text[:400],
                            )
                        )
                        await _emit_step_boundary(
                            "planned_execution_step",
                            {
                                "phase": "end",
                                "step_index": step_index,
                                "total_steps": total_steps,
                                "objective": step.objective,
                                "tools": list(step.tools),
                                "status": _non_replanable_status(failure_text),
                                "error": failure_text[:800],
                            },
                        )
                        agent_state = _compact_agent_state_with_summaries(overflow=False)
                        pending_steps.clear()
                        step_finished = True

                    while not step_finished:
                        try:
                            step_payload["messages"] = await self._prepare_messages_for_llm(
                                list(step_payload.get("messages") or []),
                                graph_request,
                                tools=active_tools,
                            )
                            step_result = await deep_agent.ainvoke(
                                step_payload,
                                config=deep_config,
                            )
                        except Exception as step_exc:
                            failure = f"步骤“{step.objective}”执行异常 " f"{type(step_exc).__name__}: {str(step_exc)[:800]}"
                            # 上下文溢出：不带着全量工具目录重规划，但压缩上下文后继续后续步骤。
                            if is_context_size_error(step_exc):
                                logger.warning(
                                    "DeepAgent 步骤因上下文窗口不足失败，跳过当前步并继续后续步骤: %s",
                                    failure,
                                )
                                completed_steps.append(
                                    CompletedExecutionStep(
                                        objective=step.objective,
                                        result="本步骤因模型上下文窗口不足未能执行。",
                                    )
                                )
                                await _emit_step_boundary(
                                    "planned_execution_step",
                                    {
                                        "phase": "end",
                                        "step_index": step_index,
                                        "total_steps": total_steps,
                                        "objective": step.objective,
                                        "tools": list(step.tools),
                                        "status": "skipped_context_overflow",
                                    },
                                )
                                agent_state = _compact_agent_state_with_summaries(overflow=True)
                                step_finished = True
                                break
                            if is_non_replanable_tool_failure(failure):
                                await _abort_unrecoverable_step(failure)
                                break
                            if replan_count >= 2:
                                raise
                            await _replan_remaining(failure)
                            break

                        result_messages = list(step_result.get("messages") or [])
                        step_messages = result_messages[len(step_payload["messages"]) :]
                        limit_kind = detect_limit_kind(step_messages)
                        if limit_kind:
                            _collect_output_messages(step_messages)
                            agent_state = step_result
                            should_continue = await ask_limit_continue(
                                kind=limit_kind,
                                step_objective=step.objective,
                                config=config,
                            )
                            if should_continue and limit_middleware.grant_continue(limit_kind):
                                logger.info(
                                    "DeepAgent 步骤限制续跑: kind=%s, objective=%s, continue_count=%s",
                                    limit_kind,
                                    step.objective,
                                    limit_middleware.continue_count,
                                )
                                continue_msg = _internal_message("用户选择继续当前步骤。请从中断处接着完成，" "不要重复已成功的工具调用；证据足够后立即结束。")
                                step_payload = {
                                    **agent_state,
                                    "messages": list(agent_state.get("messages") or []) + [continue_msg],
                                }
                                continue
                            completed_steps.append(
                                CompletedExecutionStep(
                                    objective=step.objective,
                                    result=_step_summary(step_messages) or "本步骤因调用/预算上限提前结束。",
                                )
                            )
                            agent_state = _compact_agent_state_with_summaries(overflow=False)
                            await _emit_step_boundary(
                                "planned_execution_step",
                                {
                                    "phase": "end",
                                    "step_index": step_index,
                                    "total_steps": total_steps,
                                    "objective": step.objective,
                                    "tools": list(step.tools),
                                    "status": f"limited_{limit_kind}",
                                },
                            )
                            step_finished = True
                            break

                        failure = _step_failure(step_messages)
                        agent_state = step_result
                        if k8s_target_lookup_exhausted_from_messages(step_messages):
                            _collect_output_messages(step_messages)
                            remaining_steps = drop_k8s_followup_steps_after_unresolved_target(pending_steps)
                            logger.info(
                                "DeepAgent k8s 目标反查已收口，跳过后续需 namespace 步骤 dropped=%s",
                                len(pending_steps) - len(remaining_steps),
                            )
                            completed_steps.append(
                                CompletedExecutionStep(
                                    objective=step.objective,
                                    result=_step_summary(step_messages) or "当前集群无法定位该告警对象。",
                                )
                            )
                            pending_steps = remaining_steps
                            agent_state = _compact_agent_state_with_summaries(overflow=False)
                            await _emit_step_boundary(
                                "planned_execution_step",
                                {
                                    "phase": "end",
                                    "step_index": step_index,
                                    "total_steps": total_steps,
                                    "objective": step.objective,
                                    "tools": list(step.tools),
                                    "status": "target_unresolved",
                                },
                            )
                            step_finished = True
                            break
                        if failure:
                            _collect_output_messages(step_messages)
                            if is_context_size_error(failure):
                                logger.warning(
                                    "DeepAgent 步骤工具结果提示上下文不足，跳过当前步并继续后续步骤: %s",
                                    failure,
                                )
                                completed_steps.append(
                                    CompletedExecutionStep(
                                        objective=step.objective,
                                        result="本步骤因模型上下文窗口不足未能完成。",
                                    )
                                )
                                await _emit_step_boundary(
                                    "planned_execution_step",
                                    {
                                        "phase": "end",
                                        "step_index": step_index,
                                        "total_steps": total_steps,
                                        "objective": step.objective,
                                        "tools": list(step.tools),
                                        "status": "skipped_context_overflow",
                                    },
                                )
                                agent_state = _compact_agent_state_with_summaries(overflow=True)
                                step_finished = True
                                break
                            if is_non_replanable_tool_failure(failure):
                                await _abort_unrecoverable_step(failure, extra_messages=step_messages)
                                break
                            if replan_count >= 2:
                                raise ToolPlanningError(failure)
                            await _replan_remaining(failure, extra_messages=step_messages)
                            break

                        _collect_output_messages(step_messages)
                        # 仅在本步实际跑过配置分析时提前推进修复闭环，避免列表/诊断步后抢弹选择卡。
                        if "analyze_deployment_configurations" in (step.tools or []):
                            await _maybe_run_repair_workflow()
                        completed_steps.append(
                            CompletedExecutionStep(
                                objective=step.objective,
                                result=_step_summary(step_messages),
                            )
                        )
                        # 步间只保留摘要，避免巨型 diagnose/logs 结果拖垮后续步与最终总结。
                        agent_state = _compact_agent_state_with_summaries(overflow=False)
                        await _emit_step_boundary(
                            "planned_execution_step",
                            {
                                "phase": "end",
                                "step_index": step_index,
                                "total_steps": total_steps,
                                "objective": step.objective,
                                "tools": list(step.tools),
                            },
                        )
                        step_finished = True

                    if replanned:
                        continue

                active_tools.clear()
                visibility_middleware.include_always_visible = False
                limit_middleware.enforce_limits = False
                # 若分析步因上限提前结束，仍要在最终总结前补上修复闭环。
                await _maybe_run_repair_workflow()
                completed_text = "\n".join(f"- {step.objective}: {step.result}" for step in completed_steps) or "没有需要执行工具的步骤"
                repair_already_done = any(
                    getattr(message, "type", "") == "tool" and getattr(message, "name", "") == "generate_repair_report"
                    for message in collected_output_messages
                )
                if repair_already_done:
                    final_message = _internal_message(
                        f"工具执行计划目标：{plan.goal or planning_question}\n"
                        f"已完成步骤及结果：\n{completed_text}\n\n"
                        "配置检查报告与修复对比已通过界面卡片展示。"
                        "当前没有可用工具，不要继续调用工具；"
                        "请用一两句告知用户查看上方报告与修复建议，不要重复 Markdown 表格或声称数据被截断。"
                    )
                elif len(completed_steps) == 1 and self._planned_step_already_answered(collected_output_messages):
                    # 单步已经把答案写进正文（技能表 / 工具一两句话）。
                    # 再跑总结轮会换个说法复述，用户看到两份结果。
                    result = {"messages": list(agent_state.get("messages") or [])}
                    final_message = None
                else:
                    final_message = _internal_message(
                        f"工具执行计划目标：{plan.goal or planning_question}\n"
                        f"已完成步骤及结果：\n{completed_text}\n\n"
                        "现在向用户给出最终答案。当前没有可用工具，不要继续调用工具；"
                        "请基于已有证据直接总结结论、依据和下一步建议。"
                        "用户已经看过步骤里的表格或清单时，不要再输出表格、不要重复名单，最多补一两句。"
                    )
                if final_message is not None:
                    final_payload = {
                        **agent_state,
                        "messages": list(agent_state.get("messages") or []) + [final_message],
                    }
                    final_payload["messages"] = await self._prepare_messages_for_llm(
                        list(final_payload.get("messages") or []),
                        graph_request,
                    )
                    result = await deep_agent.ainvoke(
                        final_payload,
                        config=deep_config,
                    )
                    final_messages = list(result.get("messages") or [])
                    _collect_output_messages(final_messages[len(final_payload["messages"]) :])
            except Exception as _await_exc:
                # deepagent 框架层异常(典型:execute 工具撞 sandbox 命令白名单)会把整
                # 个 graph 标 ERROR,LLM 没机会拿到 ToolMessage 写 follow-up。
                # 上下文不足时不要再喂长 system/工具目录给模型“解释失败”，避免二次浪费。
                if is_context_size_error(_await_exc):
                    logger.warning(
                        "DeepAgent 因上下文窗口不足失败，直接返回短提示: %s",
                        str(_await_exc)[:400],
                    )
                    return {"messages": [AIMessage(content=("当前模型上下文窗口不足，无法完成本次带工具的诊断。" "请换用更大上下文的模型，或减少启用的工具类别后再试。"))]}
                try:
                    err_prompt = (
                        f"上一轮工具执行失败(异常 {type(_await_exc).__name__}:"
                        f" {str(_await_exc)[:800]}),请用中文告诉用户失败原因,"
                        "并给出可执行的替代方案(例如改用白名单内的命令 uvx / python -m,"
                        "或换其他可用工具)。不要再尝试调同样的命令。"
                    )
                    fallback_messages = await self._prepare_messages_for_llm(
                        original_messages + [HumanMessage(content=err_prompt)],
                        graph_request,
                    )
                    fallback_response = await llm.ainvoke(fallback_messages, config=config)
                    fallback_text = str(getattr(fallback_response, "content", "") or "").strip()
                    if not fallback_text:
                        fallback_text = f"工具执行失败:{type(_await_exc).__name__}: {str(_await_exc)[:400]}\n" "请尝试改用白名单内的等效命令(uvx / python -m 等)或换其他工具。"
                    return {"messages": [AIMessage(content=fallback_text)]}
                except Exception:
                    return {
                        "messages": [
                            AIMessage(
                                content=f"工具执行失败:{type(_await_exc).__name__}: {str(_await_exc)[:400]}\n" "请尝试改用白名单内的等效命令(uvx / python -m 等)或换其他工具。"
                            )
                        ]
                    }
            finally:
                # 用完即弃：销毁本次运行的一次性技能沙箱目录
                # _cleanup_sandbox 内部有 None 守卫,但这里再写一次防御:
                # sandbox_dir 只在 _build_skill_backend_and_sources 成功返回时
                # 才会被赋值,setup 阶段抛错时这个变量不存在,直接 finally 会 NameError。
                if sandbox_dir:
                    self._cleanup_sandbox(sandbox_dir)

            # 分步执行路径已单独累积对外消息；其余路径仍从最终 state 截取新增消息。
            final_messages = result.get("messages", [])
            if collected_output_messages:
                new_messages = collected_output_messages
            else:
                if not final_messages:
                    return {"messages": [AIMessage(content="DeepAgent 未返回任何消息")]}
                input_message_count = len(original_messages)
                new_messages = [
                    message
                    for message in final_messages[input_message_count:]
                    if not (isinstance(message, HumanMessage) and message.additional_kwargs.get("opspilot_planned_execution"))
                ]

            if not new_messages:
                return {"messages": [AIMessage(content="DeepAgent 未产生新的响应")]}

            # 后处理:扫新消息里的 ToolMessage,按 TOOL_RESULT_TO_CAPABILITY 触发
            # report 渲染。这样普通工具(LLM 不需要显式调 Pydantic tool)也能
            # 自动产出结构化报告事件。前端保留模型正文，并按事件到达顺序
            # 追加结构化卡片；同一执行内复用 report_id，避免重复卡片。
            # 深 agent 异步包装节点不在 langchain runnable 回调树里,直接调
            # `dispatch_custom_event` 会因缺 parent run id 静默失败,所以走
            # `adispatch_custom_event` 并把 `config` 传进去,让事件能正确 emit。
            try:

                async def _emit_via_async_config(capability: str, payload: dict):
                    await adispatch_custom_event(capability, payload, config=config)

                self._post_process_tool_results(
                    new_messages,
                    skill_id=getattr(graph_request, "skill_id", None),
                    event_dispatcher=_emit_via_async_config,
                )
                await self._aflush_pending_report_emits()
                # 报告后处理只看本轮新增消息，避免重复派发。
                # 修复状态机必须能看到 analyze ToolMessage：分步执行会在步间把
                # agent_state 压成摘要，final_messages 往往已丢失分析结果；
                # 此时应使用 original + collected_output（含各步工具结果）。
                # 非分步路径 collected 为空，仍回退到 final_messages（含完整历史）。
                repair_history = list(original_messages) + list(collected_output_messages) if collected_output_messages else final_messages
                await self._run_pending_k8s_repair_workflow(
                    repair_history,
                    config,
                    output_messages=collected_output_messages if collected_output_messages else new_messages,
                )
            except Exception:
                # PPR 失败时 re-raise,让上层 langgraph 走正常 ERROR 处理路径
                raise

            # 直接返回新消息列表，让 agui_stream 逐个处理
            # 这样可以实时发送：工具调用 -> 工具结果 -> 最终响应
            return {"messages": new_messages}

        graph_builder.add_node(deep_wrapper_name, deep_wrapper_node)
        return deep_wrapper_name
