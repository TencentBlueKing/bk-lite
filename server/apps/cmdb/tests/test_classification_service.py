"""CMDB 模型分类服务覆盖测试（fake_graph 桩 GraphClient）。

对照 specs/capabilities/legacy-prd-cmdb-模型管理.md：模型分类增删改查、是否被模型引用校验、多语言名称。
"""

import pytest

from apps.cmdb.constants.constants import CLASSIFICATION, MODEL
from apps.cmdb.services.classification import ClassificationManage
from apps.core.exceptions.base_app_exception import BaseAppException

MODULE = "apps.cmdb.services.classification"


@pytest.mark.django_db
def test_create_model_classification(fake_graph):
    fg = fake_graph(MODULE, query_entity=([], 0), create_entity={"classification_id": "net", "_id": 1})
    result = ClassificationManage.create_model_classification({"classification_id": "net", "classification_name": "网络"})
    assert result["classification_id"] == "net"
    assert any(c[0] == "create_entity" for c in fg.calls)


@pytest.mark.django_db
def test_search_classification_info_found(fake_graph):
    fake_graph(MODULE, query_entity=([{"_id": 1, "classification_id": "net"}], 1))
    result = ClassificationManage.search_model_classification_info("net")
    assert result["classification_id"] == "net"


@pytest.mark.django_db
def test_search_classification_info_missing(fake_graph):
    fake_graph(MODULE, query_entity=([], 0))
    assert ClassificationManage.search_model_classification_info("net") == {}


@pytest.mark.django_db
def test_check_classification_is_used_raises(fake_graph):
    fake_graph(MODULE, query_entity=([], 3))  # model_count=3 > 0
    with pytest.raises(BaseAppException):
        ClassificationManage.check_classification_is_used("net")


@pytest.mark.django_db
def test_check_classification_not_used(fake_graph):
    fake_graph(MODULE, query_entity=([], 0))
    # count=0 → 不抛异常，返回 None
    assert ClassificationManage.check_classification_is_used("net") is None


@pytest.mark.django_db
def test_delete_model_classification(fake_graph):
    fg = fake_graph(MODULE)
    ClassificationManage.delete_model_classification(12)
    assert any(c[0] == "batch_delete_entity" for c in fg.calls)


@pytest.mark.django_db
def test_update_model_classification(fake_graph):
    fg = fake_graph(
        MODULE,
        query_entity=([{"_id": 99}], 1),  # exist_items（会排除自身 id=12）
        set_entity_properties=[{"_id": 12, "classification_name": "网络2"}],
    )
    result = ClassificationManage.update_model_classification(
        12, {"classification_name": "网络2", "classification_id": "willpop", "exist_model": True}
    )
    assert result["classification_name"] == "网络2"
    # 校验 set_entity_properties 调用时已弹出 classification_id/exist_model
    call = next(c for c in fg.calls if c[0] == "set_entity_properties")
    assert "classification_id" not in call[1][2]
    assert "exist_model" not in call[1][2]


@pytest.mark.django_db
def test_search_model_classification(fake_graph):
    classifications = [
        {"classification_id": "net", "classification_name": "网络"},
        {"classification_id": "host", "classification_name": "主机"},
    ]
    models = [{"classification_id": "net"}]

    def _query(label, params, **kwargs):
        return (classifications, len(classifications)) if label == CLASSIFICATION else (models, len(models))

    fake_graph(MODULE, query_entity=_query)
    result = ClassificationManage.search_model_classification("zh-Hans")
    by_id = {c["classification_id"]: c for c in result}
    assert by_id["net"]["exist_model"] is True
    assert by_id["host"]["exist_model"] is False
