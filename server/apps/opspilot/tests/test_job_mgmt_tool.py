"""作业工具：模型只看终态，暂存文件和定时检查都不重新提交。"""

import json
from datetime import timedelta

import pytest
from django.core.files.storage import FileSystemStorage
from django.utils import timezone

from apps.job_mgmt.constants import ExecutionStatus, OSType
from apps.job_mgmt.models import DistributionFile, JobExecution, Playbook, Script, Target
from apps.opspilot.enum import SkillChannelChoices
from apps.opspilot.metis.llm.middleware.tool_runtime import ToolTimeoutMiddleware
from apps.opspilot.models import ChatAttachment, LLMSkill, SkillChannel, SkillConversation, SkillConversationMessage
from apps.opspilot.services.chat_attachment_service import cleanup_chat_attachments
from apps.opspilot.services.job_output_text import model_visible_text
from apps.opspilot.services.job_tool_service import (
    distribute_staged_files,
    list_playbook_scripts,
    list_staged_distribute_files,
    run_custom_script,
    run_library_script,
    scan_job_watches,
    schedule_job_watch,
    skill_has_job_mgmt,
    stage_distribute_file,
)
from apps.opspilot.tasks.job_tool import cleanup_opspilot_job_staged_files, scan_opspilot_job_watches

pytestmark = pytest.mark.django_db


class _Request:
    def __init__(self, name):
        self.tool_call = {"name": name, "id": "call-1"}


@pytest.fixture(autouse=True)
def _quiet_job_side_effects(monkeypatch):
    monkeypatch.setenv("JOB_TOOL_POLL_SECONDS", "0")
    monkeypatch.setenv("JOB_TOOL_POLL_INTERVAL", "0")
    monkeypatch.setattr(
        "apps.job_mgmt.services.celery_dispatch.dispatch_celery_task",
        lambda task_func, execution: "queued",
    )

    async def _upload(*args, **kwargs):
        return None

    monkeypatch.setattr("apps.job_mgmt.services.opspilot_gateway.upload_file_to_s3", _upload)
    monkeypatch.setattr("apps.job_mgmt.services.opspilot_gateway._job_object_size", lambda file_key: 8)
    monkeypatch.setattr("apps.opspilot.services.job_tool_service._publish_job_file", lambda *args, **kwargs: None)
    monkeypatch.setattr("apps.opspilot.services.job_tool_service._discard_job_file", lambda *args, **kwargs: None)

    def _through_handler(self, data, timeout=30):
        from apps.job_mgmt.nats_opspilot import job_opspilot_action

        return job_opspilot_action(data)

    monkeypatch.setattr("apps.rpc.job_mgmt.JobMgmt.job_opspilot_action", _through_handler)
    monkeypatch.setattr("apps.opspilot.services.job_tool_service._PENDING_DISPLAYS", {})


@pytest.fixture
def staged_storage(tmp_path, monkeypatch):
    storage = FileSystemStorage(location=tmp_path, base_url="/staged/")
    monkeypatch.setattr(ChatAttachment._meta.get_field("file"), "storage", storage)
    return storage


def _config(message="", session="sess-job"):
    return {
        "configurable": {
            "caller_identity": {
                "username": "alice",
                "domain": "domain.com",
                "team_id": 1,
                "include_children": True,
            },
            "skill_session_id": session,
            "user_message": message,
        }
    }


def _target():
    return Target.objects.create(name="web-1", ip="10.0.0.8", os_type=OSType.LINUX, team=[1])


def _script():
    return Script.objects.create(name="库脚本", content="echo from-library", script_type="shell", timeout=77, team=[1])


def _conversation(session_id):
    skill = LLMSkill.objects.create(name=f"skill-{session_id}", team=[1], usage_team=[1], tools=[{"name": "job_mgmt"}])
    channel = SkillChannel.objects.create(
        skill=skill,
        channel_type=SkillChannelChoices.WEB_CHAT,
        enabled=True,
        usage_team=[1],
    )
    return SkillConversation.objects.create(
        session_id=session_id,
        skill=skill,
        channel=channel,
        external_user_id="alice@domain.com",
    )


def test_playbook_listing_does_not_claim_the_tools_can_execute_it():
    from apps.opspilot.metis.llm.tools.job_mgmt.tools import JOB_MGMT_PROMPT, job_mgmt_list_playbook_scripts, job_mgmt_run_custom, job_mgmt_run_library

    assert "不表示这些工具能执行 Playbook" in JOB_MGMT_PROMPT
    assert "只执行作业脚本" in JOB_MGMT_PROMPT
    description = job_mgmt_list_playbook_scripts.description
    assert "不能跑 Playbook" in description
    assert "只执行作业脚本" in description
    assert "不提交作业" in description
    for tool in (job_mgmt_run_library, job_mgmt_run_custom):
        assert "Playbook" not in tool.description


