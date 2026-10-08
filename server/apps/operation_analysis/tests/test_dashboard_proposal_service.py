import json

from apps.operation_analysis.services.dashboard_proposal_service import (
    brief_from_source,
    dashboard_confirmation_intent,
    prepare_dashboard_proposal,
    proposal_from_edit_state,
    search_briefs,
)


def test_structured_edit_state_preserves_widget_contract_and_filters():
    snapshot = {
        "snapshotVersion": "1.0",
        "dashboardId": 7,
        "mode": "edit",
        "name": "资产概览",
        "layout": [
            {
                "i": "card-1",
                "x": 0,
                "y": 0,
                "w": 3,
                "h": 2,
                "name": "资产总数",
                "valueConfig": {
                    "chartType": "single",
                    "dataSource": 23,
                    "selectedFields": ["value"],
                    "dataSourceParams": [{"name": "organization", "value": "org-1"}],
                    "filterBindings": {"organization__string": True},
                    "thresholdColors": [{"value": "10", "color": "red"}],
                },
            }
        ],
        "filters": [
            {
                "id": "organization__string",
                "key": "organization",
                "name": "组织",
                "type": "string",
                "defaultValue": "org-1",
                "order": 0,
                "enabled": True,
            }
        ],
        "filterValues": {"organization__string": "org-2"},
        "otherConfig": {"displayMode": "compact"},
        "refreshInterval": 60,
    }
    message = f"用户要调整当前盘\n\n## 仪表盘编辑状态\n{json.dumps(snapshot, ensure_ascii=False)}\n</current_page>"

    proposal = proposal_from_edit_state(message)

    assert proposal["dashboardId"] == 7
    assert proposal["layout"][0]["valueConfig"]["dataSourceParams"][0]["value"] == "org-1"
    assert proposal["layout"][0]["valueConfig"]["filterBindings"] == {"organization__string": True}
    assert proposal["filters"][0]["id"] == "organization__string"
    assert proposal["otherConfig"] == {"displayMode": "compact"}


def test_dashboard_confirmation_requires_an_unambiguous_positive_answer():
    assert dashboard_confirmation_intent("确认") == "apply"
    assert dashboard_confirmation_intent("可以应用") == "apply"
    assert dashboard_confirmation_intent("先不要应用") == "cancel"
    assert dashboard_confirmation_intent("暂不应用") == "cancel"
    assert dashboard_confirmation_intent("不确认") == "cancel"
    assert dashboard_confirmation_intent("应用效果会怎么样") is None


def test_incomplete_source_is_not_recommended():
    assert brief_from_source({"id": 1, "name": "空", "chart_type": ["single"], "field_schema": []}) is None
    brief = brief_from_source(
        {
            "id": 2,
            "name": "资产统计",
            "desc": "资产总数",
            "chart_type": ["single"],
            "field_schema": [{"name": "value", "type": "number"}],
            "params": [{"name": "organization_id", "alias_name": "组织", "required": True, "value": "org-001"}],
        }
    )
    assert brief["chart_type"] == ["single"]
    assert brief["params"][0]["default"] == "org-001"
    keyed = brief_from_source(
        {
            "id": 4,
            "name": "主机列表",
            "chart_type": ["table"],
            "field_schema": [{"key": "hostname", "title": "主机名", "value_type": "string", "description": "主机名称"}],
        }
    )
    assert keyed["fields"] == [{"name": "hostname", "type": "string", "desc": "主机名称"}]


