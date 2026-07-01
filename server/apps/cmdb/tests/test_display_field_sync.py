# -*- coding: utf-8 -*-
"""DisplayFieldSynchronizer 同步链路测试。

对照 spec/CMDB·资产：组织/用户展示信息变更时，重建实例 _display 冗余字段。
只 mock 真实外部边界（GraphClient 图库、ExcludeFieldsCache 缓存、Group/User DB、Celery），
断言真实的 _display 重建值、batch_update 入参契约与各类早返回分支。
"""
import pytest

from apps.cmdb.display_field.sync import (
    DisplayFieldSynchronizer,
    sync_display_fields_for_system_mgmt,
)

MODULE = "apps.cmdb.display_field.sync"


class _FakeGraph:
    """记录 batch_update_node_properties 调用并按预置实例驱动 sync_all。"""

    def __init__(self, instances):
        self._instances = instances
        self.updates = []  # list of (label, ids, data)

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False

    def query_entity(self, label, params):
        return list(self._instances), len(self._instances)

    def batch_update_node_properties(self, label, ids, data):
        self.updates.append((label, list(ids), dict(data)))
        return {}


def _install_graph(monkeypatch, instances):
    fake = _FakeGraph(instances)
    monkeypatch.setattr(f"{MODULE}.GraphClient", lambda *a, **k: fake)
    return fake


def _install_mapping(monkeypatch, mapping):
    monkeypatch.setattr(
        "apps.cmdb.display_field.cache.ExcludeFieldsCache.get_model_fields_mapping",
        classmethod(lambda cls: mapping),
    )


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

    out = DisplayFieldSynchronizer.sync_all(
        {"organizations": [{"id": 1, "name": "研发部"}, {"id": 2, "name": "运维部"}]}
    )

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

        def values_list(self, field, flat=False):
            return ["历史部门"]

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

    out = DisplayFieldSynchronizer.sync_all(
        {"users": [{"id": 1, "username": "admin", "display_name": "超级管理员"}]}
    )
    assert out["users"] == 1
    _, ids, data = fake.updates[0]
    assert ids == [20]
    # 有 display_name → "display_name(username)"
    assert data["owner_display"] == "超级管理员(admin)"


def test_sync_all_user_without_display_name_uses_username(monkeypatch):
    fake = _install_graph(monkeypatch, [{"_id": 21, "model_id": "host", "owner": 1}])
    _install_mapping(monkeypatch, {"host": {"user": ["owner"]}})

    out = DisplayFieldSynchronizer.sync_all(
        {"users": [{"id": 1, "username": "alice", "display_name": ""}]}
    )
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
            return [{"username": "bob", "display_name": "鲍勃"}]

    monkeypatch.setattr(f"{MODULE}.User.objects", _QS())

    out = DisplayFieldSynchronizer.sync_all(
        {"users": [{"id": 1, "username": "admin", "display_name": "管理员"}]}
    )
    assert out["users"] == 1
    _, _, data = fake.updates[0]
    assert data["owner_display"] == "管理员(admin), 鲍勃(bob)"


def test_sync_all_user_no_intersection_skips(monkeypatch):
    fake = _install_graph(monkeypatch, [{"_id": 23, "model_id": "host", "owner": [5]}])
    _install_mapping(monkeypatch, {"host": {"user": ["owner"]}})

    out = DisplayFieldSynchronizer.sync_all(
        {"users": [{"id": 1, "username": "admin", "display_name": "x"}]}
    )
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
