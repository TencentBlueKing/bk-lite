from copy import deepcopy
from unittest.mock import Mock, patch

import pytest

from apps.console_mgmt.models import Notification
from apps.itsm.models import FormModel, HandlerGroup, NotifyTemplate, Ticket, TicketTask, TriggerLog, Workflow, WorkflowVersion
from apps.itsm.services.ticket.service import TicketService
from apps.itsm.services.triggers import fire_triggers
from apps.itsm.tests.test_review_regressions import request
from apps.itsm.tests.test_trigger_resources import get, response_data
from apps.itsm.views.extend import resources
from apps.itsm.views.users import UserSearchView
from apps.system_mgmt.models import IMAccountAssociation, IMNotificationChannel, IMNotificationUserMapping, IntegrationInstance, User

pytestmark = [pytest.mark.django_db, pytest.mark.usefixtures("delivery_worker")]
DOMAIN = "notice.example"
OTHER_DOMAIN = "foreign.example"


def user(name, *, domain=DOMAIN, disabled=False):
    return User.objects.create(username=name, display_name=name, domain=domain, disabled=disabled)


def channel(name, team, domain=DOMAIN, *, instance_domain=None):
    instance = IntegrationInstance.objects.create(
        name=name,
        provider_key="feishu",
        domain=instance_domain or domain,
        team=team,
        status="ready",
        capability_status={"im_notification": "ready"},
    )
    association = IMAccountAssociation.objects.create(name=name, integration_instance=instance, domain=domain, status="ready")
    return IMNotificationChannel.objects.create(
        account_association=association, name=name, integration_instance=instance, team=team, status="ready", domain=domain
    )


def template(name, media, *, domain=DOMAIN):
    return NotifyTemplate.objects.create(
        event=name, title_tpl="{{ ticket_title }} " + name, content_tpl="{{ sn }} {{ workflow }} {{ node }}", channel_type=media, domain=domain
    )


def mapping(target, source):
    IMNotificationUserMapping.objects.create(
        account_association=target.account_association,
        user=source,
        external_identity_key="user_id",
        external_identity_value=f"external-{source.pk}",
        external_receive_key="user_id",
        match_context={"source": "manual"},
        external_snapshot={"user_id": f"external-{source.pk}"},
    )


def rule_request(method, payload):
    req = request(method, payload, domain=DOMAIN, permissions=["rule-Add", "rule-Edit", "rule-View"], username="owner")
    req.user.group_list = [{"id": 11}]
    return req


@pytest.fixture
def fixture():
    form = FormModel.objects.create(name="采购模板", key="apply", domain=DOMAIN)
    flow = Workflow.objects.create(name="采购流程", key="apply", form=form, domain=DOMAIN)
    schema = {
        "fields": [
            {"key": "person", "type": "user", "label": "采购负责人"},
            {"key": "people", "type": "multiUser", "label": "采购协办人"},
            {"key": "untrusted", "type": "input", "label": "备注"},
        ]
    }
    version = WorkflowVersion.objects.create(workflow=flow, version_no=1, is_published=True, design={"form_schema": schema}, domain=DOMAIN)
    flow.current_version = version
    flow.save(update_fields=["current_version"])
    creator, handler, fixed, member, referenced = [user(name) for name in ["creator", "handler", "fixed", "member", "referenced"]]
    absent, obsolete, pending = [user(name) for name in ["absent", "obsolete", "pending"]]
    disabled = user("disabled", disabled=True)
    user("remote", domain=OTHER_DOMAIN)
    group = HandlerGroup.objects.create(name="采购组", members=[member.username, creator.username, disabled.username, "remote"], domain=DOMAIN)
    foreign_group = HandlerGroup.objects.create(name="其他租户", members=[absent.username], domain=OTHER_DOMAIN)
    selected = channel("测试飞书一", [11])
    other = channel("测试飞书二", [11])
    forbidden = channel("其他团队", [12])
    foreign = channel("其他租户渠道", [11], OTHER_DOMAIN)
    mixed = channel("其他租户集成", [11], instance_domain=OTHER_DOMAIN)
    im_template = template("采购核对", "im")
    site_template = template("站内确认", "site")
    foreign_template = template("其他租户模板", "im", domain=OTHER_DOMAIN)
    for item in (creator, handler, fixed, member, referenced, absent, obsolete, pending, disabled):
        mapping(selected, item)
        mapping(other, item)
    rule = {
        "name": "动作投递",
        "event": "ticket_update",
        "config": {
            "scope": {"mode": "include", "workflow_ids": [flow.pk]},
            "actions": [
                {
                    "type": "notice",
                    "value": "",
                    "notice": {
                        "recipients": {
                            "roles": ["creator", "current_assignees"],
                            "users": ["fixed"],
                            "group_ids": [group.pk],
                            "field_keys": ["person", "people"],
                        },
                        "channels": [{"type": "im", "channel_id": selected.pk, "template_id": im_template.pk}],
                    },
                }
            ],
        },
    }
    return {
        "flow": flow,
        "version": version,
        "recipient_ids": [entry.pk for entry in (creator, handler, fixed, member, referenced)],
        "rule": rule,
        "group": group,
        "foreign_group": foreign_group,
        "selected": selected,
        "other": other,
        "forbidden": forbidden,
        "foreign": foreign,
        "mixed": mixed,
        "im_template": im_template,
        "site_template": site_template,
        "foreign_template": foreign_template,
    }


