"""CMDB CQL 参数验证器覆盖测试。

对照 specs/capabilities/legacy-prd-cmdb-资产.md：查询中不可参数化的标签/字段/关系名走白名单校验，防注入。
"""

import pytest

from apps.cmdb.graph.validators import CQLValidator
from apps.core.exceptions.base_app_exception import BaseAppException


# validate_id
def test_validate_id_ok():
    assert CQLValidator.validate_id("5") == 5
    assert CQLValidator.validate_id(5) == 5


def test_validate_id_negative():
    with pytest.raises(BaseAppException):
        CQLValidator.validate_id(-1)


def test_validate_id_non_numeric():
    with pytest.raises(BaseAppException):
        CQLValidator.validate_id("abc")


# validate_ids
def test_validate_ids_ok():
    assert CQLValidator.validate_ids([1, "2", 3]) == [1, 2, 3]


def test_validate_ids_not_list():
    with pytest.raises(BaseAppException):
        CQLValidator.validate_ids("123")


def test_validate_ids_empty():
    with pytest.raises(BaseAppException):
        CQLValidator.validate_ids([])


# validate_label
def test_validate_label_ok():
    assert CQLValidator.validate_label("host") == "host"
    assert CQLValidator.validate_label("主机") == "主机"


def test_validate_label_empty():
    with pytest.raises(BaseAppException):
        CQLValidator.validate_label("")


def test_validate_label_injection():
    with pytest.raises(BaseAppException):
        CQLValidator.validate_label("host; DROP")


# validate_field
def test_validate_field_ok():
    assert CQLValidator.validate_field("name") == "name"
    assert CQLValidator.validate_field("_id") == "_id"


def test_validate_field_bad_start():
    with pytest.raises(BaseAppException):
        CQLValidator.validate_field("1name")


def test_validate_field_chinese_rejected():
    with pytest.raises(BaseAppException):
        CQLValidator.validate_field("名称")


def test_validate_field_empty():
    with pytest.raises(BaseAppException):
        CQLValidator.validate_field("")


# validate_relation
def test_validate_relation_ok():
    assert CQLValidator.validate_relation("belongs") == "belongs"
    assert CQLValidator.validate_relation("属于") == "属于"


def test_validate_relation_injection():
    with pytest.raises(BaseAppException):
        CQLValidator.validate_relation("rel-injection!")


def test_validate_relation_empty():
    with pytest.raises(BaseAppException):
        CQLValidator.validate_relation("")


# validate_order_type
def test_validate_order_type():
    assert CQLValidator.validate_order_type("asc") == "ASC"
    assert CQLValidator.validate_order_type("DESC") == "DESC"
    assert CQLValidator.validate_order_type(None) == "ASC"


def test_validate_order_type_invalid():
    with pytest.raises(BaseAppException):
        CQLValidator.validate_order_type("sideways")
