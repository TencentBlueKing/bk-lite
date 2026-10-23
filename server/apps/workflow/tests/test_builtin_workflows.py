import pytest
from django.contrib.auth import get_user_model
from rest_framework.test import APIRequestFactory

from apps.system_mgmt.models import Channel, ChannelChoices
from apps.workflow.models import Workflow, WorkflowExecution
from apps.workflow.services.builtin_workflows import (
    BUILTIN_EXECUTOR_RECIPIENT,
    BUILTIN_LINUX_KEY,
    BUILTIN_WINDOWS_KEY,
    builtin_engine_name,
    collapse_builtin_workflow_versions,
    ensure_builtin_health_workflows,
)
from apps.workflow.views import WorkflowViewSet


def _request(factory, method, path, user, data=None):
    request = getattr(factory, method)(path, data=data, format="json")
    request.user = user
    request.COOKIES = {"current_team": "1"}
    return request


@pytest.fixture
def builtin_user(db):
    return get_user_model().objects.create(
        username="admin",
        domain="domain.com",
        password="x",
        is_superuser=True,
        group_list=[{"id": 1, "name": "Default"}],
    )


@pytest.fixture
def builtin_channels(db):
    nats = Channel.objects.create(
        name="告警中心",
        channel_type=ChannelChoices.NATS,
        config={"method_name": "receive_alert_events"},
        description="",
        team=[1],
    )
    later = Channel.objects.create(
        name="zzz邮箱",
        channel_type=ChannelChoices.EMAIL,
        config={"smtp_server": "127.0.0.1", "port": 1025},
        description="",
        team=[1],
    )
    first = Channel.objects.create(
        name="aaa邮箱",
        channel_type=ChannelChoices.EMAIL,
        config={"smtp_server": "127.0.0.1", "port": 1025},
        description="",
        team=[1],
    )
    return {"nats": nats, "email_first": first, "email_later": later}


def _patch_builtin_deps(mocker):
    mocker.patch("apps.workflow.services.builtin_workflows.ConductorClient").return_value
    mocker.patch(
        "apps.workflow.services.builtin_workflows.seed_builtin_health_template_snapshot",
        side_effect=lambda fmt, team_id: {
            "object_key": f"workflow/templates/demo/team-{team_id}/health.{fmt}",
            "format": fmt,
            "sha256": "a" * 64,
            "size": 128,
            "filename_prefix": f"health-{fmt}",
        },
    )
    mocker.patch("apps.workflow.services.builtin_workflows.ensure_platform_atom")
    mocker.patch("apps.workflow.services.builtin_workflows.sync_published_triggers")


@pytest.mark.django_db
def test_ensure_builtin_health_workflows_are_idempotent(builtin_user, builtin_channels, mocker):
    _patch_builtin_deps(mocker)

    first = ensure_builtin_health_workflows(team_id=1, username=builtin_user.username, domain=builtin_user.domain)
    second = ensure_builtin_health_workflows(team_id=1, username=builtin_user.username, domain=builtin_user.domain)

    assert len(first) == 2
    assert {item.engine_name for item in first} == {
        builtin_engine_name(1, BUILTIN_WINDOWS_KEY),
        builtin_engine_name(1, BUILTIN_LINUX_KEY),
    }
    assert Workflow.objects.filter(is_builtin=True, team=[1]).count() == 2
    assert {item.pk for item in second} == {item.pk for item in first}
    assert all(not item.has_draft and item.enabled and item.current_version == 1 for item in second)
    descriptions = {item.name: item.description for item in second}
    assert descriptions["Linux 主机巡检（Excel）"] == "选择 Linux 主机采集后生成 Excel 巡检报告并通知。"
    assert descriptions["Windows 主机巡检（Word）"] == "选择 Windows 主机采集后生成 Word 巡检报告并通知。"
    notify = first[0].definition["tasks"][3]["inputParameters"]
    assert notify["channel_id"] == builtin_channels["email_first"].id
    assert notify["recipients"] == [BUILTIN_EXECUTOR_RECIPIENT]
    for workflow in first:
        positions = workflow.canvas_metadata["positions"]
        assert {positions[key]["y"] for key in ("trigger_form", "scan", "summarize", "report", "notify")} == {260}


@pytest.mark.django_db
def test_ensure_builtin_publishes_next_version_when_template_snapshot_changes(builtin_user, builtin_channels, mocker):
    snapshots = {"generation": "first"}

    def snapshot(fmt, team_id):
        return {
            "object_key": f"workflow/templates/demo/team-{team_id}/health-{snapshots['generation']}.{fmt}",
            "format": fmt,
            "sha256": "a" * 64,
            "size": 128,
            "filename_prefix": f"health-{fmt}",
        }

    mocker.patch("apps.workflow.services.builtin_workflows.ConductorClient").return_value
    mocker.patch("apps.workflow.services.builtin_workflows.seed_builtin_health_template_snapshot", side_effect=snapshot)
    mocker.patch("apps.workflow.services.builtin_workflows.ensure_platform_atom")
    mocker.patch("apps.workflow.services.builtin_workflows.sync_published_triggers")

    first = ensure_builtin_health_workflows(team_id=1, username=builtin_user.username, domain=builtin_user.domain)
    snapshots["generation"] = "second"
    second = ensure_builtin_health_workflows(team_id=1, username=builtin_user.username, domain=builtin_user.domain)

    assert [item.current_version for item in first] == [1, 1]
    assert [item.current_version for item in second] == [2, 2]
    linux = next(item for item in second if item.engine_name == builtin_engine_name(1, BUILTIN_LINUX_KEY))
    script = linux.definition["tasks"][0]["inputParameters"]["script_content"]
    assert linux.definition["tasks"][0]["inputParameters"]["script_type"] == "python"
    assert script.startswith("#!/usr/bin/env python3\n")
    assert "#!/bin/bash" not in script
    assert 'print("result="' in script
    assert "BK_LITE_RESULT=" not in script
    assert linux.versions.filter(version=1).exists()
    assert linux.versions.filter(version=2).exists()


