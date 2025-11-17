import asyncio
import math
import time
from collections import deque
from dataclasses import dataclass
from enum import Enum
from typing import TypedDict, Annotated, Optional, List, Tuple, Dict, Any

from langchain_core.messages import BaseMessage, HumanMessage, AIMessage
from langchain_core.prompts import ChatPromptTemplate, MessagesPlaceholder
from langchain_core.runnables import RunnableConfig
from langgraph.constants import END
from langgraph.graph import StateGraph, add_messages
from pydantic import BaseModel, Field, ConfigDict
from loguru import logger

from neco.core.utils.template_loader import TemplateLoader
from neco.llm.chain.entity import BasicLLMRequest, BasicLLMResponse
from neco.llm.chain.graph import BasicGraph
from neco.llm.chain.node import ToolsNodes


class LatsAgentResponse(BasicLLMResponse):
    pass


class LatsAgentRequest(BasicLLMRequest):
    pass


class SearchStrategy(Enum):
    """搜索策略枚举"""
    PURE_LATS = "pure_lats"              # 纯LATS树搜索


class SearchPhase(Enum):
    """搜索阶段枚举"""
    INITIALIZATION = "initialization"
    COMPLETED = "completed"


@dataclass
class LATSConfig:
    """LATS搜索引擎配置"""
    # 搜索参数
    max_candidates: int = 3              # 每次扩展的候选数量
    max_tree_depth: int = 3              # 最大搜索深度
    exploration_weight: float = 1.414    # UCB探索权重(√2)

    # 质量阈值
    solution_threshold: float = 8.0      # 解决方案分数阈值
    early_stop_threshold: float = 9.0    # 早停分数阈值

    # 性能配置
    max_search_time: float = 20.0        # 最大搜索时间(秒)
    enable_pruning: bool = True          # 启用搜索剪枝


class MultiDimensionalReflection(BaseModel):
    """多维度反思评估模型"""
    model_config = ConfigDict(arbitrary_types_allowed=True)

    # 核心评估维度
    accuracy: float = Field(ge=0, le=10, description="答案准确性评分")
    completeness: float = Field(ge=0, le=10, description="答案完整性评分")
    relevance: float = Field(ge=0, le=10, description="答案相关性评分")
    clarity: float = Field(ge=0, le=10, description="表达清晰度评分")

    # 高级评估维度
    creativity: float = Field(ge=0, le=10, description="创新性和独特见解")
    actionability: float = Field(ge=0, le=10, description="可执行性和实用性")

    # 综合评估
    overall_score: float = Field(ge=0, le=10, description="加权综合评分")
    confidence: float = Field(ge=0, le=1, description="评估置信度")

    # 反思内容
    strengths: List[str] = Field(description="回答的优点")
    weaknesses: List[str] = Field(description="回答的不足")
    suggestions: List[str] = Field(description="改进建议")

    # 决策标志
    found_solution: bool = Field(description="是否找到满意解决方案")
    needs_tools: bool = Field(description="是否需要工具调用")

    def as_message(self) -> HumanMessage:
        """转换为消息格式用于上下文传递"""
        reflection_text = f"""**评估结果** (置信度: {self.confidence:.2f})
- 准确性: {self.accuracy}/10 | 完整性: {self.completeness}/10
- 相关性: {self.relevance}/10 | 清晰度: {self.clarity}/10
- 创新性: {self.creativity}/10 | 实用性: {self.actionability}/10

**综合评分**: {self.overall_score}/10

**优点**: {'; '.join(self.strengths)}
**不足**: {'; '.join(self.weaknesses)}
**建议**: {'; '.join(self.suggestions)}"""
        return HumanMessage(content=reflection_text)

    @property
    def normalized_score(self) -> float:
        return self.overall_score / 10.0

    @classmethod
    def create_default(cls, basic_score: float = 5.0) -> "MultiDimensionalReflection":
        """创建默认评估结果"""
        return cls(
            accuracy=basic_score,
            completeness=basic_score,
            relevance=basic_score,
            clarity=basic_score,
            creativity=basic_score * 0.8,
            actionability=basic_score * 0.9,
            overall_score=basic_score,
            confidence=0.6,
            strengths=["基础回答结构合理"],
            weaknesses=["需要更深入分析"],
            suggestions=["增加具体细节和例证"],
            found_solution=basic_score >= 7.0,
            needs_tools=False
        )


