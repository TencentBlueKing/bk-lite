"""AutoRelationRuleReconcileService 自动关联收敛服务单元测试。

对照 apps/cmdb/services/auto_relation_reconcile.py：
  - 匹配规则判定（exact/iexact/contains/未知）
  - 空值判定 / mapping 读取
  - schedule_* 调度入口的规范化与去重、DEBUG 直跑 vs send_task
  - 期望目标集合计算、mapping 过滤（n:1/1:1 歧义、1:n 目标抢占）
  - reconcile_source_instance 的增删幂等、reconcile_for_instance / full_sync_rule 编排

只在 GraphClient / ModelManage / celery 这些真实外部边界打桩，断言真实输出与副作用。
"""
import pydantic.root_model  # noqa: F401  预热，避免覆盖率插桩竞态

import pytest

from apps.cmdb.services import auto_relation_reconcile as mod
from apps.cmdb.services.auto_relation_reconcile import (
    AUTO_RELATION_EDGE_RULE_ID_FIELD,
    AUTO_RELATION_EDGE_SOURCE,
    AUTO_RELATION_EDGE_SOURCE_FIELD,
    AutoRelationRuleReconcileService as SVC,
    schedule_incoming_rule_full_sync_by_model_ids,
    schedule_instance_auto_relation_reconcile,
    schedule_rule_auto_relation_full_sync,
)
from apps.cmdb.services.auto_relation_rule import (
    AUTO_RELATION_MATCHING_RULE_CONTAINS,
    AUTO_RELATION_MATCHING_RULE_EXACT,
    AUTO_RELATION_MATCHING_RULE_IEXACT,
    AutoRelationMatchPair,
    AutoRelationRule,
)


# --------------------------------------------------------------------------
# Fake GraphClient（按方法记录调用、返回预置值）
# --------------------------------------------------------------------------
class FakeGraph:
    def __init__(self, **returns):
        self.returns = returns
        self.created_edges = []
        self.deleted_edges = []

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False

    def query_entity(self, label, conds):
        return self.returns.get("query_entity", ([], 0))

    def query_entity_by_id(self, _id):
        return self.returns.get("query_entity_by_id", {})

    def query_edge(self, label, conds):
        # 支持按条件返回不同结果的回调
        cb = self.returns.get("query_edge")
        if callable(cb):
            return cb(label, conds)
        return cb if cb is not None else []

    def create_edge(self, *args, **kwargs):
        self.created_edges.append((args, kwargs))
        return {}

    def delete_edge(self, edge_id):
        self.deleted_edges.append(edge_id)
        return {}


def _rule(pairs, enabled=True, rule_id="r1"):
    return AutoRelationRule(rule_id=rule_id, enabled=enabled, match_pairs=pairs)


def _pair(src, dst, matching_rule=AUTO_RELATION_MATCHING_RULE_EXACT):
    return AutoRelationMatchPair(src_field_id=src, dst_field_id=dst, matching_rule=matching_rule)


# --------------------------------------------------------------------------
# _matches_pair
# --------------------------------------------------------------------------
def test_matches_pair_exact_hit_and_miss():
    p = _pair("a", "b", AUTO_RELATION_MATCHING_RULE_EXACT)
    assert SVC._matches_pair("x", "x", p) is True
    assert SVC._matches_pair("x", "y", p) is False
    # exact 不对 None 短路，None==None 仍成立
    assert SVC._matches_pair(None, None, p) is True


def test_matches_pair_iexact_normalizes_case_and_space():
    p = _pair("a", "b", AUTO_RELATION_MATCHING_RULE_IEXACT)
    assert SVC._matches_pair("  Host-A ", "host-a", p) is True
    assert SVC._matches_pair("a", "b", p) is False
    # None 直接 False（非 exact 时短路）
    assert SVC._matches_pair(None, "x", p) is False


def test_matches_pair_contains():
    p = _pair("a", "b", AUTO_RELATION_MATCHING_RULE_CONTAINS)
    assert SVC._matches_pair("10.0", " 10.0.0.1 ", p) is True
    assert SVC._matches_pair("zzz", "10.0.0.1", p) is False


