"""
Supervisor Multi-Agent 测试

测试 Supervisor 协调多个专业 Agent 完成任务的能力。

运行方式：
    # 运行测试
    uv run pytest tests/llm/agent/supervisor_multi_agent_test.py -v
    
    # 带日志输出
    uv run pytest tests/llm/agent/supervisor_multi_agent_test.py -v -s

环境变量要求：
    - TEST_LLM_API_KEY: LLM API 密钥
    - TEST_LLM_API_URL: LLM API 地址
    - TEST_LLM_MODEL: 使用的模型名称

测试场景：
    test_supervisor_multi_agent_time_zone: 
        Supervisor 协调 Shell Agent 和 Python Agent 查询时区和时间
"""
import os
import pytest
from loguru import logger

from neco.llm.agent.supervisor_multi_agent import (
    SupervisorMultiAgentGraph,
    SupervisorMultiAgentRequest,
    AgentConfig
)
from neco.llm.chain.entity import ToolsServer

NEW_API_KEY = os.getenv('TEST_LLM_API_KEY')
NEW_API_URL = os.getenv('TEST_LLM_API_URL')
TEST_LLM_MODEL = os.getenv('TEST_LLM_MODEL')

TEST_PROMPTS = [
    '用 Shell 工具看看现在几点，然后用 Python 工具把 时+分 乘以 2 告诉我结果',
]


@pytest.mark.asyncio
@pytest.mark.parametrize('prompt', TEST_PROMPTS)
async def test_supervisor_multi_agent_time_zone(prompt):
    """测试 Supervisor 协调多个 Agent 完成时区和时间查询任务"""
    logger.info(f"测试任务: {prompt}")

    # 配置 Shell Agent - 负责执行 shell 命令获取系统时区
    shell_agent_config = AgentConfig(
        name="shell_agent",
        description="专门执行 shell 命令的专家，擅长使用系统命令查询时区、日期等系统信息",
        tools_servers=[
            ToolsServer(
                name='shell',
                url='langchain:shell'
            )
        ],
        system_message_prompt="你是一个 shell 命令专家。使用 shell 命令获取系统信息。",
        temperature=0.7
    )

    # 配置 Python Agent - 负责执行 Python 代码获取时间
    python_agent_config = AgentConfig(
        name="python_agent",
        description="专门执行 Python 代码的专家，擅长使用 Python 获取当前时间、日期等信息",
        tools_servers=[
            ToolsServer(
                name='python',
                url='langchain:python'
            ),
            ToolsServer(
                name='current_time',
                url='langchain:current_time'
            )
        ],
        system_message_prompt="你是一个 Python 编程专家。使用 Python 代码或时间工具获取时间信息。",
        temperature=0.7
    )

    # 创建 Supervisor 请求
    request = SupervisorMultiAgentRequest(
        openai_api_base=NEW_API_URL,
        openai_api_key=NEW_API_KEY,
        model=TEST_LLM_MODEL,
        user_message=prompt,
        chat_history=[],
        agents=[shell_agent_config, python_agent_config],
        supervisor_system_prompt=(
            "你是一个任务协调主管，负责将用户任务委派给最合适的专家 Agent。\n"
            "- shell_agent: 擅长执行 shell 命令，查询系统级信息（如时区）\n"
            "- python_agent: 擅长执行 Python 代码，获取时间日期信息\n\n"
            "请根据任务需求选择合适的 Agent，可以按顺序调用多个 Agent 完成任务。\n"
            "最后汇总所有 Agent 的结果，给出完整的答案。"
        ),
        max_iterations=5
    )

    # 创建并运行图
    graph = SupervisorMultiAgentGraph()
    result = graph.agui_stream(request)

    # 打印所有 SSE 事件
    async for sse_event in result:
        print(sse_event, end='')
