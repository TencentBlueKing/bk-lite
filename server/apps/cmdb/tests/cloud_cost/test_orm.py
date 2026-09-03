"""云成本权限查询入口与参数化计划测试。"""

from datetime import date

import pytest

from apps.cmdb.services.cloud_cost import orm
from apps.cmdb.services.cloud_cost.query import CloudCostQueryPlan, compile_cloud_cost_query


USER = {"team": 1, "user": "tester"}
PERMISSION = {1: {"inst_names": []}}


def _plan(kind="summary", **overrides):
    values = {
        "kind": kind,
        "bill_permission_map": PERMISSION,
        "log_permission_map": PERMISSION,
    }
    values.update(overrides)
    return CloudCostQueryPlan(**values)


def test_summary_plan_has_no_row_cap_and_deduplicates_association_pairs():
    compiled = compile_cloud_cost_query(_plan())

    assert "WITH DISTINCT bill, log" in compiled.statement
    assert "sum(toFloat(log.total_cost))" in compiled.statement
    assert "LIMIT" not in compiled.statement
    assert 100000 not in compiled.params.values()


def test_plan_parameterizes_filters_and_both_permission_scopes():
    injection = "db') RETURN bill //"
    compiled = compile_cloud_cost_query(
        _plan(
            inst_type=injection,
            user_department="研发",
            applying_user="alice",
            billing_period=(date(2026, 6, 1), date(2026, 6, 30)),
        ),
    )

    assert injection not in compiled.statement
    assert injection in compiled.params.values()
    assert "bill.organization" in compiled.statement
    assert "log.organization" in compiled.statement
    assert "bill.inst_name" not in compiled.statement
    assert "log.billing_date >=" in compiled.statement


def test_plan_applies_instance_name_permission_inside_each_org_scope():
    scoped = {1: {"inst_names": ["allowed-bill"]}}
    compiled = compile_cloud_cost_query(
        _plan(bill_permission_map=scoped, log_permission_map={2: {"inst_names": ["allowed-log"]}}),
    )

    assert "bill.inst_name IN" in compiled.statement
    assert "log.inst_name IN" in compiled.statement
    assert ["allowed-bill"] in compiled.params.values()
    assert ["allowed-log"] in compiled.params.values()


def test_distribution_rejects_unregistered_group_field():
    with pytest.raises(ValueError, match="unsupported cloud cost group field"):
        compile_cloud_cost_query(_plan("distribution", group_field="name) RETURN bill"))


def test_detail_plan_returns_exact_total_and_page_from_one_snapshot():
    compiled = compile_cloud_cost_query(
        _plan(
            "bill_detail",
            page=3,
            page_size=20,
            sort_field="department",
            sort_order="asc",
        ),
    )

    assert "ORDER BY item.department ASC, item.bill_key ASC" in compiled.statement
    assert "WITH collect(item) AS items" in compiled.statement
    assert "RETURN size(items) AS total, items[$skip..$end] AS items" in compiled.statement
    assert compiled.params["skip"] == 40
    assert compiled.params["end"] == 60


@pytest.mark.parametrize(
    ("sort_field", "expression"),
    [
        ("total_cost_incurred", "item.total_cost"),
        ("instance_name", "item.instance_name"),
        ("department", "item.department"),
    ],
)
def test_detail_plan_supports_registered_global_sort_fields(sort_field, expression):
    compiled = compile_cloud_cost_query(
        _plan("bill_detail", sort_field=sort_field, sort_order="desc"),
    )

    assert f"ORDER BY {expression} DESC, item.bill_key ASC" in compiled.statement


def test_detail_rejects_unregistered_sort_field_and_order():
    with pytest.raises(ValueError, match="unsupported cloud cost sort field"):
        compile_cloud_cost_query(_plan("bill_detail", sort_field="bill.foo"))
    with pytest.raises(ValueError, match="unsupported cloud cost sort order"):
        compile_cloud_cost_query(_plan("bill_detail", sort_order="sideways"))


def test_plan_uses_one_common_cypher_contract_for_both_graph_adapters():
    compiled = compile_cloud_cost_query(_plan())

    assert "coalesce(bill.organization, [])" in compiled.statement
    assert "coalesce(log.organization, [])" in compiled.statement
    assert "typeof(" not in compiled.statement
    assert "valueType(" not in compiled.statement
    assert "elementId(" not in compiled.statement


def test_query_summary_fails_closed_when_either_model_permission_is_missing(monkeypatch):
    permissions = iter((PERMISSION, None))
    monkeypatch.setattr(orm, "_perm", lambda *args, **kwargs: next(permissions))
    monkeypatch.setattr(orm, "_execute", lambda plan: pytest.fail("graph query must not execute"))

    assert orm.query_summary(USER) == {}


def test_query_summary_passes_normalized_plan_to_graph(monkeypatch):
    monkeypatch.setattr(orm, "_perm", lambda *args, **kwargs: PERMISSION)
    captured = []
    monkeypatch.setattr(
        orm,
        "_execute",
        lambda plan: captured.append(plan) or [{"total_cost": 100001.0, "instance_count": 100001}],
    )

    result = orm.query_summary(USER, inst_type="database")

    assert result["total_cost"] == 100001.0
    assert captured[0].kind == "summary"
    assert captured[0].inst_type == "database"
    assert captured[0].bill_permission_map == PERMISSION
    assert captured[0].log_permission_map == PERMISSION


def test_query_bill_detail_empty_permission_preserves_response_shape(monkeypatch):
    monkeypatch.setattr(orm, "_perm", lambda *args, **kwargs: None)

    assert orm.query_bill_detail(USER, page=2, page_size=10) == {"total": 0, "items": []}