def test_prepare_keeps_organization_control_and_declared_option_source():
    brief = brief_from_source(
        {
            "id": 2,
            "name": "资产统计",
            "chart_type": ["single"],
            "field_schema": [{"key": "value", "title": "数量", "value_type": "number"}],
            "params": [
                {
                    "name": "organization",
                    "type": "string",
                    "filterType": "filter",
                    "inputConfig": {"control": "organization"},
                }
            ],
        }
    )
    prepared = prepare_dashboard_proposal(
        {
            "schemaVersion": "1.0",
            "layout": [
                {
                    "i": "card-1",
                    "valueConfig": {"chartType": "single", "dataSource": 2, "selectedFields": ["value"]},
                }
            ],
            "filters": [],
        },
        [brief],
    )
    param = prepared["proposal"]["layout"][0]["valueConfig"]["dataSourceParams"][0]
    assert prepared["ok"] is True
    assert param["inputConfig"]["control"] == "organization"

    dynamic = brief_from_source(
        {
            "id": 3,
            "name": "机房列表",
            "chart_type": ["table"],
            "field_schema": [{"key": "name"}],
            "params": [
                {
                    "name": "room",
                    "type": "string",
                    "filterType": "filter",
                    "inputConfig": {
                        "control": "select",
                        "optionsSource": {
                            "type": "dynamic",
                            "sourceRef": {"type": "rest_api", "value": "cmdb/get_room_list"},
                            "valueField": "id",
                            "labelField": "name",
                        },
                    },
                }
            ],
        }
    )
    prepared = prepare_dashboard_proposal(
        {
            "schemaVersion": "1.0",
            "layout": [
                {
                    "i": "table-1",
                    "valueConfig": {
                        "chartType": "table",
                        "dataSource": 3,
                        "tableConfig": {"columns": [{"key": "name"}]},
                    },
                }
            ],
            "filters": [],
        },
        [dynamic],
    )
    assert prepared["ok"] is True
    assert prepared["proposal"]["layout"][0]["valueConfig"]["dataSourceParams"][0]["inputConfig"]["optionsSource"]["sourceRef"]["type"] == "rest_api"


def test_search_returns_matching_visualization_candidates():
    briefs = [
        brief_from_source(
            {
                "id": 2,
                "name": "资产统计",
                "chart_type": ["single"],
                "field_schema": [{"name": "value"}],
            }
        ),
        brief_from_source(
            {
                "id": 3,
                "name": "组织列表",
                "chart_type": [],
                "field_schema": [{"name": "id"}, {"name": "name"}],
            }
        ),
    ]
    found = search_briefs([{"text": "资产总数", "purpose": "visualization", "chartType": "single"}], briefs)
    assert [item["id"] for item in found] == [2]
    titled = brief_from_source(
        {
            "id": 8,
            "name": "CMDB实例",
            "chart_type": ["table"],
            "field_schema": [{"key": "bk_host_name", "title": "主机名", "value_type": "string"}],
        }
    )
    by_title = search_briefs([{"text": "主机名", "purpose": "visualization", "chartType": "table"}], [titled])
    assert [item["id"] for item in by_title] == [8]


def test_log_overview_search_is_scoped_to_the_log_semantic_domain():
    requirements = [
        {
            "text": "帮我搭建一个日志情况概览的仪表盘",
            "purpose": "visualization",
            "domain": "CMDB",  # 模型提出错误领域时，用户原话仍是主证据。
        }
    ]
    briefs = [
        {
            "id": 192,
            "name": "日志命中数",
            "tags": ["日志"],
            "chart_type": ["line", "single"],
            "fields": [],
            "params": [],
        },
        {
            "id": 218,
            "name": "CMDB 覆盖概览",
            "tags": ["CMDB"],
            "chart_type": ["single", "gauge"],
            "fields": [{"name": "model_count", "type": "number", "desc": "模型数量"}],
            "params": [],
        },
        {
            "id": 232,
            "name": "数据治理健康度概览",
            "tags": ["CMDB"],
            "chart_type": ["single", "gauge"],
            "fields": [{"name": "total_health_score", "type": "number", "desc": "健康度"}],
            "params": [],
        },
        {
            "id": 264,
            "name": "日志用法总览",
            "desc": "日志采集实例、提取规则和告警规则概览",
            "tags": ["日志"],
            "chart_type": ["single", "gauge"],
            "fields": [{"name": "collect_instance_count", "type": "number", "desc": "日志采集实例数"}],
            "params": [],
        },
    ]

    found = search_briefs(requirements, briefs)

    assert found[0]["id"] == 264
    assert {tag for item in found for tag in item["tags"]} == {"日志"}
    assert {item["id"] for item in found}.isdisjoint({218, 232})


def test_unknown_overview_does_not_match_an_unrelated_overview_source():
    found = search_briefs(
        [{"text": "订单收入概览", "purpose": "visualization", "analysisType": "overview"}],
        [
            {
                "id": 218,
                "name": "CMDB 覆盖概览",
                "tags": ["CMDB"],
                "chart_type": ["single"],
                "fields": [{"name": "model_count", "type": "number", "desc": "模型数量"}],
                "params": [],
            }
        ],
    )

    assert found == []


