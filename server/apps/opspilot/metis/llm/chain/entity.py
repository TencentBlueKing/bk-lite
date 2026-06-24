from typing import Any, Callable, Dict, List, Optional

from pydantic import BaseModel, ConfigDict, Field


class NormalizedToolCall(BaseModel):
    """规范化后的 tool_call 访问器。

    LangChain 的 tool_calls 有时是 dict（{"name","id","args"}），有时是对象
    （带 .name/.id/.args 属性）。本模型把两种形态统一为稳定字段，避免在
    调用点反复写 `tc.get(...) if isinstance(tc, dict) else getattr(...)`。

    注意：仅作只读访问用途，不改变发往 LLM/前端的 tool_call 事件结构。
    """

    name: str = ""
    id: str = ""
    args: Dict[str, Any] = Field(default_factory=dict)
    # 保留原始对象/字典，供需要原样回写 state 的场景（如重试收窄 tool_calls）
    raw: Any = Field(default=None, exclude=True)

    model_config = ConfigDict(arbitrary_types_allowed=True)


def normalize_tool_call(tc: Any) -> NormalizedToolCall:
    """把单个 tool_call（dict 或对象）规范化为 NormalizedToolCall。"""
    if isinstance(tc, dict):
        return NormalizedToolCall(
            name=tc.get("name", "") or "",
            id=tc.get("id", "") or "",
            args=tc.get("args", {}) or {},
            raw=tc,
        )
    return NormalizedToolCall(
        name=getattr(tc, "name", "") or "",
        id=getattr(tc, "id", "") or "",
        args=getattr(tc, "args", {}) or {},
        raw=tc,
    )


def normalize_tool_calls(tool_calls: Optional[List[Any]]) -> List[NormalizedToolCall]:
    """把 tool_calls 列表整体规范化。"""
    return [normalize_tool_call(tc) for tc in (tool_calls or [])]


class ExtraConfig(BaseModel):
    """BasicLLMRequest.extra_config 的强类型视图（只读访问已知键）。

    extra_config 是一个自由格式 dict，由 chat_service 构建并通过 `**extra_config`
    展开进 LangGraph 的 configurable。前端发送的 execution_id/thread_id 等请求级
    字段必须原样保留，因此本模型用 extra="allow" 容忍任意额外键，并仅为已知键
    提供类型化访问。不要用本模型替换 dict 本身（会破坏 `**` 展开）。
    """

    model_config = ConfigDict(extra="allow")

    # 请求级字段（前端/调度注入）
    execution_id: Optional[str] = None
    thread_id: Optional[str] = None
    node_id: Optional[str] = None
    trigger_type: Optional[str] = None
    attachment_id: Optional[Any] = None
    show_think: Optional[bool] = None
    enable_rag_source: Optional[bool] = None
    enable_rag_strict_mode: Optional[bool] = None
    matched_skill_packages: List[Any] = Field(default_factory=list)
    skill_package_capabilities: List[str] = Field(default_factory=list)
    skill_package_reports: Dict[str, Any] = Field(default_factory=dict)
    skill_package_workflows: Dict[str, Any] = Field(default_factory=dict)

    # 多实例强制选择
    instance_name: Optional[str] = None
    instance_id: Optional[Any] = None
    require_choice_before_tools: bool = Field(default=False, alias="_require_choice_before_tools")
    multi_instance_options: List[Any] = Field(default_factory=list, alias="_multi_instance_options")

    @classmethod
    def from_raw(cls, raw: Optional[dict]) -> "ExtraConfig":
        """从原始 extra_config dict 构建（None/空容忍）。"""
        return cls.model_validate(raw or {})


class PrepareStepContext(BaseModel):
    """prepareStep 钩子接收的上下文"""

    step_number: int = 0
    messages: List[Any] = []
    tools: List[Any] = []
    model: str = ""
    metadata: Dict[str, Any] = {}

    class Config:
        arbitrary_types_allowed = True


class PrepareStepResult(BaseModel):
    """prepareStep 钩子返回的修改指令"""

    # None 表示不修改该字段
    messages: Optional[List[Any]] = None
    tools: Optional[List[Any]] = None
    additional_system_prompt: Optional[str] = None
    stop: bool = False  # 是否强制终止循环
    metadata: Dict[str, Any] = {}

    class Config:
        arbitrary_types_allowed = True


# prepareStep 钩子类型: 接收 PrepareStepContext，返回 PrepareStepResult
# 签名: async def hook(ctx: PrepareStepContext) -> PrepareStepResult
PrepareStepHook = Callable[[PrepareStepContext], Any]


class StopConditionContext(BaseModel):
    """stopWhen 条件判断时的上下文"""

    step_number: int = 0
    total_tokens: int = 0
    messages: List[Any] = []
    last_tool_calls: List[Any] = []
    metadata: Dict[str, Any] = {}

    class Config:
        arbitrary_types_allowed = True


