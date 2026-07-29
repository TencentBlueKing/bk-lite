"""告警中心 BDD：转派 / 关闭 / 解决 三段状态迁移。

对照 specs/capabilities/legacy-prd-告警中心-告警.md：
- 处理中 → 待响应（转派）
- 处理中 → 已关闭（关闭，带 reason）
- 处理中 → 已处理（解决，带 note）

复用 conftest 中 db / api_client 等 fixtures。3 happy + 7 corner。
"""

import json
from pathlib import Path

import pytest
from pytest_bdd import given, parsers, scenarios, then, when

from apps.alerts.constants.constants import AlertStatus
from apps.alerts.models.models import Alert
from apps.alerts.service.alter_operator import AlertOperator

FEATURE = str(Path(__file__).parent / "alert_lifecycle_full.feature")
scenarios(FEATURE)

STATUS_MAP = {
    "unassigned": AlertStatus.UNASSIGNED,
    "pending": AlertStatus.PENDING,
    "processing": AlertStatus.PROCESSING,
    "closed": AlertStatus.CLOSED,
    "resolved": AlertStatus.RESOLVED,
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


def _create_alert(alert_id, status, operators=None, team=None):
    return Alert.objects.create(
        alert_id=alert_id, level="0", title=f"t-{alert_id}", content="c",
        fingerprint=f"fp-{alert_id}", status=STATUS_MAP[status],
        operator=operators or [], team=team or [1],
    )


@given(parsers.re(r'存在告警 "(?P<aid>[^"]+)"，状态为 "(?P<status>[^"]+)"，处理人为 \[(?P<ops>[^\]]*)\]'))
def _seed_alert(_alerts_db, aid, status, ops):
    operators = [s.strip().strip('"') for s in ops.split(",") if s.strip()]
    _create_alert(aid, status, operators=operators)


@when(parsers.re(
    r'用户 "(?P<user>[^"]+)" 对告警 "(?P<aid>[^"]+)" 执行操作 "(?P<action>[^"]+)"，附加数据 (?P<payload>.+)'
))
def _when_op(ctx, user, aid, action, payload):
    op = AlertOperator(user=user)
    try:
        ctx["result"] = op.operate(action, aid, json.loads(payload))
    except ValueError as exc:
        ctx["error"] = exc


@then("操作应当成功")
def _ok(ctx):
    assert ctx["error"] is None, ctx["error"]
    assert ctx["result"]["result"] is True, ctx["result"]


@then(parsers.parse('操作应当失败，消息包含 "{snippet}"'))
def _fail(ctx, snippet):
    assert ctx["result"]["result"] is False
    assert snippet in ctx["result"]["message"], ctx["result"]


@then(parsers.parse('告警 "{aid}" 的状态应当为 "{status}"'))
def _status(aid, status):
    assert Alert.objects.get(alert_id=aid).status == STATUS_MAP[status]


@then(parsers.parse('告警 "{aid}" 的处理人应当包含 "{username}"'))
def _operator(aid, username):
    assert username in Alert.objects.get(alert_id=aid).operator


@then(parsers.parse('操作返回数据 close_reason 应当为 "{value}"'))
def _close_reason(ctx, value):
    assert ctx["result"]["data"]["close_reason"] == value


@then(parsers.parse('操作返回数据 resolve_note 应当为 "{value}"'))
def _resolve_note(ctx, value):
    assert ctx["result"]["data"]["resolve_note"] == value
