import re
from datetime import timedelta
from urllib.parse import parse_qs, urlsplit

import pytest
from django.utils import timezone

from apps.system_mgmt.models import Channel, ChannelChoices, User
from apps.workflow.models import ExecutionArtifact, Workflow, WorkflowExecution
from apps.workflow.services.atoms import notification_atom
from apps.workflow.services.report_links import read_report_download_link

pytestmark = pytest.mark.django_db


@pytest.fixture(autouse=True)
def prevent_network(mocker):
    mocker.patch("requests.sessions.Session.request", side_effect=AssertionError("本测试禁止访问真实渠道"))


@pytest.fixture
def execution():
    workflow = Workflow.objects.create(name="附件投递", team=[7], definition={})
    return WorkflowExecution.objects.create(workflow=workflow, workflow_version=1, team=[7])


@pytest.fixture
def artifacts(execution):
    return [
        ExecutionArtifact.objects.create(
            execution=execution,
            team=[7],
            filename=name,
            object_key=f"reports/{name}",
            size=8,
            expires_at=timezone.now() + timedelta(days=1),
        )
        for name in ("早报.docx", "明细.xlsx")
    ]


def deliver(channel_type, execution, refs, **overrides):
    channel = Channel.objects.create(name="附件模拟渠道", team=[7], channel_type=channel_type, config={"bot_key": "test-key"})
    recipients = []
    if channel_type == ChannelChoices.EMAIL:
        user = User.objects.create(username="mail_user", email="test@example.com", password="x", group_list=[{"id": 7}])
        recipients = [str(user.pk)]
    return notification_atom(
        {
            "channel_id": channel.pk,
            "notification_type": "WECOM_BOT" if channel_type == ChannelChoices.ENTERPRISE_WECHAT_BOT else channel_type.upper(),
            "__bklite_context": {"organization_id": 7, "execution_id": str(execution.pk)},
            "body": "请查收",
            "title": "日报",
            "recipients": recipients,
            "artifacts": refs,
            **overrides,
        }
    )["delivery"]


@pytest.mark.parametrize(
    "channel_type", [ChannelChoices.EMAIL, ChannelChoices.FEISHU_BOT, ChannelChoices.DINGTALK_BOT, ChannelChoices.CUSTOM_WEBHOOK]
)
def test_notification_links_open_both_bound_files_once(mocker, settings, execution, artifacts, channel_type):
    settings.WEB_BASE_URL = "https://portal.example"
    send = mocker.patch("apps.system_mgmt.nats.channels.send_msg_with_channel", return_value={"result": True})
    refs = [{"id": str(record.pk), "filename": "错误上游文件名"} for record in artifacts]
    delivery = deliver(channel_type, execution, refs, report_artifact=refs[0])
    assert delivery["code"] == "delivered"
    content = send.call_args.args[2]
    assert content.count("早报.docx") == content.count("明细.xlsx") == 1
    assert "错误上游文件名" not in content
    urls = re.findall(r"https://[^\s<>)\"]+", content)
    for artifact, url in zip(artifacts, urls, strict=True):
        assert urlsplit(url).path == "/api/proxy/workflow/api/artifacts/shared/"
        assert read_report_download_link(parse_qs(urlsplit(url).query)["token"][0]) == {
            "execution_id": str(execution.pk),
            "team": 7,
            "artifact_id": str(artifact.pk),
        }


@pytest.mark.parametrize("failure", ["", "upload_failed", "file_send_failed"])
def test_wecom_posts_markdown_with_links_then_native_files(mocker, settings, execution, artifacts, failure):
    settings.WEB_BASE_URL = "https://portal.example"
    mocker.patch("apps.system_mgmt.utils.channel_utils.is_valid_webhook_url", return_value=True)
    mocker.patch("apps.workflow.services.artifacts.WorkflowObjectStore.get", return_value=(b"document", "", 8))
    responses = [{"errcode": 0}, {"errcode": 0, "media_id": "media-1"}, {"errcode": 0}]
    responses += [{"errcode": 45001}] if failure == "upload_failed" else [{"errcode": 0, "media_id": "media-2"}, {"errcode": 1 if failure else 0}]
    post = mocker.patch(
        "apps.system_mgmt.utils.channel_utils.requests.post", side_effect=[mocker.Mock(json=lambda item=item: item) for item in responses]
    )

    mocker.patch("apps.system_mgmt.utils.channel_utils.safe_post", post)
    delivery = deliver(ChannelChoices.ENTERPRISE_WECHAT_BOT, execution, [{"id": str(artifact.pk)} for artifact in artifacts])
    first, *rest = post.call_args_list
    assert first.kwargs["json"]["msgtype"] == "markdown"
    body = first.kwargs["json"]["markdown"]["content"]
    assert all(f"[{artifact.filename}](https://portal.example/" in body for artifact in artifacts)
    assert len(re.findall("msgtype.*?markdown", str(post.call_args_list))) == 1
    assert post.call_count == len(responses)
    upload, file_request = rest[:2]
    assert upload.args == ("https://qyapi.weixin.qq.com/cgi-bin/webhook/upload_media",)
    assert upload.kwargs["params"] == {"key": "test-key", "type": "file"}
    assert file_request.kwargs["params"] == {"key": "test-key"}
    assert upload.kwargs["headers"]["Content-Type"].startswith("multipart/form-data; boundary=")
    assert 'name="media"; filename="早报.docx"; filelength=8'.encode() in upload.kwargs["data"]
    assert b"document" in upload.kwargs["data"]
    assert file_request.kwargs["json"] == {"msgtype": "file", "file": {"media_id": "media-1"}}
    assert all(call.kwargs["allow_redirects"] is False for call in post.call_args_list)
    assert delivery["retryable"] is False
    assert delivery["data"]["files_sent"] == (1 if failure else 2)
    assert delivery["data"]["files_link_only"] == (1 if failure else 0)
    assert delivery["data"]["files"][0]["status"] == "sent"
    if failure:
        assert delivery["code"] == "delivered_with_file_fallback"
        assert delivery["data"]["files"][1]["reason"] == failure
    else:
        assert delivery["code"] == "delivered"