class StopConditionResult(BaseModel):
    """stopWhen 条件的判断结果"""

    should_stop: bool = False
    reason: str = ""
    summary_message: str = ""  # 强制停止时附加给用户的说明


# stopWhen 条件类型: 接收 StopConditionContext，返回 StopConditionResult
# 签名: def condition(ctx: StopConditionContext) -> StopConditionResult
StopWhenCondition = Callable[[StopConditionContext], Any]


class RetryConfig(BaseModel):
    """自适应重试配置"""

    enabled: bool = True
    max_retries_per_tool: int = 2  # 单个工具调用最大重试次数
    retry_on_error_keywords: List[str] = Field(
        default_factory=lambda: [
            "timeout",
            "connection refused",
            "rate_limit",
            "status 500",
            "status 502",
            "status 503",
            "status 504",
            "http 500",
            "http 502",
            "http 503",
            "http 504",
        ],
        description="触发重试的错误关键词（不区分大小写）",
    )
    backoff_seconds: float = 1.0  # 重试间隔基数（指数退避: base * 2^attempt）


class ReflectionConfig(BaseModel):
    """循环内反思配置"""

    enabled: bool = True
    consecutive_failures_threshold: int = 3  # 连续失败 N 次触发反思
    repetition_window: int = 6  # 检测重复的窗口大小（最近 N 条工具调用）
    repetition_threshold: int = 3  # 窗口内同一工具被调用 N 次以上视为循环


class ToolPoolConfig(BaseModel):
    """动态工具选择（工具池按需激活）配置"""

    enabled: bool = True
    auto_activate_threshold: int = 6  # 工具函数总数 ≤ 此值时全部激活，不启用动态选择


class ToolChoiceConfig(BaseModel):
    """工具选择控制配置

    控制 LLM 是否必须/禁止/优先使用某个工具。
    - mode: "auto"(默认) | "none"(禁止工具) | "any"(强制使用某个工具) | "specific"(强制指定工具)
    - tool_name: mode="specific" 时指定的工具名称
    - apply_on_steps: 仅在指定步骤范围内生效（None=全部步骤）
    """

    mode: str = Field(default="auto", description="工具选择模式: auto/none/any/specific")
    tool_name: Optional[str] = Field(default=None, description="mode=specific 时强制使用的工具名称")
    apply_on_steps: Optional[List[int]] = Field(default=None, description="仅在指定步数列表生效（None=全部步骤）")


class TimeoutConfig(BaseModel):
    """超时熔断配置"""

    enabled: bool = True
    total_timeout_seconds: float = Field(default=300.0, description="总超时（秒），从首步开始计时，0=不限制")
    step_timeout_seconds: float = Field(default=60.0, description="单步工具执行超时（秒），0=不限制")
    llm_timeout_seconds: float = Field(default=300.0, description="单次 LLM 调用超时（秒），0=不限制")


class MessageTrimConfig(BaseModel):
    """消息裁剪配置（在 compaction 之前执行的轻量级裁剪）"""

    enabled: bool = True
    max_single_message_tokens: int = Field(default=4000, description="单条消息最大 token 数，超出则截断尾部")
    image_retain_recent: int = Field(default=3, description="保留最近 N 条含图片的消息，更早的图片移除仅保留文字")
    trim_tool_message_prefix: str = Field(default="...(内容过长已截断，保留前 {kept} tokens)", description="截断提示模板")


class DoneToolConfig(BaseModel):
    """done tool 显式终止配置"""

    enabled: bool = False
    tool_name: str = Field(default="__done__", description="done tool 的名称")
    description: str = Field(
        default="当你完成任务并准备好最终结果时，调用此工具来结束任务。将结构化结果填入 result 参数。",
        description="done tool 的描述（告诉 LLM 何时调用）",
    )
    result_schema: Optional[Dict[str, Any]] = Field(
        default=None,
        description="期望的结构化输出 JSON Schema（None=接受任意 JSON）",
    )


class ToolVerificationSpec(BaseModel):
    """单个工具的验证规格 — 附加在工具元数据中"""

    verify_tool: str = Field(description="用于验证的工具名")
    args_mapping: Dict[str, str] = Field(
        default_factory=dict,
        description="参数映射: {verify_tool_arg: action_tool_arg}，从操作工具的参数中提取验证工具的参数",
    )
    delay_seconds: float = Field(default=0.0, description="验证前等待时间（秒），某些操作需要时间生效")
    description: str = Field(default="", description="验证说明（注入 LLM 上下文）")