def test_matches_pair_unknown_rule_returns_false():
    p = _pair("a", "b", "regex_not_supported")
    assert SVC._matches_pair("x", "x", p) is False


# --------------------------------------------------------------------------
# _is_empty_value / _get_mapping
# --------------------------------------------------------------------------
@pytest.mark.parametrize(
    "value,expected",
    [
        (None, True),
        ("", True),
        ("   ", True),
        ([], True),
        ({}, True),
        ((), True),
        (set(), True),
        ("x", False),
        ([1], False),
        (0, False),
        (False, False),
    ],
)
def test_is_empty_value(value, expected):
    assert SVC._is_empty_value(value) is expected


def test_get_mapping_default_and_explicit():
    assert SVC._get_mapping({}) == "n:n"
    assert SVC._get_mapping({"mapping": "1:1"}) == "1:1"
    assert SVC._get_mapping({"mapping": None}) == "n:n"


# --------------------------------------------------------------------------
# _calculate_desired_target_ids
# --------------------------------------------------------------------------
def test_calculate_desired_target_ids_matches_targets():
    src = {"_id": 1, "ip": "10.0.0.1"}
    targets = [
        {"_id": 11, "host_ip": "10.0.0.1"},
        {"_id": 12, "host_ip": "10.0.0.2"},
    ]
    rules = [_rule([_pair("ip", "host_ip")])]
    assoc = {"dst_model_id": "host"}
    out = SVC._calculate_desired_target_ids(src, assoc, rules, target_instances=targets)
    assert out == {11}


def test_calculate_desired_target_ids_skips_when_source_field_empty():
    src = {"_id": 1, "ip": ""}  # 源字段为空 → 整条规则跳过
    targets = [{"_id": 11, "host_ip": "10.0.0.1"}]
    rules = [_rule([_pair("ip", "host_ip")])]
    out = SVC._calculate_desired_target_ids(src, {"dst_model_id": "host"}, rules, target_instances=targets)
    assert out == set()


def test_calculate_desired_target_ids_queries_when_targets_not_given(monkeypatch):
    fake = FakeGraph(query_entity=([{"_id": 99, "host_ip": "1.1.1.1"}], 1))
    monkeypatch.setattr(mod, "GraphClient", lambda *a, **k: fake)
    src = {"_id": 1, "ip": "1.1.1.1"}
    rules = [_rule([_pair("ip", "host_ip")])]
    out = SVC._calculate_desired_target_ids(src, {"dst_model_id": "host"}, rules)
    assert out == {99}


# --------------------------------------------------------------------------
# _filter_desired_targets_for_mapping
# --------------------------------------------------------------------------
def test_filter_mapping_n1_ambiguous_drops_all():
    assoc = {"mapping": "n:1", "model_asst_id": "m1"}
    src = {"_id": 1}
    filtered, conflicts = SVC._filter_desired_targets_for_mapping(assoc, src, {10, 11})
    assert filtered == set()
    assert conflicts == 1


def test_filter_mapping_1n_target_claim_collision():
    assoc = {"mapping": "1:n", "model_asst_id": "m1"}
    claims = {}
    # 第一个源占用目标 20
    f1, c1 = SVC._filter_desired_targets_for_mapping(assoc, {"_id": 1}, {20}, target_claims=claims)
    assert f1 == {20} and c1 == 0 and claims == {20: 1}
    # 第二个源也想要 20 → 冲突丢弃
    f2, c2 = SVC._filter_desired_targets_for_mapping(assoc, {"_id": 2}, {20, 21}, target_claims=claims)
    assert f2 == {21} and c2 == 1
    assert claims == {20: 1, 21: 2}


def test_filter_mapping_nn_passthrough():
    assoc = {"mapping": "n:n"}
    f, c = SVC._filter_desired_targets_for_mapping(assoc, {"_id": 1}, {1, 2, 3})
    assert f == {1, 2, 3} and c == 0


