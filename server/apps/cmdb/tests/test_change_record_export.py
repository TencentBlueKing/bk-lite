"""CMDB 变更记录与导出工具覆盖测试。

对照 spec/prd/CMDB·操作日志/资产：实例属性/关联变更记录落库，标签值导出序列化。
"""

import pytest

from apps.cmdb.models.change_record import (
    CREATE_INST,
    CREATE_INST_ASST,
    DELETE_INST_ASST,
    ChangeRecord,
)
from apps.cmdb.utils.change_record import (
    batch_create_change_record,
    create_change_record,
    create_change_record_by_asso,
)
from apps.cmdb.utils.export import Export, serialize_tag_values_for_export


# --------------------------------------------------------------------------
# export 纯函数
# --------------------------------------------------------------------------


def test_serialize_tag_values_empty():
    assert serialize_tag_values_for_export([]) == ""


def test_serialize_tag_values_joins():
    assert serialize_tag_values_for_export(["a:1", " b:2 ", ""]) == "a:1,b:2"


def test_format_user_display_username_both():
    assert Export._format_user_display_username({"username": "u1", "display_name": "用户1"}) == "用户1(u1)"


def test_format_user_display_username_only_username():
    assert Export._format_user_display_username({"username": "u1"}) == "u1"


def test_format_user_display_username_none():
    assert Export._format_user_display_username(None) is None


# --------------------------------------------------------------------------
# change_record （DB）
# --------------------------------------------------------------------------


@pytest.mark.django_db
def test_create_change_record():
    create_change_record(
        inst_id=1, model_id="host", label="主机", _type=CREATE_INST,
        after_data={"name": "h1"}, operator="admin", message="新建",
    )
    rec = ChangeRecord.objects.get(inst_id=1, model_id="host")
    assert rec.after_data == {"name": "h1"}
    assert rec.operator == "admin"


@pytest.mark.django_db
def test_batch_create_change_record():
    records = [
        {"inst_id": 1, "model_id": "host", "after_data": {"n": 1}},
        {"inst_id": 2, "model_id": "host", "after_data": {"n": 2}},
    ]
    batch_create_change_record(label="主机", _type=CREATE_INST, change_records=records, operator="admin")
    assert ChangeRecord.objects.filter(model_id="host").count() == 2


@pytest.mark.django_db
def test_create_change_record_by_asso_create():
    data = {
        "src": {"_id": 1, "model_id": "host"},
        "dst": {"_id": 2, "model_id": "switch"},
    }
    create_change_record_by_asso(label="关联", _type=CREATE_INST_ASST, data=data, operator="admin")
    # src/dst 都有 model_id → 2 条记录，且使用 after_data
    assert ChangeRecord.objects.filter(type=CREATE_INST_ASST).count() == 2


@pytest.mark.django_db
def test_create_change_record_by_asso_delete_skips_no_model():
    data = {
        "src": {"_id": 1, "model_id": "host"},
        "dst": {"_id": 2},  # 无 model_id → 跳过
    }
    create_change_record_by_asso(label="关联", _type=DELETE_INST_ASST, data=data, operator="admin")
    assert ChangeRecord.objects.filter(type=DELETE_INST_ASST).count() == 1
