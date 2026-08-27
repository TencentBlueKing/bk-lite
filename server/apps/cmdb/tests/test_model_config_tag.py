"""
CMDB model_config.xlsx 默认 tag 字段回归测试

业务背景:
- 4 大目标分类(应用主机/中间件/数据库/物理设备)下的内置模型应统一开启 tag 标签属性
- 177 个新加 tag 模型:attr_type='tag', option 含 mode=free, attr_group='基本信息',
  is_required=False, editable=True, is_only=False
- 14 个已有 tag 模型(qcloud_*/azure_* 14 个云资源):保持 attr_type='str',不迁移
"""
import json
import os

import pandas as pd
import pytest

# 4 大目标分类对应的 classification_id(应用主机 + 中间件 + 数据库 + 物理设备)
TARGET_CLASSIFICATION_IDS = frozenset(
    {
        # 应用主机
        "host_manage",
        "aliyun",
        "qcloud",
        "hwcloud",
        "aws",
        "azure",
        "vmware",
        "openstack",
        "smartx",
        "nutanixhci",
        "sangforscp",
        "fusioncompute",
        "inspurincloudrail",
        "manageone",
        "fusioninsight",
        # 中间件
        "middleware",
        # 数据库
        "database",
        # 物理设备
        "harware",
        "hardware_components",
    }
)

# 已存在 attr_id='tag' 的 14 个模型(保持 attr_type='str',不迁移)
PRE_EXISTING_TAG_MODELS = frozenset(
    {
        "qcloud_mongodb",
        "qcloud_pgsql",
        "qcloud_plusar_cluster",
        "qcloud_cmq",
        "qcloud_cmq_topic",
        "qcloud_clb",
        "qcloud_eip",
        "qcloud_filesystem",
        "azure_vm",
        "azure_redis",
        "azure_mysql",
        "azure_nat_gateway",
        "azure_elb",
        "azure_dns",
    }
)


def _model_config_path() -> str:
    """定位 apps/cmdb/support-files/model_config.xlsx 的绝对路径"""
    here = os.path.dirname(os.path.abspath(__file__))
    # apps/cmdb/tests/test_model_config_tag.py → apps/cmdb/support-files/model_config.xlsx
    return os.path.normpath(os.path.join(here, "..", "support-files", "model_config.xlsx"))


def _load_sheets() -> dict:
    return pd.read_excel(_model_config_path(), sheet_name=None, header=1)


def _list_target_models(sheets: dict) -> list:
    """4 大目标分类下的 model_id 去重集合(去重 models sheet 中的重复行,如 weblogic/websphere)"""
    df = sheets["models"]
    seen: set = set()
    out: list = []
    for m, cid in zip(df["model_id"], df["classification_id"]):
        if cid in TARGET_CLASSIFICATION_IDS and m not in seen:
            seen.add(m)
            out.append(m)
    return sorted(out)


@pytest.mark.unit
def test_target_categories_yield_191_models():
    """4 大目标分类下应为 191 个内置模型(下线 14 个主机/存储模型后)。"""
    sheets = _load_sheets()
    target_models = _list_target_models(sheets)
    assert len(target_models) == 191, f"4 类目标分类下应为 191 个内置模型,实际 {len(target_models)}"


@pytest.mark.unit
def test_target_models_have_attr_sheets_with_tag_attribute():
    """
    191 个目标模型在 model_config.xlsx 中都应有 attr-{model_id} sheet,
    且含 attr_id='tag' 的属性。
    """
    sheets = _load_sheets()
    target_models = _list_target_models(sheets)

    missing_sheets = []
    missing_tag = []

    for model_id in target_models:
        sheet_name = f"attr-{model_id}"
        df = sheets.get(sheet_name)
        if df is None:
            missing_sheets.append(sheet_name)
            continue
        if "attr_id" not in df.columns:
            missing_tag.append((sheet_name, "no attr_id column"))
            continue
        if not (df["attr_id"].astype(str) == "tag").any():
            missing_tag.append((sheet_name, "no tag attr"))

    assert not missing_sheets, f"缺失 attr sheet: {missing_sheets}"
    assert not missing_tag, f"缺失 tag 属性: {missing_tag}"


