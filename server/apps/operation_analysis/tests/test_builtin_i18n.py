"""运营分析内置画布/数据源读时语言覆盖（不依赖 Django migrate）。"""

from types import SimpleNamespace

import pytest

from apps.operation_analysis.services.builtin_i18n import overlay_canvas_payload, overlay_datasource_payload, overlay_directory_payload

pytestmark = pytest.mark.unit

DASHBOARD_KEY = "dashboard::CMDB仪表盘_内置"
SCREEN_KEY = "screen::告警运营大屏_内置"
DIRECTORY_KEY = "__builtin__"
DATASOURCE_KEY = "CMDB 覆盖概览::cmdb/get_cmdb_statistics"

REPORT_KEY = "report::僵尸机报表"

CATALOG = {
    "directories": {DIRECTORY_KEY: {"name": "Built-in"}},
    "dashboards": {
        DASHBOARD_KEY: {
            "name": "CMDB Dashboard",
            "desc": "CMDB overview",
            "filters": {
                "time": {"name": "Time"},
                "dimension": {
                    "name": "Dimension",
                    "options": {"model": "Model", "organization": "Organization"},
                },
            },
            "widgets": {
                "w1": {
                    "name": "Models",
                    "description": "Model count",
                    "columns": {"model": "Model Name"},
                    "params": {"model_id": "Model ID"},
                    "actions": {"__actions__": "View"},
                },
                "group-overview": {"name": "Overview", "description": "Resource overview"},
            },
        }
    },
    "screens": {
        SCREEN_KEY: {
            "name": "Alert Ops Screen",
            "desc": "Alert operations screen",
            "decorations": {"title": "Cabinet Overview"},
            "widgets": {"alert-kpi-created": {"title": "Created Today"}},
        }
    },
    "datasources": {
        DATASOURCE_KEY: {
            "name": "CMDB Coverage Overview",
            "desc": "Classification / model / instance coverage",
            "fields": {"model_count": {"title": "Models", "description": "Model total"}},
            "params": {"time": "Time Range"},
        }
    },
    "reports": {
        REPORT_KEY: {
            "name": "Zombie Host Report",
            "desc": "Idle host report",
            "filters": {
                "system_uuids": "Application System",
                "zombie_whitelist": {
                    "name": "Zombie Host Allowlist",
                    "options": {"yes": "Yes", "no": "No"},
                },
            },
            "widgets": {
                "zombie-table": {
                    "name": "Zombie Host List",
                    "description": "Logins and resource usage for selected systems",
                    "params": {"login_max": "Login Count Max"},
                }
            },
        }
    },
}


def test_overlay_skips_user_canvas():
    data = {"name": "我的仪表盘", "desc": "自定义"}
    instance = SimpleNamespace(is_build_in=False, build_in_key=DASHBOARD_KEY)
    result = overlay_canvas_payload(data, instance, "en", catalog=CATALOG)
    assert result["name"] == "我的仪表盘"


def test_overlay_dashboard_name_widgets_filters():
    data = {
        "name": "CMDB仪表盘",
        "desc": "CMDB仪表盘",
        "filters": [{"id": "time__timeRange", "key": "time", "name": "时间"}],
        "view_sets": [
            {
                "id": "group-overview",
                "itemType": "group",
                "name": "资源概览",
                "description": "所选主机数",
                "subGridOpts": {
                    "children": [
                        {
                            "id": "w1",
                            "name": "模型数",
                            "description": "模型数量",
                            "itemType": "widget",
                            "valueConfig": {
                                "tableConfig": {"columns": [{"key": "model", "title": "模型名"}]},
                                "dataSourceParams": [
                                    {"name": "model_id", "alias_name": "模型ID"},
                                ],
                            },
                        }
                    ]
                },
            }
        ],
    }
    instance = SimpleNamespace(is_build_in=True, build_in_key=DASHBOARD_KEY)
    result = overlay_canvas_payload(data, instance, "en", catalog=CATALOG)
    assert result["name"] == "CMDB Dashboard"
    assert result["desc"] == "CMDB overview"
    assert result["filters"][0]["name"] == "Time"
    group = result["view_sets"][0]
    assert group["name"] == "Overview"
    child = group["subGridOpts"]["children"][0]
    assert child["name"] == "Models"
    assert child["description"] == "Model count"
    assert child["valueConfig"]["tableConfig"]["columns"][0]["title"] == "Model Name"
    assert child["valueConfig"]["dataSourceParams"][0]["alias_name"] == "Model ID"


def test_overlay_filter_options_and_widget_actions():
    data = {
        "name": "CMDB仪表盘",
        "filters": [
            {
                "key": "dimension",
                "name": "统计维度",
                "options": [
                    {"label": "模型", "value": "model"},
                    {"label": "组织", "value": "organization"},
                ],
            }
        ],
        "view_sets": [
            {
                "id": "w1",
                "name": "模型数",
                "valueConfig": {
                    "actions": [{"columnKey": "__actions__", "text": "查看", "url": "/cmdb/assetData"}],
                    "dataSourceParams": [
                        {
                            "name": "model_id",
                            "alias_name": "模型ID",
                            "inputConfig": {
                                "optionsSource": {
                                    "type": "static",
                                    "staticItems": [{"label": "模型", "value": "model"}],
                                }
                            },
                        }
                    ],
                },
            }
        ],
    }
    instance = SimpleNamespace(is_build_in=True, build_in_key=DASHBOARD_KEY)
    result = overlay_canvas_payload(data, instance, "en", catalog=CATALOG)
    assert result["filters"][0]["name"] == "Dimension"
    assert result["filters"][0]["options"][0]["label"] == "Model"
    assert result["filters"][0]["options"][1]["label"] == "Organization"
    widget = result["view_sets"][0]
    assert widget["valueConfig"]["actions"][0]["text"] == "View"
    assert widget["valueConfig"]["dataSourceParams"][0]["alias_name"] == "Model ID"


