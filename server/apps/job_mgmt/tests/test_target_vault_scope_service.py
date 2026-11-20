from types import SimpleNamespace

import pytest

from apps.job_mgmt.models import JobExecution, Target
from apps.job_mgmt.services.target_vault import describe_target_credentials, resolve_target_fields
from apps.system_mgmt.models import Group, User
from apps.system_mgmt.services.credential_service import create_credential, seed_builtin_types, update_credential

pytestmark = [pytest.mark.integration, pytest.mark.django_db]


@pytest.fixture
def binding():
    parent = Group.objects.create(name="vault owner")
    child = Group.objects.create(name="job team", parent_id=parent.pk)
    sibling = Group.objects.create(name="other team")
    seed_builtin_types()
    user = User.objects.create(username="operator", domain="example.test", group_list=[child.pk])
    actor = {"username": user.username, "domain": user.domain, "current_team": child.pk}
    owner = dict(actor, current_team=parent.pk, group_list=[parent.pk])
    fields = {"username": "host-user", "auth_method": "password", "password": "first-secret"}
    cred = create_credential({"name": "Host login", "type": "ssh", "group_id": parent.pk, "fields": fields}, actor=owner)
    target = Target.objects.create(name="target", ip="192.0.2.12", credential_source="credential", credential_id=cred.credential_id, team=[child.pk])
    execution = JobExecution.objects.create(name="check", target_list=[{"target_id": target.pk}], team=[child.pk], credential_actor=actor)
    return SimpleNamespace(
        child=child, sibling=sibling, user=user, actor=actor, owner=owner, fields=fields, cred=cred, target=target, execution=execution
    )


def test_current_actor_reads_latest_value_and_loses_access_on_revocation(binding):
    b = binding
    metadata = describe_target_credentials([b.cred.credential_id], b.actor)[b.cred.credential_id]
    assert metadata["name"] == "Host login" and "fields" not in metadata
    assert resolve_target_fields(b.target, execution=b.execution)["password"] == "first-secret"
    update_credential(b.cred.credential_id, {"fields": {**b.fields, "password": "new-secret"}}, actor=b.owner)
    assert resolve_target_fields(b.target, execution=b.execution)["password"] == "new-secret"
    b.user.group_list = [b.sibling.pk]
    b.user.save(update_fields=["group_list"])
    with pytest.raises(ValueError):
        resolve_target_fields(b.target, execution=b.execution)


def test_scheduled_team_uses_active_ancestor_after_creator_leaves(binding):
    b = binding
    b.execution.enforce_scheduled_team_boundary = True
    b.execution.credential_actor = {}
    b.user.delete()
    assert resolve_target_fields(b.target, execution=b.execution)["username"] == "host-user"
    b.cred.disabled = True
    b.cred.save(update_fields=["disabled"])
    with pytest.raises(ValueError):
        resolve_target_fields(b.target, execution=b.execution)
    b.cred.disabled = False
    b.cred.save(update_fields=["disabled"])
    b.execution.team = [b.sibling.pk]
    b.target.team = [b.sibling.pk]
    with pytest.raises(ValueError):
        resolve_target_fields(b.target, execution=b.execution)


def test_unverified_legacy_execution_wrong_target_and_wrong_protocol_are_rejected(binding):
    b = binding
    b.execution.credential_actor = {}
    with pytest.raises(ValueError):
        resolve_target_fields(b.target, execution=b.execution)
    b.execution.credential_actor = b.actor
    b.target.os_type = "windows"
    with pytest.raises(ValueError):
        resolve_target_fields(b.target, execution=b.execution)
    b.target.os_type = "linux"
    b.target.team = [b.sibling.pk]
    with pytest.raises(ValueError):
        resolve_target_fields(b.target, execution=b.execution)