@pytest.mark.django_db
def test_collapse_builtin_versions_keeps_current_body_as_v1(builtin_user, builtin_channels, mocker):
    snapshots = {"generation": "first"}

    def snapshot(fmt, team_id):
        return {
            "object_key": f"workflow/templates/demo/team-{team_id}/health-{snapshots['generation']}.{fmt}",
            "format": fmt,
            "sha256": "a" * 64,
            "size": 128,
            "filename_prefix": f"health-{fmt}",
        }

    mocker.patch("apps.workflow.services.builtin_workflows.ConductorClient").return_value
    mocker.patch("apps.workflow.services.builtin_workflows.seed_builtin_health_template_snapshot", side_effect=snapshot)
    mocker.patch("apps.workflow.services.builtin_workflows.ensure_platform_atom")
    mocker.patch("apps.workflow.services.builtin_workflows.sync_published_triggers")

    ensure_builtin_health_workflows(team_id=1, username=builtin_user.username, domain=builtin_user.domain)
    snapshots["generation"] = "second"
    ensure_builtin_health_workflows(team_id=1, username=builtin_user.username, domain=builtin_user.domain)
    linux = Workflow.objects.get(engine_name=builtin_engine_name(1, BUILTIN_LINUX_KEY))
    custom = Workflow.objects.create(
        name="自定义流程",
        team=[1],
        definition={"name": "custom", "version": 3, "tasks": []},
        current_version=3,
        draft_base_version=3,
        is_builtin=False,
        engine_name="bklite_workflow_custom",
    )
    custom.versions.create(version=3, definition=custom.definition, canvas_metadata={})
    execution = WorkflowExecution.objects.create(
        workflow=linux,
        workflow_version=2,
        status=WorkflowExecution.Status.SUCCEEDED,
        team=[1],
        started_by=builtin_user.username,
    )

    assert collapse_builtin_workflow_versions() == 2

    linux.refresh_from_db()
    custom.refresh_from_db()
    execution.refresh_from_db()
    assert linux.current_version == 1
    assert linux.draft_base_version == 1
    assert linux.definition["version"] == 1
    report = next(task for task in linux.definition["tasks"] if task["taskReferenceName"] == "report")
    assert report["inputParameters"]["template_snapshot"]["object_key"].endswith("health-second.xlsx")
    assert list(linux.versions.values_list("version", flat=True)) == [1]
    assert linux.versions.get(version=1).definition["version"] == 1
    assert execution.workflow_version == 1
    assert custom.current_version == 3
    assert custom.versions.filter(version=3).exists()


@pytest.mark.django_db
def test_ensure_builtin_skips_nats_preferred_channel(builtin_user, builtin_channels, mocker):
    _patch_builtin_deps(mocker)

    workflows = ensure_builtin_health_workflows(
        team_id=1,
        username=builtin_user.username,
        domain=builtin_user.domain,
        channel_id=builtin_channels["nats"].id,
    )

    assert workflows[0].definition["tasks"][3]["inputParameters"]["channel_id"] == builtin_channels["email_first"].id


@pytest.mark.django_db
def test_ensure_builtin_allows_empty_channel_when_no_email(builtin_user, mocker):
    _patch_builtin_deps(mocker)
    Channel.objects.create(
        name="告警中心",
        channel_type=ChannelChoices.NATS,
        config={"method_name": "receive_alert_events"},
        description="",
        team=[1],
    )

    workflows = ensure_builtin_health_workflows(team_id=1, username=builtin_user.username, domain=builtin_user.domain)

    assert len(workflows) == 2
    notify = workflows[0].definition["tasks"][3]["inputParameters"]
    assert "channel_id" not in notify
    assert notify["recipients"] == [BUILTIN_EXECUTOR_RECIPIENT]


@pytest.mark.django_db
def test_builtin_workflow_rejects_delete_draft_and_publish(builtin_user, builtin_channels, mocker):
    _patch_builtin_deps(mocker)
    workflow = ensure_builtin_health_workflows(team_id=1, username=builtin_user.username)[0]
    factory = APIRequestFactory()

    destroy = WorkflowViewSet.as_view({"delete": "destroy"})
    draft = WorkflowViewSet.as_view({"patch": "partial_update"})
    publish = WorkflowViewSet.as_view({"post": "publish"})

    assert destroy(_request(factory, "delete", f"/workflows/{workflow.id}/", builtin_user), pk=workflow.id).status_code == 409
    assert (
        draft(
            _request(
                factory,
                "patch",
                f"/workflows/{workflow.id}/",
                builtin_user,
                {"name": "改名", "draft_revision": workflow.draft_revision},
            ),
            pk=workflow.id,
        ).status_code
        == 409
    )
    assert publish(_request(factory, "post", f"/workflows/{workflow.id}/publish/", builtin_user, {}), pk=workflow.id).status_code == 409
    assert Workflow.objects.filter(pk=workflow.pk, deleted_at__isnull=True, is_builtin=True).exists()