class LATSTreeNode:
    """LATS树搜索节点 - 专业化实现"""

    def __init__(
            self,
            messages: List[BaseMessage],
            reflection: MultiDimensionalReflection,
            parent: Optional["LATSTreeNode"] = None,
            node_id: str = None,
    ):
        self.messages = messages
        self.parent = parent
        self.children: List["LATSTreeNode"] = []
        self.reflection = reflection

        # 节点标识和层级
        self.node_id = node_id or f"node_{id(self)}"
        self.depth = parent.depth + 1 if parent is not None else 1

        # MCTS统计信息
        self.visits = 0
        self.total_reward = 0.0
        self.average_reward = 0.0

        # 状态标志
        self._is_solved = reflection.found_solution if reflection else False
        self._creation_time = time.time()

        # 初始化时进行反向传播
        if self._is_solved:
            self._mark_tree_as_solved()
        self.backpropagate(reflection.normalized_score)

    def __repr__(self) -> str:
        return (
            f"<LATSTreeNode id={self.node_id}, depth={self.depth}, "
            f"visits={self.visits}, avg_reward={self.average_reward:.3f}, "
            f"solved={self.is_solved}>"
        )

    @property
    def is_solved(self) -> bool:
        """节点是否已找到解决方案"""
        return self._is_solved

    @property
    def is_terminal(self) -> bool:
        """节点是否为叶子节点"""
        return not self.children

    @property
    def is_fully_expanded(self) -> bool:
        """节点是否已完全扩展(有具体的实现依据)"""
        # 简单启发式：如果有5个或更多子节点，认为已充分扩展
        return len(self.children) >= 5

    @property
    def best_child(self) -> Optional["LATSTreeNode"]:
        """返回最佳子节点"""
        if not self.children:
            return None
        return max(
            self.children,
            key=lambda child: (
                int(child.is_solved) * 100 +  # 优先考虑解决方案
                child.average_reward * 10 +    # 然后考虑质量
                child.reflection.confidence    # 最后考虑置信度
            )
        )

    @property
    def height(self) -> int:
        """返回以此节点为根的子树高度"""
        if not self.children:
            return 1
        return 1 + max(child.height for child in self.children)

    @property
    def tree_size(self) -> int:
        """返回以此节点为根的子树大小"""
        if not self.children:
            return 1
        return 1 + sum(child.tree_size for child in self.children)

    def upper_confidence_bound(self, exploration_weight: float = 1.414) -> float:
        """计算UCB值，平衡探索与开发"""
        if self.parent is None:
            raise ValueError("根节点无法计算UCB值")

        if self.visits == 0:
            return float('inf')  # 未访问节点优先级最高

        # UCB1公式: avg_reward + c * sqrt(ln(parent_visits) / visits)
        exploitation_term = self.average_reward
        exploration_term = exploration_weight * math.sqrt(
            math.log(self.parent.visits) / self.visits
        )

        # 加入多维度奖励
        quality_bonus = self.reflection.confidence * 0.1

        return exploitation_term + exploration_term + quality_bonus

    def backpropagate(self, reward: float) -> None:
        """反向传播奖励值到所有祖先节点"""
        current_node = self

        while current_node is not None:
            current_node.visits += 1
            current_node.total_reward += reward
            current_node.average_reward = current_node.total_reward / current_node.visits
            current_node = current_node.parent

    def get_messages(self, include_reflections: bool = True) -> List[BaseMessage]:
        """获取节点消息，可选择是否包含反思"""
        if include_reflections and self.reflection:
            return self.messages + [self.reflection.as_message()]
        return self.messages.copy()

    def get_trajectory(self, include_reflections: bool = True) -> List[BaseMessage]:
        """获取从根到当前节点的完整轨迹"""
        trajectory = []
        path_nodes = []

        # 收集路径上的所有节点
        current_node = self
        while current_node is not None:
            path_nodes.append(current_node)
            current_node = current_node.parent

        # 从根开始构建轨迹
        for node in reversed(path_nodes):
            trajectory.extend(node.get_messages(include_reflections))

        return trajectory

    def get_all_descendants(self) -> List["LATSTreeNode"]:
        """获取所有后代节点"""
        descendants = []
        queue = deque(self.children)

        while queue:
            node = queue.popleft()
            descendants.append(node)
            queue.extend(node.children)

        return descendants

    def get_best_solution_node(self) -> Optional["LATSTreeNode"]:
        """在当前子树中寻找最佳解决方案节点"""
        all_nodes = [self] + self.get_all_descendants()

        # 筛选已解决的终端节点
        solution_nodes = [
            node for node in all_nodes
            if node.is_solved and node.is_terminal
        ]

        if not solution_nodes:
            return None

        # 返回综合评分最高的解决方案
        return max(
            solution_nodes,
            key=lambda node: (
                node.reflection.overall_score * 10 +
                node.reflection.confidence * 5 +
                node.visits  # 访问次数作为tie-breaker
            )
        )

    def _mark_tree_as_solved(self) -> None:
        """将整个路径标记为已解决"""
        current_node = self.parent
        while current_node is not None:
            current_node._is_solved = True
            current_node = current_node.parent

    def prune_low_quality_children(self, threshold: float = 0.3) -> int:
        """剪枝低质量子节点，返回被剪枝的节点数"""
        if not self.children:
            return 0

        initial_count = len(self.children)
        self.children = [
            child for child in self.children
            if child.average_reward >= threshold or child.is_solved
        ]

        pruned_count = initial_count - len(self.children)
        if pruned_count > 0:
            logger.debug(f"节点 {self.node_id} 剪枝了 {pruned_count} 个低质量子节点")

        return pruned_count


