"""ModelManage 属性创建/更新/查询：GraphClient 边界 mock，钉死校验与回写。"""
from unittest.mock import MagicMock, patch

import pytest

from apps.cmdb.services.model import ModelManage
from apps.core.exceptions.base_app_exception import BaseAppException

pytestmark = pytest.mark.unit


class _Graph:
    def __init__(self, models=None, attrs="[]"):
        self.models = models if models is not None else [{"_id": 11, "model_id": "host", "model_name": "主机", "attrs": attrs}]
        self.last_attrs = None

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False

    def query_entity(self, *a, **k):
        return self.models, len(self.models)

    def set_entity_properties(self, *args, **kwargs):
        payload = args[2] if len(args) > 2 else kwargs.get("data") or {}
        self.last_attrs = payload.get("attrs")
        return [{"attrs": self.last_attrs or "[]"}]

    def batch_delete_entity(self, *a, **k):
        return None


def test_create_model_attr_missing_model_and_duplicate():
    with patch("apps.cmdb.services.model.GraphClient", return_value=_Graph(models=[])):
        with pytest.raises(BaseAppException, match="model not present"):
            ModelManage.create_model_attr("host", {"attr_id": "cpu", "attr_type": "str", "attr_name": "CPU"})

    existing = '[{"attr_id":"cpu","attr_type":"str"}]'
    with patch("apps.cmdb.services.model.GraphClient", return_value=_Graph(attrs=existing)):
        with pytest.raises(BaseAppException, match="model attr repetition"):
            ModelManage.create_model_attr("host", {"attr_id": "cpu", "attr_type": "str", "attr_name": "CPU"})


def test_create_model_attr_writes_attr_and_change_record(monkeypatch):
    graph = _Graph()
    records = []
    monkeypatch.setattr(
        "apps.cmdb.services.model.create_change_record",
        lambda **kw: records.append(kw),
    )
    monkeypatch.setattr(
        "apps.cmdb.display_field.ExcludeFieldsCache.update_on_model_change",
        lambda model_id: None,
    )
    with patch("apps.cmdb.services.model.GraphClient", return_value=graph):
        attr = ModelManage.create_model_attr(
            "host",
            {
                "attr_id": "cpu",
                "attr_type": "str",
                "attr_name": "CPU",
                "attr_group": "default",
                "is_required": False,
                "editable": True,
                "option": [],
                "user_prompt": "",
            },
            username="alice",
        )
    assert attr["attr_id"] == "cpu"
    assert '"cpu"' in (graph.last_attrs or "")
    assert records[0]["operator"] == "alice"
    assert records[0]["_type"]
    assert "创建模型属性" in records[0]["message"]


def test_create_model_attr_tag_and_enum_public_library(monkeypatch):
    graph = _Graph()
    monkeypatch.setattr("apps.cmdb.services.model.create_change_record", lambda **kw: None)
    monkeypatch.setattr(
        "apps.cmdb.display_field.ExcludeFieldsCache.update_on_model_change",
        lambda model_id: None,
    )
    monkeypatch.setattr(
        "apps.cmdb.services.public_enum_library.get_library_or_raise",
        lambda lid: type("Lib", (), {"options": [{"id": "on", "name": "开"}]})(),
    )
    with patch("apps.cmdb.services.model.GraphClient", return_value=graph):
        tag = ModelManage.create_model_attr(
            "host",
            {"attr_id": "tag", "attr_type": "tag", "attr_name": "标签", "attr_group": "g", "option": {}},
        )
    assert tag["attr_id"] == "tag"
    assert tag["editable"] is True

    graph2 = _Graph()
    with patch("apps.cmdb.services.model.GraphClient", return_value=graph2):
        enum_attr = ModelManage.create_model_attr(
            "host",
            {
                "attr_id": "status",
                "attr_type": "enum",
                "attr_name": "状态",
                "attr_group": "g",
                "option": {
                    "enum_rule_type": "public_library",
                    "public_library_id": 3,
                    "option": [],
                },
            },
        )
    assert enum_attr["option"] == [{"id": "on", "name": "开"}]
    assert enum_attr["enum_rule_type"] == "public_library"