def test_overlay_screen_title_and_decoration():
    data = {
        "name": "告警运营大屏",
        "desc": "告警大屏",
        "view_sets": {
            "items": [{"id": "alert-kpi-created", "title": "今日已产生"}],
            "decorations": {"title": "机柜全景"},
        },
    }
    instance = SimpleNamespace(is_build_in=True, build_in_key=SCREEN_KEY)
    result = overlay_canvas_payload(data, instance, "en", catalog=CATALOG)
    assert result["name"] == "Alert Ops Screen"
    assert result["view_sets"]["items"][0]["title"] == "Created Today"
    assert result["view_sets"]["decorations"]["title"] == "Cabinet Overview"


def test_overlay_datasource_fields_and_params():
    data = {
        "name": "CMDB 覆盖概览",
        "desc": "覆盖",
        "field_schema": [{"key": "model_count", "title": "模型数", "description": "模型总数"}],
        "params": [{"name": "time", "alias_name": "时间范围"}],
    }
    instance = SimpleNamespace(is_build_in=True, build_in_key=DATASOURCE_KEY)
    result = overlay_datasource_payload(data, instance, "en", catalog=CATALOG)
    assert result["name"] == "CMDB Coverage Overview"
    assert result["field_schema"][0]["title"] == "Models"
    assert result["params"][0]["alias_name"] == "Time Range"


def test_overlay_directory_name():
    data = {"name": "内置目录"}
    instance = SimpleNamespace(is_build_in=True, build_in_key=DIRECTORY_KEY)
    result = overlay_directory_payload(data, instance, "en", catalog=CATALOG)
    assert result["name"] == "Built-in"


def test_missing_widget_keeps_stored_name():
    data = {"name": "CMDB仪表盘", "view_sets": [{"id": "custom-w", "name": "用户组件"}]}
    instance = SimpleNamespace(is_build_in=True, build_in_key=DASHBOARD_KEY)
    result = overlay_canvas_payload(data, instance, "en", catalog=CATALOG)
    assert result["view_sets"][0]["name"] == "用户组件"


def test_language_pack_overlays_cmdb_dashboard_from_loader():
    from apps.core.utils.loader import clear_language_cache

    clear_language_cache("operation_analysis")
    data = {"name": "CMDB仪表盘", "desc": "CMDB仪表盘"}
    instance = SimpleNamespace(is_build_in=True, build_in_key=DASHBOARD_KEY)
    result = overlay_canvas_payload(data, instance, "en")
    assert result["name"] == "CMDB Dashboard"
    zh = overlay_canvas_payload({"name": "CMDB仪表盘"}, instance, "zh-CN")
    assert zh["name"] == "CMDB仪表盘"


def test_overlay_report_name_filters_section_and_static_options():
    data = {
        "name": "僵尸机报表",
        "desc": "中文说明",
        "view_sets": {
            "schema_version": 1,
            "filters": [
                {"id": "system_uuids__string", "key": "system_uuids", "name": "应用系统"},
                {
                    "id": "zombie_whitelist__string",
                    "key": "zombie_whitelist",
                    "name": "僵尸机白名单",
                    "inputConfig": {
                        "optionsSource": {
                            "type": "static",
                            "staticItems": [
                                {"label": "是", "value": "yes"},
                                {"label": "否", "value": "no"},
                            ],
                        }
                    },
                },
            ],
            "sections": [
                {
                    "id": "zombie-table",
                    "valueConfig": {
                        "name": "僵尸机列表",
                        "description": "中文描述",
                        "dataSourceParams": [{"name": "login_max", "alias_name": "登录次数上限"}],
                    },
                }
            ],
        },
    }
    instance = SimpleNamespace(is_build_in=True, build_in_key=REPORT_KEY)
    result = overlay_canvas_payload(data, instance, "en", catalog=CATALOG)
    assert result["name"] == "Zombie Host Report"
    assert result["desc"] == "Idle host report"
    filters = result["view_sets"]["filters"]
    assert filters[0]["name"] == "Application System"
    assert filters[1]["name"] == "Zombie Host Allowlist"
    assert filters[1]["inputConfig"]["optionsSource"]["staticItems"][0]["label"] == "Yes"
    assert filters[1]["inputConfig"]["optionsSource"]["staticItems"][1]["label"] == "No"
    section = result["view_sets"]["sections"][0]
    assert section["valueConfig"]["name"] == "Zombie Host List"
    assert section["valueConfig"]["description"] == "Logins and resource usage for selected systems"
    assert section["valueConfig"]["dataSourceParams"][0]["alias_name"] == "Login Count Max"


def test_language_pack_overlays_zombie_report_from_loader():
    from apps.core.utils.loader import clear_language_cache

    clear_language_cache("operation_analysis")
    instance = SimpleNamespace(is_build_in=True, build_in_key=REPORT_KEY)
    en = overlay_canvas_payload({"name": "僵尸机报表", "desc": "中文说明"}, instance, "en")
    assert en["name"] == "Zombie Host Report"
    zh = overlay_canvas_payload({"name": "僵尸机报表"}, instance, "zh-CN")
    assert zh["name"] == "僵尸机报表"
