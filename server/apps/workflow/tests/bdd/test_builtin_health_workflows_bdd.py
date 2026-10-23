from __future__ import annotations

import hashlib
from io import StringIO
from pathlib import Path

import pytest
from django.core.management import call_command
from django.core.management.base import CommandError
from pytest_bdd import given, scenarios, then, when

from apps.system_mgmt.models import Channel, ChannelChoices
from apps.workflow.models import Workflow, WorkflowTrigger
from apps.workflow.services.builtin_workflows import BUILTIN_EXECUTOR_RECIPIENT, BUILTIN_LINUX_KEY, BUILTIN_WINDOWS_KEY, builtin_engine_name
from apps.workflow.services.conductor import ConductorUnavailable
from apps.workflow.services.demo_templates import builtin_health_template_path

FEATURE = str(Path(__file__).parent / "builtin_health_workflows.feature")
scenarios(FEATURE)

pytestmark = [pytest.mark.bdd, pytest.mark.django_db]

WINDOWS_NAME = "Windows 主机巡检（Word）"
LINUX_NAME = "Linux 主机巡检（Excel）"


class MemoryObjectStore:
    def __init__(self):
        self.objects: dict[str, bytes] = {}

    def put(self, key: str, content) -> None:
        payload = content.read() if hasattr(content, "read") else content
        self.objects[key] = bytes(payload)


class RecordingConductor:
    def __init__(self):
        self.workflows: list[dict] = []

    def register_task_definitions(self, definitions) -> None:
        self.task_definitions = definitions

    def register_workflow(self, definition) -> None:
        self.workflows.append(definition)


class UnavailableConductor:
    def __init__(self):
        raise ConductorUnavailable("conductor down")


@pytest.fixture
def ctx(authenticated_user, mocker):
    store = MemoryObjectStore()
    conductor = RecordingConductor()
    mocker.patch("apps.workflow.services.demo_templates.WorkflowObjectStore", return_value=store)
    mocker.patch("apps.workflow.services.builtin_workflows.ConductorClient", return_value=conductor)
    return {
        "user": authenticated_user,
        "team_id": 1,
        "other_team_id": 2,
        "store": store,
        "conductor": conductor,
        "error": None,
        "mocker": mocker,
    }


def _init(ctx, team_id):
    try:
        call_command(
            "init_workflow_builtins",
            team_ids=[team_id],
            username=ctx["user"].username,
            domain=ctx["user"].domain,
            stdout=StringIO(),
        )
    except CommandError as error:
        ctx["error"] = error


def _builtins(team_id):
    return list(Workflow.objects.filter(is_builtin=True, team=[team_id]).order_by("name"))


def _task_inputs(workflow: Workflow, reference: str) -> dict:
    for task in workflow.definition.get("tasks") or []:
        if task.get("taskReferenceName") == reference:
            return task["inputParameters"]
    raise AssertionError(f"{workflow.name} 缺少节点 {reference}")


def _allowed_systems(workflow: Workflow) -> list[str]:
    binding = workflow.canvas_metadata["input_schema"]["properties"]["targets"]["x-target-binding"]
    return list(binding["allowedOperatingSystems"])


@given("当前团队有一个可用的邮件渠道")
def email_channel(ctx):
    ctx["channel"] = Channel.objects.create(
        name="巡检邮箱",
        channel_type=ChannelChoices.EMAIL,
        config={"smtp_server": "127.0.0.1", "port": 1025},
        description="",
        team=[ctx["team_id"]],
    )


@given("当前团队已有一条用户自己的流程")
def user_workflow(ctx):
    ctx["user_workflow"] = Workflow.objects.create(
        name="用户自己的发布流程",
        team=[ctx["team_id"]],
        status=Workflow.Status.PUBLISHED,
        is_builtin=False,
        engine_name="bklite_workflow_user_owned",
    )


@given("流程引擎拒绝注册")
def conductor_down(ctx):
    ctx["mocker"].patch("apps.workflow.services.builtin_workflows.ConductorClient", UnavailableConductor)
    ctx["conductor"] = None


@when("管理员初始化当前团队的内置巡检")
def init_current_team(ctx):
    _init(ctx, ctx["team_id"])


@when("管理员初始化非法团队的内置巡检")
def init_illegal_team(ctx):
    _init(ctx, 0)


@when("管理员连续两次初始化当前团队的内置巡检")
def init_twice(ctx):
    _init(ctx, ctx["team_id"])
    ctx["first_ids"] = set(Workflow.objects.filter(is_builtin=True, team=[ctx["team_id"]]).values_list("pk", flat=True))
    _init(ctx, ctx["team_id"])


@when("管理员分别初始化当前团队和另一个团队的内置巡检")
def init_two_teams(ctx):
    _init(ctx, ctx["team_id"])
    _init(ctx, ctx["other_team_id"])