def make_ticket(fixture, *, is_test=False):
    flow, version = fixture["flow"], fixture["version"]
    ticket = Ticket.objects.create(
        sn="NOTICE-001",
        title="验收消息",
        creator="creator",
        created_by="absent",
        workflow=flow,
        workflow_version=version,
        is_test=is_test,
        domain=DOMAIN,
        form_data={"person": ["referenced"], "people": ["member", "fixed", "disabled", "remote"], "untrusted": "absent"},
    )
    TicketTask.objects.create(ticket=ticket, assignee="handler", node_id="approve", node_name="采购审核", status="claimed")
    TicketTask.objects.create(ticket=ticket, assignee="obsolete", node_id="submit", node_name="提交", status="done")
    return ticket


def test_notification_catalog_uses_authorized_channels_and_published_person_fields(fixture):
    from apps.itsm.views.triggers import trigger_options

    domain_options = response_data(trigger_options(rule_request("get", None)))["notice"]
    assert {entry["id"] for entry in domain_options["channels"]} == {fixture["selected"].pk, fixture["other"].pk}
    assert domain_options["groups"] == [{"id": fixture["group"].pk, "name": "采购组"}]
    assert {entry["id"] for entry in domain_options["templates"]} == {fixture["im_template"].pk, fixture["site_template"].pk}
    assert domain_options["form_field_groups"] == [
        {
            "name": "采购流程",
            "workflow_id": fixture["flow"].pk,
            "form_id": fixture["flow"].form_id,
            "service_ids": [],
            "fields": [{"key": "person", "label": "采购负责人"}, {"key": "people", "label": "采购协办人"}],
        }
    ]
    assert get("/api/v1/itsm/api/triggers/options/", permissions=["ticket-View"], domain=DOMAIN).status_code == 403
    users = UserSearchView().get(request(payload={"q": "fixed"}, permissions=["rule-Add"], domain=DOMAIN))
    assert users.status_code == 200 and [entry["username"] for entry in users.data["items"]] == ["fixed"]


