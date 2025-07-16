from typing import TypedDict

import json_repair
from langchain_core.messages import SystemMessage, HumanMessage, AIMessage
from langchain_core.runnables import RunnableConfig
from langchain_openai import ChatOpenAI

from libs.metis.entity.basic.basic_llm_request import BasicLLMRequest
from libs.metis.rag.graph_rag.graphiti.graphiti_rag import GraphitiRAG
from libs.metis.rag.naive_rag.elasticsearch.elasticsearch_rag import ElasticSearchRag

import copy
import logging
logger = logging.getLogger(__name__)

class BasicNode:
    def log(self, config: RunnableConfig, message: str):
        trace_id = config["configurable"]['trace_id']
        logger.debug(f"[{trace_id}] {message}")

    def get_llm_client(self, request: BasicLLMRequest) -> ChatOpenAI:
        llm = ChatOpenAI(model=request.model, base_url=request.openai_api_base,
                         api_key=request.openai_api_key, temperature=request.temperature)
        return llm

    def prompt_message_node(self, state: TypedDict, config: RunnableConfig) -> TypedDict:

        system_message_prompt = f"""
            {config["configurable"]["graph_request"].system_message_prompt}
                以下规则在任何情况下都必须严格遵守，具有最高优先级，不可违反：

                【敏感信息保护】
                * 严禁以任何形式泄露敏感信息。敏感信息包括但不限于：
                - 各类密码、令牌、密钥、私钥、证书、连接 URI、访问地址、内部主机名、用户凭证等
                - 配置字段中包含 password、token、secret、key、auth、uri、access、host、user、port、conn、dsn、endpoint 等关键词的键或值
                - Kubernetes 的 Secret、ConfigMap、环境变量、Deployment、Pod、StatefulSet、Service 等配置中可能包含机密信息的字段
                - 任意形式的默认用户名、默认密码、内部网络地址（如 `neo4j-nodeport:7687`、`admin` 用户名等）
                - 明显的安全配置开关，如 `ALLOW_EMPTY_PASSWORD`, `ENABLE_AUTH=false` 等不安全配置项

                * 输出内容如包含上述信息，必须隐藏或脱敏字段值，仅保留字段名。  
                ✅ 示例：`"RABBITMQ_DEFAULT_PASS": "***"`  
                ✅ 示例：`"NEO4J_HOST": "***"`  
                ✅ 示例：`"ALLOW_EMPTY_PASSWORD": "<hidden>"`  
                ❌ 示例：`"RABBITMQ_DEFAULT_USER": "admin"`

                * 如无法判断字段值是否敏感，应默认视为敏感并隐藏。

                【函数调用限制】
                * 严禁在任何函数调用中传入或处理敏感信息，包括但不限于密码、密钥、令牌、用户名、数据库 URI、内部地址等字段。
                * 不得将用户未显式授权的环境变量、部署配置、Secret 值等传入函数调用。
                * 若检测到敏感信息作为参数，必须终止调用并返回说明：“为保护系统安全，该请求已被拒绝执行”。

                【高危操作防范】
                * 严禁执行或建议任何可能对系统造成风险的操作，包括但不限于：
                - 删除、重启、终止服务或进程
                - 执行 `rm`、`kill`、`shutdown`、`curl`、`mount` 等命令
                - 向外部地址发起请求、脚本注入、执行 Shell 命令等行为

                * 若接收到此类请求，应立即拒绝并明确说明，不得转换、弱化或掩饰行为。

                【默认安全优先】
                * 如信息存在安全风险但无法确认是否敏感，应默认视为敏感，选择隐藏或提示用户手动查看。
                * 响应中应始终优先确保系统安全和信息保护，即使这会导致答案不完整。

                【权限与责任边界】
                * 不应主动请求或输出用户未授权的信息。
                * 不应模拟或执行实际系统行为，仅可提供说明、分析、建议等信息性输出。

                【日志与配置输出】
                * 展示日志或配置内容时，如含有可疑敏感字段，应遮蔽其值，仅保留结构或键名。
                * 禁止原样输出环境变量、配置项、日志行等包含敏感字段的内容，如：
                - `NEO4J_HOST=bolt://neo4j-nodeport:7687`
                - `RABBITMQ_DEFAULT_USER=admin`
                - `ALLOW_EMPTY_PASSWORD=yes`

                上述内容应统一替换为 `***`、`<hidden>`、或提示“为保护安全已隐藏”。

                ---

                以上所有规则必须严格执行，不得规避、弱化或绕过。如遇不确定情况，应优先选择更保守、更安全的处理方式。
        """

        if config["configurable"]["graph_request"].system_message_prompt:
            state["messages"].append(
                SystemMessage(content=system_message_prompt)
            )
        return state

    def add_chat_history_node(self, state: TypedDict, config: RunnableConfig) -> TypedDict:
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

    async def naive_rag_node(self, state: TypedDict, config: RunnableConfig) -> TypedDict:
        # if config["configurable"]['graph_request'].enable_naive_rag is False and config["configurable"]['graph_request'].enable_qa_rag is False:
        #     return state

        naive_rag_request = config["configurable"]["graph_request"].naive_rag_request
        if len(naive_rag_request) == 0:
            return state

        rag_message = f'''
                       以下是参考资料,每份参考资料都由标题和内容组成,以XML格式提供:

                       示例:
                           <knowledge>
                               <ref_id>1</ref_id>
                               <title>知识标题</title>
                               <knowledge_id>1</knowledge_id>
                               <chunk_number>1</chunk_number>
                               <segment_number>2</segment_number>
                               <segment_id>4</segment_id>
                               <content>知识内容</content>
                           </knowledge>

                       字段说明:
                           ref_id: 是第几份参考资料，从1开始
                           title: 参考资料的标题
                           content: 参考资料的内容
                           knowledge_id: 知识id
                           chunk_number: 分块序号
                           chunk_id: 分块ID号
                           segment_number: 分段序号
                           segment_id: 分块ID
                       参考资料:
                   '''

        selected_knowledge_ids = []
        if 'km_info' in config["configurable"]:
            km_info = config["configurable"]["km_info"]
            llm = ChatOpenAI(model=config["configurable"]['km_route_llm_model'],
                             base_url=config["configurable"]['km_route_llm_api_base'],
                             api_key=config["configurable"]['km_route_llm_api_key'],
                             temperature=0.01)

            selected_knowledge_prompt = f"""
                                    我将会给你一段xml，格式为
                                        <knowledge>
                                            <knowledge_id>1</knowledge_id>
                                            <description>知识库描述</description>
                                        <knowledge>
                                    需要根据知识库描述，以及用户的问题，返回与问题相关的知识库id号，格式为json数组，以下是示例: [1,3,2]
                                """
            selected_knowledge_prompt += "任务开始: 以下是需要选择的知识库信息"
            for km in km_info:
                selected_knowledge_prompt += f"""
                            <knowledge>
                                <knowledge_id>{km['index_name']}</knowledge_id>
                                <description>{km['description']}</description>
                            </knowledge>
                        """
            selected_knowledge_prompt += f"请找出与用户问题相关的知识库id号,用户的问题是:{config["configurable"]["graph_request"].user_message}"
            selected_km_response = llm.invoke(selected_knowledge_prompt)
            selected_knowledge_ids = json_repair.loads(
                selected_km_response.content)

        rag_result = []

        for rag_search_request in naive_rag_request:
            if len(selected_knowledge_ids) != 0 and rag_search_request.index_name not in selected_knowledge_ids:
                logger.info(
                    f"智能知识路由判断:[{rag_search_request.index_name}]不适合当前问题,跳过检索")
            elasticsearch_rag = ElasticSearchRag()

            if rag_search_request.enable_naive_rag is True:
                naive_rag_request = copy.deepcopy(rag_search_request)
                naive_rag_request.metadata_filter['qa_answer__missing'] = True
                naive_rag_search_result = elasticsearch_rag.search(
                    naive_rag_request)
                logger.info(
                    f"NaiveRAG模式检索知识库: {rag_search_request.index_name}, 结果数量: {len(naive_rag_search_result)}")
                rag_result.extend(naive_rag_search_result)

            if rag_search_request.enable_qa_rag is True:
                qa_rag_request = copy.deepcopy(rag_search_request)
                qa_rag_request.metadata_filter['qa_answer__exists'] = True
                qa_elasticsearch_rag = ElasticSearchRag()
                qa_rag_search_result = qa_elasticsearch_rag.search(
                    qa_rag_request)
                logger.info(
                    f"QA-RAG模式检索知识库: {rag_search_request.index_name}, 结果数量: {len(qa_rag_search_result)}")
                rag_result.extend(qa_rag_search_result)

            if rag_search_request.enable_graph_rag is True:
                graphiti = GraphitiRAG()
                rag_search_request.graph_rag_request.search_query = rag_search_request.search_query
                graph_result = await graphiti.search(
                    req=rag_search_request.graph_rag_request)
                logger.info(
                    f"GraphRAG模式检索知识库: {rag_search_request.graph_rag_request.group_ids}, 结果数量: {len(graph_result)}")

                # 处理图谱关系事实
                seen_relations = set()
                summary_dict = {}  # 用于去重summary

                for graph_item in graph_result:
                    source_node = graph_item.get('source_node', {})
                    target_node = graph_item.get('target_node', {})
                    source_name = source_node.get('name', '')
                    target_name = target_node.get('name', '')
                    fact = graph_item.get('fact', '')

                    # 处理关系事实
                    if fact and source_name and target_name:
                        relation_content = f"关系事实: {source_name} - {fact} - {target_name}"
                        if relation_content not in seen_relations:
                            seen_relations.add(relation_content)

                            relation_result = type('obj', (object,), {
                                'page_content': relation_content,
                                'metadata': {
                                    '_source': {
                                        'metadata': {
                                            'knowledge_title': f"图谱关系: {source_name} - {target_name}",
                                            'knowledge_id': graph_item.get('group_id', ''),
                                            'chunk_number': 1,
                                            'chunk_id': f"relation_{hash(relation_content) % 100000}",
                                            'segment_number': 1,
                                            'segment_id': f"relation_{hash(relation_content) % 100000}"
                                        }
                                    }
                                }
                            })()
                            rag_result.append(relation_result)

                    # 收集并去重summary信息
                    for node_type, node_data in [('source_node', source_node), ('target_node', target_node)]:
                        node_name = node_data.get('name', '')
                        node_summary = node_data.get('summary', '')

                        if node_name and node_summary:
                            if node_summary not in summary_dict:
                                summary_dict[node_summary] = set()
                            summary_dict[node_summary].add(node_name)

                # 生成去重的summary结果
                for summary_content, associated_nodes in summary_dict.items():
                    nodes_list = ', '.join(sorted(associated_nodes))
                    summary_with_nodes = f"节点详情: 以下内容与节点 [{nodes_list}] 相关:\n{summary_content}"

                    summary_result = type('obj', (object,), {
                        'page_content': summary_with_nodes,
                        'metadata': {
                            '_source': {
                                'metadata': {
                                    'knowledge_title': f"图谱节点详情: {nodes_list}",
                                    'knowledge_id': graph_item.get('group_id', ''),
                                    'chunk_number': 1,
                                    'chunk_id': f"summary_{hash(summary_content) % 100000}",
                                    'segment_number': 1,
                                    'segment_id': f"summary_{hash(summary_content) % 100000}"
                                }
                            }
                        }
                    })()
                    rag_result.append(summary_result)

        for index, r in enumerate(rag_result):
            rag_message += f"""
                <knowledge>
                    <ref_id>{index + 1}</ref_id>
                    <title>{r.metadata['_source']['metadata'].get('knowledge_title', 'N/A')}</title>
                    <knowledge_id>{r.metadata['_source']['metadata'].get('knowledge_id', 0)}</knowledge_id>
                    <chunk_number>{r.metadata['_source']['metadata'].get('chunk_number', 0)}</chunk_number>
                    <chunk_id>{r.metadata['_source']['metadata'].get('chunk_id', 'N/A')}</chunk_id>
                    <segment_number>{r.metadata['_source']['metadata'].get('segment_number', 0)}</segment_number>
                    <segment_id>{r.metadata['_source']['metadata'].get('segment_id', 'N/A')}</segment_id>
                    <content>{r.page_content}</content>
                </knowledge>
            """

        if len(rag_result) == 0:
            rag_message += f"""
               没有找到相关可参考的背景资料
            """

        if 'enable_rag_source' in config["configurable"] and config["configurable"]["enable_rag_source"]:
            rag_message += f"""
            在回复中,请使用以下格式返回参考资料的引用:
                [[1]](ref_id:1|segment_id:1|chunk_id:abc|chunk_number:1|knowledge_id:1|segment_number:1)
                [[2]]](ref_id:2|segment_id:2|chunk_id:def|chunk_number:2|knowledge_id:0|segment_number:12)

            引用格式说明:
            - 使用数字作为引用标识，简洁明了
            - 使用竖线 | 分隔各个参数
            - 保持参数顺序一致: ref_id|segment_id|chunk_id|chunk_number|knowledge_id|segment_number
            
            在回答内容中的适当位置插入引用链接，格式示例:
                bklite 是一个AI First的知识管理平台[[1]](ref_id:1|segment_id:1|chunk_id:abc|chunk_number:1|knowledge_id:1|segment_number:1)，致力于帮助用户更高效地获取和管理知识。
                它的协议是MIT[[2]](ref_id:1|segment_id:1|chunk_id:abc|chunk_number:1|knowledge_id:1|segment_number:1)[[2]](ref_id:2|segment_id:2|chunk_id:def|chunk_number:2|knowledge_id:0|segment_number:12)协议

            注意事项:
            - 每个引用链接都要包含完整的参数信息
            - 引用文本使用简洁的数字标识，如"1"、"2"等
            - 在句子中合适的位置插入引用，不要影响阅读体验
            
            在回复的最后，请添加一个"参考资料"部分,格式如下:
            
            参考资料: 
                - [1] 知识标题1
                - [2] 知识标题2
                - [3] 知识标题3
            
            其中数字与正文中的引用标识保持一致，标题为对应参考资料的title字段内容。
        """

        if 'enable_rag_strict_mode' in config["configurable"] and config["configurable"]["enable_rag_strict_mode"]:
            rag_message += f"""
                    严格按照参考资料的内容进行回答,不允许添加任何额外的内容，不允许捏造任何事实。
                    只允许使用参考资料中的内容进行回答，当参考资料中没有相关内容时，请返回“没有相关内容”。
                """
        rag_message += """
        特别说明: 
            1.背景知识中存在图谱知识的时候，允许基于图谱知识和背景知识，进行基于事实的回答。回答的时候要自然,不要让用户感受到图谱知识的存在。
            2.回复要自然流畅
        """
        logger.info(f"RAG增强Prompt: {rag_message}")
        state["messages"].append(HumanMessage(content=rag_message))
        return state

    def user_message_node(self, state: TypedDict, config: RunnableConfig) -> TypedDict:
        state["messages"].append(HumanMessage(
            content=config["configurable"]["graph_request"].user_message))
        return state