class VerificationConfig(BaseModel):
    """全局验证配置 — 附加在 BasicLLMRequest 上"""

    enabled: bool = Field(default=False, description="是否启用执行后验证")
    # 工具级验证规格覆盖（优先级高于工具自带元数据）
    overrides: Dict[str, ToolVerificationSpec] = Field(
        default_factory=dict,
        description="工具名 -> 验证规格覆盖",
    )
    # 验证失败后是否注入上下文让 LLM 处理
    inject_failure_context: bool = Field(default=True, description="验证失败时注入上下文让 LLM 决策")
    # 最大验证重试次数（同一工具调用）
    max_verify_retries: int = Field(default=1, description="验证失败后最多重新验证次数")
    # 重试间隔
    retry_delay_seconds: float = Field(default=5.0, description="重新验证间隔（秒）")


class ToolRollbackSpec(BaseModel):
    """单个工具的回滚规格 — 描述如何在操作失败后恢复到操作前状态

    回滚流程：操作前拍快照 → 执行操作 → 验证结果 → 验证失败时执行回滚
    """

    snapshot_tool: Optional[str] = Field(
        default=None,
        description="操作前拍快照的工具名（None=不拍快照，回滚时由 LLM 自行决定）",
    )
    snapshot_args_mapping: Dict[str, str] = Field(
        default_factory=dict,
        description="快照工具参数映射: {snapshot_tool_arg: action_tool_arg}",
    )
    rollback_tool: Optional[str] = Field(
        default=None,
        description="回滚工具名（None=不可自动回滚，仅提示 LLM）",
    )
    rollback_args_mapping: Dict[str, str] = Field(
        default_factory=dict,
        description="回滚工具静态参数映射: {rollback_tool_arg: action_tool_arg}",
    )
    rollback_snapshot_args: Dict[str, str] = Field(
        default_factory=dict,
        description="从快照结果中提取的回滚参数: {rollback_tool_arg: json_path}，如 {'replicas': 'spec.replicas'}",
    )
    strategy: str = Field(
        default="prompt",
        description="回滚策略: auto(自动回滚) | prompt(注入上下文让LLM决定) | none(不可回滚)",
    )
    description: str = Field(default="", description="回滚说明")


class RollbackConfig(BaseModel):
    """全局回滚配置 — 附加在 BasicLLMRequest 上

    与 VerificationConfig 协作：验证失败 → 触发回滚
    """

    enabled: bool = Field(default=False, description="是否启用回滚能力")
    # 工具级回滚规格覆盖（优先级高于工具自带元数据和注册表）
    overrides: Dict[str, ToolRollbackSpec] = Field(
        default_factory=dict,
        description="工具名 -> 回滚规格覆盖",
    )
    # 验证失败时是否自动触发回滚（仅对 strategy=auto 的工具）
    auto_rollback_on_verify_fail: bool = Field(
        default=True,
        description="验证失败时自动触发回滚（strategy=auto 的工具）",
    )
    # 回滚失败后是否注入上下文让 LLM 处理
    inject_rollback_context: bool = Field(
        default=True,
        description="回滚结果（成功或失败）注入上下文让 LLM 知晓",
    )


class ApprovalConfig(BaseModel):
    """人工审批配置 — 控制危险工具调用前的人类确认"""

    enabled: bool = Field(default=False, description="是否启用审批")
    # 需要审批的工具名列表（空列表=该节点所有工具都需审批）
    tools: List[str] = Field(default_factory=list, description="需要审批的工具名列表，空=全部工具")
    # 审批等待超时
    timeout_seconds: int = Field(default=300, description="审批等待超时（秒）")
    # 超时降级策略
    timeout_fallback: str = Field(default="skip", description="超时降级策略: skip|deny|allow")
    # 无人值守（定时任务）场景策略
    unattended_strategy: str = Field(default="skip", description="无人值守策略: skip|deny|allow")
    # 是否发通知
    notify: bool = Field(default=True, description="是否发送通知（无论审批结果）")
    # 轮询间隔
    poll_interval_seconds: float = Field(default=1.0, description="轮询 Redis 间隔（秒）")


class ApprovalRequest(BaseModel):
    """一次审批请求的完整标识"""

    execution_id: str = Field(description="执行 ID")
    node_id: str = Field(description="发起审批的节点 ID（workflow 节点 ID 或 skill_test）")
    tool_call_id: str = Field(description="tool_call ID")
    tool_name: str = Field(description="工具名")
    tool_args: Dict[str, Any] = Field(default_factory=dict, description="工具参数")
    context_summary: str = Field(default="", description="操作上下文摘要")
    timeout_seconds: int = Field(default=300, description="审批超时")


class ApprovalDecision(BaseModel):
    """审批决策"""

    decision: str = Field(description="approve|reject")
    reason: str = Field(default="", description="决策原因")
    decided_by: str = Field(default="", description="决策人")