@pytest.mark.parametrize(
    "bad_target",
    ["forbidden", "foreign", "mixed", "foreign_group", "site_template", "foreign_template", "nonperson", "foreign_user", "empty", "duplicate"],
)
def test_rejects_invalid_notice_sources_and_channels(fixture, bad_target):
    payload = deepcopy(fixture["rule"])
    notice = payload["config"]["actions"][0]["notice"]
    route = notice["channels"][0]
    if bad_target in {"forbidden", "foreign", "mixed"}:
        route["channel_id"] = fixture[bad_target].pk
    elif bad_target.endswith("_template"):
        route["template_id"] = fixture[bad_target].pk
    elif bad_target == "foreign_group":
        notice["recipients"]["group_ids"] = [fixture[bad_target].pk]
    elif bad_target == "nonperson":
        notice["recipients"]["field_keys"] = ["untrusted"]
    elif bad_target == "foreign_user":
        notice["recipients"]["users"] = ["remote"]
    elif bad_target == "empty":
        notice["channels"] = []
    elif bad_target == "duplicate":
        notice["channels"].append(route.copy())
    assert resources(rule_request("post", payload), "triggers").status_code == 400


@pytest.mark.parametrize("content_mode", [None, "template"])
def test_sends_selected_template_and_recipient_union_only_on_selected_im(fixture, django_capture_on_commit_callbacks, content_mode):
    payload = fixture["rule"]
    if content_mode is not None:
        payload["config"]["actions"][0]["notice"]["content_mode"] = content_mode
    saved = response_data(resources(rule_request("post", payload), "triggers"))
    assert saved["config"]["actions"] == payload["config"]["actions"]
    ticket = make_ticket(fixture)
    with patch("apps.itsm.services.notify.service.SystemMgmt") as rpc, django_capture_on_commit_callbacks(execute=True):
        rpc.return_value.send_msg_with_channel.return_value = {"result": True}
        fire_triggers(ticket, "save", "owner")
    sender = rpc.return_value.send_msg_with_channel
    sender.assert_called_once()
    channel_id, title, content, user_ids = sender.call_args.args
    assert channel_id == fixture["selected"].pk
    assert title == "验收消息 采购核对"
    assert content.startswith("NOTICE-001 采购流程 采购审核")
    assert content.endswith(f"/itsm/tickets/{ticket.pk}")
    assert set(user_ids) == set(fixture["recipient_ids"])
    assert sender.call_args.kwargs == {"channel_type": "im_notification"}
    assert not Notification.objects.filter(target_url=f"/itsm/tickets/{ticket.pk}").exists()
    log = TriggerLog.objects.get(ticket_id=ticket.pk)
    assert log.status == "success" and "测试飞书一" in log.message and "5 人" in log.message


def test_custom_content_renders_variables_on_each_selected_channel(fixture, settings, django_capture_on_commit_callbacks):
    settings.WEB_BASE_URL = "https://workbench.example/"
    template("trigger", "site")
    template("trigger", "im")
    payload = fixture["rule"]
    action = payload["config"]["actions"][0]
    action["value"] = "\n".join(
        ("${ticket_title} | $sn | $workflow | $node | $creator | $trigger_name | $ticket_link", "普通文本 {{ 2 + 2 }} | $url | $未知 | $$ | $20")
    )
    action["notice"].update(content_mode="custom", channels=[{"type": "site"}, {"type": "im", "channel_id": fixture["selected"].pk}])
    saved = response_data(resources(rule_request("post", payload), "triggers"))
    assert saved["config"]["actions"] == [action]

    ticket = make_ticket(fixture)
    with patch("apps.itsm.services.notify.service.SystemMgmt") as rpc, django_capture_on_commit_callbacks(execute=True):
        rpc.return_value.send_msg_with_channel.return_value = {"result": True}
        fire_triggers(ticket, "save", "owner")

    relative_link = f"/itsm/tickets/{ticket.pk}"
    expected = "\n".join(
        (
            f"验收消息 | NOTICE-001 | 采购流程 | 采购审核 | creator | 动作投递 | https://workbench.example{relative_link}",
            "普通文本 {{ 2 + 2 }} | $url | $未知 | $ | $20",
        )
    )
    site = Notification.objects.get(target_url=relative_link)
    assert site.content == f"动作投递\n{expected}"
    sender = rpc.return_value.send_msg_with_channel
    sender.assert_called_once()
    channel_id, title, content, user_ids = sender.call_args.args
    assert (channel_id, title, content) == (fixture["selected"].pk, "动作投递", expected)
    assert set(user_ids) == set(fixture["recipient_ids"])
    assert TriggerLog.objects.get(ticket_id=ticket.pk).status == "success"


