import asyncio
import math
import time
from collections import deque
from dataclasses import dataclass
from enum import Enum
from typing import TypedDict, Annotated, Optional, List, Tuple, Dict, Any, Union
from concurrent.futures import ThreadPoolExecutor

from langchain_core.messages import BaseMessage, HumanMessage, AIMessage
from langchain_core.prompts import ChatPromptTemplate, MessagesPlaceholder
from langchain_core.runnables import RunnableConfig
from langgraph.constants import END
from langgraph.graph import StateGraph, add_messages
from pydantic import BaseModel, Field, ConfigDict
from loguru import logger

from neco.core.utils.template_loader import TemplateLoader
from neco.llm.chain.entity import BasicLLMRequest, BasicLLMResponse, ToolsServer
from neco.llm.chain.graph import BasicGraph
from neco.llm.chain.node import ToolsNodes

class LatsAgentResponse(BasicLLMResponse):
    pass


class LatsAgentRequest(BasicLLMRequest):
    tools_servers: List[ToolsServer] = []
    langchain_tools: List[str] = []

# ========== LATS核心配置和枚举 ==========

class SearchStrategy(Enum):
    """搜索策略枚举"""
    PURE_LATS = "pure_lats"              # 纯LATS树搜索
    LATS_WITH_REACT = "lats_with_react"  # LATS + ReAct工具调用
    ADAPTIVE = "adaptive"                # 自适应策略选择

class SearchPhase(Enum):
    """搜索阶段枚举"""
    INITIALIZATION = "initialization"
    TREE_SEARCH = "tree_search"
    TOOL_EXECUTION = "tool_execution"
    SYNTHESIS = "synthesis"
    COMPLETED = "completed"