def test_list_playbook_scripts_uses_current_team_and_path():
    Playbook.objects.create(
        name="nginx",
        team=[1],
        file_list=["site/playbook.yml", "site/README.md"],
    )
    Playbook.objects.create(name="nginx", team=[2], file_list=["site/playbook.yml"])
    listed = list_playbook_scripts(_config(), name="nginx", path="site/playbook.yml")
    assert listed["result"] is True
    assert listed["data"]["count"] == 1
    assert listed["data"]["items"][0]["paths"] == ["site/playbook.yml"]
    assert JobExecution.objects.count() == 0


def test_display_lookup_and_skill_session_key_survive_the_async_stream():
    import asyncio

    from apps.opspilot.services.job_tool_service import latest_display_payload

    conversation = _conversation("sess-skill-key")
    conversation.messages.create(
        role=SkillConversationMessage.ROLE_USER,
        content="用 python 执行 print('opspilot-ok')",
    )
    target = _target()
    accepted = run_custom_script(
        _config("选定节点", session="skill:sess-skill-key"),
        script_type="python",
        script_content="print('opspilot-ok')",
        target_source="作业管理目标",
        target_ids=[target.id],
    )
    task_id = json.loads(accepted)["task_id"]
    assert conversation.messages.filter(role=SkillConversationMessage.ROLE_ASSISTANT, content__contains=f'"task_id": {task_id}').exists()

    async def load():
        return latest_display_payload(task_id)

    loaded = asyncio.run(load())
    assert loaded["task_id"] == task_id
    assert loaded["result_url"] == f"/job/execution/job-record?id={task_id}"
    assert conversation.messages.filter(content__contains=loaded["result_url"]).exists()


def test_search_respects_a_named_source_and_a_chosen_id(monkeypatch):
    from apps.opspilot.services.job_tool_service import search_job_targets

    def fake_call(_action, _user_info, _body):
        return {
            "result": True,
            "data": {
                "count": 2,
                "hits": [
                    {"source": "manual", "id": "2", "name": "ffff", "ip": "10.10.40.117", "os": "windows"},
                    {"source": "node_mgmt", "id": "126f1539", "name": "10.10.40.117", "ip": "169.254.213.177", "os": "windows"},
                ],
            },
        }

    monkeypatch.setattr("apps.opspilot.services.job_tool_service._call", fake_call)
    narrowed = search_job_targets(
        _config("用 bat 脚本，正文为 ipconfig，选择 节点管理 目标 10.10.40.117"),
        "10.10.40.117",
    )
    assert narrowed["use"]["source"] == "node_mgmt"
    assert narrowed["use"]["id"] == "126f1539"
    assert "ffff" not in json.dumps(narrowed, ensure_ascii=False)

    chosen = search_job_targets(
        _config("10.10.40.117 169.254.213.177 (node_mgmt:126f1539-0bd4-4fc7-b43e-2e3ba54ed42e)"),
        "10.10.40.117 169.254.213.177",
    )
    assert chosen["use"]["id"] == "126f1539-0bd4-4fc7-b43e-2e3ba54ed42e"
    assert "不要再问来源" in chosen["message"]


def test_execute_tools_tell_the_model_not_to_pass_an_ip_as_target_ids():
    from apps.opspilot.metis.llm.tools.job_mgmt.tools import job_mgmt_run_custom, job_mgmt_run_library

    for tool in (job_mgmt_run_custom, job_mgmt_run_library):
        schema = tool.args_schema.model_json_schema()
        target_ids = schema["properties"]["target_ids"]["description"]
        assert "不要填 ip" in target_ids
        assert "节点主键" in target_ids
        assert "作业管理目标" in schema["properties"]["target_source"]["description"]


def test_job_tool_timeout_does_not_ask_for_resubmit():
    middleware = ToolTimeoutMiddleware(timeout_seconds=300)
    assert middleware._timeout_for(_Request("job_mgmt_query")) == 360
    assert "不要重新提交" in middleware._timeout_message(_Request("job_mgmt_run_library")).content
    assert middleware._timeout_for(_Request("monitor_query")) == 300
    assert "可换参数重试" in middleware._timeout_message(_Request("monitor_query")).content


def test_missing_identity_refuses_without_a_job():
    from apps.opspilot.metis.llm.tools.job_mgmt.tools import _run

    result = _run(lambda: run_library_script({"configurable": {}}, script_id=1, target_source="manual", target_ids=[1]))
    assert result["result"] is False
    assert JobExecution.objects.count() == 0