def test_prepare_drops_alias_used_as_param_value_and_marks_table_columns_visible():
    briefs = [
        brief_from_source(
            {
                "id": 197,
                "name": "主机资源使用率Top10",
                "chart_type": ["table", "topN"],
                "field_schema": [{"key": "rank"}, {"key": "display_name"}],
                "params": [
                    {"name": "metric_type", "alias_name": "指标类型", "filterType": "fixed", "value": "cpu"},
                    {"name": "instance_ids", "alias_name": "主机", "type": "string", "filterType": "filter"},
                ],
            }
        )
    ]
    prepared = prepare_dashboard_proposal(
        {
            "schemaVersion": "1.0",
            "layout": [
                {
                    "i": "ai-197",
                    "valueConfig": {
                        "chartType": "table",
                        "dataSource": 197,
                        "dataSourceParams": [{"name": "instance_ids", "value": "主机"}],
                        "tableConfig": {"columns": [{"key": "rank"}, {"key": "display_name"}]},
                    },
                },
                {
                    "i": "ai-197-list",
                    "valueConfig": {
                        "chartType": "topN",
                        "dataSource": 197,
                        "dataSourceParams": [{"name": "instance_ids", "value": ["主机"]}],
                    },
                },
            ],
            "filters": [],
        },
        briefs,
    )
    assert prepared["ok"] is True
    params = {item["name"]: item for item in prepared["proposal"]["layout"][0]["valueConfig"]["dataSourceParams"]}
    assert params["instance_ids"].get("value") in (None, "")
    list_params = {item["name"]: item for item in prepared["proposal"]["layout"][1]["valueConfig"]["dataSourceParams"]}
    assert list_params["instance_ids"].get("value") == []
    assert params["metric_type"]["value"] == "cpu"
    columns = prepared["proposal"]["layout"][0]["valueConfig"]["tableConfig"]["columns"]
    assert columns[0]["visible"] is True
    assert columns[0]["title"] == "rank"
    assert columns[1]["order"] == 1


def test_prepare_accepts_list_param_value_on_second_pass():
    brief = brief_from_source(
        {
            "id": 267,
            "name": "主机资源快照",
            "chart_type": ["single"],
            "field_schema": [{"key": "host_count", "value_type": "number", "title": "主机数"}],
            "params": [{"name": "instance_ids", "alias_name": "主机", "filterType": "filter", "value": []}],
        }
    )
    first = prepare_dashboard_proposal(
        {
            "schemaVersion": "1.0",
            "layout": [{"i": "ai-267", "name": "主机数", "valueConfig": {"chartType": "single", "dataSource": 267, "selectedFields": ["host_count"]}}],
            "filters": [],
        },
        [brief],
    )
    assert first["ok"] is True
    second = prepare_dashboard_proposal(first["proposal"], [brief])
    assert second["ok"] is True


def test_prepare_fills_fixed_default_and_rejects_unknown_chart():
    briefs = [
        brief_from_source(
            {
                "id": 2,
                "name": "资产统计",
                "chart_type": ["single"],
                "field_schema": [{"name": "value"}],
                "params": [{"name": "organization_id", "filterType": "fixed", "value": "org-001", "required": True}],
            }
        )
    ]
    prepared = prepare_dashboard_proposal(
        {
            "schemaVersion": "1.0",
            "layout": [{"i": "card-1", "valueConfig": {"chartType": "single", "dataSource": 2, "selectedFields": ["value"]}}],
            "filters": [],
        },
        briefs,
    )
    assert prepared["ok"] is True
    assert prepared["proposal"]["layout"][0]["valueConfig"]["dataSourceParams"][0]["value"] == "org-001"

    quoted = prepare_dashboard_proposal(
        {
            "schemaVersion": "1.0",
            "layout": [{"i": "card-1", "valueConfig": {"chartType": "single", "dataSource": "2", "selectedFields": ["value"]}}],
            "filters": [],
        },
        briefs,
    )
    assert quoted["ok"] is True
    assert quoted["proposal"]["layout"][0]["valueConfig"]["dataSource"] == 2

    rejected = prepare_dashboard_proposal(
        {"schemaVersion": "1.0", "layout": [{"valueConfig": {"chartType": "networkStatusTopology", "dataSource": 2}}], "filters": []},
        briefs,
    )
    assert rejected["ok"] is False
    assert rejected["reason"] == "chart_type"

    mixed = prepare_dashboard_proposal(
        {
            "schemaVersion": "1.0",
            "layout": [
                {"i": "topo-1", "valueConfig": {"chartType": "networkStatusTopology"}},
                {"i": "card-1", "valueConfig": {"chartType": "single", "dataSource": 2, "selectedFields": ["value"]}},
            ],
            "filters": [],
        },
        briefs,
    )
    assert mixed["ok"] is True
    assert [item["i"] for item in mixed["proposal"]["layout"]] == ["card-1"]

    missing = prepare_dashboard_proposal(
        {
            "schemaVersion": "1.0",
            "layout": [
                {"i": "topo-1", "valueConfig": {"chartType": "networkStatusTopology"}},
                {"i": "card-2", "valueConfig": {"chartType": "single", "dataSource": 99, "selectedFields": ["value"]}},
            ],
            "filters": [],
        },
        briefs,
    )
    assert missing["ok"] is False
    assert missing["reason"] == "pending"
    assert missing["pending"][0]["reason"] == "datasource_not_found"