@pytest.mark.parametrize("invalid", ["team", "execution", "expired", "deleted", "missing", "relative", "oversized", "malformed"])
def test_invalid_explicit_file_stops_delivery(mocker, settings, execution, artifacts, invalid):
    settings.WEB_BASE_URL = "" if invalid == "relative" else "https://portal.example"
    blocked = artifacts[1]
    ref = {"id": str(blocked.pk)}
    if invalid == "execution":
        blocked.execution = WorkflowExecution.objects.create(workflow=execution.workflow, workflow_version=1, team=[7])
    elif invalid == "team":
        blocked.team = [8]
    elif invalid == "expired":
        blocked.expires_at = timezone.now() - timedelta(seconds=1)
    elif invalid == "deleted":
        blocked.deleted_at = timezone.now()
    elif invalid == "missing":
        ref["id"] = "00000000-0000-0000-0000-000000000000"
    elif invalid == "oversized":
        blocked.size = 51 * 1024 * 1024
    elif invalid == "malformed":
        ref = {}
    blocked.save()
    send = mocker.patch("apps.system_mgmt.nats.channels.send_msg_with_channel")
    with pytest.raises(ValueError, match="报告文件|WEB_BASE_URL"):
        deliver(ChannelChoices.CUSTOM_WEBHOOK, execution, [{"id": str(artifacts[0].pk)}, ref])
    send.assert_not_called()


def test_wecom_rejects_oversized_markdown_before_http(mocker, settings, execution, artifacts):
    settings.WEB_BASE_URL = "https://portal.example"
    post = mocker.patch("apps.system_mgmt.utils.channel_utils.requests.post")
    with pytest.raises(ValueError, match="4096"):
        deliver(ChannelChoices.ENTERPRISE_WECHAT_BOT, execution, [{"id": str(artifacts[0].pk)}], body="警" * 1350)
    post.assert_not_called()


def test_wecom_keeps_download_link_for_native_file_outside_provider_size(mocker, settings, execution, artifacts):
    settings.WEB_BASE_URL = "https://portal.example"
    artifact = artifacts[0]
    artifact.size = 20 * 1024 * 1024 + 1
    artifact.save(update_fields=["size"])
    mocker.patch("apps.system_mgmt.utils.channel_utils.is_valid_webhook_url", return_value=True)
    read = mocker.patch("apps.workflow.services.artifacts.WorkflowObjectStore.get")
    post = mocker.patch("apps.system_mgmt.utils.channel_utils.requests.post", return_value=mocker.Mock(json=lambda: {"errcode": 0}))

    delivery = deliver(ChannelChoices.ENTERPRISE_WECHAT_BOT, execution, [{"id": str(artifact.pk)}])

    post.assert_called_once()
    assert artifact.filename in post.call_args.kwargs["json"]["markdown"]["content"]
    read.assert_not_called()
    assert delivery["data"]["files"] == [
        {"id": str(artifact.pk), "filename": artifact.filename, "status": "link_only", "reason": "file_size_unsupported"}
    ]


def test_wecom_refused_markdown_stops_before_upload(mocker, settings, execution, artifacts):
    settings.WEB_BASE_URL = "https://portal.example"
    mocker.patch("apps.system_mgmt.utils.channel_utils.is_valid_webhook_url", return_value=True)
    post = mocker.patch("apps.system_mgmt.utils.channel_utils.requests.post", return_value=mocker.Mock(json=lambda: {"errcode": 93000}))
    read = mocker.patch("apps.workflow.services.artifacts.WorkflowObjectStore.get")
    with pytest.raises(ValueError, match="企微机器人未接受通知正文"):
        deliver(ChannelChoices.ENTERPRISE_WECHAT_BOT, execution, [{"id": str(artifacts[0].pk)}])
    read.assert_not_called()
    post.assert_called_once()