class LATSAgentState(TypedDict):
    """专业化LATS Agent状态管理"""
    messages: Annotated[List[BaseMessage], add_messages]
    graph_request: LatsAgentRequest

    # LATS树搜索状态
    root: Optional[LATSTreeNode]
    current_phase: SearchPhase
    search_config: LATSConfig

    # 搜索统计
    search_start_time: float
    total_evaluations: int
    best_score_so_far: float

    # 中间结果
    intermediate_results: List[Dict[str, Any]]
    tool_execution_needed: bool


class LatsAgentNode(ToolsNodes):
    """LATS Agent - 专业化树搜索执行节点"""

    async def _evaluate_candidate(
        self,
        user_input: str,
        candidate_messages: List[BaseMessage],
        config: RunnableConfig,
        search_config: LATSConfig
    ) -> MultiDimensionalReflection:
        """高级多维度候选方案评估"""
        try:
            # 提取候选回答内容
            contents = []
            for msg in candidate_messages:
                if hasattr(msg, 'content') and msg.content:
                    contents.append(str(msg.content))
            candidate_content = "\n\n".join(contents) if contents else "空回答"

            # 智能获取评估标准
            evaluation_criteria = "准确性、完整性、相关性、清晰度、实用性"  # 默认标准
            try:
                from pydantic import BaseModel

                class EvaluationCriteria(BaseModel):
                    question_type: str = Field(
                        description="问题类型：时间查询类、方法指导类、原因解释类、通用问答类")
                    criteria: str = Field(description="对应的评估标准关键词")

                criteria_prompt = f"""
                请分析以下用户问题的类型，并提供相应的评估标准。

                用户问题：{user_input}

                请从以下类型中选择最符合的：
                1. 时间查询类：时间查询准确性、实时性、格式规范性
                2. 方法指导类：方法完整性、可操作性、步骤清晰度
                3. 原因解释类：解释深度、逻辑性、例证充分性
                4. 通用问答类：准确性、完整性、相关性、清晰度、实用性
                """

                criteria_result = await self.structured_output_parser.parse_with_structured_output(
                    user_message=criteria_prompt,
                    pydantic_class=EvaluationCriteria
                )
                evaluation_criteria = criteria_result.criteria

            except Exception as e:
                logger.warning(f"智能评估标准获取失败，使用默认标准: {e}")

            # 构建评估提示
            evaluation_prompt = TemplateLoader.render_template(
                "prompts/lats_agent/multi_dimensional_evaluation",
                {
                    "user_question": user_input,
                    "candidate_answer": candidate_content,
                    "evaluation_criteria": evaluation_criteria
                }
            )

            # 执行多维度评估
            result = await self.structured_output_parser.parse_with_structured_output(
                user_message=evaluation_prompt,
                pydantic_class=MultiDimensionalReflection
            )

            # 设置标志
            result.needs_tools = False
            if result.overall_score >= search_config.solution_threshold:
                result.found_solution = True

            logger.debug(
                f"候选评估完成: {result.overall_score:.2f}/10 (置信度: {result.confidence:.2f})")
            return result

        except Exception as e:
            logger.warning(f"多维度评估失败，使用默认评估: {e}")
            return MultiDimensionalReflection.create_default(6.0)

    def select_node_for_expansion(self, root: LATSTreeNode, config: LATSConfig) -> LATSTreeNode:
        """使用改进的UCB算法选择扩展节点"""
        if not root.children:
            return root

        current = root
        selection_path = [root]

        # 沿着UCB值最高的路径向下选择
        while current.children:
            # 判断是否应该扩展当前节点
            should_expand = (
                not current.is_solved and
                current.depth < config.max_tree_depth and
                (current.visits < 3 or len(current.children) < config.max_candidates)
            )

            if not should_expand and current.is_fully_expanded:
                # 已充分扩展，继续向下选择
                best_child = max(
                    current.children,
                    key=lambda child: child.upper_confidence_bound(
                        config.exploration_weight)
                )
                current = best_child
                selection_path.append(current)
            else:
                break

        logger.debug(
            f"MCTS选择路径: {' -> '.join(f'Node{i}' for i in range(len(selection_path)))}, "
            f"最终选择深度: {current.depth}"
        )
        return current

    async def _process_candidates_with_evaluation(
        self,
        candidates: List[BaseMessage],
        user_message: str,
        config: RunnableConfig,
        search_config: LATSConfig
    ) -> Tuple[List[List[BaseMessage]], List[MultiDimensionalReflection]]:
        """处理和评估候选方案 - 并行评估以提高速度"""

        candidate_message_lists = [[candidate] for candidate in candidates]
        progress_messages = config.setdefault('progress_messages', [])

        # 显示评估开始信息
        progress_messages.append(
            AIMessage(content=f"\n\n📊 **评估 {len(candidates)} 个候选方案**\n\n"))

        # 准备评估进度消息
        for i in range(len(candidate_message_lists)):
            progress_messages.append(
                AIMessage(content=f"\n\n📊 **评估候选 {i+1}/{len(candidate_message_lists)}**\n\n"))

        # 并行评估所有候选方案
        logger.debug(f"开始并行评估 {len(candidate_message_lists)} 个候选方案")
        
        async def evaluate_with_fallback(i: int, messages: List[BaseMessage]) -> MultiDimensionalReflection:
            """带降级处理的评估函数"""
            try:
                return await self._evaluate_candidate(user_message, messages, config, search_config)
            except Exception as e:
                logger.warning(f"候选 {i+1} 评估失败: {e}")
                return MultiDimensionalReflection.create_default(4.0)
        
        # 并行执行所有评估
        evaluation_tasks = [
            evaluate_with_fallback(i, messages)
            for i, messages in enumerate(candidate_message_lists)
        ]
        valid_reflections = await asyncio.gather(*evaluation_tasks)
        
        logger.debug(f"并行评估完成，获得 {len(valid_reflections)} 个评估结果")

        # 添加评估结果消息
        for i, reflection in enumerate(valid_reflections):
            progress_messages.append(AIMessage(
                content=f"\n\n✅ 候选 {i+1}: **{reflection.overall_score:.1f}/10**\n\n"))

        # 记录评估摘要
        if valid_reflections:
            scores = [r.overall_score for r in valid_reflections]
            confidences = [r.confidence for r in valid_reflections]
            solved_count = sum(
                1 for r in valid_reflections if r.found_solution)
            avg_score = sum(scores) / len(scores)
            avg_confidence = sum(confidences) / len(confidences)

            logger.info(
                f"📊 评估完成: {len(valid_reflections)}候选 | "
                f"质量分布: 最高{max(scores):.1f} 平均{avg_score:.1f} 最低{min(scores):.1f} | "
                f"置信度: {avg_confidence:.2f} | 解决方案: {solved_count}个"
            )

        # 应用早停策略
        for reflection in valid_reflections:
            if reflection.overall_score >= search_config.early_stop_threshold:
                reflection.found_solution = True
                logger.info(
                    f"🎯 达到早停阈值 {search_config.early_stop_threshold}，标记为解决方案")

        return candidate_message_lists, list(valid_reflections)

    async def _generate_candidates(self, user_message: str, messages: List[BaseMessage], config: RunnableConfig) -> List[BaseMessage]:
        """生成候选方案 - 使用 ReAct 模式并行生成以提高速度"""

        # 从配置获取候选数量
        search_config = config.get('configurable', {}).get(
            'search_config', LATSConfig())
        max_candidates = getattr(search_config, 'max_candidates', 3)

        # 使用候选生成模板
        system_message = TemplateLoader.render_template(
            "prompts/lats_agent/candidate_generation",
            {
                "user_question": user_message,
                "context_length": len(messages)
            }
        )

        # 准备进度消息
        progress_messages = [
            AIMessage(content=f"\n\n🔍 **生成候选方案 {i+1}/{max_candidates}**\n\n")
            for i in range(max_candidates)
        ]
        config.setdefault('progress_messages', []).extend(progress_messages)

        # 并行生成多个候选方案
        logger.debug(f"开始并行生成 {max_candidates} 个候选方案")
        
        tasks = [
            self.invoke_react_for_candidate(user_message, messages, config, system_message)
            for _ in range(max_candidates)
        ]
        
        candidates = await asyncio.gather(*tasks)
        logger.debug(f"并行生成完成，获得 {len(candidates)} 个候选方案")

        return list(candidates)

    async def expand(self, state: LATSAgentState, config: RunnableConfig) -> LATSAgentState:
        """扩展搜索树"""
        logger.info("🌳 开始扩展搜索树")

        search_depth = state["root"].height if state["root"] else 0
        search_start_msg = f"🔍 **第 {search_depth + 1} 轮优化搜索**"

        root = state["root"]
        if not root:
            logger.error("搜索树根节点未初始化")
            return state

        best_candidate = self.select_node_for_expansion(
            root, state.get("search_config", LATSConfig()))
        messages = best_candidate.get_trajectory()

        config['progress_messages'] = [AIMessage(content=search_start_msg)]

        user_message = config["configurable"]["graph_request"].user_message
        new_candidates = await self._generate_candidates(user_message, messages, config)

        output_messages, reflections = await self._process_candidates_with_evaluation(
            new_candidates, user_message, config, state.get(
                "search_config", LATSConfig())
        )

        progress_messages = config.get('progress_messages', [])
        search_config = state.get("search_config", LATSConfig())

        # 扩展搜索树
        child_nodes = [
            LATSTreeNode(messages=cand, reflection=reflection,
                         parent=best_candidate)
            for cand, reflection in zip(output_messages, reflections)
        ]
        best_candidate.children.extend(child_nodes)

        best_score = max((r.overall_score for r in reflections), default=0)
        status_icon = '✨' if best_score >= 8.0 else '🔍 继续优化...'
        progress_messages.append(
            AIMessage(content=f"\n\n🎯 **最佳评分: {best_score:.1f}/10** {status_icon}\n\n"))

        # 检查解决方案 - 使用更严格的标准
        solution_nodes = [node for node, r in zip(child_nodes, reflections)
                          if r.found_solution and r.overall_score >= search_config.solution_threshold]

        if solution_nodes:
            best_solution = max(
                solution_nodes, key=lambda node: node.reflection.overall_score)
            logger.info(
                f"🎉 找到高质量解决方案! 评分: {best_solution.reflection.overall_score}/10")

            # 只有真正高质量的解决方案才标记为已解决
            root._is_solved = True
            messages_to_add = progress_messages
        else:
            # 不要在这里添加最终答案，让搜索继续进行
            messages_to_add = progress_messages
            logger.info(f"🔍 当前最佳评分 {best_score:.1f}，继续搜索更优方案")

        return {
            **state,
            "messages": state.get("messages", []) + messages_to_add
        }

    async def generate_final_answer(self, state: LATSAgentState, config: RunnableConfig) -> dict:
        """生成最终答案节点"""
        logger.info("📝 生成最终总结答案")

        root = state["root"]

        # 找到最佳解决方案节点
        best_solution_node = root.get_best_solution_node()
        if not best_solution_node:
            # 如果没有找到明确的解决方案，选择评分最高的节点
            all_nodes = [root] + root.get_all_descendants()
            best_solution_node = max(
                all_nodes, key=lambda node: node.reflection.overall_score)
            logger.info(
                f"使用评分最高的节点作为最终方案: {best_solution_node.reflection.overall_score}/10")

        # 获取最佳解决方案的完整轨迹
        solution_trajectory = best_solution_node.get_trajectory(
            include_reflections=False)

        # 构建完整的解决方案上下文，包含所有相关信息
        solution_parts = []
        for msg in solution_trajectory:
            content = getattr(msg, 'content', None)
            if content and isinstance(content, str):
                # 过滤掉进度提示消息
                if not any(content.startswith(prefix) for prefix in ["�", "�📊", "🧠", "✅ **初始评分", "⏰", "🌳"]):
                    solution_parts.append(content.strip())
        
        # 合并所有相关内容
        final_solution_content = "\n\n".join(solution_parts) if solution_parts else "抱歉，无法生成满意的答案。"
        
        logger.debug(f"[generate_final_answer] 提取到的解决方案内容: {final_solution_content[:200]}")

        # 生成最终综合答案
        system_message = TemplateLoader.render_template(
            "prompts/lats_agent/intelligent_assistant")

        user_question = config['configurable']['graph_request'].user_message

        question = TemplateLoader.render_template(
            "prompts/lats_agent/final_answer_synthesis",
            {
                "user_question": user_question,
                "solution_content": final_solution_content
            }
        )

        # 使用独立的 OpenAI 客户端生成最终答案，避免 LangGraph 流式捕获
        client = self.structured_output_parser._get_openai_client()
        model_name = getattr(self.llm, 'model_name', None) or getattr(
            self.llm, 'model', 'gpt-3.5-turbo')
        temperature = getattr(self.llm, 'temperature', 0.7)

        call_kwargs = {
            'model': model_name,
            'messages': [
                {'role': 'system', 'content': system_message},
                {'role': 'user', 'content': question}
            ],
            'temperature': temperature,
        }

        if hasattr(self.llm, 'extra_body') and self.llm.extra_body:
            call_kwargs['extra_body'] = self.llm.extra_body

        raw_response = client.chat.completions.create(**call_kwargs)
        final_answer_content = raw_response.choices[0].message.content

        logger.info("✅ 最终答案生成完成")
        return {
            **state,
            "messages": state.get("messages", []) + [AIMessage(content=final_answer_content)]
        }

    def should_continue(self, state: LATSAgentState) -> str:
        """决定是否继续搜索或进入最终答案生成"""
        root = state.get("root")

        # 如果有根节点，检查是否找到解决方案
        if root and root.is_solved:
            logger.info("✅ 已找到解决方案，生成最终答案")
            return "generate_final_answer"

        # 检查搜索深度和时间
        search_config = state.get('search_config', LATSConfig())
        elapsed_time = time.time() - state.get("search_start_time", time.time())

        if root and root.height >= search_config.max_tree_depth:
            logger.info(f"⏹️ 达到最大搜索深度 {search_config.max_tree_depth}，生成最终答案")
            return "generate_final_answer"

        if elapsed_time >= search_config.max_search_time:
            logger.info(f"⏰ 达到最大搜索时间 {search_config.max_search_time}s，生成最终答案")
            return "generate_final_answer"

        # 检查是否所有节点的评分都太低，避免无限搜索
        if root:
            all_nodes = [root] + root.get_all_descendants()
            best_score = max(
                node.reflection.overall_score for node in all_nodes)
            if best_score < 5.0 and root.height >= 2:
                logger.info(f"⚠️ 搜索质量不佳 (最佳: {best_score}/10)，提前结束")
                return "generate_final_answer"

        logger.info("🌳 继续扩展搜索树")
        return "expand"

    async def generate_initial_response(self, state: LATSAgentState, config: RunnableConfig) -> dict:
        """生成初始响应 - 使用 ReAct 模式生成第一个候选并评估"""
        request = config['configurable']['graph_request']
        user_message = request.user_message

        # 简化状态初始化
        state['search_config'] = LATSConfig()
        state['search_start_time'] = time.time()
        state['current_phase'] = SearchPhase.INITIALIZATION

        progress_start_msg = AIMessage(content="\n\n🧠 **智能分析中...**\n\n")

        system_message = TemplateLoader.render_template(
            "prompts/lats_agent/initial_response")

        initial_candidate = await self.invoke_react_for_candidate(
            user_message,
            state.get("messages", []),
            config,
            system_message
        )

        eval_progress_msg = AIMessage(content="\n\n📊 **评估答案质量**\n\n")

        search_config = state.get('search_config', LATSConfig())
        output_messages = [initial_candidate]
        reflection = await self._evaluate_candidate(user_message, output_messages, config, search_config)

        root = LATSTreeNode(messages=output_messages, reflection=reflection)
        state['root'] = root

        logger.info(
            f"📊 初始响应评估完成 | 评分: {reflection.overall_score}/10 | 解决方案: {reflection.found_solution}")

        # 使用更严格的标准判断是否为解决方案
        is_high_quality_solution = (reflection.found_solution and
                                    reflection.overall_score >= search_config.solution_threshold and
                                    reflection.confidence >= 0.8)

        if is_high_quality_solution:
            eval_result_msg = f"\n\n✅ **初始评分: {reflection.overall_score:.1f}/10** 🎉\n\n"
            messages_to_add = [progress_start_msg, eval_progress_msg, AIMessage(
                content=eval_result_msg), initial_candidate]
            root._is_solved = True
        else:
            eval_result_msg = f"\n\n✅ **初始评分: {reflection.overall_score:.1f}/10** \n\n🔍 寻找更优方案...\n\n"
            messages_to_add = [progress_start_msg, eval_progress_msg,
                               initial_candidate, AIMessage(content=eval_result_msg)]

        return {
            **state,
            "messages": state.get("messages", []) + messages_to_add
        }