def test_capabilities_cover_datasource_widgets_and_exclude_scene_widgets():
    from apps.operation_analysis.services.dashboard_proposal_service import AI_CHART_TYPES, load_widget_capabilities

    payload = load_widget_capabilities()
    assert payload["schemaVersion"] == "1.0"
    assert "single" in AI_CHART_TYPES
    assert "topologyMap" in AI_CHART_TYPES
    assert "networkStatusTopology" not in AI_CHART_TYPES
    assert len(AI_CHART_TYPES) == 14


def test_edit_state_section_is_dropped_instead_of_truncated():
    from apps.opspilot.services.skill_channel_chat_service import _sanitize_page_context

    marker = "EDITSTATE_MARKER"
    snapshot = _sanitize_page_context(
        {
            "title": "盘",
            "sections": [
                {
                    "id": "dashboard-edit-state",
                    "label": "仪表盘编辑状态",
                    "content": marker + ("x" * 9000),
                    "priority": 100,
                    "atomic": True,
                }
            ],
        }
    )
    assert snapshot is not None
    assert all(marker not in section["content"] for section in snapshot["sections"])


def test_list_visible_briefs_keeps_only_current_org(monkeypatch):
    class Tags:
        def all(self):
            return []

    class Source:
        def __init__(self, source_id, groups):
            self.id = source_id
            self.name = "资产统计" if source_id == 2 else "其他组织"
            self.desc = ""
            self.chart_type = ["single"]
            self.params = [{"name": "organization_id", "filterType": "fixed", "value": "org-001", "required": True}]
            self.field_schema = [{"name": "value"}]
            self.groups = groups
            self.is_build_in = False
            self.tag = Tags()

    class Query:
        def __init__(self):
            self.sources = [
                Source(2, [7]),
                Source(3, [8]),
                Source(4, []),
            ]
            self.sources[2].is_build_in = True
            self.sources[2].name = "内置概览"
            self.filtered = False
            self.limited = None

        def filter(self, query):
            self.filtered = True
            text = str(query)
            assert "groups__contains" in text
            assert "is_build_in" in text
            return self

        def only(self, *fields):
            assert fields == ("id", "name", "desc", "chart_type", "params", "field_schema")
            return self

        def prefetch_related(self, *_args):
            return self

        def order_by(self, *fields):
            assert fields == ("id",)
            return self

        def __getitem__(self, item):
            from apps.operation_analysis.services.dashboard_proposal_service import VISIBLE_BRIEF_LIMIT

            assert item == slice(None, VISIBLE_BRIEF_LIMIT)
            self.limited = item.stop
            return self

        def __iter__(self):
            assert self.filtered
            assert self.limited == 500
            from apps.operation_analysis.common.datasource_visibility import can_access_datasource_in_org

            return iter(source for source in self.sources if can_access_datasource_in_org(source, 7))

    class Model:
        objects = Query()

    monkeypatch.setattr(
        "apps.operation_analysis.models.datasource_models.DataSourceAPIModel",
        Model,
    )
    from apps.operation_analysis.services.dashboard_proposal_service import list_visible_briefs

    briefs = list_visible_briefs(7)
    assert [item["id"] for item in briefs] == [2, 4]
    prepared = prepare_dashboard_proposal(
        {
            "schemaVersion": "1.0",
            "layout": [
                {
                    "i": "card-1",
                    "valueConfig": {"chartType": "single", "dataSource": 2, "selectedFields": ["value"]},
                }
            ],
            "filters": [],
        },
        briefs,
    )
    assert prepared["ok"] is True
    assert prepared["proposal"]["layout"][0]["valueConfig"]["dataSourceParams"][0]["value"] == "org-001"