def test_beat_with_default_rollout_uses_task_team_after_creator_leaves(binding, monkeypatch):
    from apps.job_mgmt import tasks
    from apps.job_mgmt.models import ScheduledTask

    b = binding
    b.user.delete()
    task = ScheduledTask.objects.create(
        name="vault cron",
        job_type="script",
        script_type="shell",
        script_content="echo ok",
        schedule_type="cron",
        cron_expression="0 0 * * *",
        target_source="manual",
        target_list=[{"target_id": b.target.pk}],
        team=[b.child.pk],
        is_enabled=True,
        created_by="departed",
    )
    monkeypatch.setattr(tasks, "SCHEDULED_TASK_TEAM_BOUNDARY_ENFORCED", False)
    monkeypatch.setattr(tasks, "_dispatch_execution_job", lambda *args: True)
    tasks.execute_scheduled_task(task.pk)
    run = JobExecution.objects.get(scheduled_task=task)
    assert run.enforce_scheduled_team_boundary and not run.credential_actor
    assert resolve_target_fields(b.target, execution=run)["username"] == "host-user"


def test_untrusted_nats_cannot_select_managed_target_even_with_forged_actor(binding, monkeypatch):
    from unittest.mock import Mock

    from apps.job_mgmt import nats_api

    b = binding
    dispatch = Mock()
    monkeypatch.setattr(nats_api, "dispatch_celery_task", dispatch)
    payload = {
        "name": "legacy",
        "team": [b.child.pk],
        "target_source": "manual",
        "target_list": [{"target_id": b.target.pk}],
        "script_type": "shell",
        "script_content": "echo ok",
        "credential_actor": b.actor,
        "trusted_actor": b.actor,
    }
    result = nats_api.job_script_execute(payload)
    assert result["result"] is False
    assert not JobExecution.objects.filter(name="legacy").exists()
    dispatch.assert_not_called()


def test_reexecution_uses_current_actor_and_rechecks_target_team(binding, monkeypatch):
    from apps.job_mgmt.services.execution_service import ExecutionAuthorizationError, ExecutionService

    b = binding
    monkeypatch.setattr(ExecutionService, "_dispatch_or_raise", lambda _: None)
    b.execution.job_type = "script"
    b.execution.credential_actor = {"username": "old-operator", "domain": "old.test", "current_team": b.child.pk}
    b.execution.save()
    new = ExecutionService.create_re_execution(
        original=b.execution,
        username=b.user.username,
        authorized_team_ids={b.child.pk},
        credential_actor=b.actor,
    )
    assert new.credential_actor == b.actor
    assert resolve_target_fields(b.target, execution=new)["password"] == "first-secret"
    b.target.team = [b.sibling.pk]
    b.target.save()
    with pytest.raises(ExecutionAuthorizationError):
        ExecutionService.create_re_execution(
            original=b.execution,
            username=b.user.username,
            authorized_team_ids={b.child.pk},
            credential_actor=b.actor,
        )


def test_concurrent_manual_patch_cannot_restore_secret_after_vault_switch(binding):
    from rest_framework import serializers

    from apps.job_mgmt.serializers.target import TargetSerializer

    b = binding
    original = Target.objects.create(
        team=[b.child.pk],
        ip="192.0.2.14",
        name="manual",
        cloud_region_id=1,
        ssh_user="old",
        ssh_password="old-cipher",
    )
    request = SimpleNamespace(user=b.user, COOKIES={"current_team": str(b.child.pk)})
    pending = TargetSerializer(original, data={"name": "edited"}, partial=True, context={"request": request})
    assert pending.is_valid(), pending.errors
    updated = Target.objects.get(pk=original.pk)
    updated.credential_source = "credential"
    updated.credential_id = b.cred.credential_id
    updated.ssh_password = ""
    updated.ssh_user = ""
    updated.save()
    with pytest.raises(serializers.ValidationError):
        pending.save()
    original.refresh_from_db()
    assert original.credential_id == b.cred.credential_id and not original.ssh_password
