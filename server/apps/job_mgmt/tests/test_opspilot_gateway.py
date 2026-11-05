"""OpsPilot 作业入口：组织、高危和脚本类型都由服务端决定。"""

import pytest
from django.core.cache import cache

from apps.job_mgmt.constants import DangerousLevel, ExecutionStatus, MatchType, OSType
from apps.job_mgmt.models import DangerousPath, DangerousRule, DistributionFile, JobExecution, Playbook, Script, Target
from apps.job_mgmt.nats_opspilot import job_opspilot_action
from apps.job_mgmt.services.opspilot_auth import sign_opspilot_job_request
from apps.job_mgmt.services.opspilot_gateway import (
    ACTION_DISTRIBUTE,
    ACTION_EXECUTE,
    ACTION_LIST_PLAYBOOK_SCRIPTS,
    ACTION_QUERY,
    run_opspilot_action,
    run_opspilot_distribute,
)

pytestmark = pytest.mark.django_db

ACTOR = {"user": "alice", "domain": "domain.com", "team": 1, "include_children": False}


@pytest.fixture(autouse=True)
def _quiet_dispatch(monkeypatch):
    monkeypatch.setattr(
        "apps.job_mgmt.services.celery_dispatch.dispatch_celery_task",
        lambda task_func, execution: "queued",
    )

    async def _upload(*args, **kwargs):
        return None

    monkeypatch.setattr("apps.job_mgmt.services.opspilot_gateway.upload_file_to_s3", _upload)
    cache.clear()


def _target(team, name="web-1", ip="10.0.0.8", os_type=OSType.LINUX):
    return Target.objects.create(name=name, ip=ip, os_type=os_type, team=team)


def _script(team, content="echo opspilot-ok", script_type="shell", timeout=77, params=None):
    return Script.objects.create(
        name="库脚本",
        content=content,
        script_type=script_type,
        timeout=timeout,
        params=params or [],
        team=team,
    )


def _execute(body, actor=ACTOR, token=None):
    signed = token if token is not None else sign_opspilot_job_request(ACTION_EXECUTE, actor)
    return run_opspilot_action(ACTION_EXECUTE, signed, actor, body)


def _library_body(script, target, **extra):
    body = {
        "mode": "library",
        "script_id": script.id,
        "target_source": "manual",
        "target_ids": [target.id],
        "params": [],
    }
    body.update(extra)
    return body


def test_unsigned_request_creates_nothing():
    script = _script([1])
    target = _target([1])
    result = _execute(_library_body(script, target), token="not-a-signature")
    assert result["result"] is False
    assert JobExecution.objects.count() == 0


def test_other_team_script_and_target_create_nothing():
    foreign_script = _script([2])
    own_target = _target([1])
    refused_script = _execute(_library_body(foreign_script, own_target))
    assert refused_script["result"] is False
    assert JobExecution.objects.count() == 0

    own_script = _script([1], content="echo own-script")
    foreign_target = _target([2], name="foreign", ip="10.9.9.9")
    refused_target = _execute(_library_body(own_script, foreign_target))
    assert refused_target["result"] is False
    assert JobExecution.objects.count() == 0


def test_request_body_cannot_replace_actor_or_library_body():
    script = _script([1], content="echo from-library")
    target = _target([1])
    result = _execute(
        _library_body(
            script,
            target,
            script_content="echo HACKED_BODY",
            team=99,
            user="mallory",
            executor="mallory",
        )
    )
    assert result["result"] is True
    execution = JobExecution.objects.get()
    assert execution.script_content == "echo from-library"
    assert execution.team == [1]
    assert execution.created_by == "alice"
    assert execution.executor_user == "alice"
    assert execution.timeout == 77


def test_forbidden_command_creates_nothing_even_when_confirmed():
    DangerousRule.objects.create(
        name="禁止标记",
        pattern="OPS_FORBIDDEN_MARKER",
        level=DangerousLevel.FORBIDDEN,
        is_enabled=True,
        team=[1],
    )
    cache.clear()
    script = _script([1], content="echo OPS_FORBIDDEN_MARKER")
    target = _target([1])
    result = _execute(_library_body(script, target, danger_confirmed=True))
    assert result["code"] == "forbidden"
    assert JobExecution.objects.count() == 0


