"""CMDB ModelManage 图查询后处理覆盖测试（mock GraphClient）。

对照 spec/prd/CMDB·模型管理：模型查询结果做名称国际化、属性默认值归一等后处理。
"""

import json

import pytest


class FakeGraph:
    """模拟 GraphClient 上下文管理器，query_entity 返回预置数据。"""

    def __init__(self, entities=None):
        self._entities = entities or []

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False

    def query_entity(self, *args, **kwargs):
        return list(self._entities), len(self._entities)


@pytest.fixture
def patch_graph(monkeypatch):
    def _patch(entities):
        monkeypatch.setattr(
            "apps.cmdb.services.model.GraphClient",
            lambda *a, **k: FakeGraph(entities),
        )
    return _patch


# --------------------------------------------------------------------------
# search_model
# --------------------------------------------------------------------------


@pytest.mark.django_db
def test_search_model_postprocess(patch_graph):
    from apps.cmdb.services.model import ModelManage

    patch_graph([
        {"model_id": "host", "model_name": "主机", "_id": 1},
        {"model_id": "switch", "model_name": "交换机", "_id": 2},
    ])
    models = ModelManage.search_model()
    assert len(models) == 2
    # 后处理补充 order_id
    assert all("order_id" in m for m in models)


@pytest.mark.django_db
def test_search_model_info_found(patch_graph):
    from apps.cmdb.services.model import ModelManage

    patch_graph([{"model_id": "host", "model_name": "主机", "_id": 1}])
    info = ModelManage.search_model_info("host")
    assert info["model_id"] == "host"


@pytest.mark.django_db
def test_search_model_info_not_found(patch_graph):
    from apps.cmdb.services.model import ModelManage

    patch_graph([])
    assert ModelManage.search_model_info("missing") == {}


# --------------------------------------------------------------------------
# search_model_attr
# --------------------------------------------------------------------------


@pytest.mark.django_db
def test_search_model_attr_normalizes(patch_graph):
    from apps.cmdb.services.model import ModelManage

    attrs = [{"attr_id": "name", "attr_name": "名称", "attr_type": "str"}]
    patch_graph([{"model_id": "host", "model_name": "主机", "_id": 1, "attrs": json.dumps(attrs)}])
    result = ModelManage.search_model_attr("host")
    # 归一后补充默认约束字段
    item = next(a for a in result if a["attr_id"] == "name")
    assert "is_required" in item
    assert item["default_value"] == []


# --------------------------------------------------------------------------
# delete_model / update_model（FakeGraphClient via fake_graph fixture）
# --------------------------------------------------------------------------


@pytest.mark.django_db
def test_delete_model(fake_graph):
    from apps.cmdb.services.model import ModelManage

    fake = fake_graph("apps.cmdb.services.model")
    ModelManage.delete_model(5)
    # batch_delete_entity 被调用
    assert any(call[0] == "batch_delete_entity" for call in fake.calls)


@pytest.mark.django_db
def test_update_model(fake_graph):
    from apps.cmdb.services.model import ModelManage

    fake = fake_graph(
        "apps.cmdb.services.model",
        query_entity=([{"model_id": "other", "_id": 99}], 1),
        set_entity_properties=[{"model_id": "host", "_id": 5, "model_name": "新主机"}],
    )
    out = ModelManage.update_model(5, {"model_id": "host", "model_name": "新主机"})
    assert out["model_name"] == "新主机"
    assert any(call[0] == "set_entity_properties" for call in fake.calls)


@pytest.mark.django_db
def test_create_model_attr(fake_graph, monkeypatch):
    from apps.cmdb.services import model as model_mod
    from apps.cmdb.services.model import ModelManage

    new_attr = {"attr_id": "ip", "attr_name": "IP", "attr_type": "str"}
    updated_attrs = json.dumps([
        {"attr_id": "name", "attr_name": "名称", "attr_type": "str"},
        new_attr,
    ])
    fake_graph(
        "apps.cmdb.services.model",
        query_entity=([{"model_id": "host", "model_name": "主机", "_id": 1,
                        "attrs": json.dumps([{"attr_id": "name", "attr_name": "名称", "attr_type": "str"}])}], 1),
        set_entity_properties=[{"_id": 1, "attrs": updated_attrs}],
    )
    # 屏蔽缓存刷新与变更记录（避免图/DB 依赖）
    monkeypatch.setattr("apps.cmdb.display_field.ExcludeFieldsCache.update_on_model_change", lambda model_id: None)
    monkeypatch.setattr(model_mod, "create_change_record", lambda **kw: None)

    result = ModelManage.create_model_attr("host", dict(new_attr), username="admin")
    assert result["attr_id"] == "ip"