def test_filter_mapping_empty_short_circuits():
    assoc = {"mapping": "n:1"}
    f, c = SVC._filter_desired_targets_for_mapping(assoc, {"_id": 1}, set())
    assert f == set() and c == 0


# --------------------------------------------------------------------------
# reconcile_source_instance：创建 / 删除 / 幂等跳过
# --------------------------------------------------------------------------
def test_reconcile_source_instance_creates_missing_edge(monkeypatch):
    src = {"_id": 1, "ip": "10.0.0.1", "model_id": "vm"}
    assoc = {
        "model_asst_id": "vm_run_host",
        "src_model_id": "vm",
        "dst_model_id": "host",
        "asst_id": "run",
        "mapping": "n:n",
    }
    rules = [_rule([_pair("ip", "host_ip")])]
    targets = [{"_id": 11, "host_ip": "10.0.0.1"}]
    fake = FakeGraph(query_edge=lambda *a: [])  # 无既有边
    monkeypatch.setattr(mod, "GraphClient", lambda *a, **k: fake)
    monkeypatch.setattr(
        "apps.cmdb.services.instance.InstanceManage.check_asso_mapping", lambda data: None
    )
    summary = SVC.reconcile_source_instance(src, assoc, rules, target_instances=targets)
    assert summary["created"] == 1
    assert summary["deleted"] == 0
    assert summary["desired"] == 1
    assert len(fake.created_edges) == 1
    # 校验落库的边数据契约
    edge_data = fake.created_edges[0][0][5]
    assert edge_data["dst_inst_id"] == 11
    assert edge_data[AUTO_RELATION_EDGE_SOURCE_FIELD] == AUTO_RELATION_EDGE_SOURCE
    assert edge_data[AUTO_RELATION_EDGE_RULE_ID_FIELD] == "vm_run_host"


def test_reconcile_source_instance_deletes_stale_auto_edge(monkeypatch):
    src = {"_id": 1, "ip": "10.0.0.9", "model_id": "vm"}
    assoc = {
        "model_asst_id": "vm_run_host",
        "src_model_id": "vm",
        "dst_model_id": "host",
        "asst_id": "run",
        "mapping": "n:n",
    }
    rules = [_rule([_pair("ip", "host_ip")])]
    targets = [{"_id": 11, "host_ip": "10.0.0.1"}]  # 目标 11 不再匹配（src ip 变了）
    stale_edge = {
        "_id": "e-stale",
        "dst_inst_id": 11,
        AUTO_RELATION_EDGE_SOURCE_FIELD: AUTO_RELATION_EDGE_SOURCE,
        AUTO_RELATION_EDGE_RULE_ID_FIELD: "vm_run_host",
    }
    fake = FakeGraph(query_edge=lambda *a: [stale_edge])
    monkeypatch.setattr(mod, "GraphClient", lambda *a, **k: fake)
    summary = SVC.reconcile_source_instance(src, assoc, rules, target_instances=targets)
    assert summary["deleted"] == 1
    assert summary["created"] == 0
    assert fake.deleted_edges == ["e-stale"]


def test_reconcile_source_instance_skips_existing_target(monkeypatch):
    src = {"_id": 1, "ip": "10.0.0.1", "model_id": "vm"}
    assoc = {
        "model_asst_id": "vm_run_host",
        "src_model_id": "vm",
        "dst_model_id": "host",
        "asst_id": "run",
        "mapping": "n:n",
    }
    rules = [_rule([_pair("ip", "host_ip")])]
    targets = [{"_id": 11, "host_ip": "10.0.0.1"}]
    # 已存在到 11 的边（非 auto 来源也算 existing target），desired 命中应跳过
    existing = {"_id": "e1", "dst_inst_id": 11, AUTO_RELATION_EDGE_SOURCE_FIELD: "manual"}
    fake = FakeGraph(query_edge=lambda *a: [existing])
    monkeypatch.setattr(mod, "GraphClient", lambda *a, **k: fake)
    summary = SVC.reconcile_source_instance(src, assoc, rules, target_instances=targets)
    assert summary["skipped"] == 1
    assert summary["created"] == 0
    assert fake.created_edges == []