def _job_record(conversation, task_id):
    for message in conversation.messages.filter(role=SkillConversationMessage.ROLE_ASSISTANT).order_by("id"):
        events = json.loads(message.content)
        for event in events:
            if event.get("name") == "job_record" and event["value"]["task_id"] == task_id:
                return message, events, event["value"]
    raise AssertionError(task_id)


def _shift_watch(conversation, task_id, *, next_run_at, deadline_at=None):
    message, events, record = _job_record(conversation, task_id)
    record["watch"]["next_run_at"] = next_run_at.isoformat()
    if deadline_at is not None:
        record["watch"]["deadline_at"] = deadline_at.isoformat()
    message.content = json.dumps(events, ensure_ascii=False)
    message.save(update_fields=["content"])


def test_library_result_hides_script_and_output_and_retry_keeps_one_job():
    _conversation("sess-job")
    script = _script()
    target = _target()
    first = run_library_script(
        _config("执行库脚本"),
        script_id=script.id,
        target_source="manual",
        target_ids=[target.id],
    )
    second = run_library_script(
        _config("再看一次"),
        script_id=script.id,
        target_source="manual",
        target_ids=[target.id],
    )
    payload = json.loads(first)
    assert json.loads(second)["task_id"] == payload["task_id"]
    assert payload["status"] == "仍在执行"
    assert payload["output_shown"] is False
    assert payload["result_url"] == f"/job/execution/job-record?id={payload['task_id']}"
    assert "echo from-library" not in first
    assert "stdout" not in first
    assert JobExecution.objects.count() == 1


def test_custom_script_must_come_from_the_user_message():
    target = _target()
    refused = run_custom_script(
        _config("帮我跑一下"),
        script_type="python",
        script_content="print('opspilot-ok')",
        target_source="manual",
        target_ids=[target.id],
    )
    assert refused["result"] is False
    assert JobExecution.objects.count() == 0

    message = "用 python 执行 print('opspilot-ok')"
    accepted = run_custom_script(
        _config(message, session="sess-custom"),
        script_type="python",
        script_content="print('opspilot-ok')",
        target_source="manual",
        target_ids=[target.id],
    )
    payload = json.loads(accepted)
    assert payload["status"] == "仍在执行"
    assert "print('opspilot-ok')" not in accepted
    assert JobExecution.objects.get().script_type == "python"
    assert JobExecution.objects.get().timeout == 600


def test_custom_script_stays_valid_after_the_user_selects_a_target():
    conversation = _conversation("sess-custom-later")
    target = _target()
    conversation.messages.create(
        role=SkillConversationMessage.ROLE_USER,
        content="用 python 执行 print('opspilot-ok')",
    )
    accepted = run_custom_script(
        _config(f"web-1 10.0.0.8 (manual:{target.id})", session="sess-custom-later"),
        script_type="python",
        script_content="print('opspilot-ok')",
        target_source="作业管理目标",
        target_ids=[target.id],
    )
    assert json.loads(accepted)["status"] == "仍在执行"
    assert JobExecution.objects.get().script_content == "print('opspilot-ok')"

    split = _conversation("sess-custom-split")
    split.messages.create(role=SkillConversationMessage.ROLE_USER, content="脚本类型 python")
    split.messages.create(role=SkillConversationMessage.ROLE_USER, content="脚本内容 print('opspilot-ok')")
    refused = run_custom_script(
        _config("用这个节点", session="sess-custom-split"),
        script_type="python",
        script_content="print('opspilot-ok')",
        target_source="manual",
        target_ids=[target.id],
    )
    assert refused["result"] is False
    assert JobExecution.objects.filter(script_content="print('opspilot-ok')").count() == 1


def test_library_script_requires_the_name_in_the_user_message():
    script = _script()
    target = _target()
    refused = run_library_script(
        _config("创建一个快速执行作业"),
        script_id=script.id,
        target_source="manual",
        target_ids=[target.id],
    )
    assert refused["ask"] is True
    assert refused["options"][0] == "使用脚本 库脚本"
    assert "echo from-library" not in json.dumps(refused, ensure_ascii=False)
    assert JobExecution.objects.count() == 0


def test_historical_script_name_does_not_confirm_library_script():
    session = "sess-script-history"
    conversation = _conversation(session)
    conversation.messages.create(role=SkillConversationMessage.ROLE_USER, content="请执行库脚本，也跑一下 ls")
    script = _script()
    short = Script.objects.create(name="ls", content="ls", script_type="shell", timeout=77, team=[1])
    target = _target()
    for script_id in (script.id, short.id):
        refused = run_library_script(
            _config("创建一个快速执行作业", session=session),
            script_id=script_id,
            target_source="manual",
            target_ids=[target.id],
        )
        assert refused["ask"] is True
        assert refused["options"][0].startswith("使用脚本 ")
    assert JobExecution.objects.count() == 0

    accepted = run_library_script(
        _config("使用脚本 库脚本", session=session),
        script_id=script.id,
        target_source="manual",
        target_ids=[target.id],
    )
    assert json.loads(accepted)["status"] == "仍在执行"
    assert JobExecution.objects.count() == 1


