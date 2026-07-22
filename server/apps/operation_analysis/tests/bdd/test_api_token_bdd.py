"""运营分析 API Token 权限 BDD（中文 Gherkin）。

对照 specs/capabilities/legacy-prd-运营分析-管理.md：
- HasPermission 装饰器在 api_pass=True 路径下的判定；
- 缺失权限 / 错误 app / 错误权限名 → 403；
- is_superuser 优先放行。

2 happy + 4 corner（6 场景）。
"""

import json
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import pytest
from pytest_bdd import given, parsers, scenarios, then, when
from rest_framework import status

from apps.core.decorators.api_permission import HasPermission
from apps.core.utils.web_utils import WebUtils

FEATURE = str(Path(__file__).parent / "api_token.feature")
scenarios(FEATURE)


@pytest.fixture
def ctx():
    return {"user": None, "result": None}


def _make_user(permission: dict, is_superuser: bool):
    return SimpleNamespace(
        id=1, username="tester", domain="domain.com",
        group_list=[1], roles=[],
        permission={k: set(v) for k, v in permission.items()},
        is_superuser=is_superuser,
        role_ids=[], locale="en", is_authenticated=True,
    )


# ---------------------------------------------------------------------------
# 假设
# ---------------------------------------------------------------------------

@given(parsers.parse('当前 user 拥有权限映射 {raw} is_superuser={flag}'))
def _seed_user(ctx, raw, flag):
    ctx["user"] = _make_user(json.loads(raw), is_superuser=(flag.lower() == "true"))


@given("当前 user 是 superuser")
def _seed_superuser(ctx):
    ctx["user"] = _make_user({}, is_superuser=True)


# ---------------------------------------------------------------------------
# 当
# ---------------------------------------------------------------------------

@when(parsers.parse('API Token 调用受 "{perm}" 保护的接口'))
def _call_protected(ctx, perm):
    @HasPermission(perm, app_name="ops-analysis")
    def _endpoint(request):
        return SimpleNamespace(status_code=200)

    request = SimpleNamespace(user=ctx["user"], api_pass=True, COOKIES={"current_team": "1"})

    with patch.object(WebUtils, "response_403") as mock_403:
        mock_403.return_value = SimpleNamespace(status_code=403)
        ctx["result"] = _endpoint(request)


# ---------------------------------------------------------------------------
# 那么
# ---------------------------------------------------------------------------

@then(parsers.parse("响应状态码应当为 {code:d}"))
def _status(ctx, code):
    assert ctx["result"].status_code == code, ctx["result"]