def test_reconcile_source_instance_conflict_on_check_asso_mapping(monkeypatch):
    from apps.core.exceptions.base_app_exception import BaseAppException

    src = {"_id": 1, "ip": "10.0.0.1", "model_id": "vm"}
    assoc = {
        "model_asst_id": "vm_run_host",
        "src_model_id": "vm",
        "dst_model_id": "host",
        "asst_id": "run",
        "mapping": "n:n",
    }
    rules = [_rule([_pair("ip", "host_ip")])]
    targets = [{"_id": 11, "host_ip": "10.0.0.1"}]
    fake = FakeGraph(query_edge=lambda *a: [])
    monkeypatch.setattr(mod, "GraphClient", lambda *a, **k: fake)

    def _raise(_data):
        raise BaseAppException("mapping violated")

    monkeypatch.setattr("apps.cmdb.services.instance.InstanceManage.check_asso_mapping", _raise)
    summary = SVC.reconcile_source_instance(src, assoc, rules, target_instances=targets)
    assert summary["created"] == 0
    assert summary["conflicts"] == 1
    assert fake.created_edges == []


# --------------------------------------------------------------------------
# cleanup_auto_edges_by_rule
# --------------------------------------------------------------------------
def test_cleanup_auto_edges_by_rule(monkeypatch):
    edges = [{"_id": "a"}, {"_id": "b"}]
    fake = FakeGraph(query_edge=lambda *a: edges)
    monkeypatch.setattr(mod, "GraphClient", lambda *a, **k: fake)
    deleted = SVC.cleanup_auto_edges_by_rule("m1")
    assert deleted == 2
    assert fake.deleted_edges == ["a", "b"]


# --------------------------------------------------------------------------
# _list_enabled_rules_by_src_model / _list_enabled_rule_ids_by_dst_model
# --------------------------------------------------------------------------
def test_list_enabled_rules_by_src_model_filters(monkeypatch):
    associations = [
        {  # 不是源模型 → 跳过
            "src_model_id": "other",
            "dst_model_id": "host",
            "model_asst_id": "x",
            "auto_relation_rule": {"version": 1, "rules": [{"rule_id": "r", "enabled": True, "match_pairs": [{"src_field_id": "ip", "dst_field_id": "host_ip"}]}]},
        },
        {  # 源模型匹配且有启用规则 → 入选
            "src_model_id": "vm",
            "dst_model_id": "host",
            "model_asst_id": "vm_run_host",
            "auto_relation_rule": {"version": 1, "rules": [{"rule_id": "r", "enabled": True, "match_pairs": [{"src_field_id": "ip", "dst_field_id": "host_ip"}]}]},
        },
        {  # 源模型匹配但规则全 disabled → 跳过
            "src_model_id": "vm",
            "dst_model_id": "host",
            "model_asst_id": "vm_disabled",
            "auto_relation_rule": {"version": 1, "rules": [{"rule_id": "r", "enabled": False, "match_pairs": [{"src_field_id": "ip", "dst_field_id": "host_ip"}]}]},
        },
    ]
    monkeypatch.setattr(
        "apps.cmdb.services.model.ModelManage.model_association_search", lambda mid: associations
    )
    out = SVC._list_enabled_rules_by_src_model("vm")
    assert len(out) == 1
    assoc, rules = out[0]
    assert assoc["model_asst_id"] == "vm_run_host"
    assert rules[0].enabled is True


