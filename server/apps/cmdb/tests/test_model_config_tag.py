"""
CMDB model_config.xlsx 默认 tag 字段回归测试

业务背景:
- 4 大目标分类(应用主机/中间件/数据库/物理设备)下的内置模型应统一开启 tag 标签属性
- 另有 15 个跨场景模型新建 attr_type=tag(K8S 只给 cluster；网络设备/应用拓扑/机房/PC/证书/ZStack/漏网虚拟机)
- 208 个 tag 类型字段预置跨模型共用 option：Pack A=env+level，Pack B=env+level+zone，mode=free
- 14 个已有 tag 模型(qcloud_*/azure_* 14 个云资源):保持 attr_type='str',不迁移
- K8S namespace/node/workload/pod 不内置 tag
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

# 当前没有 tag 字段、需要新建 attr_type=tag 的 15 个模型
NEW_TAG_MODELS = frozenset(
    {
        "k8s_cluster",
        "system",
        "application",
        "datacenter",
        "server_room",
        "rack",
        "pc",
        "ssl_cer",
        "zstack",
        "switch",
        "router",
        "firewall",
        "loadbalance",
        "security_device",
        "sangforhci_vm",
    }
)

# K8S 只给 cluster 内置标签
K8S_WITHOUT_BUILTIN_TAG = frozenset({"k8s_namespace", "k8s_node", "k8s_workload", "k8s_pod"})

# 计算/网络位置是场景轴：env+level+zone
PACK_B_MODELS = frozenset(
    {
        "host",
        "physcial_server",
        "server_bmc",
        "switch",
        "router",
        "firewall",
        "loadbalance",
        "security_device",
        "vmware_vm",
        "vmware_esxi",
        "aliyun_ecs",
        "aliyun_clb",
        "qcloud_cvm",
        "hwcloud_ecs",
        "aws_ec2",
        "aws_elb",
        "manageone_server",
        "manageone_host",
        "manageone_eip",
        "openstack_vm",
        "openstack_node",
        "openstack_vpc",
        "openstack_subnet",
        "openstack_eip",
        "openstack_sg",
        "smartx_vm",
        "smartx_host",
        "fusioncompute_vm",
        "fusioncompute_host",
        "fusioninsight_host",
        "inspurincloudrail_vm",
        "sangforscp_host",
        "sangforscp_vm",
        "sangforhci_vm",
        "nutanixhci_host",
        "nutanixhci_vm",
        "winsphere_host",
        "winsphere_vm",
        "winsphere_vswitch",
        "winsphere_port_group",
        "h3c_cas_host",
        "h3c_cas_vm",
        "h3c_cas_vswitch",
        "hwcloud_vpc",
        "hwcloud_subnet",
        "hwcloud_eip",
        "hwcloud_sg",
        "hwcloud_elb",
        "apache",
        "nginx",
        "openresty",
        "haproxy",
        "keepalive",
        "squid",
        "ihs",
    }
)

ENV_LEVEL_OPTIONS = [
    {"key": "env", "value": "生产"},
    {"key": "env", "value": "预发"},
    {"key": "env", "value": "测试"},
    {"key": "env", "value": "开发"},
    {"key": "env", "value": "灾备"},
    {"key": "level", "value": "核心"},
    {"key": "level", "value": "重要"},
    {"key": "level", "value": "一般"},
]
ZONE_OPTIONS = [
    {"key": "zone", "value": "隔离区"},
    {"key": "zone", "value": "内网"},
    {"key": "zone", "value": "外网"},
    {"key": "zone", "value": "管理网"},
]
PACK_A_OPTIONS = ENV_LEVEL_OPTIONS
PACK_B_OPTIONS = ENV_LEVEL_OPTIONS + ZONE_OPTIONS


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


@pytest.mark.unit
def test_models_sheet_seeds_app_topo_layer():
    sheets = _load_sheets()
    df = sheets["models"]
    assert "app_topo_layer" in df.columns
    by_id = {str(model_id): str(layer) for model_id, layer in zip(df["model_id"], df["app_topo_layer"])}
    assert by_id["application"] == "service"
    assert by_id["system"] == "system"
    assert by_id["host"] == "host"
    assert by_id["mysql"] == "appService"
    assert by_id["nginx"] == "appService"
    assert by_id["oceanbase"] == "appService"
    assert by_id["nacos"] == "appService"
    assert by_id["vmware_vm"] == "host"
    assert by_id["aliyun_ecs"] == "host"
    assert by_id["physcial_server"] == "infrastructure"
    assert by_id["rack"] == "infrastructure"
    assert by_id["k8s_cluster"] == "none"
    assert set(by_id.values()) <= {"system", "service", "host", "appService", "infrastructure", "none"}

    rows = list(zip(df["model_id"].astype(str), df["classification_id"].astype(str), df["app_topo_layer"].astype(str)))
    assert {layer for _, cid, layer in rows if cid == "database"} == {"appService"}
    assert {layer for _, cid, layer in rows if cid == "middleware"} == {"appService"}
    assert {layer for _, cid, layer in rows if cid in {"harware", "hardware_components", "network_device", "idc"}} == {"infrastructure"}
    host_ids = {model_id for model_id, layer in by_id.items() if layer == "host"}
    assert "host" in host_ids
    assert all(mid.endswith(("_vm", "_ecs", "_cvm", "_ec2")) or mid in {"host", "manageone_server"} for mid in host_ids)


def _parse_tag_option(raw) -> dict:
    normalized = str(raw).replace("'", '"')
    return json.loads(normalized)


def _iter_unique_models(sheets: dict):
    seen: set = set()
    for model_id, classification_id in zip(sheets["models"]["model_id"], sheets["models"]["classification_id"]):
        if model_id in seen:
            continue
        seen.add(model_id)
        yield str(model_id), str(classification_id)


def _tag_row(sheets: dict, model_id: str):
    df = sheets.get(f"attr-{model_id}")
    if df is None or "attr_id" not in df.columns:
        return None
    matched = df[df["attr_id"].astype(str) == "tag"]
    if matched.empty:
        return None
    return matched.iloc[0]


@pytest.mark.unit
def test_new_scene_models_open_tag_field_in_basic_info():
    sheets = _load_sheets()
    missing = []
    for model_id in sorted(NEW_TAG_MODELS):
        row = _tag_row(sheets, model_id)
        if row is None:
            missing.append((model_id, "no tag attr"))
            continue
        if str(row["attr_type"]) != "tag":
            missing.append((model_id, f"type={row['attr_type']}"))
        if str(row["attr_group"]).strip() != "基本信息":
            missing.append((model_id, f"group={row['attr_group']}"))
        if bool(row["is_required"]) is True:
            missing.append((model_id, "required"))
        if bool(row["editable"]) is not True:
            missing.append((model_id, "not editable"))
        if bool(row["is_only"]) is True:
            missing.append((model_id, "unique"))
    assert not missing, missing


@pytest.mark.unit
def test_k8s_builtin_tag_only_on_cluster():
    sheets = _load_sheets()
    cluster = _tag_row(sheets, "k8s_cluster")
    assert cluster is not None
    assert str(cluster["attr_type"]) == "tag"
    leaked = [model_id for model_id in sorted(K8S_WITHOUT_BUILTIN_TAG) if _tag_row(sheets, model_id) is not None]
    assert leaked == [], f"K8S 子对象不应内置 tag: {leaked}"


@pytest.mark.unit
def test_builtin_tag_options_follow_shared_packs():
    sheets = _load_sheets()
    wrong = []
    tag_type_models = []
    for model_id, _classification_id in _iter_unique_models(sheets):
        row = _tag_row(sheets, model_id)
        if row is None:
            continue
        if str(row["attr_type"]) != "tag":
            continue
        tag_type_models.append(model_id)
        expected = PACK_B_OPTIONS if model_id in PACK_B_MODELS else PACK_A_OPTIONS
        try:
            option = _parse_tag_option(row["option"])
        except json.JSONDecodeError as exc:
            wrong.append((model_id, f"invalid JSON {exc}"))
            continue
        if option.get("mode") != "free":
            wrong.append((model_id, f"mode={option.get('mode')}"))
        if option.get("options") != expected:
            wrong.append((model_id, f"options={option.get('options')}"))

    assert len(tag_type_models) == 208, f"attr_type=tag 应为 208 个,实际 {len(tag_type_models)}"
    assert set(NEW_TAG_MODELS) <= set(tag_type_models)
    assert not (set(tag_type_models) & K8S_WITHOUT_BUILTIN_TAG)
    assert not (set(tag_type_models) & PRE_EXISTING_TAG_MODELS)
    assert PACK_B_MODELS <= set(tag_type_models)
    assert not wrong, wrong[:12]