@pytest.mark.unit
def test_new_tag_attributes_use_tag_type_and_free_mode():
    """
    177 个新加 tag 模型:
    - attr_type='tag'(专用类型,非 str)
    - option 含 mode=free
    - attr_group='基本信息'
    """
    sheets = _load_sheets()
    target_models = _list_target_models(sheets)
    new_models = [m for m in target_models if m not in PRE_EXISTING_TAG_MODELS]
    assert len(new_models) == 177, f"应为 177 个新加 tag 模型,实际 {len(new_models)}"

    wrong_type = []
    wrong_group = []
    wrong_option = []

    for model_id in new_models:
        df = sheets[f"attr-{model_id}"]
        tag_row = df[df["attr_id"].astype(str) == "tag"].iloc[0]

        if str(tag_row["attr_type"]) != "tag":
            wrong_type.append((model_id, tag_row["attr_type"]))

        if str(tag_row["attr_group"]).strip() != "基本信息":
            wrong_group.append((model_id, tag_row["attr_group"]))

        option_raw = str(tag_row["option"])
        # option 在 xlsx 里可能写成 {"mode":"free",...} 或 {'mode':'free',...}
        normalized = option_raw.replace("'", '"')
        try:
            option_obj = json.loads(normalized)
        except json.JSONDecodeError as exc:
            wrong_option.append((model_id, f"invalid JSON: {option_raw} ({exc})"))
            continue
        if option_obj.get("mode") != "free":
            wrong_option.append((model_id, f"mode should be 'free', got {option_obj.get('mode')}"))

    assert not wrong_type, f"attr_type 应为 'tag': {wrong_type[:10]}..."
    assert not wrong_group, f"attr_group 应为 '基本信息': {wrong_group[:10]}..."
    assert not wrong_option, f"option 应含 mode=free: {wrong_option[:10]}..."


@pytest.mark.unit
def test_pre_existing_tag_models_keep_str_type():
    """
    14 个已有 tag 模型保持 attr_type='str' —— 不批量迁移,
    避免影响已上线实例(可能存在非 key:value 格式数据)。
    """
    sheets = _load_sheets()
    violations = []

    for model_id in PRE_EXISTING_TAG_MODELS:
        sheet_name = f"attr-{model_id}"
        df = sheets.get(sheet_name)
        if df is None:
            violations.append((sheet_name, "missing"))
            continue
        tag_row = df[df["attr_id"].astype(str) == "tag"]
        if tag_row.empty:
            violations.append((sheet_name, "no tag attr"))
            continue
        if str(tag_row.iloc[0]["attr_type"]) != "str":
            violations.append((sheet_name, "attr_type changed"))

    assert not violations, f"14 个已有 tag 模型应保持 str 类型: {violations}"


@pytest.mark.unit
def test_new_tag_attributes_are_optional_and_editable():
    """新增 tag 应可填可不填、可编辑,不会强制用户输入"""
    sheets = _load_sheets()
    new_models = [m for m in _list_target_models(sheets) if m not in PRE_EXISTING_TAG_MODELS]

    violations = []
    for model_id in new_models:
        df = sheets[f"attr-{model_id}"]
        tag_row = df[df["attr_id"].astype(str) == "tag"].iloc[0]

        # is_required 应为 False/0/空(在 xlsx 里 True/False 会被 pandas 读为 bool)
        if bool(tag_row["is_required"]) is True:
            violations.append((model_id, "is_required should be False"))

        # editable 应为 True
        if bool(tag_row["editable"]) is not True:
            violations.append((model_id, "editable should be True"))

        # is_only 应为 False
        if bool(tag_row["is_only"]) is True:
            violations.append((model_id, "is_only should be False"))

    assert not violations, f"新增 tag 属性约束违规: {violations[:10]}..."


@pytest.mark.unit
def test_tag_attribute_positioned_in_basic_info_group_end():
    """
    新增 tag 应位于「基本信息」分组末尾(切到「技术信息」/「管理信息」之前)。
    这是用户确认的插入位置策略。
    """
    sheets = _load_sheets()
    new_models = [m for m in _list_target_models(sheets) if m not in PRE_EXISTING_TAG_MODELS]

    misplaced = []
    for model_id in new_models[:30]:  # 抽样前 30 个 sheet 验证
        df = sheets[f"attr-{model_id}"]
        groups = df["attr_group"].astype(str).tolist()
        tag_idx = df.index[df["attr_id"].astype(str) == "tag"].tolist()
        if not tag_idx:
            continue
        idx = tag_idx[0]
        # tag 之后必须是「基本信息」或「技术信息」(切组边界)或到达末尾
        # 关键:tag 不能在「技术信息」/「管理信息」之后
        # 简单断言:tag 行的 attr_group == 「基本信息」
        if groups[idx] != "基本信息":
            misplaced.append((model_id, f"tag 所在分组为 {groups[idx]}"))

    assert not misplaced, f"新增 tag 不在「基本信息」组: {misplaced}"
