"""Browser-Use 公开工具的端到端参数与结果契约。

Browser、Agent 与 LLM 属于外部运行时边界；任务构建、凭据占位、回调、
异常映射和临时会话目录均执行真实生产代码。
"""

from types import SimpleNamespace
from unittest.mock import patch

import pydantic.root_model  # noqa: F401
import pytest

from apps.opspilot.metis.llm.tools.browser_use import browser_tool


class BrowserResult:
    def __init__(self, content="dashboard healthy", success=True):
        self.content = content
        self.success = success

    def final_result(self):
        return self.content

    def is_successful(self):
        return self.success

    def has_errors(self):
        return not self.success

    def errors(self):
        return [] if self.success else ["browser failed"]

    def number_of_steps(self):
        return 3


class ExternalBrowser:
    instances = []

    def __init__(self, **kwargs):
        self.kwargs = kwargs
        self.killed = False
        self.__class__.instances.append(self)

    async def kill(self):
        self.killed = True


class ExternalBrowserAgent:
    instances = []
    result = BrowserResult()
    raised = None

    def __init__(self, **kwargs):
        self.kwargs = kwargs
        self.__class__.instances.append(self)

    async def run(self, **kwargs):
        if self.__class__.raised is not None:
            raise self.__class__.raised
        return self.__class__.result


class ExternalChatOpenAI:
    def __init__(self, **kwargs):
        self.kwargs = kwargs


def graph_config(**extra):
    configurable = {
        "graph_request": SimpleNamespace(
            model="gpt-test",
            openai_api_key="test-key",
            openai_api_base="https://llm.example.com/v1",
            locale="zh-Hans",
            thread_id="thread-1",
        )
    }
    configurable.update(extra)
    return {"configurable": configurable}


@pytest.fixture(autouse=True)
def reset_external_browser_state():
    ExternalBrowser.instances = []
    ExternalBrowserAgent.instances = []
    ExternalBrowserAgent.result = BrowserResult()
    ExternalBrowserAgent.raised = None


@pytest.fixture
def browser_runtime():
    with (
        patch.object(browser_tool, "Browser", ExternalBrowser),
        patch.object(browser_tool, "BrowserAgent", ExternalBrowserAgent),
        patch.object(browser_tool, "ChatOpenAI", ExternalChatOpenAI),
    ):
        yield


pytestmark = pytest.mark.unit


def test_browse_website_keeps_credentials_out_of_task_and_emits_task_event(
    browser_runtime,
):
    events = []

    result = browser_tool.browse_website.invoke(
        {
            "url": "https://93.184.216.34/login",
            "task": "登录后执行健康检查",
            "username": "admin",
            "password": "super-secret",
        },
        config=graph_config(
            browser_custom_event_callback=events.append,
            execution_id="exec-1",
        ),
    )

    assert result["success"] is True
    assert result["content"] == "dashboard healthy"
    agent_kwargs = ExternalBrowserAgent.instances[0].kwargs
    assert "<secret>x_username</secret>" in agent_kwargs["task"]
    assert "<secret>x_password</secret>" in agent_kwargs["task"]
    assert "super-secret" not in agent_kwargs["task"]
    assert agent_kwargs["sensitive_data"]["x_password"] == "super-secret"
    assert events[0]["tool"] == "browse_website"
    assert "super-secret" not in events[0]["task_final"]
    assert ExternalBrowser.instances[0].killed is True


def test_browse_website_maps_login_failure_to_non_retryable_result(
    browser_runtime,
):
    ExternalBrowserAgent.raised = browser_tool.LoginFailureError(
        "用户名或密码错误",
        failure_count=2,
    )

    result = browser_tool.browse_website.invoke(
        {
            "url": "https://93.184.216.34/login",
            "task": "登录",
            "username": "admin",
            "password": "wrong",
        },
        config=graph_config(),
    )

    assert result == {
        "success": False,
        "content": None,
        "url": "https://93.184.216.34/login",
        "task": (
            "【凭据已提供】用户名: <secret>x_username</secret>, "
            "密码: <secret>x_password</secret>。登录"
        ),
        "has_errors": True,
        "errors": ["用户名或密码错误"],
        "steps_taken": 0,
        "login_failure": True,
        "login_failure_count": 2,
    }
    assert ExternalBrowser.instances[0].killed is True


def test_browse_website_maps_execution_interrupt_to_explicit_result(
    browser_runtime,
):
    ExternalBrowserAgent.raised = browser_tool.BrowserExecutionInterruptedError(
        "execution interrupted"
    )

    result = browser_tool.browse_website.invoke(
        {
            "url": "https://93.184.216.34",
            "task": "检查首页",
        },
        config=graph_config(),
    )

    assert result["success"] is False
    assert result["interrupted"] is True
    assert result["errors"] == ["execution interrupted"]
    assert result["steps_taken"] == 0


def test_extract_webpage_info_builds_selector_task_and_returns_data(
    browser_runtime,
):
    result = browser_tool.extract_webpage_info.invoke(
        {
            "url": "https://93.184.216.34/product",
            "selectors": {
                "name": "商品名称",
                "price": "商品价格",
            },
        },
        config=graph_config(),
    )

    assert result == {
        "success": True,
        "data": "dashboard healthy",
        "url": "https://93.184.216.34/product",
        "selectors": {
            "name": "商品名称",
            "price": "商品价格",
        },
    }
    task = ExternalBrowserAgent.instances[0].kwargs["task"]
    assert "- name: 商品名称" in task
    assert "- price: 商品价格" in task


def test_browser_tools_reject_private_url_before_starting_runtime(
    browser_runtime,
):
    browse_result = browser_tool.browse_website.invoke(
        {
            "url": "http://127.0.0.1/admin",
            "task": "打开管理页",
        },
        config=graph_config(),
    )
    extract_result = browser_tool.extract_webpage_info.invoke(
        {
            "url": "http://169.254.169.254/latest/meta-data",
        },
        config=graph_config(),
    )

    assert browse_result["success"] is False
    assert extract_result["success"] is False
    assert ExternalBrowser.instances == []