@pytest.mark.parametrize(
    ("mode", "value", "with_template"),
    [("custom", " \n", False), ("custom", "已通过", True), ("template", "已通过", True), ("invalid", "", False)],
)
def test_notification_content_modes_reject_conflicting_input(fixture, mode, value, with_template):
    payload = fixture["rule"]
    action = payload["config"]["actions"][0]
    action["value"] = value
    action["notice"]["content_mode"] = mode
    if not with_template:
        action["notice"]["channels"][0].pop("template_id")
    assert resources(rule_request("post", payload), "triggers").status_code == 400


def test_test_ticket_never_sends_selected_im_or_falls_back_to_site(fixture, django_capture_on_commit_callbacks):
    response_data(resources(rule_request("post", fixture["rule"]), "triggers"))
    ticket = make_ticket(fixture, is_test=True)
    with patch("apps.itsm.services.notify.service.SystemMgmt") as rpc, django_capture_on_commit_callbacks(execute=True):
        fire_triggers(ticket, "save", "owner")
    rpc.assert_not_called()
    assert not Notification.objects.filter(target_url=f"/itsm/tickets/{ticket.pk}").exists()
    assert "测试工单" in TriggerLog.objects.get(ticket_id=ticket.pk).message


def test_activity_enter_uses_live_tasks_instead_of_stale_task_projection(fixture, django_capture_on_commit_callbacks):
    payload = fixture["rule"]
    payload["event"] = "activity_into"
    notice = payload["config"]["actions"][0]["notice"]
    notice["recipients"] = {"roles": ["current_assignees"], "users": [], "group_ids": [], "field_keys": []}
    notice["channels"] = [{"type": "site", "template_id": fixture["site_template"].pk}]
    response_data(resources(rule_request("post", payload), "triggers"))
    ticket = make_ticket(fixture)
    ticket.process_instance_id = "flowable-01"
    ticket.save(update_fields=["process_instance_id"])
    engine = Mock()
    engine.list_tasks_including_children.return_value = [
        {"id": "step-1", "taskDefinitionKey": "review1", "name": "初审", "assignee": "pending"},
        {"id": "step-2", "taskDefinitionKey": "review2", "name": "复审", "assignee": "member"},
    ]
    with (
        patch("apps.itsm.services.ticket.service.itsm_event.send"),
        patch("apps.itsm.services.todo_sync.push_todo"),
        django_capture_on_commit_callbacks(execute=True),
    ):
        TicketService(engine).sync_ticket(ticket)
    sent = list(Notification.objects.filter(target_url=f"/itsm/tickets/{ticket.pk}"))
    assert len(sent) == 2
    assert all(set(message.recipient_usernames) == {"pending", "member"} for message in sent)
    assert all("验收消息 站内确认" in message.content for message in sent)


def test_sends_each_selected_route_even_if_another_route_raises(fixture, django_capture_on_commit_callbacks, caplog):
    payload = fixture["rule"]
    notice = payload["config"]["actions"][0]["notice"]
    notice["channels"].insert(0, {"type": "site", "template_id": fixture["site_template"].pk})
    notice["channels"].append({"type": "im", "channel_id": fixture["other"].pk, "template_id": fixture["im_template"].pk})
    response_data(resources(rule_request("post", payload), "triggers"))
    ticket = make_ticket(fixture)
    with (
        patch("apps.itsm.services.trigger_notice.send_site_notification", side_effect=RuntimeError("内容不应进入日志")),
        patch("apps.itsm.services.notify.service.SystemMgmt") as rpc,
        django_capture_on_commit_callbacks(execute=True),
    ):
        rpc.return_value.send_msg_with_channel.return_value = {"result": True}
        fire_triggers(ticket, "save", "owner")
    calls = rpc.return_value.send_msg_with_channel.call_args_list
    assert [entry.args[0] for entry in calls] == [fixture["selected"].pk, fixture["other"].pk]
    assert all(set(entry.args[3]) == set(fixture["recipient_ids"]) for entry in calls)
    log = TriggerLog.objects.get(ticket_id=ticket.pk)
    assert log.status == "failed" and "站内通知 发送失败" in log.message and "测试飞书二 已发送 5 人" in log.message
    records = [record for record in caplog.records if record.msg.startswith("触发器渠道投递失败")]
    assert len(records) == 1
    record = records[0]
    assert record.args == (f"itsm-trigger-{log.pk}", None, "dispatch_site", "RuntimeError")
    assert record.getMessage().endswith("failed_stage=dispatch_site error_type=RuntimeError")
    assert record.exc_info is not None
    assert record.exc_info[2] is not None
    assert "内容不应进入日志" not in caplog.text