def test_topn_picks_label_and_metric_not_schema_order():
    from apps.operation_analysis.services.dashboard_proposal_service import draft_proposal_from_candidates

    draft = draft_proposal_from_candidates(
        [
            {
                "id": 197,
                "name": "主机资源使用率Top10",
                "chart_type": ["topN"],
                "fields": [
                    {"name": "rank", "type": "integer", "desc": "排名"},
                    {"name": "display_name", "type": "string", "desc": "主机"},
                    {"name": "usage_percent", "type": "number", "desc": "使用率"},
                ],
                "params": [],
            }
        ]
    )
    config = draft["layout"][0]["valueConfig"]
    assert config["topNLabelField"] == "display_name"
    assert config["topNValueField"] == "usage_percent"
    assert draft["layout"][0]["w"] == 4
    assert draft["layout"][0]["h"] == 3
    assert draft["filters"] == []


def test_line_does_not_split_metric_type_into_multiple_widgets():
    from apps.operation_analysis.services.dashboard_proposal_service import draft_proposal_from_candidates

    draft = draft_proposal_from_candidates(
        [
            {
                "id": 19,
                "name": "主机指标趋势",
                "chart_type": ["line", "bar"],
                "fields": [],
                "params": [
                    {
                        "name": "metric_type",
                        "inputConfig": {
                            "control": "select",
                            "optionsSource": {
                                "type": "static",
                                "staticItems": [
                                    {"label": "CPU", "value": "cpu"},
                                    {"label": "内存", "value": "mem"},
                                ],
                            },
                        },
                    }
                ],
            }
        ]
    )
    assert len(draft["layout"]) == 1
    assert draft["layout"][0]["valueConfig"]["chartType"] == "line"
    assert "dataSourceParams" not in draft["layout"][0]["valueConfig"]


def test_drop_named_widget_keeps_other_ids():
    from apps.operation_analysis.services.dashboard_proposal_service import drop_named_widgets

    revised = drop_named_widgets(
        {
            "schemaVersion": "1.0",
            "layout": [
                {"i": "ai-267-host_count", "name": "主机资源快照 主机数", "valueConfig": {"chartType": "single"}},
                {"i": "ai-267-avg_cpu", "name": "主机资源快照 平均CPU(%)", "valueConfig": {"chartType": "single"}},
            ],
            "filters": [{"id": "department__string", "name": "使用部门"}],
        },
        "去掉主机资源快照 主机数这个单值组件",
    )
    assert [item["i"] for item in revised["layout"]] == ["ai-267-avg_cpu"]
    assert revised["filters"] == [{"id": "department__string", "name": "使用部门"}]
    assert revised["layout"][0].get("x") is None


def test_edit_state_round_trips_widget_ids():
    from apps.operation_analysis.services.dashboard_proposal_service import proposal_from_edit_state

    proposal = proposal_from_edit_state(
        "去掉主机数\n## 仪表盘编辑状态\ndashboardId: 424\nname: 1\nwidgets:\n"
        "- id=ai-267-host_count name=主机资源快照 主机数 chart=single dataSource=267 fields=selected:host_count params=instance_ids= bindings= pos=0,0,6,4\n"
        "- id=ai-267-avg_cpu name=主机资源快照 平均CPU(%) chart=single dataSource=267 fields=selected:avg_cpu params=instance_ids= bindings= pos=4,0,6,4\n"
        "scenes:\n- none\n"
    )
    assert [item["i"] for item in proposal["layout"]] == ["ai-267-host_count", "ai-267-avg_cpu"]
    assert proposal["layout"][0]["valueConfig"]["selectedFields"] == ["host_count"]
    assert proposal["layout"][1]["x"] == 4


