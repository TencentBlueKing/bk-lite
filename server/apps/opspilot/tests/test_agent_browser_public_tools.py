"""agent-browser 公开工具契约。

测试穿过 LangChain ``@tool`` 公共入口，只在外部 CLI 进程边界替换
``subprocess.Popen``，保留参数校验、SSRF、命令组装和结果解析生产逻辑。
"""

from unittest.mock import patch

import pydantic.root_model  # noqa: F401
import pytest

from apps.opspilot.metis.llm.tools.agent_browser import browser_tool


class CompletedAgentBrowserProcess:
    def __init__(self, stdout='{"ok": true}', stderr="", returncode=0):
        self.stdout = stdout
        self.stderr = stderr
        self.returncode = returncode

    def poll(self):
        return self.returncode

    def communicate(self, timeout=None):
        return self.stdout, self.stderr

    def terminate(self):
        return None

    def kill(self):
        return None


pytestmark = pytest.mark.unit


def test_screenshot_normalizes_unsupported_format_for_path_and_cli(tmp_path):
    process = CompletedAgentBrowserProcess()

    with (
        patch.object(
            browser_tool,
            "_DEFAULT_SCREENSHOT_DIR",
            tmp_path,
        ),
        patch.object(
            browser_tool.shutil,
            "which",
            return_value="/usr/local/bin/agent-browser",
        ),
        patch.object(
            browser_tool.subprocess,
            "Popen",
            return_value=process,
        ) as popen,
    ):
        result = browser_tool.agent_browser_screenshot.invoke(
            {
                "filename": "overview",
                "image_format": "gif",
                "timeout": 5,
            }
        )

    command = popen.call_args.args[0]
    assert result["success"] is True
    assert result["screenshot_path"].endswith("overview.png")
    assert command[command.index("--screenshot-format") + 1] == "png"


def test_run_executes_cli_and_returns_structured_output():
    process = CompletedAgentBrowserProcess(
        stdout='{"data": {"snapshot": "button ref=e1"}}'
    )

    with (
        patch.object(
            browser_tool.shutil,
            "which",
            return_value="/usr/local/bin/agent-browser",
        ),
        patch.object(
            browser_tool.subprocess,
            "Popen",
            return_value=process,
        ) as popen,
    ):
        result = browser_tool.agent_browser_run.invoke(
            {
                "command_args": ["snapshot", "-i"],
                "timeout": 5,
                "config": {"configurable": {"execution_id": "exec-1"}},
            }
        )

    assert result["success"] is True
    assert result["exit_code"] == 0
    assert result["stdout"].startswith('{"data"')
    assert popen.call_args.args[0] == [
        "/usr/local/bin/agent-browser",
        "--json",
        "snapshot",
        "-i",
    ]


def test_run_rejects_private_navigation_before_starting_cli():
    with patch.object(browser_tool.subprocess, "Popen") as popen:
        result = browser_tool.agent_browser_run.invoke(
            {
                "command_args": [
                    "open",
                    "http://127.0.0.1/admin",
                ],
                "timeout": 5,
            }
        )

    assert result["success"] is False
    assert "安全校验" in result["error"]
    popen.assert_not_called()


def test_open_and_screenshot_runs_both_commands(tmp_path):
    processes = [
        CompletedAgentBrowserProcess(stdout='{"url": "https://93.184.216.34"}'),
        CompletedAgentBrowserProcess(stdout='{"path": "page.png"}'),
    ]

    with (
        patch.object(browser_tool, "_DEFAULT_SCREENSHOT_DIR", tmp_path),
        patch.object(
            browser_tool.shutil,
            "which",
            return_value="/usr/local/bin/agent-browser",
        ),
        patch.object(
            browser_tool.subprocess,
            "Popen",
            side_effect=processes,
        ) as popen,
    ):
        result = browser_tool.agent_browser_open_and_screenshot.invoke(
            {
                "url": "https://93.184.216.34",
                "filename": "public-page.png",
                "session_name": "inspection",
                "timeout": 5,
            }
        )

    assert result["success"] is True
    assert result["screenshot_path"].endswith("public-page.png")
    assert popen.call_count == 2
    assert popen.call_args_list[0].args[0][-4:] == [
        "--session",
        "inspection",
        "open",
        "https://93.184.216.34",
    ]
    assert "screenshot" in popen.call_args_list[1].args[0]


