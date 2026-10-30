"""字段调和判断。期望值来自规格表，不从实现反推。"""

from datetime import datetime, timedelta, timezone

from apps.cmdb.collection.field_reconcile import (
    clear_manual_fields,
    decide_field_write,
    is_empty_value,
    manual_field_ids,
    other_member_still_sees,
    plan_collected_instance,
    stamp_manual_sources,
)

NOW = datetime(2026, 10, 27, tzinfo=timezone.utc)
FRESH = (NOW - timedelta(days=1)).isoformat()
STALE = (NOW - timedelta(days=8)).isoformat()


def test_empty_values_keep_zero_and_false():
    assert is_empty_value(None) and is_empty_value("") and is_empty_value([])
    assert not is_empty_value(0)
    assert not is_empty_value(False)


def test_field_absent_from_this_conversion_keeps_value_and_source():
    plan = plan_collected_instance(
        old={
            "collect_task": "1",
            "organization": [1],
            "prot": "a",
            "_collect_sources": {"fields": {"prot": {"source": "1", "updated_at": FRESH}}, "seen": {"1": FRESH}},
        },
        incoming={"other": "x", "_task_organizations": [1]},
        task_id="2",
        member_order=["2", "1"],
        field_orders={"prot": ["2", "1"]},
        now=NOW,
        stale_days=7,
    )
    assert "prot" not in plan["properties"]
    assert plan["sources_json"].find('"prot"') > 0
    assert '"source": "1"' in plan["sources_json"] or '"source":"1"' in plan["sources_json"]


def test_higher_field_task_overwrites_lower_regardless_of_time():
    assert (
        decide_field_write(current="3306", proposed="3307", source="2", source_updated_at=FRESH, task_id="1", order=["1", "2"], now=NOW, stale_days=7)
        == "write"
    )
    assert (
        decide_field_write(current="8.0", proposed="5.7", source="1", source_updated_at=FRESH, task_id="2", order=["1", "2"], now=NOW, stale_days=7)
        == "skip"
    )


def test_higher_task_empty_does_not_clear_another_source():
    assert (
        decide_field_write(current="3306", proposed="", source="2", source_updated_at=FRESH, task_id="1", order=["1", "2"], now=NOW, stale_days=7)
        == "skip"
    )


def test_current_source_can_write_empty_and_refresh():
    assert (
        decide_field_write(current="3306", proposed="", source="1", source_updated_at=FRESH, task_id="1", order=["1", "2"], now=NOW, stale_days=7)
        == "write"
    )


def test_lower_task_refreshes_its_own_field():
    plan = plan_collected_instance(
        old={
            "collect_task": "1",
            "organization": [1],
            "port": "3306",
            "_collect_sources": {"fields": {"port": {"source": "2", "updated_at": FRESH}}, "seen": {"1": FRESH}},
        },
        incoming={"port": "3307", "_task_organizations": [1]},
        task_id="2",
        member_order=["1", "2"],
        field_orders={"port": ["2", "1"]},
        now=NOW,
        stale_days=7,
    )
    assert plan["properties"]["port"] == "3307"
    assert plan["collect_task"] == "1"


def test_stale_source_can_be_taken_over_unless_disabled():
    assert (
        decide_field_write(current="8.0", proposed="5.7", source="1", source_updated_at=STALE, task_id="2", order=["1", "2"], now=NOW, stale_days=7)
        == "write"
    )
    assert (
        decide_field_write(current="8.0", proposed="5.7", source="1", source_updated_at=STALE, task_id="2", order=["1", "2"], now=NOW, stale_days=0)
        == "skip"
    )


def test_same_value_moves_source_without_rewriting_the_field():
    plan = plan_collected_instance(
        old={
            "collect_task": "2",
            "organization": [1],
            "port": "3306",
            "_collect_sources": {"fields": {"port": {"source": "2", "updated_at": FRESH}}, "seen": {}},
        },
        incoming={"port": "3306", "_task_organizations": [1]},
        task_id="1",
        member_order=["1", "2"],
        field_orders={"port": ["1", "2"]},
        now=NOW,
        stale_days=7,
    )
    assert "port" not in plan["properties"]
    assert '"source":"1"' in plan["sources_json"]
    assert plan["collect_task"] == "1"
    assert plan["suppress_change_record"] is True


def test_manual_blocks_collection_until_cleared():
    stamped = stamp_manual_sources({"port": "3306"}, {"port": "3307"}, NOW)
    assert manual_field_ids({"_collect_sources": stamped}) == ["port"]
    assert (
        decide_field_write(current="3307", proposed="3308", source="manual", source_updated_at=FRESH, task_id="1", order=["1"], now=NOW, stale_days=7)
        == "skip"
    )
    cleared = clear_manual_fields({"_collect_sources": stamped}, ["port"])
    assert manual_field_ids({"_collect_sources": cleared}) == []


def test_unchanged_value_is_not_marked_manual():
    assert stamp_manual_sources({"port": "3306"}, {"port": "3306"}, NOW) is None


def test_member_order_transfers_ownership_field_order_does_not():
    plan = plan_collected_instance(
        old={
            "collect_task": "2",
            "organization": [1],
            "port": "3306",
            "collect_time": FRESH,
            "_collect_sources": {"fields": {"port": {"source": "2", "updated_at": FRESH}}, "seen": {"2": FRESH}},
        },
        incoming={"port": "3306", "_task_organizations": [1]},
        task_id="1",
        member_order=["1", "2"],
        field_orders={"port": ["2", "1"]},
        now=NOW,
        stale_days=7,
    )
    assert plan["collect_task"] == "1"
    assert "port" not in plan["properties"]


def test_unseen_owner_hands_over_to_the_foremost_seer_and_blocks_delete():
    old = {"collect_task": "1", "organization": [1], "collect_time": STALE, "_collect_sources": {"fields": {}, "seen": {"2": FRESH}}}
    plan = plan_collected_instance(
        old=old,
        incoming={"port": "3306", "_task_organizations": [1]},
        task_id="2",
        member_order=["1", "2"],
        field_orders={"port": ["1", "2"]},
        now=NOW,
        stale_days=7,
    )
    assert plan["collect_task"] == "2"
    assert other_member_still_sees("1", old["_collect_sources"], ["1", "2"], NOW, 7) is True
    assert other_member_still_sees("1", {"seen": {"2": STALE}}, ["1", "2"], NOW, 7) is False


def test_outside_owner_and_org_conflict_do_not_transfer():
    outside = plan_collected_instance(
        old={"collect_task": "9", "organization": [1], "port": "3306"},
        incoming={"port": "3307", "_task_organizations": [1]},
        task_id="1",
        member_order=["1", "2"],
        field_orders={},
        now=NOW,
        stale_days=7,
    )
    assert outside["conflict"] == "已有资产属于其他采集任务，无法自动接管"
    org = plan_collected_instance(
        old={"collect_task": "2", "organization": [8], "port": "3306"},
        incoming={"port": "3307", "_task_organizations": [1]},
        task_id="1",
        member_order=["1", "2"],
        field_orders={},
        now=NOW,
        stale_days=7,
    )
    assert "组织" in org["conflict"]


def test_inst_name_is_not_a_reconciled_field():
    plan = plan_collected_instance(
        old={"collect_task": "1", "organization": [1], "inst_name": "mysql-a"},
        incoming={"inst_name": "mysql-b", "port": "3306", "_task_organizations": [1]},
        task_id="1",
        member_order=["1", "2"],
        field_orders={},
        now=NOW,
        stale_days=7,
    )
    assert "inst_name" not in plan["properties"]
    assert plan["properties"]["port"] == "3306"