def test_draft_packs_three_widgets_per_row_and_keeps_source_description():
    from apps.operation_analysis.services.dashboard_proposal_service import draft_proposal_from_candidates, format_proposal_inventory

    draft = draft_proposal_from_candidates(
        [
            {
                "id": 11,
                "name": "告警趋势A",
                "desc": "当前告警数量随时间变化",
                "chart_type": ["line"],
                "fields": [],
                "params": [],
            },
            {
                "id": 12,
                "name": "告警趋势B",
                "desc": "告警等级随时间变化",
                "chart_type": ["line"],
                "fields": [],
                "params": [],
            },
            {
                "id": 13,
                "name": "告警趋势C",
                "desc": "告警处理健康度",
                "chart_type": ["line"],
                "fields": [],
                "params": [],
            },
            {
                "id": 14,
                "name": "告警来源分布",
                "desc": "按来源查看告警占比",
                "chart_type": ["pie"],
                "fields": [
                    {"name": "name", "type": "string", "desc": "来源"},
                    {"name": "value", "type": "number", "desc": "数量"},
                ],
                "params": [],
            },
        ]
    )
    assert [(item["x"], item["y"], item["w"], item["h"]) for item in draft["layout"]] == [
        (0, 0, 4, 3),
        (4, 0, 4, 3),
        (8, 0, 4, 3),
        (0, 3, 4, 3),
    ]
    assert draft["layout"][0]["description"] == "当前告警数量随时间变化"
    text = format_proposal_inventory(draft)
    assert "组件清单" in text
    assert "说明: 当前告警数量随时间变化" in text
    assert "图表类型: line" in text
    assert "数据源: 11" in text
    assert "告警来源分布" in text
    assert "字段: name、value" in text


def test_revise_renames_keeps_position_and_reflows_width():
    from apps.operation_analysis.services.dashboard_proposal_service import (
        format_proposal_inventory,
        prepare_dashboard_proposal,
        revise_dashboard_proposal,
    )

    current = {
        "schemaVersion": "1.0",
        "layout": [
            {
                "i": "card-1",
                "name": "资产总数",
                "x": 0,
                "y": 0,
                "w": 6,
                "h": 3,
                "valueConfig": {"chartType": "single", "dataSource": 2, "selectedFields": ["value"]},
            },
            {
                "i": "card-2",
                "name": "资产分布",
                "x": 6,
                "y": 0,
                "w": 6,
                "h": 3,
                "valueConfig": {"chartType": "pie", "dataSource": 3, "selectedFields": ["name"]},
            },
            {
                "i": "card-3",
                "name": "资产明细",
                "x": 0,
                "y": 3,
                "w": 12,
                "h": 3,
                "valueConfig": {"chartType": "table", "dataSource": 4, "selectedFields": ["name"]},
            },
        ],
        "filters": [{"id": "org", "name": "组织"}],
    }
    renamed = revise_dashboard_proposal(current, "把资产总数的标题改成今日资产")
    assert renamed["layout"][0]["name"] == "今日资产"
    assert renamed["layout"][0]["x"] == 0
    assert renamed["layout"][0]["w"] == 6
    assert renamed["filters"][0]["id"] == "org"
    widened = revise_dashboard_proposal(current, "把布局改成每行的宽度为4")
    assert [item["w"] for item in widened["layout"]] == [4, 4, 4]
    assert widened["layout"][1]["x"] == 4
    two_per_row = revise_dashboard_proposal(current, "调整成一行两个组件")
    assert [item["w"] for item in two_per_row["layout"]] == [6, 6, 6]
    assert [(item["x"], item["y"]) for item in two_per_row["layout"]] == [(0, 0), (6, 0), (0, 3)]
    four_per_row = revise_dashboard_proposal(current, "调整布局 一行四个组件")
    assert [item["w"] for item in four_per_row["layout"]] == [3, 3, 3]
    inventory = format_proposal_inventory(four_per_row)
    assert "布局：每行最多 4 个组件，每个宽 3、高 3。" in inventory
    brief = {
        "id": 2,
        "name": "资产统计",
        "chart_type": ["single", "bar"],
        "fields": [{"name": "value"}],
        "params": [],
        "option_ready": False,
    }
    prepared = prepare_dashboard_proposal(
        renamed,
        [
            brief,
            {"id": 3, "name": "分布", "chart_type": ["pie"], "fields": [{"name": "name"}], "params": []},
            {"id": 4, "name": "明细", "chart_type": ["table"], "fields": [{"name": "name"}], "params": []},
        ],
    )
    assert prepared["ok"] is True
    assert prepared["proposal"]["layout"][0]["w"] == 6
    chart = revise_dashboard_proposal(current, "把资产总数改成柱状图")
    assert chart["layout"][0]["valueConfig"]["chartType"] == "bar"