def test_terminal_statuses_for_the_model_and_display(monkeypatch):
    def finish(task_func, execution):
        execution.status = ExecutionStatus.FAILED
        execution.success_count = 1
        execution.failed_count = 1
        execution.execution_results = [{"name": "web-1", "ip": "10.0.0.8", "stdout": "STDOUT_SECRET", "stderr": "STDERR_SECRET", "exit_code": 1}]
        execution.save()
        return "queued"

    monkeypatch.setattr("apps.job_mgmt.services.celery_dispatch.dispatch_celery_task", finish)
    conversation = _conversation("sess-display")
    script = _script()
    target = _target()
    raw = run_library_script(
        _config("执行库脚本", session="sess-display"),
        script_id=script.id,
        target_source="manual",
        target_ids=[target.id],
    )
    shown = json.loads(raw)
    assert shown["status"] == "部分失败"
    assert shown["output_shown"] is True
    assert "result_url" not in shown
    assert "STDOUT_SECRET" not in raw
    message = conversation.messages.get(role=SkillConversationMessage.ROLE_ASSISTANT)
    assert "STDOUT_SECRET" in message.content
    assert model_visible_text(message.content) == f"作业 {json.loads(raw)['task_id']}：部分失败"
    assert "STDOUT_SECRET" not in model_visible_text(message.content)


def test_script_output_reaches_the_chat_without_a_saved_conversation(monkeypatch):
    def finish(task_func, execution):
        execution.status = ExecutionStatus.SUCCESS
        execution.success_count = 1
        execution.failed_count = 0
        execution.execution_results = [{"name": "web-1", "ip": "10.0.0.8", "stdout": "STDOUT_SECRET", "stderr": "", "exit_code": 0}]
        execution.save()
        return "queued"

    monkeypatch.setattr("apps.job_mgmt.services.celery_dispatch.dispatch_celery_task", finish)
    from apps.opspilot.services.job_tool_service import latest_display_payload

    target = _target()
    raw = run_custom_script(
        _config("用 python 执行 print('opspilot-ok')", session="thread:debug-job"),
        script_type="python",
        script_content="print('opspilot-ok')",
        target_source="manual",
        target_ids=[target.id],
    )
    payload = json.loads(raw)
    assert payload["output_shown"] is True
    assert "result_url" not in payload
    assert "STDOUT_SECRET" not in raw
    assert SkillConversation.objects.filter(session_id="thread:debug-job").count() == 0
    display = latest_display_payload(payload["task_id"])
    assert display["targets"][0]["stdout"] == "STDOUT_SECRET"
    assert "result_url" not in display


def test_pending_job_without_a_conversation_still_returns_the_record_link():
    from apps.opspilot.services.job_tool_service import latest_display_payload

    target = _target()
    pending = json.loads(
        run_library_script(
            _config("执行库脚本", session="thread:debug-pending"),
            script_id=_script().id,
            target_source="manual",
            target_ids=[target.id],
        )
    )
    assert pending["output_shown"] is False
    assert pending["result_url"] == f"/job/execution/job-record?id={pending['task_id']}"
    assert "stdout" not in json.dumps(pending)
    display = latest_display_payload(pending["task_id"])
    assert display["result_url"] == pending["result_url"]
    assert display["targets"] == []
    assert SkillConversation.objects.filter(session_id="thread:debug-pending").count() == 0


def test_file_result_is_only_success_or_failure(staged_storage, monkeypatch):
    def finish(task_func, execution):
        execution.status = ExecutionStatus.SUCCESS
        execution.success_count = 1
        execution.failed_count = 0
        execution.save()
        return "queued"

    monkeypatch.setattr("apps.job_mgmt.services.celery_dispatch.dispatch_celery_task", finish)
    target = _target()
    staged = stage_distribute_file(
        owner_key="alice@domain.com",
        team_id="1",
        session_key="sess-file",
        filename="demo.txt",
        data=b"file-bytes",
    )
    result = distribute_staged_files(
        _config("把 demo.txt 覆盖到 /data/opspilot-deliver", session="sess-file"),
        file_ids=[staged.id],
        target_source="manual",
        target_ids=[target.id],
        target_path="/data/opspilot-deliver",
    )
    assert result == "成功"
    assert "/data/opspilot-deliver" not in result
    assert DistributionFile.objects.count() == 1