def test_confirm_command_waits_for_explicit_confirmation():
    DangerousRule.objects.create(
        name="确认标记",
        pattern="OPS_CONFIRM_MARKER",
        level=DangerousLevel.CONFIRM,
        is_enabled=True,
        team=[1],
    )
    cache.clear()
    script = _script([1], content="echo OPS_CONFIRM_MARKER")
    target = _target([1])
    waiting = _execute(_library_body(script, target))
    assert waiting["code"] == "confirm"
    assert "确认标记" in waiting["rules"]
    assert JobExecution.objects.count() == 0

    confirmed = _execute(_library_body(script, target, danger_confirmed=True))
    assert confirmed["result"] is True
    assert JobExecution.objects.count() == 1


@pytest.mark.parametrize("script_type", ["shell", "python", "powershell", "bat"])
def test_custom_script_types_use_default_timeout(script_type):
    os_type = OSType.WINDOWS if script_type in ("powershell", "bat") else OSType.LINUX
    target = _target(
        [1],
        ip=f"10.1.0.{['shell', 'python', 'powershell', 'bat'].index(script_type) + 2}",
        os_type=os_type,
    )
    content = "print('opspilot-ok')" if script_type == "python" else "echo opspilot-ok"
    result = _execute(
        {
            "mode": "custom",
            "script_type": script_type,
            "script_content": content,
            "target_source": "manual",
            "target_ids": [target.id],
        }
    )
    assert result["result"] is True
    execution = JobExecution.objects.get()
    assert execution.script_type == script_type
    assert execution.timeout == 600
    assert execution.script_content == content


def test_script_type_must_match_target_os():
    linux = _target([1], name="linux-1", ip="10.2.0.1", os_type=OSType.LINUX)
    windows = _target([1], name="win-1", ip="10.2.0.2", os_type=OSType.WINDOWS)
    shell = _script([1], content="echo opspilot-ok", script_type="shell")
    refused = _execute(_library_body(shell, windows))
    assert refused["result"] is False
    assert "只能执行 powershell、bat" in refused["message"]
    assert "win-1 是 Windows" in refused["message"]
    assert JobExecution.objects.count() == 0

    unknown = _target([1], name="mystery", ip="10.2.0.3")
    Target.objects.filter(id=unknown.id).update(os_type="")
    unknown_result = _execute(_library_body(shell, unknown))
    assert unknown_result["result"] is False
    assert "操作系统未知" in unknown_result["message"]
    assert JobExecution.objects.count() == 0

    accepted = _execute(
        {
            "mode": "custom",
            "script_type": "bat",
            "script_content": "echo opspilot-ok",
            "target_source": "manual",
            "target_ids": [windows.id],
        }
    )
    assert accepted["result"] is True
    assert JobExecution.objects.get().script_type == "bat"
    linux_shell = _execute(_library_body(shell, linux))
    assert linux_shell["result"] is True


def test_query_returns_output_without_script_body():
    def finish(task_func, execution):
        execution.status = ExecutionStatus.SUCCESS
        execution.success_count = 1
        execution.failed_count = 0
        execution.execution_results = [
            {
                "name": "web-1",
                "ip": "10.0.0.8",
                "status": ExecutionStatus.SUCCESS,
                "stdout": "STDOUT_SECRET",
                "stderr": "STDERR_SECRET",
                "exit_code": 0,
            }
        ]
        execution.save()
        return "queued"

    script = _script([1], content="echo from-library")
    target = _target([1])
    from apps.job_mgmt.services import celery_dispatch

    celery_dispatch.dispatch_celery_task = finish
    created = _execute(_library_body(script, target))
    token = sign_opspilot_job_request(ACTION_QUERY, ACTOR)
    queried = run_opspilot_action(ACTION_QUERY, token, ACTOR, {"task_id": created["data"]["task_id"], "script_content": "echo from-library"})
    assert queried["data"]["results"][0]["stdout"] == "STDOUT_SECRET"
    assert "script_content" not in queried["data"]


def _distribute(body, files=(("demo.txt", b"abc"),)):
    token = sign_opspilot_job_request(ACTION_DISTRIBUTE, ACTOR)
    return run_opspilot_distribute(token, ACTOR, body, list(files))


def test_missing_path_or_strategy_does_not_store_file():
    target = _target([1])
    missing_path = _distribute({"target_source": "manual", "target_ids": [target.id], "overwrite_strategy": "skip"})
    assert missing_path["code"] == "need_path"
    missing_strategy = _distribute({"target_source": "manual", "target_ids": [target.id], "target_path": "/data/opspilot-deliver"})
    assert missing_strategy["code"] == "need_overwrite"
    assert DistributionFile.objects.count() == 0
    assert JobExecution.objects.count() == 0


