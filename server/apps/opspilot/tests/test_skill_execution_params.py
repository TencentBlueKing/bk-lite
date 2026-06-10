"""opspilot.utils.skill_execution_params 纯单元测试。

规格（BL-NEW-001）：resolve_request_tools 以服务端 Skill 配置为唯一授权来源，
请求工具按 id / name 白名单过滤，未授权工具一律丢弃；请求未带 tools 时回退到
Skill 自身配置。
"""

import pytest

from apps.opspilot.utils.skill_execution_params import resolve_request_tools

pytestmark = pytest.mark.unit


def test_无请求工具时用技能工具():
    assert resolve_request_tools([], [{"id": 1, "name": "b"}]) == [{"id": 1, "name": "b"}]
    assert resolve_request_tools(None, [{"id": 1, "name": "b"}]) == [{"id": 1, "name": "b"}]


def test_都为空返回空列表():
    assert resolve_request_tools(None, None) == []
    assert resolve_request_tools([], []) == []


def test_请求携带已授权id的工具予以保留():
    """请求可为 Skill 已授权的工具携带运行时参数（如凭据）。"""
    skill_tools = [{"id": 5, "name": "mysql", "kwargs": []}]
    request_tools = [{"id": 5, "name": "mysql", "kwargs": [{"key": "password", "value": "x"}]}]
    assert resolve_request_tools(request_tools, skill_tools) == request_tools


def test_请求注入未授权id的工具被丢弃():
    """BL-NEW-001 核心：低权限用户注入 Skill 未授权的工具 ID（如通用 Python 执行）被拒绝。"""
    skill_tools = [{"id": 5, "name": "mysql", "kwargs": []}]
    request_tools = [{"id": 99, "name": "python_execute", "kwargs": []}]
    assert resolve_request_tools(request_tools, skill_tools) == []


def test_合法name配伪造id无法绕过():
    """用已授权工具的 name + 指向高危工具的 evil id 也无法绕过（只认 id）。"""
    skill_tools = [{"id": 5, "name": "python_execute", "kwargs": []}]
    request_tools = [{"id": 99, "name": "python_execute", "kwargs": []}]
    assert resolve_request_tools(request_tools, skill_tools) == []


def test_按name授权的内置工具予以保留():
    """无有效 id 的内置工具按 name 白名单放行。"""
    skill_tools = [{"name": "fileupload", "kwargs": []}]
    request_tools = [{"name": "fileupload", "kwargs": [{"key": "k", "value": "v"}]}]
    assert resolve_request_tools(request_tools, skill_tools) == request_tools


def test_未授权name的内置工具被丢弃():
    skill_tools = [{"name": "fileupload", "kwargs": []}]
    request_tools = [{"name": "shell_execute", "kwargs": []}]
    assert resolve_request_tools(request_tools, skill_tools) == []


def test_混合请求仅保留授权部分():
    skill_tools = [{"id": 5, "name": "mysql", "kwargs": []}, {"name": "fileupload", "kwargs": []}]
    request_tools = [
        {"id": 5, "name": "mysql", "kwargs": []},  # 授权
        {"id": 99, "name": "python_execute", "kwargs": []},  # 未授权 id
        {"name": "fileupload", "kwargs": []},  # 授权 name
        {"name": "shell_execute", "kwargs": []},  # 未授权 name
    ]
    assert resolve_request_tools(request_tools, skill_tools) == [
        {"id": 5, "name": "mysql", "kwargs": []},
        {"name": "fileupload", "kwargs": []},
    ]