class LatsAgentGraph(BasicGraph):
    """LATS Agent 图执行器 - 优化版本"""

    async def compile_graph(self, request: LatsAgentRequest) -> StateGraph:
        # 初始化优化版本的节点构建器
        node_builder = LatsAgentNode()
        await node_builder.setup(request)

        # 创建状态图
        graph_builder = StateGraph(LATSAgentState)

        # 添加基础图结构
        last_edge = self.prepare_graph(graph_builder, node_builder)

        # 添加 LATS 特有节点
        graph_builder.add_node("generate_initial_response",
                               node_builder.generate_initial_response)
        graph_builder.add_node("expand", node_builder.expand)
        graph_builder.add_node("generate_final_answer",
                               node_builder.generate_final_answer)

        # 构建执行流程 - 标准 LATS 流程
        graph_builder.add_edge(last_edge, 'generate_initial_response')

        # 初始响应后根据评估结果决定
        graph_builder.add_conditional_edges(
            "generate_initial_response",
            node_builder.should_continue,
            {
                "expand": "expand",
                "generate_final_answer": "generate_final_answer"
            }
        )

        # 扩展搜索后的条件分支
        graph_builder.add_conditional_edges(
            "expand",
            node_builder.should_continue,
            {
                "expand": "expand",
                "generate_final_answer": "generate_final_answer"
            }
        )

        # 最终答案生成后结束
        graph_builder.add_edge("generate_final_answer", END)

        # 编译并返回图
        compiled_graph = graph_builder.compile()
        logger.info("✅ LATS Agent 执行图编译完成")

        return compiled_graph
