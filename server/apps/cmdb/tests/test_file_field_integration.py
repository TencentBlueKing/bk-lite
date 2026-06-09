"""附件/图片字段的服务层接线集成测试。

覆盖 service.py 之外、此前未测的「接线层」：
- Excel 导出/导入对文件字段的排除（utils/export.py, utils/Import.py）
- 模型字段建/改规则经 ModelManage 的接入（services/model.py）
"""

import importlib.util
import json

import pytest

from apps.core.exceptions.base_app_exception import BaseAppException

from apps.cmdb.services.model import ModelManage
from apps.cmdb.utils.export import Export
from apps.cmdb.utils.Import import Import

# 断言依赖企业 provider 激活（字段类型/规则/排除）；无 overlay 时跳过整个模块
if importlib.util.find_spec("apps.cmdb.enterprise.instance_ops.provider") is None:
    pytest.skip("enterprise overlay absent", allow_module_level=True)


# --------------------------------------------------------------------------
# Excel 导出/导入：附件/图片字段不进入
# --------------------------------------------------------------------------

_ATTRS_WITH_FILE = [
    {"attr_id": "inst_name", "attr_name": "实例名", "attr_type": "str", "is_required": True},
    {"attr_id": "contract", "attr_name": "合同", "attr_type": "attachment"},
    {"attr_id": "photo", "attr_name": "外观", "attr_type": "image"},
]


def test_export_header_excludes_file_fields():
    # 若未排除，ATTR_TYPE_MAP["attachment"] 会 KeyError → 该测试同时守护回归
    wb = Export(_ATTRS_WITH_FILE, model_id="host").generate_header()
    sheet = wb.active
    ids = [c.value for c in sheet[3]]
    assert "inst_name" in ids
    assert "contract" not in ids
    assert "photo" not in ids


def test_import_field_maps_excludes_file_fields():
    importer = Import("host", _ATTRS_WITH_FILE, [], "admin")
    field_maps = importer._build_field_maps()
    assert "inst_name" in field_maps["attr_name_map"]
    assert "contract" not in field_maps["attr_name_map"]
    assert "photo" not in field_maps["attr_name_map"]


# --------------------------------------------------------------------------
# 模型字段规则经 ModelManage 接入
# --------------------------------------------------------------------------


@pytest.mark.django_db
def test_create_model_attr_attachment_forced_optional(fake_graph, monkeypatch):
    captured = {}

    def fake_set(*args, **kwargs):
        captured["attrs"] = args[2]["attrs"]
        return [{"attrs": args[2]["attrs"]}]

    fake_graph(
        "apps.cmdb.services.model",
        query_entity=([{"_id": 1, "model_name": "主机", "attrs": "[]"}], 1),
        set_entity_properties=fake_set,
    )
    monkeypatch.setattr(
        "apps.cmdb.display_field.ExcludeFieldsCache.update_on_model_change",
        lambda *a, **k: None,
    )

    attr = {
        "attr_id": "contract",
        "attr_name": "合同",
        "attr_type": "attachment",
        "is_required": True,  # 用户传必填
        "is_only": True,  # 用户传唯一
    }
    ModelManage.create_model_attr("host", attr, username="admin")

    persisted = json.loads(captured["attrs"])
    contract = next(a for a in persisted if a["attr_id"] == "contract")
    # 企业规则兜底：一律可选、非唯一、无约束旋钮
    assert contract["is_required"] is False
    assert contract["is_only"] is False
    assert contract["option"] == {}


@pytest.mark.django_db
def test_update_model_attr_file_type_immutable(fake_graph):
    existing = json.dumps(
        [{"attr_id": "contract", "attr_name": "合同", "attr_type": "attachment", "editable": True}]
    )
    fake_graph(
        "apps.cmdb.services.model",
        query_entity=([{"_id": 1, "model_name": "主机", "attrs": existing}], 1),
    )
    with pytest.raises(BaseAppException, match="不可切换"):
        ModelManage.update_model_attr(
            "host",
            {"attr_id": "contract", "attr_name": "合同", "attr_type": "str"},
            username="admin",
        )