@pytest.mark.django_db
def test_create_model_attr_audit_log_uses_correct_attr(fake_graph, monkeypatch):
    """回归 #3663：循环内 attr=attr 自赋值缺 break，变更日志属性张冠李戴。

    当 attrs 有多个元素且目标属性不在最后时，enterprise_ext.build_attr_change_message
    收到的应是目标属性（ip），而非列表末尾的属性（zzz_last）。
    若修复被 revert（去掉 break），此测试必定失败。
    """
    from apps.cmdb.services import model as model_mod
    from apps.cmdb.services.model import ModelManage

    target_attr = {"attr_id": "ip", "attr_name": "IP", "attr_type": "str"}
    decoy_attr = {"attr_id": "zzz_last", "attr_name": "末位属性", "attr_type": "str"}
    # 保存后 attrs 中 target 在中间，decoy 在末尾
    updated_attrs = json.dumps([
        {"attr_id": "name", "attr_name": "名称", "attr_type": "str"},
        target_attr,
        decoy_attr,
    ])
    fake_graph(
        "apps.cmdb.services.model",
        query_entity=([{"model_id": "host", "model_name": "主机", "_id": 1,
                        "attrs": json.dumps([
                            {"attr_id": "name", "attr_name": "名称", "attr_type": "str"},
                            decoy_attr,
                        ])}], 1),
        set_entity_properties=[{"_id": 1, "attrs": updated_attrs}],
    )
    monkeypatch.setattr("apps.cmdb.display_field.ExcludeFieldsCache.update_on_model_change", lambda model_id: None)
    monkeypatch.setattr(model_mod, "create_change_record", lambda **kw: None)

    captured = {}

    class FakeExt:
        def validate_attr(self, attr_info):
            return attr_info

        def build_attr_change_message(self, old, new_attr):
            captured["attr_id"] = new_attr.get("attr_id")
            return ""

    monkeypatch.setattr(model_mod, "get_model_enterprise_extension", lambda: FakeExt())

    ModelManage.create_model_attr("host", dict(target_attr), username="admin")

    # 修复前（无 break）：attr 总是 decoy_attr（列表最后一项），captured["attr_id"] == "zzz_last"
    # 修复后（有 break）：attr 是 target_attr，captured["attr_id"] == "ip"
    assert captured.get("attr_id") == "ip", (
        f"变更日志应使用目标属性 ip，实际使用了 {captured.get('attr_id')!r}（#3663 回归）"
    )


@pytest.mark.django_db
def test_create_model_attr_model_missing(fake_graph):
    from apps.cmdb.services.model import ModelManage
    from apps.core.exceptions.base_app_exception import BaseAppException

    fake_graph("apps.cmdb.services.model", query_entity=([], 0))
    with pytest.raises(BaseAppException):
        ModelManage.create_model_attr("nope", {"attr_id": "ip", "attr_name": "IP", "attr_type": "str"})


@pytest.mark.django_db
def test_create_model_attr_duplicate(fake_graph):
    from apps.cmdb.services.model import ModelManage
    from apps.core.exceptions.base_app_exception import BaseAppException

    existing = json.dumps([{"attr_id": "ip", "attr_name": "IP", "attr_type": "str"}])
    fake_graph(
        "apps.cmdb.services.model",
        query_entity=([{"model_id": "host", "model_name": "主机", "_id": 1, "attrs": existing}], 1),
    )
    with pytest.raises(BaseAppException):
        ModelManage.create_model_attr("host", {"attr_id": "ip", "attr_name": "IP", "attr_type": "str"})


# --------------------------------------------------------------------------
# create_model — 定点查询唯一性校验（issue #3379）
# --------------------------------------------------------------------------


def _patch_create_model_side_effects(monkeypatch):
    """屏蔽 create_model 的图/DB 副作用（分类查询、字段分组、缓存、变更记录）。"""
    import apps.cmdb.services.model as model_mod

    monkeypatch.setattr(
        "apps.cmdb.services.classification.ClassificationManage.search_model_classification_info",
        lambda classification_id: {"_id": 99},
    )
    monkeypatch.setattr("apps.cmdb.display_field.ExcludeFieldsCache.update_on_model_change", lambda model_id: None)
    monkeypatch.setattr(model_mod, "create_change_record", lambda **kw: None)
    monkeypatch.setattr(model_mod.FIELD_GROUP_MANAGER, "create", lambda **kw: None)


