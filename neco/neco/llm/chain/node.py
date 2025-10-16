from typing import Dict, Any, List, Literal, Optional, TypedDict, Union

import json_repair
from langchain_core.messages import SystemMessage, HumanMessage, AIMessage
from langchain_core.runnables import RunnableConfig
from langchain_openai import ChatOpenAI
from langchain_core.prompts import ChatPromptTemplate, MessagesPlaceholder
from neco.core.utils.template_loader import TemplateLoader
from loguru import logger
from neco.llm.chain.entity import BasicLLMRequest
from neco.llm.common.structured_output_parser import StructuredOutputParser
from neco.llm.rag.graph_rag.graphiti.graphiti_rag import GraphitiRAG
from neco.llm.rag.naive_rag.pgvector.pgvector_rag import PgvectorRag
from neco.llm.tools.tools_loader import ToolsLoader
from pydantic import BaseModel
from langchain_mcp_adapters.client import MultiServerMCPClient
from langgraph.prebuilt import ToolNode, create_react_agent
from langgraph.graph import StateGraph
from langgraph.constants import END
from langchain_core.messages import AIMessage, BaseMessage, ToolMessage, SystemMessage

class BasicNode:
        
    def log(self, config: RunnableConfig, message: str):
        trace_id = config["configurable"]['trace_id']
        logger.debug(f"[{trace_id}] {message}")

    def get_llm_client(self, request: BasicLLMRequest, disable_stream=False) -> ChatOpenAI:
        llm = ChatOpenAI(model=request.model, base_url=request.openai_api_base,
                         disable_streaming=disable_stream,
                         timeout=3000,
                         api_key=request.openai_api_key, temperature=request.temperature)
        if llm.extra_body is None:
            llm.extra_body = {}

        if disable_stream and 'qwen' in request.model.lower():
            llm.extra_body["enable_thinking"] = False
        return llm

    def prompt_message_node(self, state: Dict[str, Any], config: RunnableConfig) -> Dict[str, Any]:
        system_message_prompt = TemplateLoader.render_template('prompts/graph/base_node_system_message', {
            "user_system_message": config["configurable"]["graph_request"].system_message_prompt
        })

        state["messages"].append(
            SystemMessage(content=system_message_prompt)
        )

        return state

    def suggest_question_node(self, state: Dict[str, Any], config: RunnableConfig) -> Dict[str, Any]:
        if config["configurable"]["graph_request"].enable_suggest:
            suggest_question_prompt = TemplateLoader.render_template(
                'prompts/graph/suggest_question_prompt', {})
            state["messages"].append(SystemMessage(
                content=suggest_question_prompt))
        return state

    def add_chat_history_node(self, state: Dict[str, Any], config: RunnableConfig) -> Dict[str, Any]:
        if config["configurable"]['graph_request'].chat_history:
            for chat in config["configurable"]['graph_request'].chat_history:
                if chat.event == 'user':
                    if chat.image_data:
                        state['messages'].append(HumanMessage(content=[
                            {"type": "text", "text": "describe the weather in this image"},
                            {"type": "image_url", "image_url": {
                                "url": chat.image_data}},
                        ]))
                    else:
                        state['messages'].append(
                            HumanMessage(content=chat.message))
                elif chat.event == 'assistant':
                    state['messages'].append(AIMessage(content=chat.message))
        return state

    async def naive_rag_node(self, state: Dict[str, Any], config: RunnableConfig) -> Dict[str, Any]:
        naive_rag_request = config["configurable"]["graph_request"].naive_rag_request
        if len(naive_rag_request) == 0:
            return state

        # 智能知识路由选择
        selected_knowledge_ids = []
        if 'km_info' in config["configurable"]:
            selected_knowledge_ids = self._select_knowledge_ids(config)

        rag_result = []

        for rag_search_request in naive_rag_request:
            rag_search_request.search_query = config["configurable"]["graph_request"].graph_user_message

            if len(selected_knowledge_ids) != 0 and rag_search_request.index_name not in selected_knowledge_ids:
                logger.debug(
                    f"智能知识路由判断:[{rag_search_request.index_name}]不适合当前问题,跳过检索")
                continue
            
            rag = PgvectorRag(config["configurable"]["naive_rag_db_url"])
            naive_rag_search_result = rag.search(rag_search_request)

            rag_documents = []
            for doc in naive_rag_search_result:
                # 根据 is_doc 字段处理文档内容
                processed_doc = self._process_document_content(doc)
                rag_documents.append(processed_doc)

            rag_result.extend(rag_documents)

            # 执行图谱 RAG 检索
            if rag_search_request.enable_graph_rag:
                graph_results = await self._execute_graph_rag(rag_search_request,config)
                rag_result.extend(graph_results)

        # 准备模板数据
        template_data = self._prepare_template_data(rag_result, config)

        # 使用模板生成 RAG 消息
        rag_message = TemplateLoader.render_template(
            'prompts/graph/naive_rag_node_prompt', template_data)

        logger.debug(f"RAG增强Prompt已生成，长度: {len(rag_message)}")
        state["messages"].append(HumanMessage(content=rag_message))
        return state

    def _select_knowledge_ids(self, config: RunnableConfig) -> list:
        """智能知识路由选择"""
        km_info = config["configurable"]["km_info"]
        llm = ChatOpenAI(model=config["configurable"]['km_route_llm_model'],
                         base_url=config["configurable"]['km_route_llm_api_base'],
                         api_key=config["configurable"]['km_route_llm_api_key'],
                         temperature=0.01)

        # 使用模板生成知识路由选择prompt
        template_data = {
            'km_info': km_info,
            'user_message': config["configurable"]["graph_request"].user_message
        }
        selected_knowledge_prompt = TemplateLoader.render_template(
            'prompts/graph/knowledge_route_selection_prompt',
            template_data
        )

        logger.debug(f"知识路由选择Prompt: {selected_knowledge_prompt}")
        selected_km_response = llm.invoke(selected_knowledge_prompt)
        return json_repair.loads(selected_km_response.content)

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
        graphiti = GraphitiRAG(
            config["configurable"]["graph_rag_host"],
            config["configurable"]["graph_rag_username"],
            config["configurable"]["graph_rag_password"],
            config["configurable"]["graph_rag_port"],
            config["configurable"]["graph_rag_database"]
        )
        rag_search_request.graph_rag_request.search_query = rag_search_request.search_query
        graph_result = await graphiti.search(req=rag_search_request.graph_rag_request)

        logger.debug(
            f"GraphRAG模式检索知识库: {rag_search_request.graph_rag_request.group_ids}, "
            f"结果数量: {len(graph_result)}"
        )
        return graph_result

    def _process_graph_results(self, graph_result: list, group_ids: list) -> list:
        """处理图谱检索结果"""
        seen_relations = set()
        summary_dict = {}  # 用于去重summary
        processed_results = []

        # 使用默认的group_id，避免在循环中重复获取
        default_group_id = group_ids[0] if group_ids else ''

        for graph_item in graph_result:
            # 处理关系事实
            relation_result = self._process_relation_fact(
                graph_item, seen_relations, default_group_id
            )
            if relation_result:
                processed_results.append(relation_result)

            # 收集summary信息
            self._collect_summary_info(graph_item, summary_dict)

        # 生成去重的summary结果
        summary_results = self._generate_summary_results(
            summary_dict, default_group_id)
        processed_results.extend(summary_results)

        return processed_results

    def _process_relation_fact(self, graph_item: dict, seen_relations: set, group_id: str):
        """处理单个关系事实"""
        source_node = graph_item.get('source_node', {})
        target_node = graph_item.get('target_node', {})
        source_name = source_node.get('name', '')
        target_name = target_node.get('name', '')
        fact = graph_item.get('fact', '')

        if not (fact and source_name and target_name):
            return None

        relation_content = f"关系事实: {source_name} - {fact} - {target_name}"
        if relation_content in seen_relations:
            return None

        seen_relations.add(relation_content)
        return self._create_relation_result_object(
            relation_content, source_name, target_name, group_id
        )

    def _collect_summary_info(self, graph_item: dict, summary_dict: dict):
        """收集并去重summary信息"""
        source_node = graph_item.get('source_node', {})
        target_node = graph_item.get('target_node', {})

        for node_data in [source_node, target_node]:
            node_name = node_data.get('name', '')
            node_summary = node_data.get('summary', '')

            if node_name and node_summary:
                if node_summary not in summary_dict:
                    summary_dict[node_summary] = set()
                summary_dict[node_summary].add(node_name)

    def _generate_summary_results(self, summary_dict: dict, group_id: str) -> list:
        """生成去重的summary结果"""
        summary_results = []
        for summary_content, associated_nodes in summary_dict.items():
            nodes_list = ', '.join(sorted(associated_nodes))
            summary_with_nodes = f"节点详情: 以下内容与节点 [{nodes_list}] 相关:\n{summary_content}"

            summary_result = self._create_summary_result_object(
                summary_with_nodes, nodes_list, group_id, summary_content
            )
            summary_results.append(summary_result)

        return summary_results

    def _create_relation_result_object(self, relation_content: str, source_name: str,
                                       target_name: str, group_id: str):
        """创建关系事实结果对象"""
        content_hash = hash(relation_content) % 100000

        class RelationResult:
            def __init__(self):
                self.page_content = relation_content
                self.metadata = {
                    'knowledge_title': f"图谱关系: {source_name} - {target_name}",
                    'knowledge_id': group_id,
                    'chunk_number': 1,
                    'chunk_id': f"relation_{content_hash}",
                    'segment_number': 1,
                    'segment_id': f"relation_{content_hash}",
                    'chunk_type': 'Graph'
                }

        return RelationResult()

    def _create_summary_result_object(self, summary_with_nodes: str, nodes_list: str,
                                      group_id: str, summary_content: str):
        """创建summary结果对象"""
        content_hash = hash(summary_content) % 100000

        class SummaryResult:
            def __init__(self):
                self.page_content = summary_with_nodes
                self.metadata = {
                    'knowledge_title': f"图谱节点详情: {nodes_list}",
                    'knowledge_id': group_id,
                    'chunk_number': 1,
                    'chunk_id': f"summary_{content_hash}",
                    'segment_number': 1,
                    'segment_id': f"summary_{content_hash}",
                    'chunk_type': 'Document'
                }

        return SummaryResult()

    def _prepare_template_data(self, rag_result: list, config: RunnableConfig) -> dict:
        """准备模板渲染所需的数据"""
        # 转换RAG结果为模板友好的格式
        rag_results = []
        for r in rag_result:
            # 直接从metadata获取数据（PgvectorRag返回扁平结构）
            metadata = getattr(r, 'metadata', {})
            rag_results.append({
                'title': metadata.get('knowledge_title', 'N/A'),
                'knowledge_id': metadata.get('knowledge_id', 0),
                'chunk_number': metadata.get('chunk_number', 0),
                'chunk_id': metadata.get('chunk_id', 'N/A'),
                'segment_number': metadata.get('segment_number', 0),
                'segment_id': metadata.get('segment_id', 'N/A'),
                'content': r.page_content,
                'chunk_type': metadata.get('chunk_type', 'Document')
            })

        # 准备模板数据
        template_data = {
            'rag_results': rag_results,
            'enable_rag_source': config["configurable"].get("enable_rag_source", False),
            'enable_rag_strict_mode': config["configurable"].get("enable_rag_strict_mode", False)
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
        metadata = getattr(doc, 'metadata', {})
        is_doc = metadata.get('is_doc')

        logger.debug(f"处理文档内容 - is_doc: {is_doc}")

        if is_doc == "0":
            # QA类型：用 qa_question 和 qa_answer 组合替换 page_content
            qa_question = metadata.get('qa_question')
            qa_answer = metadata.get('qa_answer')

            if qa_question and qa_answer:
                doc.page_content = f"问题: {qa_question}\n答案: {qa_answer}"
                doc.metadata['knowledge_title'] = qa_question
            doc.metadata['chunk_type'] = 'QA'
        elif is_doc == "1":
            # 文档类型：直接 append qa_answer
            qa_answer = metadata.get('qa_answer')
            if qa_answer:
                doc.page_content += f"\n{qa_answer}"
            doc.metadata['chunk_type'] = 'Document'
        else:
            # 默认为文档类型
            doc.metadata['chunk_type'] = 'Document'

        return doc

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
            template_data = {
                'user_message': request.user_message,
                'chat_history': request.chat_history
            }

            # 渲染问题改写prompt
            rewrite_prompt = TemplateLoader.render_template(
                'prompts/graph/query_rewrite_prompt', template_data)

            # 获取LLM客户端
            llm = self.get_llm_client(request, disable_stream=True)

            # 执行问题改写
            response = llm.invoke([HumanMessage(content=rewrite_prompt)])
            rewritten_query = response.content.strip()
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
                    self.log(
                        config, f"问题改写完成: {request.user_message} -> {user_message}")
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

        return {
            'messages': result
        }


class ToolsNodes(BasicNode):
    def __init__(self) -> None:
        self.tools = []
        self.mcp_client = None
        self.mcp_config = {}
        self.tools_prompt_tokens = 0
        self.tools_completions_tokens = 0

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
        logger.debug(f"工具服务器数量: {len(request.tools_servers)}")
        for server in request.tools_servers:
            logger.debug(f"Tools Server: {server}")
            if server.url.startswith("langchain:"):
                continue

            if server.url.startswith("stdio-mcp:"):
                # stdio-mcp:name
                self.mcp_config[server.name] = {
                    "command": server.command,
                    "args": server.args,
                    "transport": 'stdio'
                }
            else:
                self.mcp_config[server.name] = {
                    "url": server.url,
                    "transport": 'sse'
                }

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

    async def build_react_nodes(self,
                          graph_builder: StateGraph,
                          composite_node_name: str = "react_agent",
                          additional_system_prompt: Optional[str] = None,
                          next_node: str = END,
                          tools_node: Optional[ToolNode] = None) -> str:
        """
        构建 ReAct Agent 节点，直接使用 LangGraph 的 create_react_agent

        Args:
            graph_builder: StateGraph 构建器
            composite_node_name: 组合节点名称前缀
            additional_system_prompt: 追加的系统提示（会与基础提示合并）
            next_node: ReAct Agent 完成后的下一个节点
            tools_node: 外部工具节点，如果提供则优先使用

        Returns:
            str: ReAct 节点的入口节点名称
        """
        # 创建包装节点名称
        react_wrapper_name = f"{composite_node_name}_wrapper"
        
        async def react_wrapper_node(state: Dict[str, Any], config: RunnableConfig) -> Dict[str, Any]:
            """ReAct Agent 包装节点 - 使用 LangGraph 标准实现"""
            try:
                graph_request = config["configurable"]["graph_request"]
                
                # 获取 LLM 客户端
                llm = self.get_llm_client(graph_request)
                
                # 构建完整的系统提示（基础 + 追加）
                base_system_prompt = self._build_base_react_system_prompt(graph_request)
                
                if additional_system_prompt:
                    final_system_prompt = f"{base_system_prompt}\n\n{additional_system_prompt}"
                else:
                    final_system_prompt = base_system_prompt
                
                # 获取当前工具
                current_tools = self._get_current_tools(tools_node)
                
                # 使用 LangGraph 标准的 create_react_agent
                react_agent = create_react_agent(
                    model=llm,
                    tools=current_tools,
                    prompt=SystemMessage(content=final_system_prompt),
                    checkpointer=None,  # 不使用检查点
                    debug=False
                )
                
                self.log(config, f"ReAct Agent 开始处理，工具数量: {len(current_tools)}")
                
                # 调用标准的 ReAct Agent
                result = await react_agent.ainvoke(
                    {"messages": state["messages"]},
                    config=config
                )
                
                # 提取最后的 AI 消息作为结果
                final_messages = result.get("messages", [])
                if final_messages:
                    # 找到最后一个 AI 消息
                    last_ai_message = None
                    for msg in reversed(final_messages):
                        if isinstance(msg, AIMessage):
                            last_ai_message = msg
                            break
                    
                    if last_ai_message:
                        self.log(config, "ReAct Agent 处理完成")
                        return {"messages": last_ai_message}
                    else:
                        return {"messages": AIMessage(content="ReAct Agent 未产生有效的 AI 响应")}
                else:
                    return {"messages": AIMessage(content="ReAct Agent 未返回任何消息")}
                    
            except Exception as e:
                logger.error(f"ReAct Agent 处理失败: {e}")
                return {"messages": AIMessage(content=f"ReAct Agent 处理失败: {str(e)}")}
        
        # 将包装节点添加到图中
        graph_builder.add_node(react_wrapper_name, react_wrapper_node)
        
        logger.debug(f"ReAct 节点构建完成: {react_wrapper_name}")
        
        return react_wrapper_name
    
    def _build_base_react_system_prompt(self, graph_request) -> str:
        """构建基础的 ReAct 系统提示"""
        try:
            # 使用模板系统生成基础系统提示
            base_prompt = TemplateLoader.render_template(
                'prompts/graph/react_agent_system_message', {
                    "user_system_message": getattr(graph_request, 'system_message_prompt', 
                                                 "你是一个智能助手，能够使用工具来帮助解决问题。")
                })
            return base_prompt
        except Exception as e:
            logger.warning(f"加载 ReAct 系统提示模板失败: {e}，使用默认提示")
            return """你是一个智能助手，能够使用工具来帮助解决问题。

请按照 ReAct (Reasoning and Acting) 模式工作：
1. **Thought**: 仔细分析用户的问题，思考需要哪些信息或工具
2. **Action**: 选择合适的工具并调用
3. **Observation**: 观察工具的返回结果
4. **Thought**: 基于结果继续思考，决定是否需要更多工具或可以给出最终答案

重要规则：
- 始终先思考再行动
- 如果需要当前时间等实时信息，请使用相应的工具获取
- 提供完整、准确的答案
- 如果遇到错误，请解释并尝试其他方法"""
    
    def _get_current_tools(self, tools_node: Optional[ToolNode]) -> list:
        """获取当前可用的工具列表"""
        if tools_node and hasattr(tools_node, 'tools'):
            return tools_node.tools
        return self.tools