def test_inventory_describes_four_columns_when_widget_heights_differ():
    from apps.operation_analysis.services.dashboard_proposal_service import format_proposal_inventory, revise_dashboard_proposal

    current = {
        "schemaVersion": "1.0",
        "layout": [
            {
                "i": "trend",
                "name": "告警趋势",
                "x": 0,
                "y": 0,
                "w": 4,
                "h": 3,
                "valueConfig": {"chartType": "line", "dataSource": 193},
            },
            {
                "i": "source",
                "name": "告警来源分布",
                "x": 4,
                "y": 0,
                "w": 4,
                "h": 6,
                "valueConfig": {"chartType": "pie", "dataSource": 214},
            },
        ],
        "filters": [],
    }

    revised = revise_dashboard_proposal(current, "调整当前仪表盘为一行四个组件")
    inventory = format_proposal_inventory(revised)

    assert [(item["w"], item["h"]) for item in revised["layout"]] == [(3, 3), (3, 6)]
    assert "布局：每行最多 4 个组件，每个宽 3；组件高度保持各自设置。" in inventory
    assert "保留方案中各组件的位置与尺寸" not in inventory


def test_classify_implicit_widget_goal_without_chart_noun():
    from apps.operation_analysis.services.dashboard_proposal_service import classify_dashboard_request

    assert classify_dashboard_request("新增一个cmdb的模型实例分类统计") == "extend"
    assert classify_dashboard_request("帮我新增一个cmdb数据概览的仪表盘") == "build"
    assert classify_dashboard_request("在当前仪表盘上新增一个概览") == "extend"
    assert classify_dashboard_request("新增一个概览图表") == "extend"
    assert classify_dashboard_request("增加告警趋势") == "extend"
    assert classify_dashboard_request("补充主机明细") == "extend"
    assert classify_dashboard_request("新增一个CMDB模型") == "none"
    assert classify_dashboard_request("新增用户") == "none"


def test_add_on_an_existing_dashboard_keeps_current_widgets():
    from apps.opspilot.metis.llm.tools.dashboard_proposal_memory import proposal_for_prepare

    existing = {
        "i": "kept",
        "name": "主机数",
        "x": 0,
        "y": 0,
        "w": 4,
        "h": 3,
        "valueConfig": {"chartType": "single", "dataSource": 3},
    }
    snapshot = json.dumps(
        {"snapshotVersion": "1.0", "dashboardId": "dashboard_2", "layout": [existing], "filters": []},
        ensure_ascii=False,
    )
    message = f"帮我新增一个cmdb数据概览的仪表盘\n\n## 仪表盘编辑状态\n{snapshot}"
    prepared = proposal_for_prepare(
        1,
        message,
        [
            {
                "id": 11,
                "name": "模型实例数",
                "desc": "CMDB 模型实例数量",
                "chart_type": ["single"],
                "fields": [{"name": "value", "type": "number", "desc": "数量"}],
                "params": [],
            }
        ],
    )

    assert [item["i"] for item in prepared["layout"]][0] == "kept"
    assert len(prepared["layout"]) > 1


def test_add_onto_an_empty_existing_dashboard_places_widgets():
    from apps.opspilot.metis.llm.tools.dashboard_proposal_memory import proposal_for_prepare

    snapshot = json.dumps(
        {"snapshotVersion": "1.0", "dashboardId": "dashboard_2", "layout": [], "filters": []},
        ensure_ascii=False,
    )
    message = f"新增一个告警趋势\n\n## 仪表盘编辑状态\n{snapshot}"
    prepared = proposal_for_prepare(
        1,
        message,
        [
            {
                "id": 21,
                "name": "告警趋势",
                "desc": "告警数量随时间变化",
                "chart_type": ["line"],
                "fields": [],
                "params": [],
            }
        ],
    )

    assert prepared.get("reply") is None
    assert prepared["layout"][0]["valueConfig"]["dataSource"] == 21


