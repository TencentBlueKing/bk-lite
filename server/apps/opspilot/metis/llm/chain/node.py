from typing import Any, Dict, List, Optional

import json_repair
from deepagents import create_deep_agent
from langchain_core.messages import AIMessage, BaseMessage, HumanMessage, SystemMessage
from langchain_core.runnables import RunnableConfig
from langchain_mcp_adapters.client import MultiServerMCPClient
from langchain_openai import ChatOpenAI
from langgraph.constants import END
from langgraph.graph import StateGraph
from langgraph.prebuilt import ToolNode
from loguru import logger
from pydantic import BaseModel

from apps.opspilot.metis.llm.chain.entity import BasicLLMRequest
from apps.opspilot.metis.llm.common.llm_client_factory import LLMClientFactory
from apps.opspilot.metis.llm.common.structured_output_parser import StructuredOutputParser
from apps.opspilot.metis.llm.rag.graph_rag.graphiti.graphiti_rag import GraphitiRAG
from apps.opspilot.metis.llm.rag.naive_rag.pgvector.pgvector_rag import PgvectorRag
from apps.opspilot.metis.llm.tools.tools_loader import ToolsLoader
from apps.opspilot.metis.utils.template_loader import TemplateLoader


class BasicNode:
    def log(self, config: RunnableConfig, message: str):
        trace_id = config["configurable"]["trace_id"]
        logger.debug(f"[{trace_id}] {message}")

    def get_llm_client(self, request: BasicLLMRequest, disable_stream=False, isolated=False) -> ChatOpenAI:
        """
        获取LLM客户端

        Args:
            request: LLM请求对象
            disable_stream: 是否禁用流式输出
            isolated: 是否创建独立客户端(不被LangGraph跟踪),用于内部调用如问题改写
        """
        llm = ChatOpenAI(
            model=request.model,
            base_url=request.openai_api_base,
            disable_streaming=disable_stream,
            timeout=3000,
            api_key=request.openai_api_key,
            temperature=request.temperature,
        )
        if llm.extra_body is None:
            llm.extra_body = {}

        if disable_stream and "qwen" in request.model.lower():
            llm.extra_body["enable_thinking"] = False

        # 如果需要隔离,则禁用callbacks以避免被LangGraph捕获
        if isolated:
            llm.callbacks = None

        return llm

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
            state["messages"].append(SystemMessage(content=suggest_question_prompt))
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
        from apps.opspilot.metis.llm.chain.entity import BasicLLMRequest

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
            logger.error(f"GraphRAG检索处理异常: {str(e)}")
            return []

    async def _perform_graph_search(self, rag_search_request, config: RunnableConfig) -> list:
        """执行图谱搜索"""
        graphiti = GraphitiRAG()
        rag_search_request.graph_rag_request.search_query = rag_search_request.search_query
        graph_result = await graphiti.search(req=rag_search_request.graph_rag_request)

        logger.debug(f"GraphRAG模式检索知识库: {rag_search_request.graph_rag_request.group_ids}, " f"结果数量: {len(graph_result)}")
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
            logger.error(f"问题改写过程中发生异常: {str(e)}")
            raise

    def user_message_node(self, state: Dict[str, Any], config: RunnableConfig) -> Dict[str, Any]:
        request = config["configurable"]["graph_request"]
        user_message = request.user_message

        # 如果启用问题改写功能
        if config["configurable"]["graph_request"].enable_query_rewrite:
            try:
                rewritten_message = self._rewrite_query(request, config)
                if rewritten_message and rewritten_message.strip():
                    user_message = rewritten_message
                    self.log(config, f"问题改写完成: {request.user_message} -> {user_message}")
            except Exception as e:
                logger.warning(f"问题改写失败，使用原始问题: {str(e)}")
                user_message = request.user_message

        state["messages"].append(HumanMessage(content=user_message))
        request.graph_user_message = user_message
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

    def get_tools_description(self) -> str:
        if self.tools:
            tools_info = ""
            for tool in self.tools:
                tools_info += f"{tool.name}: {tool.description}\n"
            return tools_info
        return ""

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
                self.mcp_config[server.name] = {"url": server.url, "transport": "sse"}
            if server.enable_auth:
                self.mcp_config[server.name]["headers"] = {"Authorization": server.auth_token}

        if self.mcp_config:
            self.mcp_client = MultiServerMCPClient(self.mcp_config)
            self.tools = await self.mcp_client.get_tools()

        # 初始化LangChain工具
        for server in request.tools_servers:
            if server.url.startswith("langchain:"):
                langchain_tools = ToolsLoader.load_tools(server.url, server.extra_tools_prompt, server.extra_param_prompt)
                self.tools.extend(langchain_tools)

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
            logger.error(f"构建工具节点失败: {e}")
            return ToolNode([])

    # ========== 使用 LangGraph 标准 ReAct Agent 实现 ==========

    async def build_react_nodes(
        self,
        graph_builder: StateGraph,
        composite_node_name: str = "react_agent",
        additional_system_prompt: Optional[str] = None,
        next_node: str = END,
        tools_node: Optional[ToolNode] = None,
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

        # ========== Agent 节点：调用 LLM 并决定是否使用工具 ==========
        async def agent_node(state: Dict[str, Any], config: RunnableConfig) -> Dict[str, Any]:
            """Agent 节点 - 调用绑定工具的 LLM"""
            graph_request = config["configurable"]["graph_request"]

            # 构建系统提示
            final_system_prompt = TemplateLoader.render_template(
                "prompts/graph/react_agent_system_message",
                {"user_system_message": graph_request.system_message_prompt, "additional_system_prompt": additional_system_prompt or ""},
            )

            # 获取 LLM 并绑定工具
            llm = get_llm_client(graph_request)
            if tools:
                llm_with_tools = llm.bind_tools(tools)
            else:
                llm_with_tools = llm

            # 准备消息列表
            messages = state.get("messages", [])

            # 如果消息中没有系统提示，添加一个
            if not any(isinstance(m, SystemMessage) for m in messages):
                messages = [SystemMessage(content=final_system_prompt)] + list(messages)

            # 调用 LLM
            response = await llm_with_tools.ainvoke(messages)

            return {"messages": [response]}

        # ========== 工具节点：执行工具调用 ==========
        tool_node = tools_node if tools_node else ToolNode(tools, handle_tool_errors=True)

        # ========== 条件函数：判断是否继续调用工具 ==========
        def should_continue(state: Dict[str, Any]) -> str:
            """判断是否需要继续执行工具调用"""
            messages = state.get("messages", [])
            if not messages:
                return "end"

            last_message = messages[-1]

            # 如果最后一条消息有工具调用，继续执行工具
            if hasattr(last_message, "tool_calls") and last_message.tool_calls:
                return "continue"

            # 否则结束
            return "end"

        # ========== Wrapper 节点：入口点，兼容现有 API ==========
        async def wrapper_node(state: Dict[str, Any], config: RunnableConfig) -> Dict[str, Any]:
            """Wrapper 节点 - 入口点，直接透传状态"""
            # 不做任何处理，只是作为入口点
            return {}

        # ========== 添加节点到图 ==========
        graph_builder.add_node(wrapper_node_name, wrapper_node)
        graph_builder.add_node(agent_node_name, agent_node)
        graph_builder.add_node(tools_node_name, tool_node)

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
            result = await temp_graph.ainvoke({"messages": messages[-3:] if len(messages) > 3 else messages}, config=config)

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
            logger.warning(f"ReAct 调用失败: {e}，使用降级方案")
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
