"""mlops.utils.validators 纯单元测试。

规格：validate_serving_status_change —— 仅当目标状态为 active 且容器未 running 时，
返回 400 错误响应；其余情况返回 None（放行）。
"""

from types import SimpleNamespace

import pytest

from apps.mlops.utils.validators import validate_serving_status_change

pytestmark = pytest.mark.unit


def _inst(state):
    return SimpleNamespace(container_info={"state": state} if state is not None else None)


def test_active_但容器未运行_返回400():
    resp = validate_serving_status_change(_inst("exited"), "active")
    assert resp is not None
    assert resp.status_code == 400


def test_active_且容器运行中_放行():
    assert validate_serving_status_change(_inst("running"), "active") is None


def test_非active状态_放行():
    assert validate_serving_status_change(_inst("exited"), "inactive") is None


def test_container_info_为None_视为未运行():
    resp = validate_serving_status_change(_inst(None), "active")
    assert resp is not None
    assert resp.status_code == 400