def test_snapshot_builds_public_cli_flags():
    process = CompletedAgentBrowserProcess(
        stdout='{"data": {"snapshot": "input ref=e2"}}'
    )

    with (
        patch.object(
            browser_tool.shutil,
            "which",
            return_value="/usr/local/bin/agent-browser",
        ),
        patch.object(
            browser_tool.subprocess,
            "Popen",
            return_value=process,
        ) as popen,
    ):
        result = browser_tool.agent_browser_snapshot.invoke(
            {
                "interactive_only": True,
                "compact": True,
                "max_depth": 3,
                "selector": "#main",
                "session_name": "inspection",
                "timeout": 5,
            }
        )

    assert result["success"] is True
    command = popen.call_args.args[0]
    assert command[2:] == [
        "--session",
        "inspection",
        "snapshot",
        "-i",
        "-c",
        "-d",
        "3",
        "-s",
        "#main",
    ]


def test_wait_builds_all_supported_wait_conditions():
    process = CompletedAgentBrowserProcess(stdout='{"waited": true}')

    with (
        patch.object(
            browser_tool.shutil,
            "which",
            return_value="/usr/local/bin/agent-browser",
        ),
        patch.object(
            browser_tool.subprocess,
            "Popen",
            return_value=process,
        ) as popen,
    ):
        result = browser_tool.agent_browser_wait.invoke(
            {
                "selector_or_ms": "#ready",
                "text": "Ready",
                "url_pattern": "**/dashboard",
                "load_state": "networkidle",
                "state": "visible",
                "js_condition": "window.ready === true",
                "timeout": 5,
            }
        )

    assert result["success"] is True
    command = popen.call_args.args[0]
    assert command[2:] == [
        "wait",
        "#ready",
        "--text",
        "Ready",
        "--url",
        "**/dashboard",
        "--load",
        "networkidle",
        "--state",
        "visible",
        "--fn",
        "window.ready === true",
    ]


def test_open_wait_and_snapshot_returns_each_stage():
    processes = [
        CompletedAgentBrowserProcess(stdout='{"opened": true}'),
        CompletedAgentBrowserProcess(stdout='{"loaded": true}'),
        CompletedAgentBrowserProcess(stdout='{"waited": true}'),
        CompletedAgentBrowserProcess(stdout='{"snapshot": "button ref=e1"}'),
    ]

    with (
        patch.object(
            browser_tool.shutil,
            "which",
            return_value="/usr/local/bin/agent-browser",
        ),
        patch.object(
            browser_tool.subprocess,
            "Popen",
            side_effect=processes,
        ) as popen,
    ):
        result = browser_tool.agent_browser_open_wait_and_snapshot.invoke(
            {
                "url": "https://93.184.216.34",
                "load_state": "networkidle",
                "wait_ms": 250,
                "timeout": 5,
            }
        )

    assert result["success"] is True
    assert result["open_result"]["success"] is True
    assert result["wait_result"]["success"] is True
    assert result["snapshot_result"]["success"] is True
    assert result["interstitial_result"] is None
    assert popen.call_count == 4


def test_inspect_can_return_snapshot_without_creating_screenshot():
    processes = [
        CompletedAgentBrowserProcess(stdout='{"opened": true}'),
        CompletedAgentBrowserProcess(stdout='{"loaded": true}'),
        CompletedAgentBrowserProcess(stdout='{"snapshot": "heading"}'),
    ]

    with (
        patch.object(
            browser_tool.shutil,
            "which",
            return_value="/usr/local/bin/agent-browser",
        ),
        patch.object(
            browser_tool.subprocess,
            "Popen",
            side_effect=processes,
        ) as popen,
    ):
        result = browser_tool.agent_browser_inspect.invoke(
            {
                "url": "https://93.184.216.34",
                "screenshot": False,
                "timeout": 5,
            }
        )

    assert result["success"] is True
    assert result["snapshot_result"]["success"] is True
    assert result["screenshot_result"] is None
    assert result["screenshot_path"] is None
    assert popen.call_count == 3
