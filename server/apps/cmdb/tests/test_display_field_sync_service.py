# -*- coding: utf-8 -*-
"""DisplayFieldSynchronizer 同步链路测试。

对照 spec/CMDB·资产：组织/用户展示信息变更时，重建实例 _display 冗余字段。
只 mock 真实外部边界（GraphClient 图库、ExcludeFieldsCache 缓存、Group/User DB、Celery），
断言真实的 _display 重建值、batch_update 入参契约与各类早返回分支。
"""
import pytest

from apps.cmdb.display_field.sync import DisplayFieldSynchronizer, refresh_display_sync_data, sync_display_fields_for_system_mgmt

MODULE = "apps.cmdb.display_field.sync"


class _FakeGraph:
    """记录 batch_update_node_properties 调用并按预置实例驱动 sync_all。"""

    def __init__(self, instances):
        self._instances = instances
        self.updates = []  # list of (label, ids, data)
        self.legacy_updates = []
        self.property_updates = []
        self.query_calls = []

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False

    def query_entity(self, label, params, page=None, include_count=True):
        self.query_calls.append(
            {
                "label": label,
                "params": list(params),
                "page": dict(page) if page else None,
                "include_count": include_count,
            }
        )
        instances = list(self._instances)
        for param in params:
            if param["type"] == "str[]":
                instances = [instance for instance in instances if instance.get(param["field"]) in param["value"]]
            elif param["type"] == "id>":
                instances = [instance for instance in instances if instance["_id"] > param["value"]]
        if page:
            instances = instances[page["skip"] : page["skip"] + page["limit"]]
        return instances, len(instances) if include_count else None

    def batch_update_node_properties(self, label, ids, data):
        self.legacy_updates.append((label, list(ids), dict(data)))
        self.updates.append((label, list(ids), dict(data)))
        return {}

    def batch_update_node_property_values(self, label, field, property_values):
        copied_values = [dict(item) for item in property_values]
        self.property_updates.append((label, field, copied_values))
        for item in copied_values:
            node_id = item["id"]
            existing = next((update for update in self.updates if update[1] == [node_id]), None)
            if existing:
                existing[2][field] = item["value"]
            else:
                self.updates.append((label, [node_id], {field: item["value"]}))
        return []


def _install_graph(monkeypatch, instances):
    fake = _FakeGraph(instances)
    monkeypatch.setattr(f"{MODULE}.GraphClient", lambda *a, **k: fake)
    return fake


def _install_mapping(monkeypatch, mapping):
    monkeypatch.setattr(
        "apps.cmdb.display_field.cache.ExcludeFieldsCache.get_model_fields_mapping",
        classmethod(lambda cls: mapping),
    )


def test_refresh_display_sync_data_uses_current_values_and_preserves_missing_legacy_items(monkeypatch):
    class _GroupQS:
        def filter(self, **kwargs):
            assert kwargs == {"id__in": [1, 9]}
            return self

        def values_list(self, *fields):
            assert fields == ("id", "name")
            return [(1, "当前组织名")]

    class _UserQS:
        def filter(self, **kwargs):
            assert kwargs == {"id__in": [2, 8]}
            return self

        def values(self, *fields):
            assert fields == ("id", "username", "display_name")
            return [{"id": 2, "username": "current", "display_name": "当前用户"}]

    monkeypatch.setattr(f"{MODULE}.Group.objects", _GroupQS())
    monkeypatch.setattr(f"{MODULE}.User.objects", _UserQS())

    refreshed = refresh_display_sync_data(
        {
            "organizations": [{"id": 1, "name": "旧组织名"}, {"id": 9, "name": "历史组织"}],
            "users": [
                {"id": 2, "username": "old", "display_name": "旧用户"},
                {"id": 8, "username": "legacy", "display_name": "历史用户"},
            ],
        }
    )

    assert refreshed == {
        "organizations": [{"id": 1, "name": "当前组织名"}, {"id": 9, "name": "历史组织"}],
        "users": [
            {"id": 2, "username": "current", "display_name": "当前用户"},
            {"id": 8, "username": "legacy", "display_name": "历史用户"},
        ],
    }