def test_list_enabled_rule_ids_by_dst_model(monkeypatch):
    associations = [
        {
            "src_model_id": "vm",
            "dst_model_id": "host",
            "model_asst_id": "vm_run_host",
            "auto_relation_rule": {"version": 1, "rules": [{"rule_id": "r", "enabled": True, "match_pairs": [{"src_field_id": "ip", "dst_field_id": "host_ip"}]}]},
        },
        {  # dst 不匹配
            "src_model_id": "vm",
            "dst_model_id": "switch",
            "model_asst_id": "vm_run_switch",
            "auto_relation_rule": {"version": 1, "rules": [{"rule_id": "r", "enabled": True, "match_pairs": [{"src_field_id": "ip", "dst_field_id": "host_ip"}]}]},
        },
    ]
    monkeypatch.setattr(
        "apps.cmdb.services.model.ModelManage.model_association_search", lambda mid: associations
    )
    out = SVC._list_enabled_rule_ids_by_dst_model("host")
    assert out == ["vm_run_host"]


# --------------------------------------------------------------------------
# reconcile_for_instance
# --------------------------------------------------------------------------
def test_reconcile_for_instance_not_found(monkeypatch):
    fake = FakeGraph(query_entity_by_id={})
    monkeypatch.setattr(mod, "GraphClient", lambda *a, **k: fake)
    out = SVC.reconcile_for_instance(123)
    assert out["success"] is False
    assert out["instance_id"] == 123
    assert out["created"] == 0


def test_reconcile_for_instance_aggregates_source_rules(monkeypatch):
    instance = {"_id": 1, "model_id": "vm", "ip": "10.0.0.1"}
    fake = FakeGraph(query_entity_by_id=instance, query_edge=lambda *a: [])
    monkeypatch.setattr(mod, "GraphClient", lambda *a, **k: fake)

    assoc = {
        "model_asst_id": "vm_run_host",
        "src_model_id": "vm",
        "dst_model_id": "host",
        "asst_id": "run",
        "mapping": "n:n",
    }
    rules = [_rule([_pair("ip", "host_ip")])]
    monkeypatch.setattr(SVC, "_list_enabled_rules_by_src_model", classmethod(lambda cls, mid: [(assoc, rules)]))
    monkeypatch.setattr(SVC, "_list_enabled_rule_ids_by_dst_model", classmethod(lambda cls, mid: []))
    monkeypatch.setattr(SVC, "_query_instances_by_model", classmethod(lambda cls, mid: [{"_id": 11, "host_ip": "10.0.0.1"}]))
    monkeypatch.setattr("apps.cmdb.services.instance.InstanceManage.check_asso_mapping", lambda data: None)

    out = SVC.reconcile_for_instance(1)
    assert out["success"] is True
    assert out["source_rules"] == 1
    assert out["created"] == 1
    assert out["full_sync_rules"] == 0


def test_reconcile_for_instance_schedules_full_sync_when_incoming(monkeypatch):
    instance = {"_id": 5, "model_id": "host"}
    fake = FakeGraph(query_entity_by_id=instance)
    monkeypatch.setattr(mod, "GraphClient", lambda *a, **k: fake)
    monkeypatch.setattr(SVC, "_list_enabled_rules_by_src_model", classmethod(lambda cls, mid: []))
    monkeypatch.setattr(SVC, "_list_enabled_rule_ids_by_dst_model", classmethod(lambda cls, mid: ["vm_run_host"]))

    scheduled = []
    monkeypatch.setattr(mod, "schedule_rule_auto_relation_full_sync", lambda ids: scheduled.extend(ids))
    out = SVC.reconcile_for_instance(5)
    assert out["full_sync_rules"] == 1
    assert scheduled == ["vm_run_host"]


# --------------------------------------------------------------------------
# full_sync_rule
# --------------------------------------------------------------------------
def test_full_sync_rule_cleanup_when_no_enabled_rules(monkeypatch):
    monkeypatch.setattr(
        "apps.cmdb.services.model.ModelManage.model_association_info_search", lambda mid: None
    )
    monkeypatch.setattr(SVC, "cleanup_auto_edges_by_rule", classmethod(lambda cls, mid: 7))
    out = SVC.full_sync_rule("dead_rule")
    assert out["mode"] == "cleanup"
    assert out["deleted"] == 7


