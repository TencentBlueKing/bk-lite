from typing import Any, Callable, Dict, List, Optional

from pydantic import BaseModel, Field

from apps.opspilot.metis.llm.rag.naive_rag_entity import DocumentRetrieverRequest


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
        default_factory=lambda: ["timeout", "connection", "rate_limit", "500", "502", "503", "504"],
        description="触发重试的错误关键词（不区分大小写）",
    )
    backoff_seconds: float = 1.0  # 重试间隔基数（指数退避: base * 2^attempt）


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

    system_message_prompt: str = ""
    enable_suggest: bool = False
    enable_query_rewrite: bool = False
    temperature: float = 0.7

    user_message: str = ""

    chat_history: List[ChatHistory] = []

    user_id: Optional[str] = ""
    thread_id: Optional[str] = ""

    naive_rag_request: List[DocumentRetrieverRequest] = []

    extra_config: Optional[dict] = {}

    graph_user_message: Optional[str] = ""

    tools_servers: List[ToolsServer] = []

    locale: str = "en"  # 用户语言设置，用于 browser-use 输出国际化

    # prepareStep 钩子列表（运行时注入，不序列化）
    prepare_step_hooks: List[Any] = Field(default_factory=list, description="每步执行前的回调钩子列表", exclude=True)

    # stopWhen 灵活停止配置
    max_steps: int = Field(default=50, description="最大步数限制（0=不限制，由 recursion_limit 兜底）")
    max_tokens_budget: int = Field(default=0, description="累计 token 预算上限（0=不限制）")
    stop_when_conditions: List[Any] = Field(default_factory=list, description="自定义停止条件列表", exclude=True)

    # 自适应重试配置
    retry_config: RetryConfig = Field(default_factory=RetryConfig, description="工具调用自适应重试配置")

    # 上下文 Compaction 配置
    compaction_enabled: bool = Field(default=True, description="是否启用上下文压缩")
    compaction_max_token_threshold: int = Field(default=80000, description="触发压缩的 token 阈值")
    compaction_keep_recent_messages: int = Field(default=12, description="压缩时保留最近的消息数量")
    compaction_summary_max_tokens: int = Field(default=2000, description="摘要的最大 token 数")
