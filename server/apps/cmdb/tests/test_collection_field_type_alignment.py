# -*- coding: utf-8 -*-
"""字段类型对照：插件 field_mappings 的产出类型必须与 model_config.xlsx 的 attr_type 一致。

防止「key 对了但类型错位」（如 int 字段产出字符串）。以模型设计为准。
"""
import os
import pandas as pd
import pytest

XLSX = os.path.join(os.path.dirname(__file__), "..", "support-files", "model_config.xlsx")

SKIP_FIELDS = {"inst_name", "assos", "bk_obj_id"}


def _model_types(sheet):
    df = pd.read_excel(XLSX, sheet_name="attr-" + sheet, header=1)
    return {str(r["attr_id"]): str(r["attr_type"]) for _, r in df.iterrows() if str(r.get("attr_id")) != "nan"}


def _mapping_kind(v):
    if isinstance(v, tuple):
        conv = v[0]
        name = getattr(conv, "__name__", str(conv))
        if conv is int or name in ("to_int",):
            return "int"
        if conv is float:
            return "float"
        return name
    if callable(v):
        return "callable"  # inst_name 等，产出 str
    return "str"


def _acceptable(attr_type):
    # 仅采集字段相关；time 接受 ISO 字符串；bool/organization/user 非采集字段
    if attr_type == "int":
        return {"int"}
    if attr_type in ("str", "time"):
        return {"str", "callable"}
    return None  # 跳过非采集类型


def _iter_cloud_plugins():
    from apps.cmdb.collection.plugins.community.cloud.hwcloud import HwCloudCollectionPlugin
    from apps.cmdb.collection.plugins.community.cloud.manageone import ManageOneCollectionPlugin
    from apps.cmdb.collection.plugins.community.cloud.openstack import OpenStackCollectionPlugin
    from apps.cmdb.collection.plugins.community.cloud.smartx import SmartXCollectionPlugin
    from apps.cmdb.collection.plugins.community.cloud.fusioninsight import FusionInsightCollectionPlugin
    return [HwCloudCollectionPlugin, ManageOneCollectionPlugin, OpenStackCollectionPlugin,
            SmartXCollectionPlugin, FusionInsightCollectionPlugin]


def test_cloud_plugins_field_types_align_with_model():
    mismatches = []
    for plug in _iter_cloud_plugins():
        for model_id, fm in plug.field_mappings.items():
            mt = _model_types(model_id)
            for field, v in fm.items():
                if field in SKIP_FIELDS:
                    continue
                attr_type = mt.get(field)
                assert attr_type is not None, f"{model_id}.{field} 不在模型字段中"
                acc = _acceptable(attr_type)
                if acc is None:
                    continue
                kind = _mapping_kind(v)
                if kind not in acc:
                    mismatches.append(f"{model_id}.{field}: 模型={attr_type} 产出={kind}")
    assert not mismatches, "字段类型与模型不符:\n" + "\n".join(mismatches)


def test_keepalive_field_types_align_with_model():
    from apps.cmdb.collection.plugins.community.middleware.keepalived import KeepalivedCollectionPlugin
    mt = _model_types("keepalive")
    mismatches = []
    for field, v in KeepalivedCollectionPlugin.field_mapping.items():
        if field in SKIP_FIELDS:
            continue
        attr_type = mt.get(field)
        if attr_type is None:
            continue
        acc = _acceptable(attr_type)
        if acc is None:
            continue
        kind = _mapping_kind(v)
        if kind not in acc:
            mismatches.append(f"keepalive.{field}: 模型={attr_type} 产出={kind}")
    assert not mismatches, "字段类型与模型不符:\n" + "\n".join(mismatches)