@pytest.mark.django_db
def test_create_model_uses_targeted_conflict_query(fake_graph, monkeypatch):
    """create_model 必须用 model_id/model_name OR 条件查询，而非全量加载所有 MODEL 节点。

    验证点：query_entity 调用的 params 参数不为空列表。
    revert 修复后（params=[]）此断言失败，证明测试覆盖了修复点。
    """
    from apps.cmdb.services.model import ModelManage

    _patch_create_model_side_effects(monkeypatch)

    # create_entity 真实行为：回显已创建节点的全部属性（含 classification_id），
    # 后续 create_edge 会读取 result['classification_id'] / result['model_id']。
    fake = fake_graph(
        "apps.cmdb.services.model",
        create_entity={
            "model_id": "new_model",
            "model_name": "新模型",
            "classification_id": "infra",
            "_id": 10,
        },
        create_edge={},
    )

    data = {
        "model_id": "new_model",
        "model_name": "新模型",
        "classification_id": "infra",
    }
    ModelManage.create_model(data)

    # 找出 query_entity 调用
    qe_calls = [(args, kwargs) for name, args, kwargs in fake.calls if name == "query_entity"]
    assert qe_calls, "query_entity 未被调用"

    # 修复后第一个 query_entity 调用（唯一性校验）传入的 params 不应为空列表
    first_params = qe_calls[0][0][1] if len(qe_calls[0][0]) > 1 else qe_calls[0][1].get("params", [])
    assert first_params != [], (
        "create_model 仍在用全量查询（params=[]）；应改为定点过滤 model_id/model_name"
    )
    # 确认过滤条件包含 model_id 和 model_name 字段
    filtered_fields = {f["field"] for f in first_params}
    assert "model_id" in filtered_fields, "唯一性查询必须包含 model_id 过滤条件"
    assert "model_name" in filtered_fields, "唯一性查询必须包含 model_name 过滤条件"


@pytest.mark.django_db
def test_create_model_raises_on_duplicate_model_id(fake_graph, monkeypatch):
    """create_model 在 model_id 重复时必须抛出异常，即使只返回少量冲突候选节点。"""
    from apps.cmdb.services.model import ModelManage
    from apps.core.exceptions.base_app_exception import BaseAppException

    _patch_create_model_side_effects(monkeypatch)

    # create_entity 的真实唯一性校验委托给 FalkorDBClient.check_unique_attr：
    # 用真实逻辑判断冲突，避免在 fake 里重写恒真断言。
    def _create_entity_with_real_check(label, properties, check_attr_map, exist_items, *a, **k):
        from apps.cmdb.graph.falkordb import FalkorDBClient

        FalkorDBClient.check_unique_attr(properties, check_attr_map["is_only"], exist_items)
        return {**properties, "_id": 10}

    # 定点查询返回一个 model_id 相同的已有模型（模拟重复）
    fake_graph(
        "apps.cmdb.services.model",
        query_entity=(
            [{"model_id": "new_model", "model_name": "其他名称", "_id": 5}],
            1,
        ),
        create_entity=_create_entity_with_real_check,
    )

    data = {
        "model_id": "new_model",
        "model_name": "新模型",
        "classification_id": "infra",
    }
    with pytest.raises(BaseAppException):
        ModelManage.create_model(data)


@pytest.mark.django_db
def test_create_model_raises_on_duplicate_model_name(fake_graph, monkeypatch):
    """create_model 在 model_name 重复时必须抛出异常。"""
    from apps.cmdb.services.model import ModelManage
    from apps.core.exceptions.base_app_exception import BaseAppException

    _patch_create_model_side_effects(monkeypatch)

    def _create_entity_with_real_check(label, properties, check_attr_map, exist_items, *a, **k):
        from apps.cmdb.graph.falkordb import FalkorDBClient

        FalkorDBClient.check_unique_attr(properties, check_attr_map["is_only"], exist_items)
        return {**properties, "_id": 10}

    # 定点查询返回一个 model_name 相同的已有模型（模拟重复）
    fake_graph(
        "apps.cmdb.services.model",
        query_entity=(
            [{"model_id": "other_id", "model_name": "新模型", "_id": 6}],
            1,
        ),
        create_entity=_create_entity_with_real_check,
    )

    data = {
        "model_id": "new_model",
        "model_name": "新模型",
        "classification_id": "infra",
    }
    with pytest.raises(BaseAppException):
        ModelManage.create_model(data)