def test_unfinished_file_distribution_returns_the_job_record_link(staged_storage):
    from apps.opspilot.services.job_tool_service import latest_display_payload, query_job

    target = _target()
    staged = stage_distribute_file(
        owner_key="alice@domain.com",
        team_id="1",
        session_key="sess-file-pending",
        filename="demo.txt",
        data=b"file-bytes",
    )
    _conversation("sess-file-pending")
    raw = distribute_staged_files(
        _config("把 demo.txt 覆盖到 /data/opspilot-deliver", session="sess-file-pending"),
        file_ids=[staged.id],
        target_source="manual",
        target_ids=[target.id],
        target_path="/data/opspilot-deliver",
    )
    payload = json.loads(raw)
    execution = JobExecution.objects.get()
    assert execution.status == ExecutionStatus.PENDING
    assert payload == {
        "task_id": execution.id,
        "status": "仍在执行",
        "result_url": f"/job/execution/job-record?id={execution.id}",
        "waited_seconds": payload["waited_seconds"],
    }
    assert payload["waited_seconds"] >= 0
    assert "失败" not in raw
    display = latest_display_payload(payload["task_id"])
    assert display["kind"] == "file"
    assert display["result_url"] == payload["result_url"]
    checked = json.loads(query_job(_config("看一下任务状态", session="sess-file-pending"), execution.id))
    assert checked["status"] == "仍在执行"
    assert checked["result_url"] == payload["result_url"]


def test_file_query_failure_after_submit_keeps_the_record_link(staged_storage, monkeypatch):
    monkeypatch.setattr(
        "apps.opspilot.services.job_tool_service._poll",
        lambda _user_info, _task_id: ({"result": False, "message": "作业平台暂时不可用"}, 1.2),
    )
    session = "sess-file-query-fail"
    target = _target()
    staged = _stage(session)
    raw = distribute_staged_files(
        _config("把 demo.txt 覆盖到 /data/opspilot-deliver", session=session),
        file_ids=[staged.id],
        target_source="manual",
        target_ids=[target.id],
        target_path="/data/opspilot-deliver",
    )
    execution = JobExecution.objects.get()
    payload = json.loads(raw)
    assert payload == {
        "task_id": execution.id,
        "status": "仍在执行",
        "result_url": f"/job/execution/job-record?id={execution.id}",
        "waited_seconds": 1,
    }
    assert raw != "失败"


def test_reused_file_query_failure_keeps_the_record_link(staged_storage, monkeypatch):
    session = "sess-file-reuse-query"
    _conversation(session)
    target = _target()
    staged = _stage(session)
    config = _config("把 demo.txt 覆盖到 /data/opspilot-deliver", session=session)
    kwargs = {
        "file_ids": [staged.id],
        "target_source": "manual",
        "target_ids": [target.id],
        "target_path": "/data/opspilot-deliver",
    }
    first = json.loads(distribute_staged_files(config, **kwargs))
    from apps.opspilot.services import job_tool_service

    def fail_query(action, user_info, body):
        if action == "query_execution":
            return {"result": False, "message": "作业平台暂时不可用"}
        return job_tool_service._rpc(action, user_info, body)

    monkeypatch.setattr(job_tool_service, "_call", fail_query)
    raw = distribute_staged_files(config, **kwargs)
    payload = json.loads(raw)
    assert payload["task_id"] == first["task_id"]
    assert payload["status"] == "仍在执行"
    assert payload["result_url"] == first["result_url"]
    assert raw != "失败"
    assert JobExecution.objects.count() == 1


def test_failed_file_distribution_stays_a_plain_failure(staged_storage, monkeypatch):
    def finish(task_func, execution):
        execution.status = ExecutionStatus.FAILED
        execution.failed_count = 1
        execution.save()
        return "queued"

    monkeypatch.setattr("apps.job_mgmt.services.celery_dispatch.dispatch_celery_task", finish)
    target = _target()
    staged = stage_distribute_file(
        owner_key="alice@domain.com",
        team_id="1",
        session_key="sess-file-failed",
        filename="demo.txt",
        data=b"file-bytes",
    )
    result = distribute_staged_files(
        _config("把 demo.txt 覆盖到 /data/opspilot-deliver", session="sess-file-failed"),
        file_ids=[staged.id],
        target_source="manual",
        target_ids=[target.id],
        target_path="/data/opspilot-deliver",
    )
    assert result == "失败"
    assert JobExecution.objects.get().status == ExecutionStatus.FAILED


def test_follow_up_finds_the_only_staged_file_without_repeating_its_name(staged_storage):
    stage_distribute_file(
        owner_key="alice@domain.com",
        team_id="1",
        session_key="thread:debug",
        filename="1111.txt",
        data=b"file-bytes",
    )
    result = distribute_staged_files(
        _config("已上传，分发到节点管理目标 local", session="thread:debug"),
        target_source="node_mgmt",
        target_ids=["node-1"],
    )
    assert result["ask"] is True
    assert "路径" in result["question"]


