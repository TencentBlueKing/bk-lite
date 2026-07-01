"""core.utils.exempt.api_exempt 纯单元测试。

规格：给视图函数打 api_exempt=True 标记（供鉴权中间件放行），
同时保留原函数元数据，并对同步/异步函数都生效。
"""

import asyncio

import pytest

from apps.core.utils.exempt import api_exempt

pytestmark = pytest.mark.unit


def test_同步函数被标记且可正常调用():
    @api_exempt
    def view(x):
        """原始 docstring"""
        return x + 1

    assert view.api_exempt is True
    assert view(1) == 2
    # functools.wraps 保留元数据
    assert view.__name__ == "view"
    assert view.__doc__ == "原始 docstring"


def test_异步函数被标记且可正常调用():
    @api_exempt
    async def view(x):
        return x * 2

    assert view.api_exempt is True
    assert asyncio.iscoroutinefunction(view)
    assert asyncio.run(view(3)) == 6
    assert view.__name__ == "view"
