from apps.workflow_orchestration.services.demo_showcase import build_health_inspection_showcase_workflow


def test_health_showcase_workflow_binds_format_specific_template_and_script():
    snapshot = {
        "object_key": "workflow-orchestration/templates/demo/team-1/health.docx",
        "format": "docx",
        "sha256": "b" * 64,
        "size": 256,
        "filename_prefix": "health-inspection-docx",
    }

    item = build_health_inspection_showcase_workflow(
        team_id=1,
        channel_id=3,
        username="admin",
        fmt="docx",
        template_snapshot=snapshot,
        script_type="powershell",
        script_content="Write-Output ok",
        operating_system="windows",
    )

    assert item["key"] == "health_docx"
    assert item["name"] == "[TDD/BDD] Windows 主机巡检 Word"
    tasks = item["definition"]["tasks"]
    assert tasks[0]["inputParameters"]["script_type"] == "powershell"
    assert tasks[0]["inputParameters"]["script_content"] == "Write-Output ok"
    assert tasks[1]["inputParameters"]["template_snapshot"]["format"] == "docx"
    assert tasks[2]["inputParameters"]["channel_id"] == 3
    assert tasks[2]["inputParameters"]["recipients"] == ["admin"]
    targets = item["metadata"]["trigger_nodes"][0]["input_schema"]["properties"]["targets"]
    assert targets["x-target-binding"]["allowedOperatingSystems"] == ["windows"]


def test_linux_excel_showcase_restricts_targets_to_linux():
    snapshot = {
        "object_key": "workflow-orchestration/templates/demo/team-1/health.xlsx",
        "format": "xlsx",
        "sha256": "c" * 64,
        "size": 128,
        "filename_prefix": "health-inspection-xlsx",
    }
    item = build_health_inspection_showcase_workflow(
        team_id=1,
        channel_id=3,
        username="admin",
        fmt="xlsx",
        template_snapshot=snapshot,
        script_type="shell",
        script_content="echo ok",
        operating_system="linux",
    )
    assert item["name"] == "[TDD/BDD] Linux 主机巡检 Excel"
    assert item["definition"]["tasks"][0]["inputParameters"]["script_type"] == "shell"
    targets = item["metadata"]["trigger_nodes"][0]["input_schema"]["properties"]["targets"]
    assert targets["x-target-binding"]["allowedOperatingSystems"] == ["linux"]


def test_health_showcase_workflow_rejects_mismatched_template_format():
    try:
        build_health_inspection_showcase_workflow(
            team_id=1,
            channel_id=1,
            username="admin",
            fmt="xlsx",
            template_snapshot={
                "object_key": "workflow-orchestration/templates/demo/team-1/health.docx",
                "format": "docx",
                "sha256": "c" * 64,
                "size": 128,
                "filename_prefix": "health",
            },
            script_type="powershell",
            script_content="Write-Output ok",
        )
    except ValueError as error:
        assert "模板快照与目标格式不一致" in str(error)
    else:
        raise AssertionError("expected ValueError")