# --------------------------------------------------------------------------
# sync_all：早返回分支
# --------------------------------------------------------------------------


def test_sync_all_empty_returns_zeros():
    out = DisplayFieldSynchronizer.sync_all({})
    assert out == {"organizations": 0, "users": 0}


def test_sync_all_skips_model_without_fields(monkeypatch):
    # 实例属于 host，但 host 既无 org 字段也无 user 字段 → 不更新
    fake = _install_graph(monkeypatch, [{"_id": 1, "model_id": "host", "org": [1]}])
    _install_mapping(monkeypatch, {"host": {}})

    out = DisplayFieldSynchronizer.sync_all({"organizations": [{"id": 1, "name": "新部门"}]})
    assert out == {"organizations": 0, "users": 0}
    assert fake.updates == []


def test_sync_all_skips_instance_without_model_id(monkeypatch):
    fake = _install_graph(monkeypatch, [{"_id": 1, "org": [1]}])  # 无 model_id
    _install_mapping(monkeypatch, {"host": {"organization": ["org"]}})

    out = DisplayFieldSynchronizer.sync_all({"organizations": [{"id": 1, "name": "x"}]})
    assert out == {"organizations": 0, "users": 0}
    assert fake.updates == []


# --------------------------------------------------------------------------
# sync_all：组织字段重建
# --------------------------------------------------------------------------


def test_sync_all_rebuilds_organization_display(monkeypatch):
    fake = _install_graph(
        monkeypatch,
        [{"_id": 10, "model_id": "host", "org": [1, 2]}],
    )
    _install_mapping(monkeypatch, {"host": {"organization": ["org"], "user": []}})

    out = DisplayFieldSynchronizer.sync_all({"organizations": [{"id": 1, "name": "研发部"}, {"id": 2, "name": "运维部"}]})

    assert out["organizations"] == 1
    assert len(fake.updates) == 1
    label, ids, data = fake.updates[0]
    assert label == "instance"
    assert ids == [10]
    # 多值组织以 ", " 连接，顺序与实例字段一致
    assert data["org_display"] == "研发部, 运维部"


def test_sync_all_org_no_intersection_skips(monkeypatch):
    # 实例组织 [3]，变更只涉及 [1] → 无交集，不更新
    fake = _install_graph(monkeypatch, [{"_id": 10, "model_id": "host", "org": [3]}])
    _install_mapping(monkeypatch, {"host": {"organization": ["org"]}})

    out = DisplayFieldSynchronizer.sync_all({"organizations": [{"id": 1, "name": "研发部"}]})
    assert out["organizations"] == 0
    assert fake.updates == []


def test_sync_all_org_missing_id_falls_back_to_db(monkeypatch):
    # 实例组织 [1, 9]，变更只含 1；9 不在 map 里 → 走 Group DB 兜底
    fake = _install_graph(monkeypatch, [{"_id": 10, "model_id": "host", "org": [1, 9]}])
    _install_mapping(monkeypatch, {"host": {"organization": ["org"]}})

    class _QS:
        def filter(self, **kw):
            assert kw == {"id__in": [9]}
            return self

        def values_list(self, *fields):
            assert fields == ("id", "name")
            return [(9, "历史部门")]

    monkeypatch.setattr(f"{MODULE}.Group.objects", _QS())

    out = DisplayFieldSynchronizer.sync_all({"organizations": [{"id": 1, "name": "研发部"}]})
    assert out["organizations"] == 1
    _, _, data = fake.updates[0]
    assert data["org_display"] == "研发部, 历史部门"


def test_sync_all_org_scalar_value_normalized_to_list(monkeypatch):
    # 实例组织为标量 1（非列表）→ 内部归一化为列表后仍能匹配
    fake = _install_graph(monkeypatch, [{"_id": 11, "model_id": "host", "org": 1}])
    _install_mapping(monkeypatch, {"host": {"organization": ["org"]}})

    out = DisplayFieldSynchronizer.sync_all({"organizations": [{"id": 1, "name": "研发部"}]})
    assert out["organizations"] == 1
    _, _, data = fake.updates[0]
    assert data["org_display"] == "研发部"


