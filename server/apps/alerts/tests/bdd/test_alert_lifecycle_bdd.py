"""告警中心 BDD：AlertOperator 状态机生命周期（中文 Gherkin）。

对照 specs/capabilities/legacy-prd-告警中心-告警.md：未分派 → 待响应 → 处理中 → 关闭，
覆盖分派/认领的权限、状态、入参校验，含两条 happy path 与多条 corner case。
"""

import json
from pathlib import Path

import pytest
from pytest_bdd import given, parsers, scenarios, then, when

from apps.alerts.constants.constants import AlertStatus
from apps.alerts.models.models import Alert
from apps.alerts.service.alter_operator import AlertOperator

FEATURE = str(Path(__file__).parent / "alert_lifecycle.feature")
scenarios(FEATURE)

STATUS_MAP = {
    "unassigned": AlertStatus.UNASSIGNED,
    "pending": AlertStatus.PENDING,
    "processing": AlertStatus.PROCESSING,
    "closed": AlertStatus.CLOSED,
}


@pytest.fixture
def ctx():
    return {"result": None, "error": None}


@pytest.fixture
def _alerts_db(db):
    return db


@given(parsers.parse('存在团队为 {team:d} 的系统用户 "{username}"'))
def _make_sys_user(_alerts_db, username, team):
    from apps.system_mgmt.models.user import User

    User.objects.get_or_create(
        username=username,
        defaults={"domain": "domain.com", "group_list": [{"id": team}]},
    )


def _create_alert(alert_id, status, team=None, operators=None):
    return Alert.objects.create(
        alert_id=alert_id,
        level="0",
        title=f"t-{alert_id}",
        content="c",
        fingerprint=f"fp-{alert_id}",
        status=STATUS_MAP[status],
        operator=operators or [],
        team=team or [1],
    )


@given(parsers.parse('存在告警 "{alert_id}"，状态为 "{status}"，团队为 [{team:d}]'))
def _make_alert_team(_alerts_db, alert_id, status, team):
    _create_alert(alert_id, status, team=[team])


@given(parsers.re(r'存在告警 "(?P<alert_id>[^"]+)"，状态为 "(?P<status>[^"]+)"，处理人为 \[(?P<ops>[^\]]*)\]'))
def _make_alert_ops(_alerts_db, alert_id, status, ops):
    operators = [s.strip().strip('"') for s in ops.split(",") if s.strip()]
    _create_alert(alert_id, status, operators=operators)


# ---------- 当 ----------

def _dispatch(ctx, user, action, alert_id, payload, allowed=None):
    op = AlertOperator(user=user, allowed_alert_ids=allowed)
    data = json.loads(payload) if payload else {}
    try:
        ctx["result"] = op.operate(action, alert_id, data)
    except ValueError as exc:
        ctx["error"] = exc


@when(parsers.re(r'系统对告警 "(?P<alert_id>[^"]+)" 执行操作 "(?P<action>[^"]+)"，附加数据 (?P<payload>.+)'))
def _when_system(ctx, action, alert_id, payload):
    _dispatch(ctx, "system", action, alert_id, payload)


@when(parsers.re(r'用户 "(?P<user>[^"]+)" 对告警 "(?P<alert_id>[^"]+)" 执行操作 "(?P<action>[^"]+)"，附加数据 (?P<payload>.+)'))
def _when_user(ctx, user, action, alert_id, payload):
    _dispatch(ctx, user, action, alert_id, payload)


@when(parsers.re(r'用户 "(?P<user>[^"]+)" 尝试对告警 "(?P<alert_id>[^"]+)" 执行操作 "(?P<action>[^"]+)"，附加数据 (?P<payload>.+)'))
def _when_user_try(ctx, user, action, alert_id, payload):
    _dispatch(ctx, user, action, alert_id, payload)


@when(parsers.re(
    r'受限用户 "(?P<user>[^"]+)" 仅允许 \[(?P<allowed>[^\]]*)\] '
    r'时对告警 "(?P<alert_id>[^"]+)" 执行操作 "(?P<action>[^"]+)"，附加数据 (?P<payload>.+)'
))
def _when_restricted(ctx, user, allowed, action, alert_id, payload):
    allow_list = [s.strip().strip('"') for s in allowed.split(",") if s.strip()]
    _dispatch(ctx, user, action, alert_id, payload, allowed=allow_list)


# ---------- 那么 ----------

@then("操作应当成功")
def _result_success(ctx):
    assert ctx["error"] is None, f"unexpected error: {ctx['error']}"
    assert ctx["result"] is not None
    assert ctx["result"]["result"] is True, ctx["result"]


@then(parsers.parse('操作应当失败，消息包含 "{snippet}"'))
def _result_fail(ctx, snippet):
    assert ctx["error"] is None, f"unexpected error: {ctx['error']}"
    assert ctx["result"] is not None
    assert ctx["result"]["result"] is False
    assert snippet in ctx["result"]["message"], ctx["result"]


@then("应当抛出 ValueError")
def _value_error(ctx):
    assert isinstance(ctx["error"], ValueError), f"expected ValueError, got {ctx['error']!r}"


@then(parsers.parse('告警 "{alert_id}" 的状态应当为 "{status}"'))
def _alert_status(alert_id, status):
    assert Alert.objects.get(alert_id=alert_id).status == STATUS_MAP[status]


@then(parsers.parse('告警 "{alert_id}" 的处理人应当包含 "{username}"'))
def _alert_operator(alert_id, username):
    assert username in Alert.objects.get(alert_id=alert_id).operator