class StepProgressEvent(BaseModel):
    """Agent 步骤级进度事件（通过 CUSTOM 事件发射，name='agent_step_progress'）"""

    step: int = Field(description="当前步数")
    max_steps: int = Field(description="最大步数上限")
    status: str = Field(description="running | tool_executing | completed | interrupted | timeout")
    description: str = Field(default="", description="当前步骤描述")
    tool_name: Optional[str] = Field(default=None, description="本步调用的工具名")
    elapsed_seconds: float = Field(default=0.0, description="本步耗时（秒）")
    total_elapsed_seconds: float = Field(default=0.0, description="总耗时（秒）")


class BasicLLMResponse(BaseModel):
    message: str
    total_tokens: int = 0
    prompt_tokens: int = 0
    completion_tokens: int = 0
    browser_steps: List[str] = []  # browser_use 步骤信息，格式: ["step1 xxx", "step2 xxx", ..., "最终结果: xxx"]


class ChatHistory(BaseModel):
    event: str
    message: str
    image_data: List[str] = []


class ToolsServer(BaseModel):
    name: str
    url: str = ""
    transport: str = ""
    command: str = ""
    args: list = []
    extra_param_prompt: dict = {}
    extra_tools_prompt: str = ""
    enable_auth: bool = False
    auth_token: str = ""


class BasicLLMRequest(BaseModel):
    openai_api_base: str = "https://api.openai.com"
    openai_api_key: str = ""
    model: str = "gpt-4o"
    protocol_type: str = "openai"  # "openai" 或 "anthropic"
    vendor_type: str = ""

    system_message_prompt: str = ""
    enable_suggest: bool = False
    enable_query_rewrite: bool = False
    temperature: float = 0.7

    user_message: str = ""

    chat_history: List[ChatHistory] = []

    user_id: Optional[str] = ""
    thread_id: Optional[str] = ""

    naive_rag_request: List[Any] = []

    extra_config: Optional[dict] = {}

    def typed_extra_config(self) -> "ExtraConfig":
        """返回 extra_config 的强类型只读视图（已知键带类型，未知键容忍保留）。"""
        return ExtraConfig.from_raw(self.extra_config)

    graph_user_message: Optional[str] = ""

    tools_servers: List[ToolsServer] = []

    locale: str = "en"  # 用户语言设置，用于 browser-use 输出国际化

    # prepareStep 钩子列表（运行时注入，不序列化）
    prepare_step_hooks: List[Any] = Field(default_factory=list, description="每步执行前的回调钩子列表", exclude=True)

    # stopWhen 灵活停止配置
    max_steps: int = Field(default=50, description="最大步数限制（0=不限制，由 recursion_limit 兜底）")
    max_tokens_budget: int = Field(default=0, description="累计 token 预算上限（0=不限制）")
    soft_budget_ratio: float = Field(default=0.8, description="软预算比例（0-1），达到时注入 wrap-up 提示；1.0=禁用软预算")
    stop_when_conditions: List[Any] = Field(default_factory=list, description="自定义停止条件列表", exclude=True)

    # 自适应重试配置
    retry_config: RetryConfig = Field(default_factory=RetryConfig, description="工具调用自适应重试配置")

    # 循环内反思配置
    reflection_config: ReflectionConfig = Field(default_factory=ReflectionConfig, description="循环内反思配置")

    # 动态工具选择配置
    tool_pool_config: ToolPoolConfig = Field(default_factory=ToolPoolConfig, description="工具池按需激活配置")

    # toolChoice 控制配置
    tool_choice_config: ToolChoiceConfig = Field(default_factory=ToolChoiceConfig, description="工具选择控制配置")

    # 超时熔断配置
    timeout_config: TimeoutConfig = Field(default_factory=TimeoutConfig, description="超时熔断配置")

    # 消息裁剪配置
    message_trim_config: MessageTrimConfig = Field(default_factory=MessageTrimConfig, description="消息裁剪配置")

    # done tool 显式终止配置
    done_tool_config: DoneToolConfig = Field(default_factory=DoneToolConfig, description="done tool 显式终止配置")

    # 人工审批配置
    approval_config: ApprovalConfig = Field(default_factory=ApprovalConfig, description="人工审批配置")

    # 执行后验证配置
    verification_config: VerificationConfig = Field(default_factory=VerificationConfig, description="执行后验证配置")

    # 回滚配置
    rollback_config: RollbackConfig = Field(default_factory=RollbackConfig, description="操作回滚配置")

    # 上下文 Compaction 配置
    compaction_enabled: bool = Field(default=True, description="是否启用上下文压缩")
    compaction_max_token_threshold: int = Field(default=80000, description="触发压缩的 token 阈值")
    compaction_keep_recent_messages: int = Field(default=12, description="压缩时保留最近的消息数量")
    compaction_summary_max_tokens: int = Field(default=2000, description="摘要的最大 token 数")