# --------------------------------------------------------------------------
# sync_all：用户字段重建
# --------------------------------------------------------------------------


def test_sync_all_rebuilds_user_display_with_display_name(monkeypatch):
    fake = _install_graph(monkeypatch, [{"_id": 20, "model_id": "host", "owner": [1]}])
    _install_mapping(monkeypatch, {"host": {"organization": [], "user": ["owner"]}})

    out = DisplayFieldSynchronizer.sync_all({"users": [{"id": 1, "username": "admin", "display_name": "超级管理员"}]})
    assert out["users"] == 1
    _, ids, data = fake.updates[0]
    assert ids == [20]
    # 有 display_name → "display_name(username)"
    assert data["owner_display"] == "超级管理员(admin)"


def test_sync_all_user_without_display_name_uses_username(monkeypatch):
    fake = _install_graph(monkeypatch, [{"_id": 21, "model_id": "host", "owner": 1}])
    _install_mapping(monkeypatch, {"host": {"user": ["owner"]}})

    out = DisplayFieldSynchronizer.sync_all({"users": [{"id": 1, "username": "alice", "display_name": ""}]})
    assert out["users"] == 1
    _, _, data = fake.updates[0]
    assert data["owner_display"] == "alice"


def test_sync_all_user_missing_id_falls_back_to_db(monkeypatch):
    fake = _install_graph(monkeypatch, [{"_id": 22, "model_id": "host", "owner": [1, 8]}])
    _install_mapping(monkeypatch, {"host": {"user": ["owner"]}})

    class _QS:
        def filter(self, **kw):
            assert kw == {"id__in": [8]}
            return self

        def values(self, *fields):
            assert fields == ("id", "username", "display_name")
            return [{"id": 8, "username": "bob", "display_name": "鲍勃"}]

    monkeypatch.setattr(f"{MODULE}.User.objects", _QS())

    out = DisplayFieldSynchronizer.sync_all({"users": [{"id": 1, "username": "admin", "display_name": "管理员"}]})
    assert out["users"] == 1
    _, _, data = fake.updates[0]
    assert data["owner_display"] == "管理员(admin), 鲍勃(bob)"


def test_sync_all_user_no_intersection_skips(monkeypatch):
    fake = _install_graph(monkeypatch, [{"_id": 23, "model_id": "host", "owner": [5]}])
    _install_mapping(monkeypatch, {"host": {"user": ["owner"]}})

    out = DisplayFieldSynchronizer.sync_all({"users": [{"id": 1, "username": "admin", "display_name": "x"}]})
    assert out["users"] == 0
    assert fake.updates == []


# --------------------------------------------------------------------------
# sync_all：组织 + 用户同实例同时更新
# --------------------------------------------------------------------------


def test_sync_all_both_org_and_user_single_instance(monkeypatch):
    fake = _install_graph(
        monkeypatch,
        [{"_id": 30, "model_id": "host", "org": [1], "owner": [1]}],
    )
    _install_mapping(monkeypatch, {"host": {"organization": ["org"], "user": ["owner"]}})

    out = DisplayFieldSynchronizer.sync_all(
        {
            "organizations": [{"id": 1, "name": "研发部"}],
            "users": [{"id": 1, "username": "admin", "display_name": "管理员"}],
        }
    )
    # 同一实例同时计入组织与用户更新计数
    assert out == {"organizations": 1, "users": 1}
    assert len(fake.updates) == 1  # 一次 batch_update 合并两个 _display
    _, _, data = fake.updates[0]
    assert data["org_display"] == "研发部"
    assert data["owner_display"] == "管理员(admin)"


