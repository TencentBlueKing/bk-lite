"""opspilot.utils.skill_execution_params 纯单元测试。

规格：resolve_request_tools 的优先级——请求工具优先，其次技能工具，都无则空列表。
"""

import pytest

from apps.opspilot.utils.skill_execution_params import resolve_request_tools

pytestmark = pytest.mark.unit


def test_请求工具优先():
    assert resolve_request_tools(["a"], ["b"]) == ["a"]


def test_无请求工具时用技能工具():
    assert resolve_request_tools([], ["b"]) == ["b"]
    assert resolve_request_tools(None, ["b"]) == ["b"]


def test_都为空返回空列表():
    assert resolve_request_tools(None, None) == []
    assert resolve_request_tools([], []) == []