def test_deleted_template_cannot_send_with_a_default_template(fixture, django_capture_on_commit_callbacks):
    response_data(resources(rule_request("post", fixture["rule"]), "triggers"))
    template("trigger", "im")
    fixture["im_template"].delete()
    ticket = make_ticket(fixture)
    with patch("apps.itsm.services.notify.service.SystemMgmt") as rpc, django_capture_on_commit_callbacks(execute=True):
        fire_triggers(ticket, "save", "owner")
    rpc.assert_not_called()
    log = TriggerLog.objects.get(ticket_id=ticket.pk)
    assert log.status == "failed" and "模板不可用" in log.message


def test_reads_person_fields_from_the_ticket_version(fixture, django_capture_on_commit_callbacks):
    payload = fixture["rule"]
    notice = payload["config"]["actions"][0]["notice"]
    notice["recipients"] = {"field_keys": ["people"], "roles": [], "group_ids": [], "users": []}
    response_data(resources(rule_request("post", payload), "triggers"))

    ticket = make_ticket(fixture)
    ticket.workflow_version = WorkflowVersion.objects.create(
        workflow=ticket.workflow,
        version_no=2,
        is_published=True,
        design={"form_schema": {"fields": [{"key": "people", "type": "textarea"}]}},
        domain=DOMAIN,
    )
    ticket.save(update_fields=["workflow_version"])
    with patch("apps.itsm.services.notify.service.SystemMgmt") as rpc, django_capture_on_commit_callbacks(execute=True):
        fire_triggers(ticket, "save", "owner")
    rpc.assert_not_called()
    assert "无有效通知人" in TriggerLog.objects.get(ticket_id=ticket.pk).message


def test_im_batches_larger_user_groups_and_reports_missing_mapping(fixture, django_capture_on_commit_callbacks):
    payload = fixture["rule"]
    notice = payload["config"]["actions"][0]["notice"]
    notice["recipients"] = {"group_ids": [fixture["group"].pk], "field_keys": [], "roles": [], "users": []}
    response_data(resources(rule_request("post", payload), "triggers"))
    people = User.objects.bulk_create([User(username=f"receiver-{index}", domain=DOMAIN) for index in range(102)])
    for person in people[:-1]:
        mapping(fixture["selected"], person)
    fixture["group"].members = [person.username for person in people]
    fixture["group"].save(update_fields=["members"])

    ticket = make_ticket(fixture)
    with patch("apps.itsm.services.notify.service.SystemMgmt") as rpc, django_capture_on_commit_callbacks(execute=True):
        rpc.return_value.send_msg_with_channel.return_value = {"result": True}
        fire_triggers(ticket, "save", "owner")
    calls = rpc.return_value.send_msg_with_channel.call_args_list
    assert [len(entry.args[3]) for entry in calls] == [100, 1]
    assert all(entry.args[0] == fixture["selected"].pk for entry in calls)
    assert {user_id for entry in calls for user_id in entry.args[3]} == {person.pk for person in people[:-1]}
    log = TriggerLog.objects.get(ticket_id=ticket.pk)
    assert log.status == "failed" and "已发送 101 人，1 人无有效映射" in log.message