def test_sync_all_pages_by_graph_id_and_batches_field_writes(monkeypatch):
    monkeypatch.setenv("CMDB_DISPLAY_SYNC_BATCH_SIZE", "2")
    fake = _install_graph(
        monkeypatch,
        [{"_id": node_id, "model_id": "host", "org": [1]} for node_id in range(1, 6)],
    )
    _install_mapping(monkeypatch, {"host": {"organization": ["org"], "user": []}})

    out = DisplayFieldSynchronizer.sync_all({"organizations": [{"id": 1, "name": "研发部"}]})

    assert out == {"organizations": 5, "users": 0}
    assert [call["params"] for call in fake.query_calls] == [
        [{"field": "model_id", "type": "str[]", "value": ["host"]}],
        [
            {"field": "model_id", "type": "str[]", "value": ["host"]},
            {"field": "id", "type": "id>", "value": 2},
        ],
        [
            {"field": "model_id", "type": "str[]", "value": ["host"]},
            {"field": "id", "type": "id>", "value": 4},
        ],
        [
            {"field": "model_id", "type": "str[]", "value": ["host"]},
            {"field": "id", "type": "id>", "value": 5},
        ],
    ]
    assert all(call["page"] == {"skip": 0, "limit": 2} for call in fake.query_calls)
    assert all(call["include_count"] is False for call in fake.query_calls)
    assert [len(values) for _, field, values in fake.property_updates if field == "org_display"] == [2, 2, 1]
    assert fake.legacy_updates == []


def test_sync_all_clamps_batch_size_to_graph_write_limit(monkeypatch):
    monkeypatch.setenv("CMDB_DISPLAY_SYNC_BATCH_SIZE", "5000")
    fake = _install_graph(monkeypatch, [{"_id": 1, "model_id": "host", "org": [1]}])
    _install_mapping(monkeypatch, {"host": {"organization": ["org"], "user": []}})

    DisplayFieldSynchronizer.sync_all({"organizations": [{"id": 1, "name": "研发部"}]})

    assert fake.query_calls[0]["page"] == {"skip": 0, "limit": 1000}


@pytest.mark.parametrize(
    ("configured_value", "expected_limit"),
    [("invalid", 500), ("0", 1), ("-10", 1)],
)
def test_sync_all_uses_bounded_batch_size_for_invalid_and_non_positive_config(
    monkeypatch,
    configured_value,
    expected_limit,
):
    monkeypatch.setenv("CMDB_DISPLAY_SYNC_BATCH_SIZE", configured_value)
    fake = _install_graph(monkeypatch, [{"_id": 1, "model_id": "host", "org": [1]}])
    _install_mapping(monkeypatch, {"host": {"organization": ["org"], "user": []}})

    DisplayFieldSynchronizer.sync_all({"organizations": [{"id": 1, "name": "研发部"}]})

    assert fake.query_calls[0]["page"] == {"skip": 0, "limit": expected_limit}


def test_sync_all_prefetches_missing_references_once_per_page(monkeypatch):
    monkeypatch.setenv("CMDB_DISPLAY_SYNC_BATCH_SIZE", "10")
    fake = _install_graph(
        monkeypatch,
        [
            {"_id": 41, "model_id": "host", "org": [1, 9], "owner": [1, 8]},
            {"_id": 42, "model_id": "host", "org": [1, 9], "owner": [1, 8]},
        ],
    )
    _install_mapping(monkeypatch, {"host": {"organization": ["org"], "user": ["owner"]}})

    class _GroupQS:
        filter_calls = []

        def filter(self, **kwargs):
            self.filter_calls.append(kwargs)
            return self

        def values_list(self, *fields):
            assert fields == ("id", "name")
            return [(9, "历史部门")]

    class _UserQS:
        filter_calls = []

        def filter(self, **kwargs):
            self.filter_calls.append(kwargs)
            return self

        def values(self, *fields):
            assert fields == ("id", "username", "display_name")
            return [{"id": 8, "username": "bob", "display_name": "鲍勃"}]

    group_qs = _GroupQS()
    user_qs = _UserQS()
    monkeypatch.setattr(f"{MODULE}.Group.objects", group_qs)
    monkeypatch.setattr(f"{MODULE}.User.objects", user_qs)

    out = DisplayFieldSynchronizer.sync_all(
        {
            "organizations": [{"id": 1, "name": "研发部"}],
            "users": [{"id": 1, "username": "admin", "display_name": "管理员"}],
        }
    )

    assert out == {"organizations": 2, "users": 2}
    assert group_qs.filter_calls == [{"id__in": [9]}]
    assert user_qs.filter_calls == [{"id__in": [8]}]
    assert all(data == {"org_display": "研发部, 历史部门", "owner_display": "管理员(admin), 鲍勃(bob)"} for _, _, data in fake.updates)


