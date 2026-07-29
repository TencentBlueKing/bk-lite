"""告警自动分派 BDD（中文 Gherkin）。

对照 specs/capabilities/legacy-prd-告警中心-配置.md：
- AlertAssignmentOperator + execute_auto_assignment_for_alerts；
- match_type = all / filter 双路径；
- 无人员、无策略、空告警、未命中、不存在告警 ID 的拒绝路径。

2 happy + 5 corner（合 7 场景）。
"""

import json
from pathlib import Path

import pytest
from pytest_bdd import given, parsers, scenarios, then, when

from apps.alerts.common.assignment import AlertAssignmentOperator, execute_auto_assignment_for_alerts
from apps.alerts.constants.constants import AlertStatus
from apps.alerts.error import AlertNotFoundError
from apps.alerts.models.alert_operator import AlertAssignment
from apps.alerts.models.models import Alert

FEATURE = str(Path(__file__).parent / "assignment.feature")
scenarios(FEATURE)


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


@given(parsers.parse('已存在未分派告警 "{aid}" title="{title}"'))
def _seed_alert(_alerts_db, aid, title):
    Alert.objects.create(
        alert_id=aid, level="0", title=title, content="c", fingerprint="fp" + aid,
        status=AlertStatus.UNASSIGNED, source_name="prometheus", team=[1],
    )


@given(parsers.re(
    r'已存在分派策略 name="(?P<name>[^"]+)" match_type="(?P<match_type>[^"]+)" '
    r'personnel=(?P<personnel>\[[^\]]*\])$'
))
def _seed_assignment_simple(_alerts_db, name, match_type, personnel):
    AlertAssignment.objects.create(
        name=name, match_type=match_type, is_active=True,
        personnel=json.loads(personnel), match_rules=[],
        config={}, notify_channels=[], notification_scenario=[], notification_frequency={},
    )


@given(parsers.re(
    r'已存在分派策略 name="(?P<name>[^"]+)" match_type="(?P<match_type>[^"]+)" '
    r'personnel=(?P<personnel>\[[^\]]*\]) match_rules=(?P<rules>\[.*\])$'
))
def _seed_assignment_filter(_alerts_db, name, match_type, personnel, rules):
    AlertAssignment.objects.create(
        name=name, match_type=match_type, is_active=True,
        personnel=json.loads(personnel), match_rules=json.loads(rules),
        config={}, notify_channels=[], notification_scenario=[], notification_frequency={},
    )


@when(parsers.parse("我对告警 {ids} 执行自动分派"))
def _when_execute(ctx, ids):
    alert_ids = json.loads(ids)
    if not alert_ids:
        ctx["result"] = execute_auto_assignment_for_alerts([])
        return
    operator = AlertAssignmentOperator(alert_ids)
    ctx["result"] = operator.execute_auto_assignment()


@when(parsers.parse("我尝试对告警 {ids} 构造分派操作员"))
def _when_build_operator(ctx, ids):
    try:
        AlertAssignmentOperator(json.loads(ids))
    except AlertNotFoundError as exc:
        ctx["error"] = exc


@then(parsers.parse('告警 "{aid}" 的状态应当为 "{status}"'))
def _alert_status(aid, status):
    expected = {"pending": AlertStatus.PENDING, "unassigned": AlertStatus.UNASSIGNED,
                "processing": AlertStatus.PROCESSING, "closed": AlertStatus.CLOSED,
                "resolved": AlertStatus.RESOLVED}[status]
    assert Alert.objects.get(alert_id=aid).status == expected


@then(parsers.parse("已分派告警数应当为 {n:d}"))
def _assigned(ctx, n):
    assert ctx["result"]["assigned_alerts"] == n, ctx["result"]


@then(parsers.parse("总告警数应当为 {n:d}"))
def _total(ctx, n):
    assert ctx["result"]["total_alerts"] == n, ctx["result"]


@then("应当抛出告警不存在异常")
def _alert_not_found(ctx):
    assert isinstance(ctx["error"], AlertNotFoundError), ctx["error"]
