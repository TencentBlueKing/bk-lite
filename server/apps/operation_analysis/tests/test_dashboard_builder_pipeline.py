from apps.operation_analysis.services.dashboard_builder_pipeline import (
    draft_proposal_for_requirements,
    plan_dashboard_requirements,
    unmatched_requirement_texts,
)


def test_explicit_dashboard_goals_are_split_with_deterministic_chart_types():
    planned = plan_dashboard_requirements("帮我搭一个仪表盘，展示资产总数、类型分布和资产明细")

    assert planned == [
        {"text": "资产总数", "purpose": "visualization", "chartType": "single"},
        {"text": "类型分布", "purpose": "visualization", "chartType": "pie"},
        {"text": "资产明细", "purpose": "visualization", "chartType": "table"},
    ]


def test_explicit_user_goals_override_a_broad_model_requirement():
    planned = plan_dashboard_requirements(
        "创建主机仪表盘，展示主机数量、CPU趋势和主机列表",
        [{"text": "主机总览", "purpose": "visualization"}],
    )

    assert [item["chartType"] for item in planned] == ["single", "line", "table"]
    assert [item["text"] for item in planned] == ["主机数量", "CPU趋势", "主机列表"]


def test_bare_followup_goal_list_is_split_without_an_introductory_verb():
    planned = plan_dashboard_requirements("告警等级分布、告警类型分布、告警来源分布")

    assert planned == [
        {"text": "告警等级分布", "purpose": "visualization", "chartType": "pie"},
        {"text": "告警类型分布", "purpose": "visualization", "chartType": "pie"},
        {"text": "告警来源分布", "purpose": "visualization", "chartType": "pie"},
    ]


def test_common_dashboard_utterances_keep_the_intended_granularity_and_chart_shape():
    cases = [
        (
            "创建告警大盘，展示告警数量、告警趋势、状态分布和告警明细",
            ["single", "line", "pie", "table"],
        ),
        ("展示CPU使用率Top10", ["topN"]),
        ("帮我搭一个主机资源仪表盘", [None]),
    ]

    for utterance, chart_types in cases:
        planned = plan_dashboard_requirements(utterance)
        assert [item.get("chartType") for item in planned] == chart_types


def test_time_scoped_dashboard_request_is_planned_as_a_trend():
    planned = plan_dashboard_requirements("我希望新增一个可以按时间范围查看告警数的仪表盘，默认时间为30天")

    assert planned[0]["chartType"] == "line"
    assert planned[0]["analysisType"] == "trend"


def test_category_statistics_without_chart_noun_is_planned_as_distribution():
    planned = plan_dashboard_requirements("新增一个cmdb的模型实例分类统计")

    assert planned[0]["chartType"] == "pie"
    assert planned[0]["analysisType"] == "distribution"


def test_parameter_option_requirement_is_preserved_for_the_search_stage():
    planned = plan_dashboard_requirements(
        "给我做个告警大盘",
        [
            {"text": "告警数据", "purpose": "visualization", "chartType": "pie"},
            {"text": "业务选项", "purpose": "parameter_options"},
        ],
    )

    assert planned == [
        {"text": "告警数据", "purpose": "visualization", "chartType": "pie"},
        {"text": "业务选项", "purpose": "parameter_options"},
    ]


def test_each_requirement_selects_one_source_and_single_uses_the_matching_field():
    requirements = plan_dashboard_requirements("展示资产总数、类型分布和资产明细")
    candidates = [
        {
            "id": 10,
            "name": "资产数量统计",
            "desc": "CMDB 资产数量",
            "tags": ["cmdb"],
            "chart_type": ["single"],
            "fields": [
                {"name": "policy_total", "desc": "策略数", "type": "number"},
                {"name": "asset_total", "desc": "资产总数", "type": "number"},
            ],
            "params": [],
        },
        {
            "id": 11,
            "name": "资产类型分布",
            "tags": ["cmdb"],
            "chart_type": ["pie"],
            "fields": [{"name": "model", "desc": "类型"}, {"name": "count", "desc": "数量"}],
            "params": [],
        },
        {
            "id": 12,
            "name": "资产明细",
            "tags": ["cmdb"],
            "chart_type": ["table"],
            "fields": [{"name": "name", "desc": "名称"}, {"name": "ip", "desc": "IP"}],
            "params": [],
        },
    ]

    proposal = draft_proposal_for_requirements(requirements, candidates)

    assert [item["valueConfig"]["dataSource"] for item in proposal["layout"]] == [10, 11, 12]
    assert [item["valueConfig"]["chartType"] for item in proposal["layout"]] == ["single", "pie", "table"]
    assert proposal["layout"][0]["valueConfig"]["selectedFields"] == ["asset_total"]


def test_unmatched_goal_is_reported_instead_of_substituting_another_dimension():
    requirements = plan_dashboard_requirements("告警等级分布、告警类型分布、告警来源分布")
    candidates = [
        {
            "id": 222,
            "name": "活跃告警等级分布",
            "tags": ["告警"],
            "chart_type": ["pie"],
            "fields": [{"name": "name", "desc": "等级"}, {"name": "value", "desc": "数量"}],
        },
        {
            "id": 214,
            "name": "告警按来源分布",
            "tags": ["告警"],
            "chart_type": ["pie"],
            "fields": [{"name": "name", "desc": "来源"}, {"name": "value", "desc": "数量"}],
        },
    ]

    assert unmatched_requirement_texts(requirements, candidates) == ["告警类型分布"]