def test_sync_all_preserves_reference_order_across_changed_and_fallback_values(monkeypatch):
    fake = _install_graph(
        monkeypatch,
        [{"_id": 43, "model_id": "host", "org": [9, 1], "owner": [8, 1]}],
    )
    _install_mapping(monkeypatch, {"host": {"organization": ["org"], "user": ["owner"]}})

    class _GroupQS:
        def filter(self, **kwargs):
            assert kwargs == {"id__in": [9]}
            return self

        def values_list(self, *fields):
            assert fields == ("id", "name")
            return [(9, "历史部门")]

    class _UserQS:
        def filter(self, **kwargs):
            assert kwargs == {"id__in": [8]}
            return self

        def values(self, *fields):
            assert fields == ("id", "username", "display_name")
            return [{"id": 8, "username": "bob", "display_name": "鲍勃"}]

    monkeypatch.setattr(f"{MODULE}.Group.objects", _GroupQS())
    monkeypatch.setattr(f"{MODULE}.User.objects", _UserQS())

    out = DisplayFieldSynchronizer.sync_all(
        {
            "organizations": [{"id": 1, "name": "研发部"}],
            "users": [{"id": 1, "username": "admin", "display_name": "管理员"}],
        }
    )

    assert out == {"organizations": 1, "users": 1}
    assert fake.updates[0][2] == {
        "org_display": "历史部门, 研发部",
        "owner_display": "鲍勃(bob), 管理员(admin)",
    }


def test_sync_all_exact_page_boundary_reads_empty_terminal_page(monkeypatch):
    monkeypatch.setenv("CMDB_DISPLAY_SYNC_BATCH_SIZE", "2")
    fake = _install_graph(
        monkeypatch,
        [{"_id": node_id, "model_id": "host", "org": [1]} for node_id in range(1, 5)],
    )
    _install_mapping(monkeypatch, {"host": {"organization": ["org"], "user": []}})

    out = DisplayFieldSynchronizer.sync_all({"organizations": [{"id": 1, "name": "研发部"}]})

    assert out == {"organizations": 4, "users": 0}
    assert len(fake.query_calls) == 3
    assert fake.query_calls[-1]["params"][-1] == {"field": "id", "type": "id>", "value": 4}
    assert [len(values) for _, _, values in fake.property_updates] == [2, 2]


def test_sync_all_continues_after_short_page_until_empty(monkeypatch):
    class _ShortPageGraph(_FakeGraph):
        def __init__(self):
            super().__init__([])
            self._pages = [
                [{"_id": 1, "model_id": "host", "org": [1]}],
                [{"_id": 3, "model_id": "host", "org": [1]}],
                [],
            ]

        def query_entity(self, label, params, page=None, include_count=True):
            self.query_calls.append({"label": label, "params": list(params), "page": dict(page), "include_count": include_count})
            return self._pages.pop(0), None

    fake = _ShortPageGraph()
    monkeypatch.setattr(f"{MODULE}.GraphClient", lambda *args, **kwargs: fake)
    monkeypatch.setenv("CMDB_DISPLAY_SYNC_BATCH_SIZE", "2")
    _install_mapping(monkeypatch, {"host": {"organization": ["org"], "user": []}})

    out = DisplayFieldSynchronizer.sync_all({"organizations": [{"id": 1, "name": "研发部"}]})

    assert out == {"organizations": 2, "users": 0}
    assert len(fake.query_calls) == 3
    assert [call["params"][-1] for call in fake.query_calls[1:]] == [
        {"field": "id", "type": "id>", "value": 1},
        {"field": "id", "type": "id>", "value": 3},
    ]