def test_required_param_uses_a_matching_choice_and_otherwise_asks():
    from apps.operation_analysis.services.dashboard_proposal_service import fill_confirmed_param_values, proposal_has_param_gaps

    brief = {
        "id": 9,
        "params": [
            {
                "name": "bucket",
                "alias_name": "统计口径",
                "required": True,
                "filterType": "params",
                "inputConfig": {
                    "optionsSource": {
                        "type": "static",
                        "staticItems": [
                            {"label": "按模型", "value": "model"},
                            {"label": "按分类", "value": "classification"},
                        ],
                    }
                },
            }
        ],
    }
    proposal = {
        "schemaVersion": "1.0",
        "layout": [{"i": "a", "name": "数量图", "valueConfig": {"chartType": "multiValue", "dataSource": 9}}],
        "filters": [],
    }
    filled, gaps, notes = fill_confirmed_param_values(proposal, [brief], "确认")
    assert gaps == []
    assert filled["layout"][0]["valueConfig"]["dataSourceParams"][0]["value"] == "model"
    chosen, gaps, notes = fill_confirmed_param_values(proposal, [brief], "按分类")
    assert gaps == []
    assert chosen["layout"][0]["valueConfig"]["dataSourceParams"][0]["value"] == "classification"

    second = {
        "id": 10,
        "params": [{"name": "region", "alias_name": "地区", "required": True, "filterType": "params"}],
    }
    both = {
        "schemaVersion": "1.0",
        "layout": [
            {"i": "a", "name": "数量图", "valueConfig": {"chartType": "multiValue", "dataSource": 9}},
            {"i": "b", "name": "地区图", "valueConfig": {"chartType": "multiValue", "dataSource": 10}},
        ],
        "filters": [],
    }
    partial, gaps, notes = fill_confirmed_param_values(both, [brief, second], "华东")
    assert gaps == []
    assert partial["layout"][0]["valueConfig"]["dataSourceParams"][0]["value"] == "model"
    assert partial["layout"][1]["valueConfig"]["dataSourceParams"][0]["value"] == "华东"
    assert proposal_has_param_gaps(partial) is False


def test_explicit_relative_time_overrides_the_datasource_default():
    from apps.operation_analysis.services.dashboard_proposal_service import fill_confirmed_param_values

    brief = {
        "id": 193,
        "params": [
            {
                "name": "time",
                "alias_name": "时间范围",
                "type": "timeRange",
                "filterType": "filter",
                "required": False,
                "default": 10080,
            }
        ],
    }
    proposal = {
        "schemaVersion": "1.0",
        "layout": [
            {
                "i": "alarm-trend",
                "name": "告警数量趋势",
                "valueConfig": {
                    "chartType": "line",
                    "dataSource": 193,
                    "dataSourceParams": [{"name": "time", "type": "timeRange", "value": 10080}],
                },
            }
        ],
        "filters": [],
    }

    filled, gaps, notes = fill_confirmed_param_values(
        proposal,
        [brief],
        "我希望新增一个可以按时间范围查看告警数的仪表盘，默认时间为30天",
    )

    assert gaps == []
    assert filled["layout"][0]["valueConfig"]["dataSourceParams"][0]["value"] == 43200
    assert any("30天" in note for note in notes)


def test_removal_ignores_the_explanation_after_the_title():
    from apps.operation_analysis.services.dashboard_proposal_service import revise_dashboard_proposal

    current = {
        "schemaVersion": "1.0",
        "layout": [
            {"i": "a", "name": "告警趋势", "valueConfig": {"chartType": "line"}},
            {"i": "b", "name": "数据治理健康度趋势", "valueConfig": {"chartType": "line"}},
        ],
        "filters": [{"id": "org", "name": "组织"}],
    }
    revised = revise_dashboard_proposal(current, "去掉数据治理健康度趋势，这不是告警的数据")
    assert [item["name"] for item in revised["layout"]] == ["告警趋势"]
    assert revised["filters"][0]["id"] == "org"