def test_update_model_attr_missing_and_protected():
    with pytest.raises(BaseAppException):
        ModelManage.update_model_attr("host", {"attr_id": "organization", "attr_type": "str"})
    with patch("apps.cmdb.services.model.GraphClient", return_value=_Graph(models=[])):
        with pytest.raises(BaseAppException, match="model not present"):
            ModelManage.update_model_attr("host", {"attr_id": "cpu", "attr_type": "str"})
    with patch("apps.cmdb.services.model.GraphClient", return_value=_Graph(attrs="[]")):
        with pytest.raises(BaseAppException, match="model attr not present"):
            ModelManage.update_model_attr("host", {"attr_id": "cpu", "attr_type": "str"})


def test_update_model_attr_writes_fields(monkeypatch):
    attrs = (
        '[{"attr_id":"cpu","attr_type":"str","attr_group":"old","attr_name":"旧",' '"is_required":false,"editable":true,"option":[],"user_prompt":""}]'
    )
    graph = _Graph(attrs=attrs)
    monkeypatch.setattr("apps.cmdb.services.model.create_change_record", lambda **kw: None)
    monkeypatch.setattr(
        "apps.cmdb.display_field.ExcludeFieldsCache.update_on_model_change",
        lambda model_id: None,
    )
    with patch("apps.cmdb.services.model.GraphClient", return_value=graph):
        out = ModelManage.update_model_attr(
            "host",
            {
                "attr_id": "cpu",
                "attr_type": "str",
                "attr_group": "new",
                "attr_name": "CPU核数",
                "is_required": True,
                "editable": False,
                "option": [],
                "user_prompt": "hint",
            },
        )
    assert out["attr_name"] == "CPU核数"
    assert out["attr_group"] == "new"
    assert out["is_required"] is True


def test_search_model_filters_hidden_and_permissions(monkeypatch):
    models = [
        {"model_id": "host", "model_name": "Host", "is_visible": True, "order_id": 1},
        {"model_id": "hidden", "model_name": "Hidden", "is_visible": False},
        {"model_id": "bare", "model_name": "Bare"},
    ]

    class _SearchGraph(_Graph):
        def query_entity(self, **query):
            perm = query["format_permission_dict"]
            org_key = next(iter(perm))
            assert perm[org_key][0]["field"] == "classification_id"
            assert perm[org_key][1]["value"] == ["host"]
            return models, 3

    monkeypatch.setattr(
        "apps.cmdb.services.model.SettingLanguage",
        lambda language: type("L", (), {"get_val": staticmethod(lambda *a, **k: None)})(),
    )
    with patch("apps.cmdb.services.model.GraphClient", return_value=_SearchGraph()):
        visible = ModelManage.search_model(
            language="zh-CN",
            classification_ids=["host_class"],
            permissions_map={"1": {"inst_names": ["host"]}},
            creator="alice",
        )
    ids = {m["model_id"] for m in visible}
    assert "hidden" not in ids
    assert "host" in ids
    assert "bare" in ids
    bare = next(m for m in visible if m["model_id"] == "bare")
    assert bare["is_visible"] is True
    assert bare["order_id"] == 0

    with patch("apps.cmdb.services.model.GraphClient", return_value=_SearchGraph()):
        all_models = ModelManage.search_model(
            include_hidden=True,
            classification_ids=["host_class"],
            permissions_map={"1": {"inst_names": ["host"]}},
            creator="alice",
        )
    assert {m["model_id"] for m in all_models} == {"host", "hidden", "bare"}


def test_delete_model_calls_batch_delete():
    graph = _Graph()
    graph.batch_delete_entity = MagicMock()
    with patch("apps.cmdb.services.model.GraphClient", return_value=graph):
        ModelManage.delete_model(99)
    graph.batch_delete_entity.assert_called_once_with("model", [99])