def test_uploaded_file_id_wins_when_the_model_invents_one(staged_storage):
    staged = stage_distribute_file(
        owner_key="alice@domain.com",
        team_id="1",
        session_key="thread:debug",
        filename="1111.txt",
        data=b"file-bytes",
    )
    config = _config("请分发文件 1111.txt", session="thread:debug")
    config["configurable"]["distribute_file_ids"] = [staged.id]
    result = distribute_staged_files(
        config,
        file_ids=["999"],
        target_source="node_mgmt",
        target_ids=["node-1"],
    )
    assert result["ask"] is True
    assert "路径" in result["question"]


def test_earlier_message_names_the_file_when_several_are_staged(staged_storage):
    stage_distribute_file(
        owner_key="alice@domain.com",
        team_id="1",
        session_key="thread:debug",
        filename="1111.txt",
        data=b"one",
    )
    stage_distribute_file(
        owner_key="alice@domain.com",
        team_id="1",
        session_key="thread:debug",
        filename="2222.txt",
        data=b"two",
    )
    config = _config("已上传，分发到节点管理目标 local", session="thread:debug")
    config["configurable"]["graph_request"] = type(
        "Request",
        (),
        {"chat_history": [{"event": "user", "message": "请分发文件 1111.txt"}], "user_message": "已上传，分发到节点管理目标 local"},
    )()
    result = distribute_staged_files(
        config,
        target_source="node_mgmt",
        target_ids=["node-1"],
    )
    assert result["ask"] is True
    assert "路径" in result["question"]


def _stage(session_key, filename="demo.txt"):
    return stage_distribute_file(
        owner_key="alice@domain.com",
        team_id="1",
        session_key=session_key,
        filename=filename,
        data=b"file-bytes",
    )


def test_earlier_overwrite_does_not_choose_strategy_for_this_distribute(staged_storage):
    session = "sess-old-overwrite"
    conversation = _conversation(session)
    conversation.messages.create(role=SkillConversationMessage.ROLE_USER, content="上次分发请覆盖，不要跳过")
    _stage(session)
    result = distribute_staged_files(
        _config("把 demo.txt 发到 /opt/deliver", session=session),
        target_source="manual",
        target_ids=[_target().id],
        target_path="/opt/deliver",
    )
    assert result["ask"] is True
    assert result["options"] == ["覆盖", "跳过"]
    assert JobExecution.objects.count() == 0

    config = _config("把 demo.txt 发到 /opt/deliver", session="thread:overwrite-history")
    config["configurable"]["graph_request"] = type(
        "Request",
        (),
        {
            "chat_history": [{"event": "user", "message": "请覆盖已有文件"}],
            "user_message": "把 demo.txt 发到 /opt/deliver",
        },
    )()
    _stage("thread:overwrite-history")
    from_history = distribute_staged_files(
        config,
        target_source="manual",
        target_ids=[_target().id],
        target_path="/opt/deliver",
    )
    assert from_history["options"] == ["覆盖", "跳过"]
    assert JobExecution.objects.count() == 0


def test_shorter_path_is_not_accepted_from_a_longer_stated_path(staged_storage):
    session = "sess-short-path"
    _stage(session)
    shortened = distribute_staged_files(
        _config("把 demo.txt 覆盖到 /data/app/config", session=session),
        target_source="manual",
        target_ids=[_target().id],
        target_path="/data",
    )
    assert shortened == {"ask": True, "question": "请给出文件要放到的目标路径。", "options": []}
    parent = distribute_staged_files(
        _config("把 demo.txt 覆盖到 /data/app/config", session=session),
        target_source="manual",
        target_ids=[_target().id],
        target_path="/data/app",
    )
    assert parent["question"] == "请给出文件要放到的目标路径。"
    assert JobExecution.objects.count() == 0


def test_old_path_in_history_does_not_authorize_this_distribute(staged_storage):
    session = "sess-old-path"
    conversation = _conversation(session)
    conversation.messages.create(role=SkillConversationMessage.ROLE_USER, content="请放到 /data/app/config")
    _stage(session)
    reused = distribute_staged_files(
        _config("把 demo.txt 覆盖分发", session=session),
        target_source="manual",
        target_ids=[_target().id],
        target_path="/data/app/config",
    )
    assert reused["question"] == "请给出文件要放到的目标路径。"
    shortened = distribute_staged_files(
        _config("把 demo.txt 覆盖分发", session=session),
        target_source="manual",
        target_ids=[_target().id],
        target_path="/data",
    )
    assert shortened["question"] == "请给出文件要放到的目标路径。"
    assert JobExecution.objects.count() == 0


