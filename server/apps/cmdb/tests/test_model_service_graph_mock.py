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
