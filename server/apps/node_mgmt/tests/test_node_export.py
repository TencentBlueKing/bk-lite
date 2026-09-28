from apps.node_mgmt.constants.collector import CollectorConstants
from apps.node_mgmt.services.node_export import (
    EXPORT_LIMIT,
    build_export_filename,
    build_export_row,
    format_hosted_collectors_cell,
    format_organization_cell,
)


def test_export_limit_is_5000():
    assert EXPORT_LIMIT == 5000


def test_organization_cell_uses_names_not_ids():
    assert format_organization_cell([7, 8], {7: "alpha", 8: "beta"}, unassigned_label="未归属") == "alpha,beta"


def test_organization_cell_empty_is_unassigned():
    assert format_organization_cell([], {}, unassigned_label="未归属") == "未归属"


def test_hosted_cell_joins_display_name_and_status():
    cell = format_hosted_collectors_cell(
        [
            {"collector_name": "Telegraf", "status": 2},
            {"collector_name": "Vector", "status": 0},
        ],
        status_labels={0: "正常", 2: "异常"},
    )
    assert cell == "Telegraf:异常；Vector:正常"


def test_hosted_cell_empty_when_no_collectors():
    assert format_hosted_collectors_cell([], status_labels={}) == ""


def test_hosted_cell_uses_rewritten_status():
    cell = format_hosted_collectors_cell(
        [{"collector_name": "Filebeat", "status": 0, "verbose_message": CollectorConstants.IGNORE_ERROR_EMPTY_CONFIG_MESSAGES[1]}],
        status_labels={0: "正常", 2: "异常"},
    )
    assert cell == "Filebeat:正常"


def test_build_export_row_online_and_upgradeable():
    row = build_export_row(
        {
            "name": "keep-node",
            "ip": "10.0.0.1",
            "operating_system": "linux",
            "cpu_architecture": "x86_64",
            "node_type": "host",
            "install_method": "auto",
            "organization": [7],
            "active": True,
            "updated_at": "2026-09-28T12:00:00+00:00",
            "versions": [{"component_type": "controller", "version": "1.2.3", "upgradeable": True}],
            "status": {"collectors": [{"collector_name": "Telegraf", "status": 2}]},
        },
        labels={
            "unassigned": "未归属",
            "online": "在线",
            "offline": "离线",
            "yes": "是",
            "no": "否",
            "os": {"linux": "Linux", "windows": "Windows"},
            "install_method": {"auto": "远程", "manual": "手动"},
            "node_type": {"host": "主机节点", "container": "容器节点"},
            "collector_status": {0: "正常", 1: "未知的", 2: "异常", 3: "停止", 4: "未启动", 10: "安装中", 11: "未启动", 12: "安装失败"},
        },
        organization_names={7: "alpha"},
    )
    assert row[0] == "keep-node"
    assert row[1] == "10.0.0.1"
    assert row[7] == "在线"
    assert row[10] == "是"
    assert row[11] == "Telegraf:异常"


def test_filename_contains_region_and_xlsx():
    name = build_export_filename("默认云区域", stamp="20260928_120000")
    assert name == "节点清单_默认云区域_20260928_120000.xlsx"