def test_path_equal_to_an_entire_earlier_statement_is_accepted(staged_storage):
    session = "sess-whole-path"
    conversation = _conversation(session)
    conversation.messages.create(role=SkillConversationMessage.ROLE_USER, content="/data/app/config")
    _stage(session)
    raw = distribute_staged_files(
        _config("覆盖", session=session),
        target_source="manual",
        target_ids=[_target().id],
        target_path="/data/app/config",
    )
    payload = json.loads(raw)
    assert payload["status"] == "仍在执行"
    assert payload["result_url"].endswith(f"id={payload['task_id']}")
    shortened = distribute_staged_files(
        _config("覆盖", session=session),
        target_source="manual",
        target_ids=[_target().id],
        target_path="/data",
    )
    assert shortened["question"] == "请给出文件要放到的目标路径。"


def test_confirmed_path_uses_the_latest_full_token(staged_storage):
    session = "sess-confirm-path"
    conversation = _conversation(session)
    conversation.messages.create(role=SkillConversationMessage.ROLE_USER, content="先放到 /tmp")
    conversation.messages.create(role=SkillConversationMessage.ROLE_USER, content="放到 /data/app/config")
    _stage(session)
    target_id = _target().id
    shortened = distribute_staged_files(
        _config("确认路径", session=session),
        target_source="manual",
        target_ids=[target_id],
        target_path="/data",
    )
    assert shortened["question"] == "请给出文件要放到的目标路径。"
    older = distribute_staged_files(
        _config("确认路径", session=session),
        target_source="manual",
        target_ids=[target_id],
        target_path="/tmp",
    )
    assert older["question"] == "请给出文件要放到的目标路径。"
    confirmed = distribute_staged_files(
        _config("确认路径", session=session),
        target_source="manual",
        target_ids=[target_id],
        target_path="/data/app/config",
    )
    assert confirmed["options"] == ["覆盖", "跳过"]
    assert JobExecution.objects.count() == 0


def test_overwrite_question_does_not_claim_the_target_already_has_the_file(staged_storage):
    stage_distribute_file(
        owner_key="alice@domain.com",
        team_id="1",
        session_key="thread:debug",
        filename="1111.txt",
        data=b"file-bytes",
    )
    result = distribute_staged_files(
        _config(r"把 1111.txt 分发到 C:\temp", session="thread:debug"),
        target_source="node_mgmt",
        target_ids=["node-1"],
        target_path=r"C:\temp",
    )
    assert result["options"] == ["覆盖", "跳过"]
    assert "不会检查" in result["question"]
    assert "已存在" not in result["question"]


def test_another_filename_does_not_use_the_only_staged_file(staged_storage):
    stage_distribute_file(
        owner_key="alice@domain.com",
        team_id="1",
        session_key="thread:debug",
        filename="1111.txt",
        data=b"file-bytes",
    )
    result = distribute_staged_files(
        _config("请分发 report.pdf", session="thread:debug"),
        target_source="node_mgmt",
        target_ids=["node-1"],
    )
    assert result["result"] is False
    assert "没有可分发" in result["message"]


def test_staged_file_list_shows_only_this_session(staged_storage):
    stage_distribute_file(
        owner_key="alice@domain.com",
        team_id="1",
        session_key="sess-a",
        filename="1111.txt",
        data=b"file-bytes",
    )
    stage_distribute_file(
        owner_key="alice@domain.com",
        team_id="1",
        session_key="sess-b",
        filename="other.txt",
        data=b"other-bytes",
    )
    stage_distribute_file(
        owner_key="bob@domain.com",
        team_id="1",
        session_key="sess-a",
        filename="secret.txt",
        data=b"secret-bytes",
    )
    stage_distribute_file(
        owner_key="alice@domain.com",
        team_id="2",
        session_key="sess-a",
        filename="team.txt",
        data=b"team-bytes",
    )
    listed = list_staged_distribute_files(owner_key="alice@domain.com", team_id="1", session_key="sess-a")
    assert [item["name"] for item in listed] == ["1111.txt"]
    rendered = json.dumps(listed)
    assert "file-bytes" not in rendered
    assert "secret-bytes" not in rendered
    assert list_staged_distribute_files(owner_key="alice@domain.com", team_id="1", session_key="") == []


def test_staging_and_other_session_do_not_write_job_files(staged_storage):
    staged = stage_distribute_file(
        owner_key="alice@domain.com",
        team_id="1",
        session_key="sess-a",
        filename="demo.txt",
        data=b"file-bytes",
    )
    assert DistributionFile.objects.count() == 0
    foreign = stage_distribute_file(
        owner_key="bob@domain.com",
        team_id="1",
        session_key="sess-b",
        filename="demo.txt",
        data=b"other",
    )
    refused = distribute_staged_files(
        _config("把 demo.txt 覆盖到 /data/opspilot-deliver", session="sess-a"),
        file_ids=[foreign.id],
        target_source="manual",
        target_ids=[_target().id],
        target_path="/data/opspilot-deliver",
    )
    assert refused["result"] is False
    assert DistributionFile.objects.count() == 0
    assert ChatAttachment.objects.filter(id=staged.id).exists()