@then("应当生成 Windows Word 与 Linux Excel 两条已发布流程")
def two_published_builtins(ctx):
    assert ctx["error"] is None
    workflows = _builtins(ctx["team_id"])
    assert [item.name for item in workflows] == [LINUX_NAME, WINDOWS_NAME]
    assert {item.status for item in workflows} == {Workflow.Status.PUBLISHED}
    assert all(item.enabled and item.current_version == 1 and not item.has_draft for item in workflows)
    assert {item.engine_name for item in workflows} == {
        builtin_engine_name(ctx["team_id"], BUILTIN_LINUX_KEY),
        builtin_engine_name(ctx["team_id"], BUILTIN_WINDOWS_KEY),
    }
    for workflow in workflows:
        assert workflow.triggers.filter(trigger_type=WorkflowTrigger.Type.FORM).count() == 1


@then("两条流程应当挂载真实模板快照并限制对应操作系统")
def real_templates_and_operating_systems(ctx):
    windows = Workflow.objects.get(name=WINDOWS_NAME, team=[ctx["team_id"]])
    linux = Workflow.objects.get(name=LINUX_NAME, team=[ctx["team_id"]])
    expectations = (
        (windows, "powershell", "docx", ["windows"], "$ErrorActionPreference"),
        (linux, "shell", "xlsx", ["linux"], 'print("result="'),
    )
    for workflow, script_type, fmt, systems, marker in expectations:
        scan = _task_inputs(workflow, "scan")
        snapshot = _task_inputs(workflow, "report")["template_snapshot"]
        content = builtin_health_template_path(fmt).read_bytes()
        digest = hashlib.sha256(content).hexdigest()
        assert scan["script_type"] == script_type
        assert marker in scan["script_content"]
        assert "${" not in scan["script_content"]
        assert snapshot["format"] == fmt
        assert snapshot["sha256"] == digest
        assert snapshot["object_key"] == (f"workflow/templates/demo/team-{ctx['team_id']}/health-inspection-example-{digest[:16]}.{fmt}")
        assert ctx["store"].objects[snapshot["object_key"]] == content
        assert _allowed_systems(workflow) == systems


@then("通知步骤应当使用该邮件渠道且失败不阻断流程")
def notify_uses_channel(ctx):
    for workflow in _builtins(ctx["team_id"]):
        notify = next(task for task in workflow.definition["tasks"] if task["taskReferenceName"] == "notify")
        assert notify["optional"] is True
        assert notify["inputParameters"]["channel_id"] == ctx["channel"].id
        assert notify["inputParameters"]["recipients"] == [BUILTIN_EXECUTOR_RECIPIENT]


@then("通知步骤应当留空渠道且失败不阻断流程")
def notify_without_channel(ctx):
    for workflow in _builtins(ctx["team_id"]):
        notify = next(task for task in workflow.definition["tasks"] if task["taskReferenceName"] == "notify")
        assert notify["optional"] is True
        assert "channel_id" not in notify["inputParameters"]


@then("引擎应当收到这两条流程的注册")
def conductor_received_both(ctx):
    registered = {item["name"] for item in ctx["conductor"].workflows}
    assert registered == {
        builtin_engine_name(ctx["team_id"], BUILTIN_WINDOWS_KEY),
        builtin_engine_name(ctx["team_id"], BUILTIN_LINUX_KEY),
    }


@then("命令应当拒绝并且不留下内置流程")
def illegal_team_rejected(ctx):
    assert ctx["error"] is not None
    assert "team_id 非法" in str(ctx["error"])
    assert not Workflow.objects.filter(is_builtin=True).exists()


@then("内置流程应当仍是原来的两条且用户流程保留")
def idempotent_without_clobbering_user_workflow(ctx):
    assert ctx["error"] is None
    current_ids = set(Workflow.objects.filter(is_builtin=True, team=[ctx["team_id"]]).values_list("pk", flat=True))
    assert current_ids == ctx["first_ids"]
    assert len(current_ids) == 2
    assert Workflow.objects.filter(pk=ctx["user_workflow"].pk, name="用户自己的发布流程", is_builtin=False).exists()


@then("两个团队应当各自拥有两条内置流程且模板归属不串")
def teams_are_isolated(ctx):
    assert ctx["error"] is None
    assert len(_builtins(ctx["team_id"])) == 2
    assert len(_builtins(ctx["other_team_id"])) == 2
    first_keys = {item.engine_name for item in _builtins(ctx["team_id"])}
    second_keys = {item.engine_name for item in _builtins(ctx["other_team_id"])}
    assert first_keys.isdisjoint(second_keys)
    for team_id in (ctx["team_id"], ctx["other_team_id"]):
        for workflow in _builtins(team_id):
            snapshot = _task_inputs(workflow, "report")["template_snapshot"]
            assert f"/team-{team_id}/" in snapshot["object_key"]
            assert ctx["store"].objects[snapshot["object_key"]]


@then("引擎不应当留下已注册的流程")
def conductor_registered_nothing(ctx):
    assert ctx["conductor"] is None
    assert ctx["error"] is None