def test_forbidden_path_does_not_store_file():
    DangerousPath.objects.create(
        name="禁止目录",
        pattern="/data/blocked-opspilot",
        match_type=MatchType.EXACT,
        level=DangerousLevel.FORBIDDEN,
        is_enabled=True,
        team=[1],
    )
    cache.clear()
    target = _target([1])
    result = _distribute(
        {
            "target_source": "manual",
            "target_ids": [target.id],
            "target_path": "/data/blocked-opspilot",
            "overwrite_strategy": "skip",
            "danger_confirmed": True,
        }
    )
    assert result["code"] == "forbidden"
    assert DistributionFile.objects.count() == 0


def test_confirmed_distribute_stores_file_for_current_team():
    target = _target([1])
    result = _distribute(
        {
            "target_source": "manual",
            "target_ids": [target.id],
            "target_path": "/data/opspilot-deliver",
            "overwrite_strategy": "skip",
            "team": 99,
            "executor": "mallory",
        }
    )
    assert result["result"] is True
    stored = DistributionFile.objects.get()
    assert stored.team == 1
    execution = JobExecution.objects.get()
    assert execution.executor_user == "alice"
    assert execution.target_path == "/data/opspilot-deliver"


def test_nats_distribute_uses_file_key_not_request_bytes(monkeypatch):
    unsigned = job_opspilot_action(
        {
            "action": ACTION_DISTRIBUTE,
            "body": {"files": "abc"},
            "files": [{"name": "demo.txt", "file_key": "secrets/demo.txt"}],
        }
    )
    assert unsigned["result"] is False
    assert DistributionFile.objects.count() == 0

    target = _target([1])
    token = sign_opspilot_job_request(ACTION_DISTRIBUTE, ACTOR)
    body = {
        "target_source": "manual",
        "target_ids": [target.id],
        "target_path": "/data/opspilot-deliver",
        "overwrite_strategy": "skip",
    }
    rejected = job_opspilot_action(
        {
            "action": ACTION_DISTRIBUTE,
            "_internal_auth": token,
            "user_info": ACTOR,
            "body": body,
            "files": [{"name": "demo.txt", "file_key": "secrets/demo.txt"}],
        }
    )
    assert rejected["result"] is False
    assert DistributionFile.objects.count() == 0

    prepared = run_opspilot_distribute(token, ACTOR, {**body, "prepare": True}, [{"name": "demo.txt", "size": 4}])
    assert prepared == {"result": True, "code": "ready"}
    assert DistributionFile.objects.count() == 0

    monkeypatch.setattr("apps.job_mgmt.services.opspilot_gateway._job_object_size", lambda file_key: 4)
    accepted = job_opspilot_action(
        {
            "action": ACTION_DISTRIBUTE,
            "_internal_auth": token,
            "user_info": ACTOR,
            "body": body,
            "files": [{"name": "demo.txt", "file_key": "job-files/2026/11/04/" + ("a" * 21) + ".txt"}],
        }
    )
    assert accepted["result"] is True
    assert DistributionFile.objects.get().file_key.startswith("job-files/")
    assert DistributionFile.objects.get().team == 1


def test_list_playbook_scripts_returns_paths_without_file_body():
    Playbook.objects.create(
        name="nginx",
        version="v1.2.0",
        team=[1],
        readme="SECRET_README",
        file_list=[
            {
                "name": "deploy",
                "type": "directory",
                "children": [
                    {"name": "playbook.yml", "type": "file", "content": "SECRET_PLAYBOOK"},
                    {"name": "README.md", "type": "file"},
                    {"name": "..", "type": "file"},
                ],
            }
        ],
        params=[{"name": "port", "default": 80, "description": "listen"}],
    )
    Playbook.objects.create(
        name="foreign",
        team=[2],
        file_list=[{"name": "playbook.yml", "type": "file"}],
    )
    token = sign_opspilot_job_request(ACTION_LIST_PLAYBOOK_SCRIPTS, ACTOR)
    denied = run_opspilot_action(ACTION_LIST_PLAYBOOK_SCRIPTS, "not-a-signature", ACTOR, {"path": "playbook.yml"})
    assert denied["result"] is False

    listed = run_opspilot_action(ACTION_LIST_PLAYBOOK_SCRIPTS, token, ACTOR, {"name": "nginx", "path": "playbook.yml"})
    assert listed["result"] is True
    assert listed["data"]["count"] == 1
    item = listed["data"]["items"][0]
    assert item["paths"] == ["deploy/playbook.yml"]
    assert item["version"] == "v1.2.0"
    assert item["params"][0]["name"] == "port"
    assert item["params"][0]["default"] == 80
    assert "readme" not in item
    assert "content" not in item
    rendered = str(listed)
    assert "SECRET_README" not in rendered
    assert "SECRET_PLAYBOOK" not in rendered