def test_recovery_does_not_resend_unknown_im_and_completes_other_routes(fixture, django_capture_on_commit_callbacks):
    from datetime import timedelta

    from django.utils import timezone

    from apps.itsm.tasks import trigger_notice_tick

    class WorkerStopped(BaseException):
        pass

    payload = fixture["rule"]
    notice = payload["config"]["actions"][0]["notice"]
    notice["channels"].insert(0, {"type": "site", "template_id": fixture["site_template"].pk})
    notice["channels"].append({"type": "im", "channel_id": fixture["other"].pk, "template_id": fixture["im_template"].pk})
    response_data(resources(rule_request("post", payload), "triggers"))
    ticket = make_ticket(fixture)

    with patch("apps.itsm.services.notify.service.SystemMgmt") as rpc:
        with django_capture_on_commit_callbacks(execute=False) as callbacks:
            fire_triggers(ticket, "save", "owner")
        sender = rpc.return_value.send_msg_with_channel
        sender.side_effect = [WorkerStopped(), {"result": True}]
        with pytest.raises(WorkerStopped):
            callbacks[0]()

        log = TriggerLog.objects.get(ticket_id=ticket.pk)
        assert log.status == "pending"
        assert sender.call_count == 1
        trigger_notice_tick()
        assert sender.call_count == 1

        TriggerLog.objects.filter(pk=log.pk).update(delivery_claimed_at=timezone.now() - timedelta(minutes=6))
        trigger_notice_tick()
        trigger_notice_tick()

    log.refresh_from_db()
    assert log.status == "failed"
    assert "投递结果未知，请核对" in log.message
    assert "测试飞书二 已发送 5 人" in log.message
    assert [entry.args[0] for entry in sender.call_args_list] == [fixture["selected"].pk, fixture["other"].pk]
    assert Notification.objects.filter(target_url=f"/itsm/tickets/{ticket.pk}").count() == 1


def test_retry_after_result_write_failure_reuses_confirmed_receipts(fixture, django_capture_on_commit_callbacks, monkeypatch, caplog):
    from datetime import timedelta

    from django.db import DatabaseError
    from django.db.models import QuerySet
    from django.utils import timezone

    from apps.itsm.tasks import trigger_notice_tick

    response_data(resources(rule_request("post", fixture["rule"]), "triggers"))
    ticket = make_ticket(fixture)
    original_update = QuerySet.update
    storage_error = DatabaseError("通知正文不应出现在回写日志")
    fail_once = True

    def update(queryset, **fields):
        nonlocal fail_once
        if fail_once and queryset.model is TriggerLog and fields.get("status") == TriggerLog.Status.SUCCESS:
            fail_once = False
            raise storage_error
        return original_update(queryset, **fields)

    monkeypatch.setattr(QuerySet, "update", update)
    with patch("apps.itsm.services.notify.service.SystemMgmt") as rpc:
        sender = rpc.return_value.send_msg_with_channel
        sender.return_value = {"result": True}
        with django_capture_on_commit_callbacks(execute=True):
            fire_triggers(ticket, "save", "owner")

        log = TriggerLog.objects.get(ticket_id=ticket.pk)
        assert log.status == "pending"
        assert sender.call_count == 1

        TriggerLog.objects.filter(pk=log.pk).update(delivery_claimed_at=timezone.now() - timedelta(minutes=6))
        trigger_notice_tick()

    sender.assert_called_once()
    log.refresh_from_db()
    assert log.status == "success"
    assert log.delivery_payload is None
    records = [record for record in caplog.records if record.msg.startswith("触发器通知处理失败")]
    assert len(records) == 1
    record = records[0]
    assert record.args == (log.pk, "persist", "DatabaseError")
    assert record.exc_info[2] is storage_error.__traceback__
    assert str(storage_error) == "通知正文不应出现在回写日志"
    assert str(storage_error) not in caplog.text