def test_watch_stops_on_terminal_or_deadline_without_model_output():
    conversation = _conversation("sess-watch")
    script = _script()
    target = _target()
    raw = run_library_script(
        _config("执行库脚本后定时检查", session="sess-watch"),
        script_id=script.id,
        target_source="manual",
        target_ids=[target.id],
    )
    task_id = json.loads(raw)["task_id"]
    scheduled = schedule_job_watch(_config("请定时检查", session="sess-watch"), task_id=task_id, interval_minutes=60)
    assert scheduled["interval_minutes"] == 60

    execution = JobExecution.objects.get(id=task_id)
    execution.status = ExecutionStatus.TIMEOUT
    execution.execution_results = [{"name": "web-1", "ip": "10.0.0.8", "stdout": "STDOUT_SECRET", "stderr": "", "exit_code": None}]
    execution.save()
    _shift_watch(conversation, task_id, next_run_at=timezone.now() - timedelta(minutes=1))
    assert scan_opspilot_job_watches() == 1
    _message, _events, watch = _job_record(conversation, task_id)
    assert watch["watch"]["active"] is False
    assert JobExecution.objects.count() == 1
    visible = [model_visible_text(item.content) for item in conversation.messages.filter(role=SkillConversationMessage.ROLE_ASSISTANT)]
    assert any(item == f"作业 {task_id}：失败" for item in visible)
    assert all("STDOUT_SECRET" not in item for item in visible)

    deadline_conversation = _conversation("sess-deadline")
    pending = run_library_script(
        _config("先提交库脚本", session="sess-deadline"),
        script_id=script.id,
        target_source="manual",
        target_ids=[target.id],
    )
    pending_id = json.loads(pending)["task_id"]
    schedule_job_watch(_config("请定时检查", session="sess-deadline"), task_id=pending_id)
    _shift_watch(
        deadline_conversation,
        pending_id,
        next_run_at=timezone.now() - timedelta(minutes=1),
        deadline_at=timezone.now() - timedelta(minutes=1),
    )
    JobExecution.objects.filter(id=pending_id).update(
        execution_results=[{"name": "web-1", "ip": "10.0.0.8", "stdout": "DEADLINE_SECRET", "stderr": "", "exit_code": None}]
    )
    assert scan_job_watches() == 1
    _message, _events, deadline_record = _job_record(deadline_conversation, pending_id)
    assert deadline_record["watch"]["active"] is False
    deadline_visible = [
        model_visible_text(item.content) for item in deadline_conversation.messages.filter(role=SkillConversationMessage.ROLE_ASSISTANT)
    ]
    assert all("DEADLINE_SECRET" not in item for item in deadline_visible)


def test_skill_flag_and_cleanup_task(staged_storage):
    enabled = LLMSkill.objects.create(name="enabled", team=[1], usage_team=[1], tools=[{"name": "job_mgmt"}])
    disabled = LLMSkill.objects.create(name="disabled", team=[1], usage_team=[1], tools=[])
    assert skill_has_job_mgmt(enabled) is True
    assert skill_has_job_mgmt(disabled) is False
    stage_distribute_file(
        owner_key="alice@domain.com",
        team_id="1",
        session_key="sess-old",
        filename="old.txt",
        data=b"old",
    )
    ChatAttachment.objects.update(created_at=timezone.now() - timedelta(days=2))
    cleanup_chat_attachments()
    assert ChatAttachment.objects.count() == 1
    ChatAttachment.objects.update(created_at=timezone.now() - timedelta(days=8))
    assert cleanup_opspilot_job_staged_files() == 1
    assert ChatAttachment.objects.count() == 0


def test_opspilot_does_not_import_the_job_app():
    import ast
    from pathlib import Path

    root = Path(__file__).resolve().parents[1]
    offenders = []
    for path in root.rglob("*.py"):
        if "tests" in path.parts:
            continue
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for node in ast.walk(tree):
            modules = []
            if isinstance(node, ast.Import):
                modules = [alias.name for alias in node.names]
            elif isinstance(node, ast.ImportFrom) and node.module:
                modules = [node.module]
            elif isinstance(node, ast.Constant) and isinstance(node.value, str):
                modules = [node.value]
            for module in modules:
                if module == "apps.job_mgmt" or module.startswith("apps.job_mgmt."):
                    offenders.append(f"{path}:{getattr(node, 'lineno', 0)}:{module}")
    assert offenders == []
