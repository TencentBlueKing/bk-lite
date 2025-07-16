from collections import defaultdict
from typing import Dict, List, Tuple, TypedDict

from langchain_core.callbacks import StdOutCallbackHandler, StreamingStdOutCallbackHandler
from langchain_core.messages import AIMessage, BaseMessage, AIMessageChunk
from langchain_core.output_parsers import JsonOutputToolsParser, PydanticToolsParser
from langchain_core.prompt_values import ChatPromptValue
from langchain_core.prompts import ChatPromptTemplate, MessagesPlaceholder
from langchain_core.runnables import RunnableConfig
from langchain_core.runnables import chain as as_runnable
from langgraph.constants import END
from langgraph.prebuilt import ToolNode
import logging

logger = logging.getLogger(__name__)

from libs.metis.graph_core.agent.lats_agent.lats_agent_state import LatsAgentState, Node, Reflection
from libs.metis.graph_core.node.tools_node import ToolsNodes


class LatsAgentNode(ToolsNodes):
    # 类级常量配置
    MAX_CANDIDATES = 5  # 最大候选数量
    MAX_TREE_HEIGHT = 5  # 最大树高度
    EXPLORATION_WEIGHT = 1.0  # UCB算法探索权重

    def _process_tool_calls(self, message: AIMessage) -> List[Dict]:
        """处理LLM返回的工具调用

        Args:
            message: 包含工具调用的AI消息

        Returns:
            格式化的工具调用列表
        """
        if not message.tool_calls:
            return []

        return [
            {
                "name": tool_call.name,
                "args": tool_call.args,
                "id": tool_call.id
            }
            for tool_call in message.tool_calls
        ]

    # 移除冗余方法 _update_state_messages，因为在 generate_initial_response 和 expand 中已直接更新 state['messages']

    def _create_tool_node(self) -> ToolNode:
        """创建工具节点实例

        Returns:
            工具节点实例
        """
        return ToolNode(self.tools, handle_tool_errors=True)

    def get_reflection_chain(self, state: LatsAgentState, config: RunnableConfig):
        """获取用于反思和评分候选解决方案的链

        创建一个专门用于评估LLM生成的解决方案质量的反思链。该链通过Reflection工具
        对解决方案进行打分(0-10)、提供反思性评价，并判断是否完全解决了用户问题。

        Args:
            state: 当前搜索状态
            config: 运行时配置，包含请求信息

        Returns:
            可执行的反思评估链
        """
        # 获取配置的LLM客户端
        llm = self.get_llm_client(config["configurable"]["graph_request"])

        # 创建反思提示模板
        prompt = ChatPromptTemplate.from_messages(
            [
                (
                    "system",
                    "对AI助手的回答进行反思和评分。评估回答的充分性、准确性和解决问题的能力。",
                ),
                ("user", "{input}"),  # 用户的原始问题
                MessagesPlaceholder(variable_name="candidate"),  # 候选解决方案
            ]
        )

        # 构建反思链，使用Reflection工具强制输出结构化评估
        reflection_llm_chain = (
                prompt
                | llm.bind_tools(
            tools=[Reflection],
            tool_choice="Reflection"  # 强制使用Reflection工具
        ).with_config(
            run_name="Reflection",  # 为追踪添加运行名称
            configurable={"verbose": False},  # 禁止输出到控制台
            callbacks=[]  # 清空回调，防止输出
        )
                | PydanticToolsParser(tools=[Reflection])  # 解析成Reflection对象
        )

        logger.debug("反思评估链创建完成")
        return reflection_llm_chain

    def get_expansion_chain(self, state: LatsAgentState, config: RunnableConfig):
        """获取用于生成候选解决方案的链

        Args:
            state: 当前状态
            config: 运行配置

        Returns:
            候选解决方案生成链
        """

        def generate_candidates(messages: ChatPromptValue) -> List[BaseMessage]:
            """生成多个候选解决方案

            Args:
                messages: 输入消息

            Returns:
                候选解决方案消息列表
            """
            llm = self.get_llm_client(config["configurable"]["graph_request"])
            bound_kwargs = llm.bind_tools(tools=self.tools).kwargs

            candidates = []
            logger.debug(f"开始生成{self.MAX_CANDIDATES}个候选解决方案")

            for i in range(self.MAX_CANDIDATES):
                chat_result = llm.generate(
                    [messages.to_messages()],
                    callbacks=[],
                    run_name=f"GenerateCandidate_{i + 1}",
                    **bound_kwargs,
                )
                candidate = chat_result.generations[0][0].message
                candidates.append(candidate)

                self.tools_prompt_tokens += candidate.usage_metadata['input_tokens']
                self.tools_completions_tokens += candidate.usage_metadata['output_tokens']

                logger.debug(f"候选解决方案 #{i + 1}: {candidate}...")
                logger.debug(f"候选解决方案 #{i + 1}: Token用量:{candidate.usage_metadata}")

            return candidates

        prompt_template = ChatPromptTemplate.from_messages(
            [
                (
                    "system",
                    "You are an AI assistant.",
                ),
                ("user", "{input}"),
                MessagesPlaceholder(variable_name="messages", optional=True),
            ]
        )

        expansion_chain = prompt_template | generate_candidates
        return expansion_chain

    def select(self, root: Node) -> Node:
        """从根节点开始，在每个树层级选择一个子节点，直到达到叶节点

        使用上置信任边界算法(UCB)来选择节点，平衡探索与利用

        Args:
            root: 搜索树的根节点

        Returns:
            选定的节点
        """
        if not root.children:
            logger.debug(f"根节点没有子节点，直接返回根节点")
            return root

        node = root
        path = [node.depth]

        while node.children:
            max_child = max(
                node.children,
                key=lambda child: child.upper_confidence_bound(
                    self.EXPLORATION_WEIGHT)
            )
            node = max_child
            path.append(node.depth)

        logger.debug(f"从根节点选择了路径: {path}，最终选择深度为{node.depth}的节点")
        return node

    def _process_candidates(
            self,
            candidates: List[BaseMessage],
            state: LatsAgentState,
            config: RunnableConfig
    ) -> Tuple[List[List[BaseMessage]], List[Reflection]]:
        """处理候选解决方案，执行工具调用并进行反思评估

        Args:
            candidates: 候选解决方案列表
            state: 当前状态
            config: 运行配置

        Returns:
            处理后的消息和反思的元组
        """
        # 解析工具调用
        parser = JsonOutputToolsParser(return_id=True)
        parsed_tool_calls = parser.batch(candidates)

        # 创建工具节点
        tool_node = self._create_tool_node()

        # 扁平化工具调用列表，保留候选索引
        flattened_tool_calls = [
            (candidate_idx, tool_call)
            for candidate_idx, tool_calls in enumerate(parsed_tool_calls)
            for tool_call in tool_calls
        ]

        logger.debug(
            f"从{len(candidates)}个候选解决方案中解析出{len(flattened_tool_calls)}个工具调用")

        # 执行工具调用
        tool_responses = []
        for candidate_idx, tool_call in flattened_tool_calls:
            try:
                response = tool_node.invoke({
                    "messages": [
                        AIMessage(
                            content="",
                            tool_calls=[{
                                "name": tool_call["type"],
                                "args": tool_call["args"],
                                "id": tool_call["id"],
                            }]
                        )
                    ]
                })
                tool_responses.append((candidate_idx, response))
                logger.debug(f"工具调用成功: {tool_call['type']}")
            except Exception as e:
                logger.error(f"工具调用失败: {tool_call['type']}, 错误: {str(e)}")
                # 即使调用失败也添加一个空响应，保持索引一致性
                tool_responses.append(
                    (candidate_idx, {"messages": [AIMessage(content="工具调用失败")]}))

        # 按候选索引收集工具响应
        collected_responses = defaultdict(list)
        for candidate_idx, response in tool_responses:
            collected_responses[candidate_idx].append(response["messages"][0])

        # 将候选解决方案与其工具响应组合
        output_messages = []
        for idx, candidate in enumerate(candidates):
            output_messages.append([candidate] + collected_responses[idx])

        # 创建反思链进行评估
        @as_runnable
        def reflection_chain(inputs) -> Reflection:
            # 创建无输出的配置
            silent_config = {
                "callbacks": [],  # 清空回调函数
                "configurable": {"verbose": False}  # 设置为非详细模式
            }

            # 融合现有配置与静默配置
            invoke_config = {**config, **silent_config}

            # 调用反思链，但禁止输出
            tool_choices = self.get_reflection_chain(
                state, config).invoke(inputs, config=invoke_config)
            reflection = tool_choices[0]

            # 如果最后一条消息不是AI消息，则无法解决问题
            if not isinstance(inputs["candidate"][-1], AIMessage):
                reflection.found_solution = False
            return reflection

        # 批量评估所有候选解决方案
        user_message = config["configurable"]["graph_request"].user_message
        reflection_inputs = [
            {"input": user_message, "candidate": messages}
            for messages in output_messages
        ]

        # 创建批量处理的静默配置
        batch_config = {**config, "callbacks": [], "configurable": {**
                                                                    (config.get("configurable") or {}),
                                                                    "verbose": False}}

        # 使用静默配置执行批量反思评估
        reflections = reflection_chain.batch(
            reflection_inputs, config=batch_config)

        # 记录反思结果，使用紧凑格式输出候选方案评估信息
        summary_header = "📊 候选解决方案评估结果汇总"
        header_border = "=" * 50
        table_headers = f"{'序号':^5} | {'评分':^6} | {'是否解决':^8} | {'评估概要'}"
        table_divider = "-" * 80

        # 构建评估表格内容
        rows = []
        for idx, reflection in enumerate(reflections):
            solution_status = "✅" if reflection.found_solution else "❌"
            # 截取反思内容的前50个字符作为概要，避免日志过长
            summary = reflection.reflections[:50] + "..." if len(
                reflection.reflections) > 50 else reflection.reflections
            rows.append(f"{idx + 1:^5} | {reflection.score:^6}/10 | {solution_status:^8} | {summary}")

            # 在DEBUG级别输出完整的反思内容
            logger.debug(f"候选方案 #{idx + 1} 完整评估:\n{reflection.reflections}")

            # 输出方案内容概要
            if idx < len(output_messages) and output_messages[idx]:
                # 获取最后一条消息的内容（通常是最终回答）
                message_content = output_messages[idx][-1].content if output_messages[idx][-1].content else "无内容"
                content_summary = message_content[:50] + "..." if len(
                    message_content) > 50 else message_content
                logger.debug(f"方案内容: {content_summary}")

        # 找出最高评分和是否有解决方案
        summary_footer = ""
        if reflections:
            max_score = max(r.score for r in reflections)
            solved_count = sum(1 for r in reflections if r.found_solution)
            summary_footer = f"✨ 最高评分: {max_score}/10, 找到 {solved_count} 个解决方案"

        # 将所有内容拼接成一个字符串进行输出
        evaluation_summary = (
            f"\n{header_border}\n{summary_header}\n{header_border}\n"
            f"{table_headers}\n{table_divider}\n"
            f"{chr(10).join(rows)}\n{header_border}\n"
            f"{summary_footer if summary_footer else ''}"
        )

        # 使用单一日志语句输出整个评估汇总
        logger.info(evaluation_summary)

        # 假如分数等于10，则认为已经找到解决方案
        for reflection in reflections:
            if reflection.score == 10:
                reflection.found_solution = True

        return output_messages, reflections

    def expand(self, state: LatsAgentState, config: RunnableConfig) -> LatsAgentState:
        """扩展搜索树，生成新的候选解决方案

        Langgraph 执行过程中的主要搜索步骤，负责选择最佳候选节点并生成新的解决方案

        Args:
            state: 当前状态
            config: 运行配置

        Returns:
            更新后的状态
        """
        logger.info("开始扩展搜索树...")

        # 获取搜索树根节点
        root = state["root"]
        if not root:
            logger.error("搜索树根节点未初始化，无法执行扩展")
            return state

        # 记录当前状态指标
        logger.debug(
            f"当前搜索树高度: {root.height}, 节点数量: {self._count_nodes(root)}")

        # 使用树搜索算法选择当前最佳候选节点
        best_candidate = self.select(root)
        messages = best_candidate.get_trajectory()

        # 获取用户原始消息
        user_message = config["configurable"]["graph_request"].user_message
        logger.debug(f"选择深度为{best_candidate.depth}的候选节点进行扩展")

        # 生成新的候选解决方案
        new_candidates = self.get_expansion_chain(state, config).invoke({
            "input": user_message,
            "messages": messages
        })
        logger.debug(f"成功生成{len(new_candidates)}个新候选解决方案")

        # 处理候选解决方案并获取反思评估
        output_messages, reflections = self._process_candidates(
            new_candidates, state, config
        )

        # 统计已在_process_candidates方法中完成，这里不再重复输出

        # 扩展搜索树，添加子节点
        child_nodes = [
            Node(cand, parent=best_candidate, reflection=reflection)
            for cand, reflection in zip(output_messages, reflections)
        ]

        logger.info(f"将{len(child_nodes)}个新节点添加到搜索树")
        best_candidate.children.extend(child_nodes)

        # 检查是否找到解决方案
        has_solution = any(r.found_solution for r in reflections)
        if has_solution:
            solution_nodes = [node for node, r in zip(
                child_nodes, reflections) if r.found_solution]
            best_solution = max(
                solution_nodes, key=lambda node: node.reflection.score)

            # 漂亮地打印解决方案信息
            logger.info("=" * 50)
            logger.info("🎉 找到解决方案!")
            logger.info("=" * 50)
            logger.info(
                f"评分: {best_solution.reflection.score}/10 | 深度: {best_solution.depth} | 搜索树节点数: {self._count_nodes(root)}")

            # 获取最佳解决方案的内容并添加到状态消息
            final_solution = best_solution.get_trajectory(
                include_reflections=False)[-1]
            logger.info(f"解决方案内容: {final_solution}")

            # 打印反思评估
            reflection_text = best_solution.reflection.reflections[:100] + "..." if len(
                best_solution.reflection.reflections) > 100 else best_solution.reflection.reflections
            logger.info(f"评估概要: {reflection_text}")
            logger.info("-" * 50)

            # 更新状态消息
            logger.debug("更新状态消息，添加最佳解决方案")

            llm = self.get_llm_client(config["configurable"]["graph_request"])
            prompt_template = ChatPromptTemplate.from_messages(
                [
                    (
                        "system",
                        "您是一个智能AI助手，请尽可能准确、全面地回答用户问题。",
                    ),
                    ("user", "{input}"),  # 用户输入
                    MessagesPlaceholder(variable_name="messages",
                                        optional=True),  # 可选的上下文消息
                ]
            )
            chain = prompt_template | llm
            question = f"用户的问题是:{config['configurable']['graph_request'].user_message}"
            question += f"经过Lats Agent分析后，找到的解决方案是:{final_solution.content}"
            question += "请结合用户的问题和解决方案，回复用户的问题,准确，全面，简洁，不要捏造事实。"
            msg = chain.invoke({
                "input": question
            })
            state["messages"].append(msg)

            # 标记根节点为已解决
            root._is_solved = True
        else:
            logger.info("🔄 本轮搜索未找到解决方案，继续探索")

            # 即使没有找到完全解决方案，也可以添加当前最佳回答以提供渐进式响应
            if child_nodes:
                best_node = max(
                    child_nodes, key=lambda node: node.reflection.score)
                if best_node.reflection.score >= 7:  # 只有当评分足够高时才更新
                    # 漂亮地打印高质量中间结果
                    logger.info("=" * 50)
                    logger.info(
                        f"⭐ 添加高质量中间结果 (评分: {best_node.reflection.score}/10)")
                    best_message = best_node.get_trajectory(
                        include_reflections=False)[-1]
                    content_summary = best_message.content[:100] + "..." if len(
                        best_message.content) > 100 else best_message.content
                    logger.info(f"内容概要: {content_summary}")
                    logger.info("-" * 50)

                    # 更新状态消息
                    state["messages"].append(best_message)

        return state

    def _count_nodes(self, node: Node) -> int:
        """计算搜索树中的节点总数

        Args:
            node: 开始计数的节点

        Returns:
            节点总数
        """
        count = 1  # 当前节点
        for child in node.children:
            count += self._count_nodes(child)
        return count

    def should_continue(self, state: LatsAgentState) -> TypedDict:
        """决定是否继续执行图中的下一步

        Args:
            state: 当前状态

        Returns:
            下一个节点名称或结束标记
        """
        root = state["root"]

        # 记录当前执行状态的关键信息
        logger.debug(f"搜索树高度: {root.height}, 是否解决: {root.is_solved}")

        # 如果找到解决方案，结束搜索
        if root.is_solved:
            logger.info("找到解决方案，结束搜索")
            return END

        # 如果搜索深度超过限制，结束搜索
        if root.height > LatsAgentNode.MAX_TREE_HEIGHT:
            logger.info(f"搜索深度达到上限 ({LatsAgentNode.MAX_TREE_HEIGHT})，结束搜索")
            return END

        # 继续探索
        return "expand"

    def get_initial_answer_chain(self, state: LatsAgentState, config: RunnableConfig):
        """获取用于生成初始回答的链

        创建一个用于生成搜索树根节点初始回答的链。这个初始回答作为搜索的起点，
        后续迭代将基于此进行改进和扩展。

        Args:
            state: 当前搜索状态
            config: 运行时配置，包含请求信息

        Returns:
            可执行的初始回答生成链
        """
        # 获取配置的LLM客户端
        llm = self.get_llm_client(config["configurable"]["graph_request"])

        # 创建提示模板
        prompt_template = ChatPromptTemplate.from_messages(
            [
                (
                    "system",
                    "您是一个智能AI助手，请尽可能准确、全面地回答用户问题。",
                ),
                ("user", "{input}"),  # 用户输入
                MessagesPlaceholder(variable_name="messages",
                                    optional=True),  # 可选的上下文消息
            ]
        )

        # 构建初始回答链，绑定工具以允许工具调用
        initial_answer_chain = prompt_template | llm.bind_tools(
            tools=self.tools  # 允许模型使用配置的工具
        ).with_config(
            run_name="GenerateInitialCandidate"  # 为追踪添加运行名称
        )

        logger.debug("初始回答生成链创建完成")
        return initial_answer_chain

    def generate_initial_response(self, state: LatsAgentState, config: RunnableConfig) -> dict:
        """生成初始响应并构建搜索树根节点

        Args:
            state: 当前状态
            config: 运行配置

        Returns:
            更新后的状态
        """
        logger.info("开始生成初始响应...")

        # 获取用户消息并生成初始回答
        user_message = config["configurable"]["graph_request"].user_message
        res = self.get_initial_answer_chain(
            state, config).invoke({"input": user_message})
        logger.debug(f"初始回答生成完成，长度: {len(res.content)}")

        # 解析工具调用
        parser = JsonOutputToolsParser(return_id=True)
        parsed = parser.invoke(res)

        # 执行工具调用
        tool_node = ToolNode(self.tools)
        tool_responses = [
            tool_node.invoke(
                {
                    "messages": [
                        AIMessage(
                            content="",
                            tool_calls=[
                                {"name": r["type"],
                                 "args": r["args"], "id": r["id"]}
                            ],
                        )
                    ]
                }
            )
            for r in parsed
        ]

        # 合并消息
        output_messages = [res] + [tr["messages"][0] for tr in tool_responses]

        # 对初始回答进行反思评估（使用静默配置）
        silent_config = {**config, "callbacks": [],
                         "configurable": {"verbose": False}}
        reflection = self.get_reflection_chain(state, config).invoke(
            {"input": user_message, "candidate": output_messages},
            config=silent_config
        )

        # 创建搜索树根节点
        r = reflection[0]
        r.found_solution = False  # 初始响应通常不算作最终解决方案
        root = Node(output_messages, reflection=r)

        # 优雅地输出初始响应的评估信息
        logger.info("=" * 50)
        logger.info("🌟 初始响应评估结果")
        logger.info("=" * 50)
        solution_status = "✅" if r.found_solution else "❌"
        logger.info(f"评分: {r.score}/10 | 是否解决问题: {solution_status}")
        logger.info(f"评估概要: {r.reflections}")

        # 记录初始解决方案内容
        if output_messages:
            solution_content = root.get_trajectory(
                include_reflections=False)[-1].content
            content_summary = solution_content[:100] + "..." if len(
                solution_content) > 100 else solution_content
            logger.info(f"初始解决方案: {content_summary}")
            logger.info("-" * 50)

        # 更新状态
        state['root'] = root

        # 将初始回答添加到状态的消息列表
        if output_messages:
            final_message = output_messages[-1]
            logger.debug(
                f"将初始响应添加到state['messages']: {final_message.content[:100]}...")
            state["messages"].append(final_message)

        return state