def test_full_sync_rule_full_sync_path(monkeypatch):
    association = {
        "model_asst_id": "vm_run_host",
        "src_model_id": "vm",
        "dst_model_id": "host",
        "asst_id": "run",
        "mapping": "n:n",
        "auto_relation_rule": {"version": 1, "rules": [{"rule_id": "r", "enabled": True, "match_pairs": [{"src_field_id": "ip", "dst_field_id": "host_ip"}]}]},
    }
    monkeypatch.setattr(
        "apps.cmdb.services.model.ModelManage.model_association_info_search", lambda mid: association
    )
    # 目标 + 源
    monkeypatch.setattr(
        SVC,
        "_query_instances_by_model",
        classmethod(lambda cls, mid: [{"_id": 11, "host_ip": "10.0.0.1"}] if mid == "host" else [{"_id": 1, "ip": "10.0.0.1", "model_id": "vm"}]),
    )
    fake = FakeGraph(query_edge=lambda *a: [])
    monkeypatch.setattr(mod, "GraphClient", lambda *a, **k: fake)
    monkeypatch.setattr("apps.cmdb.services.instance.InstanceManage.check_asso_mapping", lambda data: None)
    out = SVC.full_sync_rule("vm_run_host")
    assert out["mode"] == "full_sync"
    assert out["source_instances"] == 1
    assert out["created"] == 1


# --------------------------------------------------------------------------
# schedule_* 调度入口
# --------------------------------------------------------------------------
def test_schedule_instance_reconcile_normalizes_and_dedupes(monkeypatch, settings):
    settings.DEBUG = True
    called = []
    # transaction.on_commit 在非事务下立即执行回调
    monkeypatch.setattr(mod.transaction, "on_commit", lambda fn: fn())
    import apps.cmdb.tasks.celery_tasks as ct
    monkeypatch.setattr(ct, "reconcile_instance_auto_association_task", lambda iid: called.append(iid))

    schedule_instance_auto_relation_reconcile([3, "3", 0, -1, "bad", 5])
    assert called == [3, 5]


def test_schedule_instance_reconcile_empty_noop(monkeypatch):
    on_commit_called = []
    monkeypatch.setattr(mod.transaction, "on_commit", lambda fn: on_commit_called.append(fn))
    schedule_instance_auto_relation_reconcile([])
    assert on_commit_called == []


def test_schedule_instance_reconcile_send_task_when_not_debug(monkeypatch, settings):
    settings.DEBUG = False
    monkeypatch.setattr(mod.transaction, "on_commit", lambda fn: fn())
    sent = []
    monkeypatch.setattr(mod.current_app, "send_task", lambda name, args: sent.append((name, args)))
    schedule_instance_auto_relation_reconcile([9])
    assert sent == [(mod.INSTANCE_RECONCILE_TASK, [9])]


def test_schedule_rule_full_sync_dedupes_and_clears_pending(monkeypatch, settings):
    settings.DEBUG = True
    mod._PENDING_RULE_FULL_SYNC_IDS.clear()
    monkeypatch.setattr(mod.transaction, "on_commit", lambda fn: fn())
    called = []
    import apps.cmdb.tasks.celery_tasks as ct
    monkeypatch.setattr(ct, "full_sync_auto_association_rule_task", lambda mid: called.append(mid))
    schedule_rule_auto_relation_full_sync(["r1", " r1 ", "", None, "r2"])
    assert called == ["r1", "r2"]
    # dispatch 后 pending 应清空
    assert mod._PENDING_RULE_FULL_SYNC_IDS == set()


def test_schedule_incoming_by_model_ids(monkeypatch):
    monkeypatch.setattr(
        SVC, "_list_enabled_rule_ids_by_dst_model", classmethod(lambda cls, mid: ["vm_run_host"] if mid == "host" else [])
    )
    captured = []
    monkeypatch.setattr(mod, "schedule_rule_auto_relation_full_sync", lambda ids: captured.append(list(ids)))
    schedule_incoming_rule_full_sync_by_model_ids(["host", "host", "", None])
    assert captured == [["vm_run_host"]]