def test_sync_all_partial_field_failure_is_safe_to_rerun(monkeypatch):
    class _FailOnceGraph(_FakeGraph):
        def __init__(self):
            super().__init__([{"_id": 44, "model_id": "host", "org": [1], "owner": [1]}])
            self._failed = False

        def batch_update_node_property_values(self, label, field, property_values):
            if field == "owner_display" and not self._failed:
                self._failed = True
                raise RuntimeError("temporary graph failure")
            return super().batch_update_node_property_values(label, field, property_values)

    fake = _FailOnceGraph()
    monkeypatch.setattr(f"{MODULE}.GraphClient", lambda *args, **kwargs: fake)
    _install_mapping(monkeypatch, {"host": {"organization": ["org"], "user": ["owner"]}})
    data = {
        "organizations": [{"id": 1, "name": "研发部"}],
        "users": [{"id": 1, "username": "admin", "display_name": "管理员"}],
    }

    with pytest.raises(RuntimeError, match="temporary graph failure"):
        DisplayFieldSynchronizer.sync_all(data)
    out = DisplayFieldSynchronizer.sync_all(data)

    assert out == {"organizations": 1, "users": 1}
    assert fake.updates[-1][2] == {
        "org_display": "研发部",
        "owner_display": "管理员(admin)",
    }


# --------------------------------------------------------------------------
# sync_all：异常向上抛出
# --------------------------------------------------------------------------


def test_sync_all_reraises_on_graph_error(monkeypatch):
    class _Boom:
        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

        def query_entity(self, *a, **k):
            raise RuntimeError("graph down")

    monkeypatch.setattr(f"{MODULE}.GraphClient", lambda *a, **k: _Boom())
    _install_mapping(monkeypatch, {"host": {"organization": ["org"]}})

    with pytest.raises(RuntimeError):
        DisplayFieldSynchronizer.sync_all({"organizations": [{"id": 1, "name": "x"}]})


# --------------------------------------------------------------------------
# 便捷封装：sync_organization_display / sync_user_display
# --------------------------------------------------------------------------


def test_sync_organization_display_returns_org_count(monkeypatch):
    monkeypatch.setattr(
        DisplayFieldSynchronizer,
        "sync_all",
        staticmethod(lambda data: {"organizations": 7, "users": 0}),
    )
    assert DisplayFieldSynchronizer.sync_organization_display([{"id": 1, "name": "x"}]) == 7


def test_sync_user_display_returns_user_count(monkeypatch):
    monkeypatch.setattr(
        DisplayFieldSynchronizer,
        "sync_all",
        staticmethod(lambda data: {"organizations": 0, "users": 3}),
    )
    assert DisplayFieldSynchronizer.sync_user_display([{"id": 1, "username": "a"}]) == 3


# --------------------------------------------------------------------------
# 系统管理入口：sync_display_fields_for_system_mgmt
# --------------------------------------------------------------------------


def test_system_mgmt_entry_skips_when_empty():
    out = sync_display_fields_for_system_mgmt()
    assert out == {"task_id": None, "status": "skipped"}


def test_system_mgmt_entry_submits_celery_task(monkeypatch):
    captured = {}

    class _Task:
        id = "task-uuid-123"

    def _delay(data):
        captured["data"] = data
        return _Task()

    import apps.cmdb.tasks.celery_tasks as celery_tasks

    monkeypatch.setattr(celery_tasks.sync_cmdb_display_fields_task, "delay", _delay)

    out = sync_display_fields_for_system_mgmt(
        organizations=[{"id": 1, "name": "研发部"}],
        users=[{"id": 1, "username": "admin", "display_name": "管理员"}],
    )
    assert out == {"task_id": "task-uuid-123", "status": "submitted"}
    # 入参契约：组织/用户都被透传给异步任务
    assert captured["data"]["organizations"] == [{"id": 1, "name": "研发部"}]
    assert captured["data"]["users"][0]["username"] == "admin"