@dataclass
class LATSConfig:
    """LATS搜索引擎配置"""
    # 搜索参数
    max_candidates: int = 5              # 每次扩展的候选数量
    max_tree_depth: int = 4              # 最大搜索深度
    exploration_weight: float = 1.414    # UCB探索权重(√2)
    
    # 质量阈值
    solution_threshold: float = 8.0      # 解决方案分数阈值
    early_stop_threshold: float = 9.0    # 早停分数阈值
    
    # 性能配置
    parallel_evaluation: bool = True     # 并行评估
    max_search_time: float = 30.0       # 最大搜索时间(秒)
    enable_pruning: bool = True          # 启用搜索剪枝
    
    # 策略选择
    strategy: SearchStrategy = SearchStrategy.ADAPTIVE
    use_react_fallback: bool = True      # 复杂查询使用ReAct

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
        reflection_text = f"""
        **评估结果** (置信度: {self.confidence:.2f})
        - 准确性: {self.accuracy}/10 | 完整性: {self.completeness}/10
        - 相关性: {self.relevance}/10 | 清晰度: {self.clarity}/10
        - 创新性: {self.creativity}/10 | 实用性: {self.actionability}/10
        
        **综合评分**: {self.overall_score}/10
        
        **优点**: {'; '.join(self.strengths)}
        **不足**: {'; '.join(self.weaknesses)}
        **建议**: {'; '.join(self.suggestions)}
        """
        return HumanMessage(content=reflection_text.strip())
    
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
    """LATS Agent - 专业化树搜索执行节点
    
    使用配置化参数替代硬编码常量，支持运行时调整搜索策略。
    """

    
    async def _evaluate_candidate(
        self, 
        user_input: str, 
        candidate_messages: List[BaseMessage], 
        config: RunnableConfig,
        search_config: LATSConfig
    ) -> MultiDimensionalReflection:
        """高级多维度候选方案评估"""
        try:
            # 构建候选回答内容
            candidate_content = self._extract_candidate_content(candidate_messages)
            
            # 让ReAct Agent自主判断是否需要工具，不做预判
            needs_tools = False
            
            # 获取智能评估标准
            evaluation_criteria = await self._get_evaluation_criteria(user_input)
            
            evaluation_prompt = TemplateLoader.render_template(
                "prompts/lats_agent/multi_dimensional_evaluation",
                {
                    "user_question": user_input,
                    "candidate_answer": candidate_content,
                    "evaluation_criteria": evaluation_criteria
                }
            )

            # 使用结构化输出解析器进行多维度评估
            result = await self.structured_output_parser.parse_with_structured_output(
                user_message=evaluation_prompt,
                pydantic_class=MultiDimensionalReflection
            )
            
            # 设置工具需求标志
            result.needs_tools = needs_tools
            
            # 根据配置调整解决方案阈值
            if result.overall_score >= search_config.solution_threshold:
                result.found_solution = True
            
            logger.debug(f"候选评估完成: {result.overall_score:.2f}/10 (置信度: {result.confidence:.2f})")
            return result
            
        except Exception as e:
            logger.warning(f"多维度评估失败，使用默认评估: {e}")
            return MultiDimensionalReflection.create_default(6.0)

    def _extract_candidate_content(self, messages: List[BaseMessage]) -> str:
        """提取候选消息的核心内容"""
        contents = []
        for msg in messages:
            if hasattr(msg, 'content') and msg.content:
                contents.append(str(msg.content))
        return "\n".join(contents) if contents else "空回答"



    async def _get_evaluation_criteria(self, user_input: str) -> str:
        """智能获取评估标准 - 使用结构化输出"""
        try:
            # 定义评估标准结构化模型
            from pydantic import BaseModel
            
            class EvaluationCriteria(BaseModel):
                question_type: str = Field(description="问题类型：时间查询类、方法指导类、原因解释类、通用问答类")
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
            
            result = await self.structured_output_parser.parse_with_structured_output(
                user_message=criteria_prompt,
                pydantic_class=EvaluationCriteria
            )
            
            return result.criteria
                
        except Exception as e:
            logger.warning(f"智能评估标准获取失败，使用默认标准: {e}")
            return "准确性、完整性、相关性、清晰度、实用性"



    def select_node_for_expansion(
        self, 
        root: LATSTreeNode, 
        config: LATSConfig
    ) -> LATSTreeNode:
        """使用改进的UCB算法选择扩展节点"""
        if not root.children:
            return root

        current = root
        selection_path = [root]
        
        # 沿着UCB值最高的路径向下选择，直到找到可扩展的节点
        while current.children and not self._should_expand_node(current, config):
            if current.is_fully_expanded:
                # 已充分扩展，继续向下选择
                best_child = max(
                    current.children,
                    key=lambda child: child.upper_confidence_bound(config.exploration_weight)
                )
                current = best_child
                selection_path.append(current)
            else:
                # 可以在当前节点扩展
                break
        
        logger.debug(
            f"MCTS选择路径: {' -> '.join(f'Node{i}' for i in range(len(selection_path)))}, "
            f"最终选择深度: {current.depth}"
        )
        return current

    def _should_expand_node(self, node: LATSTreeNode, config: LATSConfig) -> bool:
        """判断节点是否应该被扩展"""
        # 如果已经是解决方案，不需要扩展
        if node.is_solved:
            return False
            
        # 如果达到最大深度，不扩展
        if node.depth >= config.max_tree_depth:
            return False
            
        # 如果访问次数太少，继续扩展当前节点
        if node.visits < 3:
            return True
            
        # 如果子节点数量还没达到配置的候选数量，可以扩展
        return len(node.children) < config.max_candidates

    async def _process_candidates_with_evaluation(
        self,
        candidates: List[BaseMessage],
        user_message: str,
        config: RunnableConfig,
        search_config: LATSConfig
    ) -> Tuple[List[List[BaseMessage]], List[MultiDimensionalReflection]]:
        """处理和评估候选方案 - 支持并行评估"""
        
        # 准备候选消息列表
        candidate_message_lists = [[candidate] for candidate in candidates]

        # 显示评估开始信息
        eval_start_msg = f"📊 **评估 {len(candidates)} 个候选方案**"
        progress_messages = config.setdefault('progress_messages', [])
        progress_messages.append(AIMessage(content=eval_start_msg))

        # 并行评估所有候选方案
        if search_config.parallel_evaluation:
            evaluation_tasks = [
                self._evaluate_candidate(user_message, messages, config, search_config)
                for messages in candidate_message_lists
            ]
            reflections = await asyncio.gather(*evaluation_tasks, return_exceptions=True)
            
            # 处理评估异常
            valid_reflections = []
            valid_candidates = []
            for i, reflection in enumerate(reflections):
                if isinstance(reflection, Exception):
                    logger.warning(f"候选 {i} 评估失败: {reflection}")
                    valid_reflections.append(MultiDimensionalReflection.create_default(4.0))
                else:
                    valid_reflections.append(reflection)
                    # 显示每个候选的评估结果
                    eval_result_msg = f"✅ 候选 {i+1}: **{reflection.overall_score:.1f}/10**"
                    progress_messages.append(AIMessage(content=eval_result_msg))
                
                valid_candidates.append(candidate_message_lists[i])
                
        else:
            # 串行评估
            valid_reflections = []
            valid_candidates = candidate_message_lists
            for i, messages in enumerate(candidate_message_lists):
                # 显示串行评估进度
                eval_progress_msg = f"📊 **评估候选 {i+1}/{len(candidate_message_lists)}**"
                progress_messages.append(AIMessage(content=eval_progress_msg))
                
                reflection = await self._evaluate_candidate(
                    user_message, messages, config, search_config
                )
                valid_reflections.append(reflection)
                
                # 显示评估结果
                eval_result_msg = f"✅ 候选 {i+1}: **{reflection.overall_score:.1f}/10**"
                progress_messages.append(AIMessage(content=eval_result_msg))

        # 记录评估摘要
        self._log_comprehensive_evaluation_summary(valid_reflections)

        # 应用早停策略
        for reflection in valid_reflections:
            if reflection.overall_score >= search_config.early_stop_threshold:
                reflection.found_solution = True
                logger.info(f"🎯 达到早停阈值 {search_config.early_stop_threshold}，标记为解决方案")

        return valid_candidates, valid_reflections

    def _log_comprehensive_evaluation_summary(
        self, 
        reflections: List[MultiDimensionalReflection]
    ) -> None:
        """记录详细的评估摘要"""
        if not reflections:
            return

        # 统计信息
        scores = [r.overall_score for r in reflections]
        confidences = [r.confidence for r in reflections]
        solved_count = sum(1 for r in reflections if r.found_solution)
        tool_needed_count = sum(1 for r in reflections if r.needs_tools)

        logger.info(
            f"📊 多维度评估完成 | "
            f"候选数: {len(reflections)} | "
            f"质量分布: 最高{max(scores):.1f} 平均{sum(scores)/len(scores):.1f} 最低{min(scores):.1f} | "
            f"平均置信度: {sum(confidences)/len(confidences):.2f} | "
            f"解决方案: {solved_count}个 | "
            f"需要工具: {tool_needed_count}个"
        )

    async def _invoke_react_for_candidate(self, user_message: str, messages: List[BaseMessage], config: RunnableConfig, system_prompt: str) -> AIMessage:
        """复用 ReAct 逻辑生成单个候选 - 使用可复用的 ReAct 节点组合"""
        
        try:
            # 创建临时状态图来使用可复用的 ReAct 节点组合
            from langgraph.graph import StateGraph
            temp_graph_builder = StateGraph(dict)
            
            # 使用可复用的 ReAct 节点组合构建图
            react_entry_node = await self.build_react_nodes(
                graph_builder=temp_graph_builder,
                composite_node_name="temp_react_candidate",
                additional_system_prompt=system_prompt,
                next_node=END
            )
            
            # 设置起始节点
            temp_graph_builder.set_entry_point(react_entry_node)
            temp_graph_builder.add_edge(react_entry_node, END)
            
            # 编译临时图
            temp_graph = temp_graph_builder.compile()
            
            # 调用 ReAct 节点
            result = await temp_graph.ainvoke(
                {"messages": messages[-3:] if len(messages) > 3 else messages},
                config=config
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
            logger.warning(f"ReAct 调用失败: {e}，使用降级方案")
            return await self._generate_fallback_candidate(user_message, messages, system_prompt)
    
    async def _generate_fallback_candidate(self, user_message: str, messages: List[BaseMessage], system_message: str) -> AIMessage:
        """降级方案：直接使用 LLM 生成候选"""
        prompt_template = ChatPromptTemplate.from_messages([
            ("system", system_message),
            ("user", "{input}"),
            MessagesPlaceholder(variable_name="messages", optional=True),
        ])
        
        chain = prompt_template | self.llm
        try:
            candidate = await chain.ainvoke({
                "input": user_message,
                "messages": messages[-3:] if len(messages) > 3 else messages
            })
            return candidate
        except Exception as e:
            logger.error(f"降级方案也失败: {e}")
            return AIMessage(
                content=f"正在重新分析这个问题: {user_message}，寻找更好的解决方案...",
                tool_calls=[]
            )

    async def _generate_candidates(self, user_message: str, messages: List[BaseMessage], config: RunnableConfig) -> List[BaseMessage]:
        """生成候选方案 - 使用 ReAct 模式（复用 build_react_nodes 的逻辑）"""
        
        # 从配置获取候选数量
        search_config = config.get('configurable', {}).get('search_config', LATSConfig())
        max_candidates = getattr(search_config, 'max_candidates', 3)
        
        # 使用候选生成模板
        system_message = TemplateLoader.render_template(
            "prompts/lats_agent/candidate_generation",
            {
                "user_question": user_message,
                "context_length": len(messages)
            }
        )
        
        # 生成多个候选方案（每个候选都通过 ReAct 生成）
        candidates = []
        progress_messages = []
        
        for i in range(max_candidates):
            # 显示候选生成进度
            progress_msg = f"🔍 **生成候选方案 {i+1}/{max_candidates}**"
            progress_messages.append(AIMessage(content=progress_msg))
            
            logger.debug(f"使用 ReAct 模式生成第 {i+1}/{max_candidates} 个候选方案")
            candidate = await self._invoke_react_for_candidate(user_message, messages, config, system_message)
            candidates.append(candidate)
        
        # 将进度信息存储到配置中，供后续使用
        config.setdefault('progress_messages', []).extend(progress_messages)
        return candidates

    async def _generate_diverse_candidates(
        self, 
        user_message: str, 
        messages: List[BaseMessage], 
        config: RunnableConfig,
        search_config: LATSConfig
    ) -> List[BaseMessage]:
        """生成多样化的候选方案 - 使用不同的提示策略"""
        
        # 基础候选生成（复用现有逻辑）
        base_candidates = await self._generate_candidates(user_message, messages, config)
        
        # 如果需要更多候选，可以添加变体策略
        if len(base_candidates) < search_config.max_candidates:
            additional_needed = search_config.max_candidates - len(base_candidates)
            
            # 生成创新性候选
            creative_prompt = f"请从创新的角度重新思考这个问题：{user_message}"
            creative_candidates = await self._generate_candidates(creative_prompt, messages[-2:], config)
            base_candidates.extend(creative_candidates[:additional_needed])
        
        return base_candidates[:search_config.max_candidates]

    def _build_search_progress_info(
        self, 
        state: LATSAgentState, 
        selected_node: LATSTreeNode, 
        config: RunnableConfig
    ) -> str:
        """构建搜索进度信息"""
        elapsed_time = time.time() - state["search_start_time"]
        search_config = state["search_config"]
        
        return f"""🌳 **LATS智能树搜索 - 第 {selected_node.depth} 层**

🎯 **目标**: {config["configurable"]["graph_request"].user_message}
⏱️ **搜索时间**: {elapsed_time:.1f}s / {search_config.max_search_time:.0f}s
📊 **当前统计**: 已评估{state["total_evaluations"]}个候选，最高分{state["best_score_so_far"]:.1f}
🔍 **搜索策略**: {search_config.strategy.value} | 并行评估: {'启用' if search_config.parallel_evaluation else '关闭'}

💡 **正在第 {selected_node.depth} 层生成 {search_config.max_candidates} 个解决方案候选...**"""

    def _build_solution_found_message(self, solution_node: LATSTreeNode) -> str:
        """构建找到解决方案的消息"""
        reflection = solution_node.reflection
        return f"""🎉 **找到高质量解决方案！**

✨ **综合评分**: {reflection.overall_score:.1f}/10 (置信度: {reflection.confidence:.2f})
🏆 **评估亮点**: {' | '.join(reflection.strengths[:2])}
📋 **质量维度**: 准确性{reflection.accuracy:.1f} 完整性{reflection.completeness:.1f} 创新性{reflection.creativity:.1f}

🚀 **正在为您整理最终答案...**"""

    def _build_intermediate_result_message(self, node: LATSTreeNode) -> str:
        """构建中间结果消息"""
        reflection = node.reflection
        return f"""⭐ **发现优质候选答案**

📊 **质量评分**: {reflection.overall_score:.1f}/10 (置信度: {reflection.confidence:.2f})
🔍 **优势**: {reflection.strengths[0] if reflection.strengths else '结构合理'}
💡 **改进方向**: {reflection.suggestions[0] if reflection.suggestions else '继续优化'}

🌳 **继续深度搜索更优解决方案...**"""

    def _prepare_timeout_response(self, state: LATSAgentState) -> LATSAgentState:
        """准备超时响应 - 静默处理"""
        return {
            **state,
            "current_phase": SearchPhase.SYNTHESIS
        }

    async def expand(self, state: LATSAgentState, config: RunnableConfig) -> LATSAgentState:
        """扩展搜索树"""
        logger.info("🌳 开始扩展搜索树")

        # 显示搜索开始信息
        search_depth = state["root"].height if state["root"] else 0
        search_start_msg = f"🔍 **第 {search_depth + 1} 轮优化搜索**"
        
        root = state["root"]
        if not root:
            logger.error("搜索树根节点未初始化")
            return state

        # 选择最佳候选节点
        best_candidate = self.select_node_for_expansion(root, state.get("search_config", LATSConfig()))
        messages = best_candidate.get_trajectory()

        # 初始化进度消息容器
        config['progress_messages'] = [AIMessage(content=search_start_msg)]

        # 生成新候选
        user_message = config["configurable"]["graph_request"].user_message
        new_candidates = await self._generate_candidates(user_message, messages, config)

        # 处理候选并评估
        output_messages, reflections = await self._process_candidates_with_evaluation(
            new_candidates, user_message, config, state.get("search_config", LATSConfig())
        )
        
        # 获取所有进度消息
        progress_messages = config.get('progress_messages', [])

        # 添加评估结果到状态
        state['evaluation_results'] = [
            {
                'index': i + 1,
                'score': r.overall_score,
                'found_solution': r.found_solution,
                'reflections': '; '.join(r.strengths + r.weaknesses),
                'message_content': output_messages[i][-1].content if output_messages[i] else ""
            }
            for i, r in enumerate(reflections)
        ]

        # 扩展搜索树
        child_nodes = [
            LATSTreeNode(messages=cand, reflection=reflection, parent=best_candidate)
            for cand, reflection in zip(output_messages, reflections)
        ]
        best_candidate.children.extend(child_nodes)

        # 添加评估完成总结
        best_score = max((r.overall_score for r in reflections), default=0)
        eval_summary_msg = f"🎯 **最佳评分: {best_score:.1f}/10** {'✨' if best_score >= 8.0 else '🔍 继续优化...'}"
        progress_messages.append(AIMessage(content=eval_summary_msg))
        
        # 检查解决方案
        solution_nodes = [node for node, r in zip(
            child_nodes, reflections) if r.found_solution]
        if solution_nodes:
            best_solution = max(
                solution_nodes, key=lambda node: node.reflection.overall_score)

            logger.info(f"🎉 找到解决方案! 评分: {best_solution.reflection.overall_score}/10")

            # 生成最终答案
            final_answer = await self._generate_final_answer(best_solution, config)
            
            # 添加进度信息和最终答案
            messages_to_add = progress_messages + [final_answer]
            root._is_solved = True
        else:
            # 添加最佳中间结果
            if child_nodes:
                best_node = max(
                    child_nodes, key=lambda node: node.reflection.overall_score)
                if best_node.reflection.overall_score >= 7:
                    best_message = best_node.get_trajectory(
                        include_reflections=False)[-1]
                    
                    # 返回进度信息和最佳中间结果
                    messages_to_add = progress_messages + [best_message]
                    logger.info(
                        f"⭐ 添加高质量中间结果 (评分: {best_node.reflection.overall_score}/10)")
                else:
                    # 只显示进度信息，继续搜索
                    messages_to_add = progress_messages
            else:
                # 只显示进度信息，继续搜索
                messages_to_add = progress_messages

        return {
            **state,
            "messages": state.get("messages", []) + messages_to_add
        }

    async def generate_final_answer(self, state: LATSAgentState, config: RunnableConfig) -> dict:
        """生成最终答案节点"""
        logger.info("📝 生成最终总结答案")

        root = state["root"]

        # 生成最终答案，不显示状态信息
        final_answer = await self._generate_final_answer(root, config)

        logger.info("✅ 最终答案生成完成")

        # 只返回最终答案
        return {
            **state,
            "messages": state.get("messages", []) + [final_answer]
        }

    async def _generate_final_answer(self, solution_node: LATSTreeNode, config: RunnableConfig) -> BaseMessage:
        """生成最终答案 - 使用统一的LLM实例"""
        
        system_message = TemplateLoader.render_template(
            "prompts/lats_agent/intelligent_assistant")
        prompt_template = ChatPromptTemplate.from_messages([
            ("system", system_message),
            ("user", "{input}"),
            MessagesPlaceholder(variable_name="messages", optional=True),
        ])

        final_solution = solution_node.get_trajectory(
            include_reflections=False)[-1]

        # 安全地提取用户核心问题，过滤敏感系统指令
        user_question = config['configurable']['graph_request'].user_message

        question = TemplateLoader.render_template(
            "prompts/lats_agent/final_answer_synthesis",
            {
                "user_question": user_question,
                "solution_content": final_solution.content
            }
        )

        chain = prompt_template | self.llm  # 使用继承的统一LLM实例
        return await chain.ainvoke({"input": question})

    def should_continue(self, state: LATSAgentState) -> str:
        """决定是否继续搜索或进入最终答案生成"""
        root = state.get("root")
        
        # 如果有根节点，检查是否找到解决方案
        if root and root.is_solved:
            logger.info("✅ 已找到解决方案，生成最终答案")
            return "generate_final_answer"
        
        # 检查搜索深度
        search_config = state.get('search_config', LATSConfig())
        if root and root.height >= search_config.max_tree_depth:
            logger.info(f"⏹️ 达到最大搜索深度 {search_config.max_tree_depth}，生成最终答案")
            return "generate_final_answer"
        
        # 检查搜索时间
        elapsed_time = time.time() - state.get("search_start_time", time.time())
        if elapsed_time >= search_config.max_search_time:
            logger.info(f"⏰ 达到最大搜索时间 {search_config.max_search_time}s，生成最终答案")
            return "generate_final_answer"
        
        # 否则继续扩展搜索树
        logger.info("🌳 继续扩展搜索树")
        return "expand"

    async def generate_initial_response(self, state: LATSAgentState, config: RunnableConfig) -> dict:
        """生成初始响应 - 使用 ReAct 模式生成第一个候选并评估"""
        logger.info("🌱 生成初始响应 (使用 ReAct 模式)")
        
        request = config['configurable']['graph_request']
        user_message = request.user_message
        
        # 初始化完整的搜索状态
        if 'search_config' not in state:
            state['search_config'] = LATSConfig()
        if 'search_start_time' not in state:
            state['search_start_time'] = time.time()
        if 'total_evaluations' not in state:
            state['total_evaluations'] = 0
        if 'best_score_so_far' not in state:
            state['best_score_so_far'] = 0.0
        if 'intermediate_results' not in state:
            state['intermediate_results'] = []
        if 'tool_execution_needed' not in state:
            state['tool_execution_needed'] = False
        
        state['current_phase'] = SearchPhase.INITIALIZATION

        # 显示初始分析进度
        progress_start_msg = AIMessage(content="🧠 **智能分析中...**")
        
        # 使用 ReAct 模式生成初始候选答案
        system_message = TemplateLoader.render_template(
            "prompts/lats_agent/initial_response"
        )
        
        logger.info("🔧 使用 ReAct 生成初始候选答案")
        initial_candidate = await self._invoke_react_for_candidate(
            user_message, 
            state.get("messages", []), 
            config, 
            system_message
        )
        
        # 显示评估进度
        eval_progress_msg = AIMessage(content="📊 **评估答案质量**")
        
        # 评估初始响应
        search_config = state.get('search_config', LATSConfig())
        output_messages = [initial_candidate]
        reflection = await self._evaluate_candidate(user_message, output_messages, config, search_config)
        
        # 创建根节点
        root = LATSTreeNode(messages=output_messages, reflection=reflection)
        state['root'] = root
        state['total_evaluations'] = 1
        state['best_score_so_far'] = reflection.overall_score
        
        logger.info(f"📊 初始响应评估完成 | 评分: {reflection.overall_score}/10 | 解决方案: {reflection.found_solution}")
        
        # 显示评估结果
        eval_result_msg = AIMessage(content=f"✅ **初始评分: {reflection.overall_score:.1f}/10** {('🎉' if reflection.found_solution else '🔍 寻找更优方案...')}")
        
        # 返回进度信息和初始候选答案
        messages_to_add = [progress_start_msg, eval_progress_msg, initial_candidate, eval_result_msg]
        
        return {
            **state,
            "messages": state.get("messages", []) + messages_to_add
        }




class LatsAgentGraph(BasicGraph):
    """LATS Agent 图执行器 - 优化版本"""

    async def compile_graph(self, request: LatsAgentRequest) -> StateGraph:
        """编译 LATS Agent 执行图"""
        logger.info("🔧 编译 LATS Agent 执行图")

        # 初始化优化版本的节点构建器
        node_builder = LatsAgentNode()
        await node_builder.setup(request)

        # 创建状态图
        graph_builder = StateGraph(LATSAgentState)

        # 添加基础图结构
        last_edge = self.prepare_graph(graph_builder, node_builder)
        logger.debug(f"基础图构建完成，连接点: {last_edge}")

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
