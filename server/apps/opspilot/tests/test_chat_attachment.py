"""对话附件上传、门禁、注入、鉴权与清理。"""

import json
import logging
from datetime import timedelta
from types import SimpleNamespace

import pytest
from celery.exceptions import SoftTimeLimitExceeded
from django.core.files.base import ContentFile
from django.core.files.storage import FileSystemStorage
from django.core.files.uploadedfile import SimpleUploadedFile
from django.http import StreamingHttpResponse
from django.utils import timezone
from django.utils.datastructures import MultiValueDict
from rest_framework.test import APIRequestFactory, force_authenticate

from apps.base.models import User, UserAPISecret
from apps.opspilot.enum import SkillChannelChoices
from apps.opspilot.metis.llm.chain.token_utils import count_text_tokens
from apps.opspilot.models import ChatAttachment, LLMSkill, SkillChannel, SkillConversation, SkillConversationMessage
from apps.opspilot.services.chat_attachment_service import (
    PARSE_FAILED_TEMPLATE,
    ChatAttachmentError,
    apply_current_turn_attachments,
    classify_upload,
    cleanup_chat_attachments,
    compose_user_message,
    history_document_suffixes,
    load_sendable_attachments,
    parse_chat_attachment,
    read_bounded_upload,
    store_upload,
)
from apps.opspilot.services.skill_channel_chat_service import SkillChannelChatError, serialize_skill_session_messages, stream_skill_channel_chat
from apps.opspilot.tasks.chat_attachment import parse_chat_attachment_task
from apps.opspilot.views.chat_attachment import chat_attachment_status, download_chat_attachment, upload_chat_attachment
from apps.opspilot.views.skill_channel import execute_skill_embedded_chat

pytestmark = pytest.mark.django_db

PNG = b"\x89PNG\r\n\x1a\n" + b"pixels"
PDF = b"%PDF-1.4\n1 0 obj\n"
OFFICE = b"PK\x03\x04" + b"\x00" * 32
SECRET_FILE = b"SECRET_FILE_BYTES"


@pytest.fixture
def local_storage(tmp_path, monkeypatch):
    storage = FileSystemStorage(location=tmp_path, base_url="/chat-attachments/")
    monkeypatch.setattr(ChatAttachment._meta.get_field("file"), "storage", storage)
    return storage


def _user(username="chat-att-user"):
    return User.objects.create_user(
        username=username,
        password="x",
        domain="domain.com",
        locale="en",
        group_list=[{"id": 1, "name": "T1"}],
        roles=["admin"],
    )


def _skill():
    return LLMSkill.objects.create(name="att-skill", team=[1], usage_team=[1])


def _channel(skill):
    return SkillChannel.objects.create(
        skill=skill,
        channel_type=SkillChannelChoices.WEB_CHAT,
        enabled=True,
        usage_team=[1],
    )


def _conversation(skill, channel, owner="chat-att-user@domain.com"):
    return SkillConversation.objects.create(
        session_id="sess-att",
        skill=skill,
        channel=channel,
        external_user_id=owner,
    )


def _attachment(storage, *, name, data, mime, status, owner="chat-att-user@domain.com", team="1", message=None, conversation=None, parsed=""):
    attachment = ChatAttachment(
        original_name=name,
        mime_type=mime,
        size=len(data),
        status=status,
        parsed_text=parsed,
        owner_key=owner,
        team_id=team,
        message=message,
        conversation=conversation,
    )
    attachment.file.save(name, ContentFile(data), save=False)
    attachment.save()
    return attachment


def test_light_text_is_ready_without_enqueue(local_storage, monkeypatch):
    sent = []
    monkeypatch.setattr(
        "apps.opspilot.services.chat_attachment_service.current_app.send_task",
        lambda *args, **kwargs: sent.append((args, kwargs)),
    )
    attachment = store_upload(filename="notes.txt", data=b"hello file", owner_key="u@d", team_id="1")
    assert attachment.status == ChatAttachment.STATUS_READY
    assert attachment.parsed_text == "hello file"
    assert sent == []


def test_heavy_upload_stays_pending_and_enqueues_without_parsing(local_storage, monkeypatch):
    sent = []
    monkeypatch.setattr(
        "apps.opspilot.services.chat_attachment_service.current_app.send_task",
        lambda *args, **kwargs: sent.append((args, kwargs)),
    )
    called = []
    monkeypatch.setattr(
        "apps.opspilot.services.chat_attachment_service.parse_chat_attachment",
        lambda attachment_id: called.append(attachment_id),
    )
    attachment = store_upload(filename="report.pdf", data=PDF, owner_key="u@d", team_id="1")
    assert attachment.status == ChatAttachment.STATUS_PENDING
    assert called == []
    assert sent[0][0] == ("apps.opspilot.tasks.parse_chat_attachment",)
    assert sent[0][1]["queue"] == "opspilot_chat_parse"
    assert sent[0][1]["args"] == [attachment.id]


def test_rejects_unknown_type_oversize_and_forged_extension(local_storage):
    with pytest.raises(ChatAttachmentError) as unknown:
        classify_upload("payload.zip", b"PK\x03\x04zip")
    assert unknown.value.code == "unsupported_type"
    with pytest.raises(ChatAttachmentError) as executable:
        classify_upload("notes.txt", b"MZ" + b"\x00" * 8)
    assert executable.value.code == "unsupported_type"
    with pytest.raises(ChatAttachmentError) as forged:
        classify_upload("notes.pdf", PNG)
    assert forged.value.code == "magic_mismatch"
    with pytest.raises(ChatAttachmentError) as huge:
        classify_upload("shot.png", PNG + b"0" * (5 * 1024 * 1024))
    assert huge.value.code == "file_too_large"
    office = classify_upload("sheet.xlsx", OFFICE)
    assert office[0] == "document"


def test_pending_and_failed_are_rejected_without_waiting(local_storage, monkeypatch):
    pending = _attachment(local_storage, name="a.pdf", data=PDF, mime="application/pdf", status=ChatAttachment.STATUS_PENDING)
    failed = _attachment(local_storage, name="b.pdf", data=PDF, mime="application/pdf", status=ChatAttachment.STATUS_FAILED)
    parsed = []
    monkeypatch.setattr(
        "apps.opspilot.services.chat_attachment_service.parse_chat_attachment",
        lambda attachment_id: parsed.append(attachment_id),
    )
    with pytest.raises(ChatAttachmentError) as pending_error:
        load_sendable_attachments([pending.id], "chat-att-user@domain.com", "1")
    assert pending_error.value.code == "attachment_pending"
    with pytest.raises(ChatAttachmentError) as failed_error:
        load_sendable_attachments([failed.id], "chat-att-user@domain.com", "1")
    assert failed_error.value.code == "attachment_failed"
    assert parsed == []


def test_more_than_five_attachments_rejected():
    with pytest.raises(ChatAttachmentError) as exc:
        load_sendable_attachments([1, 2, 3, 4, 5, 6], "u", "1")
    assert exc.value.code == "too_many_attachments"


def test_ready_document_is_injected_and_bound(local_storage, monkeypatch):
    skill = _skill()
    channel = _channel(skill)
    owner = "chat-att-user@domain.com"
    attachment = _attachment(
        local_storage,
        name="notes.txt",
        data=b"disk is 90 percent",
        mime="text/plain",
        status=ChatAttachment.STATUS_READY,
        owner=owner,
        parsed="disk is 90 percent",
    )
    captured = {}

    def fake_stream(params, *args, **kwargs):
        captured["params"] = params
        captured["persisted"] = args[3]
        return StreamingHttpResponse(iter([b"ok"]), content_type="text/event-stream")

    monkeypatch.setattr("apps.opspilot.services.skill_channel_chat_service.stream_agui_chat", fake_stream)
    monkeypatch.setattr(
        "apps.opspilot.services.skill_channel_chat_service.capture_caller_identity",
        lambda request, user: {"username": "chat-att-user"},
    )
    request = APIRequestFactory().post("/chat")
    request.user = _user()
    request.COOKIES["current_team"] = "1"
    response = stream_skill_channel_chat(
        channel=channel,
        user_message="看一下",
        request=request,
        external_user_id=owner,
        attachment_ids=[attachment.id],
    )
    assert response.status_code == 200
    assert "disk is 90 percent" in captured["params"]["user_message"]
    assert captured["persisted"] == "看一下"
    attachment.refresh_from_db()
    assert attachment.message_id is not None
    assert attachment.conversation_id is not None
    assert attachment.message.content == "看一下"


def test_history_keeps_recent_document_and_drops_images(local_storage):
    skill = _skill()
    channel = _channel(skill)
    conversation = _conversation(skill, channel)
    older = SkillConversationMessage.objects.create(conversation=conversation, role="user", content="old question")
    newer = SkillConversationMessage.objects.create(conversation=conversation, role="user", content="new question")
    _attachment(
        local_storage,
        name="old.pdf",
        data=PDF,
        mime="application/pdf",
        status=ChatAttachment.STATUS_READY,
        message=older,
        conversation=conversation,
        parsed="OLD-BODY-" + ("字" * 400),
    )
    _attachment(
        local_storage,
        name="new.pdf",
        data=PDF,
        mime="application/pdf",
        status=ChatAttachment.STATUS_READY,
        message=newer,
        conversation=conversation,
        parsed="NEW-BODY",
    )
    _attachment(
        local_storage,
        name="shot.png",
        data=PNG,
        mime="image/png",
        status=ChatAttachment.STATUS_READY,
        message=newer,
        conversation=conversation,
    )
    recent = "[文件: new.pdf]\nNEW-BODY"
    budget = count_text_tokens(recent)
    suffixes = history_document_suffixes([older.id, newer.id], token_budget=budget, per_file_cap=budget)
    assert suffixes[newer.id] == recent
    assert suffixes[older.id] == "[文件: old.pdf]"
    assert "shot.png" not in suffixes[newer.id]
    assert "data:image" not in suffixes[newer.id]


def test_non_multimodal_drops_current_images():
    attachment = SimpleNamespace(mime_type="image/png", original_name="shot.png", parsed_text="", file=ContentFile(PNG))
    message, _remaining = compose_user_message("看图", [attachment], token_budget=100, per_file_cap=100, include_images=False)
    assert message == "看图"


def test_parse_failure_log_keeps_template_and_hides_file_bytes(local_storage, caplog, monkeypatch):
    attachment = _attachment(
        local_storage,
        name="secret.pdf",
        data=PDF + SECRET_FILE,
        mime="application/pdf",
        status=ChatAttachment.STATUS_PENDING,
    )

    class BoomParser:
        def parse_file(self, data, filename, **kwargs):
            assert SECRET_FILE in data
            raise RuntimeError("boom")

    monkeypatch.setattr("apps.opspilot.services.wiki.parsing.markitdown_parser.MarkItDownParser", BoomParser)
    with caplog.at_level(logging.ERROR, logger="opspilot"):
        parse_chat_attachment(attachment.id)
    attachment.refresh_from_db()
    assert attachment.status == ChatAttachment.STATUS_FAILED
    errors = [record for record in caplog.records if record.levelno >= logging.ERROR]
    assert len(errors) == 1
    assert errors[0].msg == PARSE_FAILED_TEMPLATE
    assert errors[0].args == (attachment.id, "parse", "RuntimeError")
    assert errors[0].exc_info is not None
    assert "SECRET_FILE_BYTES" not in errors[0].getMessage()
    assert "SECRET_FILE_BYTES" not in caplog.text
    assert attachment.parsed_text == ""


def test_parse_timeout_marks_failed(local_storage, monkeypatch):
    attachment = _attachment(local_storage, name="slow.pdf", data=PDF, mime="application/pdf", status=ChatAttachment.STATUS_PENDING)

    class SlowParser:
        def parse_file(self, data, filename, **kwargs):
            raise SoftTimeLimitExceeded()

    monkeypatch.setattr("apps.opspilot.services.wiki.parsing.markitdown_parser.MarkItDownParser", SlowParser)
    parse_chat_attachment(attachment.id)
    attachment.refresh_from_db()
    assert attachment.status == ChatAttachment.STATUS_FAILED
    assert attachment.failure_reason == "解析超时"


def test_parse_task_hard_timeout():
    assert parse_chat_attachment_task.soft_time_limit == 120
    assert parse_chat_attachment_task.time_limit == 130
    assert parse_chat_attachment_task.queue == "opspilot_chat_parse"


def test_cleanup_orphans_and_stale_pending(local_storage, django_capture_on_commit_callbacks):
    skill = _skill()
    channel = _channel(skill)
    conversation = _conversation(skill, channel)
    message = SkillConversationMessage.objects.create(conversation=conversation, role="user", content="kept")
    orphan = _attachment(local_storage, name="orphan.txt", data=b"bye", mime="text/plain", status=ChatAttachment.STATUS_READY)
    kept = _attachment(
        local_storage,
        name="kept.txt",
        data=b"stay",
        mime="text/plain",
        status=ChatAttachment.STATUS_READY,
        message=message,
        conversation=conversation,
    )
    pending = _attachment(local_storage, name="wait.pdf", data=PDF, mime="application/pdf", status=ChatAttachment.STATUS_PENDING)
    fresh = _attachment(local_storage, name="fresh.pdf", data=PDF, mime="application/pdf", status=ChatAttachment.STATUS_PENDING)
    old = timezone.now() - timedelta(hours=25)
    stale_pending = timezone.now() - timedelta(minutes=15)
    ChatAttachment.objects.filter(id__in=[orphan.id, kept.id]).update(created_at=old)
    ChatAttachment.objects.filter(id=pending.id).update(created_at=stale_pending)
    deleted = []
    local_storage.delete = lambda name: deleted.append(name)
    with django_capture_on_commit_callbacks(execute=True):
        result = cleanup_chat_attachments()
    assert result["deleted_count"] == 1
    assert result["failed_count"] == 1
    assert not ChatAttachment.objects.filter(id=orphan.id).exists()
    assert ChatAttachment.objects.filter(id=kept.id).exists()
    pending.refresh_from_db()
    fresh.refresh_from_db()
    assert pending.status == ChatAttachment.STATUS_FAILED
    assert fresh.status == ChatAttachment.STATUS_PENDING
    assert deleted


def test_deleting_conversation_removes_attachment_and_object(local_storage, django_capture_on_commit_callbacks):
    skill = _skill()
    channel = _channel(skill)
    conversation = _conversation(skill, channel)
    message = SkillConversationMessage.objects.create(conversation=conversation, role="user", content="hi")
    attachment = _attachment(
        local_storage,
        name="gone.txt",
        data=b"gone",
        mime="text/plain",
        status=ChatAttachment.STATUS_READY,
        message=message,
        conversation=conversation,
    )
    deleted = []
    local_storage.delete = lambda name: deleted.append(name)
    with django_capture_on_commit_callbacks(execute=True):
        conversation.delete()
    assert not ChatAttachment.objects.filter(id=attachment.id).exists()
    assert deleted


def test_serialize_includes_attachments_and_empty_for_old_messages(local_storage):
    skill = _skill()
    channel = _channel(skill)
    conversation = _conversation(skill, channel)
    bare = SkillConversationMessage.objects.create(conversation=conversation, role="user", content="plain")
    rich = SkillConversationMessage.objects.create(conversation=conversation, role="user", content="with file")
    attachment = _attachment(
        local_storage,
        name="notes.txt",
        data=b"abc",
        mime="text/plain",
        status=ChatAttachment.STATUS_READY,
        message=rich,
        conversation=conversation,
    )
    rows = serialize_skill_session_messages(conversation)
    assert rows[0]["attachments"] == []
    assert rows[1]["attachments"] == [{"id": attachment.id, "name": "notes.txt", "mime": "text/plain", "size": 3, "status": "ready"}]
    assert bare.content == "plain"


def test_login_and_api_secret_can_upload_and_download(local_storage, monkeypatch):
    monkeypatch.setattr("apps.opspilot.services.chat_attachment_service.current_app.send_task", lambda *args, **kwargs: None)
    factory = APIRequestFactory()
    user = _user("login-uploader")
    login_request = factory.post("/upload", {"file": SimpleUploadedFile("notes.txt", b"alpha")}, format="multipart")
    force_authenticate(login_request, user=user)
    login_request.user = user
    login_request.COOKIES["current_team"] = "1"
    login_response = upload_chat_attachment(login_request)
    assert login_response.status_code == 200
    login_id = json.loads(login_response.content)["data"]["id"]
    download = factory.get(f"/download/{login_id}")
    force_authenticate(download, user=user)
    download.user = user
    download.COOKIES["current_team"] = "1"
    downloaded = download_chat_attachment(download, login_id)
    assert downloaded.status_code == 200
    assert b"".join(downloaded.streaming_content) == b"alpha"

    plain = UserAPISecret.generate_api_secret()
    UserAPISecret.objects.create(
        username="apiuser",
        domain="domain.com",
        team=1,
        api_secret=UserAPISecret.hash_api_secret(plain),
    )
    embedded = factory.post(
        "/upload",
        {"file": SimpleUploadedFile("embed.txt", b"beta")},
        format="multipart",
        HTTP_API_AUTHORIZATION=plain,
    )
    embedded_response = upload_chat_attachment(embedded)
    assert embedded_response.status_code == 200
    embedded_id = json.loads(embedded_response.content)["data"]["id"]
    other = factory.get(f"/download/{embedded_id}")
    force_authenticate(other, user=user)
    other.user = user
    other.COOKIES["current_team"] = "2"
    denied = download_chat_attachment(other, embedded_id)
    assert denied.status_code == 403
    status_request = factory.get(f"/status/{embedded_id}", HTTP_API_AUTHORIZATION=plain)
    status_response = chat_attachment_status(status_request, embedded_id)
    assert status_response.status_code == 200
    assert json.loads(status_response.content)["data"]["status"] == "ready"


def test_stream_rejects_pending_attachment(local_storage):
    skill = _skill()
    channel = _channel(skill)
    attachment = _attachment(
        local_storage,
        name="wait.pdf",
        data=PDF,
        mime="application/pdf",
        status=ChatAttachment.STATUS_PENDING,
    )
    request = APIRequestFactory().post("/chat")
    request.user = _user()
    request.COOKIES["current_team"] = "1"
    with pytest.raises(SkillChannelChatError) as exc:
        stream_skill_channel_chat(
            channel=channel,
            user_message="发送",
            request=request,
            external_user_id="chat-att-user@domain.com",
            attachment_ids=[attachment.id],
        )
    assert "解析中" in exc.value.message
    assert SkillConversationMessage.objects.count() == 0


def test_debug_apply_does_not_bind_message(local_storage):
    attachment = _attachment(
        local_storage,
        name="notes.txt",
        data=b"body",
        mime="text/plain",
        status=ChatAttachment.STATUS_READY,
        parsed="body",
    )
    text = apply_current_turn_attachments(
        "hi",
        [attachment.id],
        owner_key="chat-att-user@domain.com",
        team_id="1",
        llm_model=None,
    )
    assert "body" in text
    attachment.refresh_from_db()
    assert attachment.message_id is None


class TrackingUpload:
    def __init__(self, name, size, chunks=None):
        self.name = name
        self.size = size
        self._chunks = chunks or []
        self.chunk_calls = 0
        self.read_calls = 0

    def chunks(self, chunk_size=None):
        self.chunk_calls += 1
        yield from self._chunks

    def read(self, size=-1):
        self.read_calls += 1
        raise AssertionError("read called")


def test_upload_rejects_oversized_content_length_without_reading(local_storage, caplog):
    user = _user("size-user")
    upload = TrackingUpload("notes.txt", 4)
    request = APIRequestFactory().post("/upload")
    request.user = user
    request.COOKIES["current_team"] = "1"
    request.META["CONTENT_LENGTH"] = str(21 * 1024 * 1024)
    request._files = MultiValueDict({"file": [upload]})
    with caplog.at_level(logging.WARNING, logger="opspilot"):
        response = upload_chat_attachment(request)
    assert response.status_code == 400
    assert json.loads(response.content)["code"] == "file_too_large"
    assert upload.chunk_calls == 0
    assert upload.read_calls == 0
    assert ChatAttachment.objects.count() == 0
    assert "file_too_large" in caplog.text
    assert "notes.txt" not in caplog.text


def test_upload_rejects_declared_image_size_without_reading(local_storage):
    user = _user("image-size-user")
    upload = TrackingUpload("shot.png", 5 * 1024 * 1024 + 1)
    request = APIRequestFactory().post("/upload")
    request.user = user
    request.COOKIES["current_team"] = "1"
    request.META["CONTENT_LENGTH"] = "128"
    request._files = MultiValueDict({"file": [upload]})
    response = upload_chat_attachment(request)
    assert response.status_code == 400
    assert json.loads(response.content)["code"] == "file_too_large"
    assert upload.chunk_calls == 0
    assert upload.read_calls == 0


def test_stream_read_aborts_when_body_exceeds_limit(monkeypatch, caplog):
    monkeypatch.setattr("apps.opspilot.services.chat_attachment_service.DOCUMENT_MAX_BYTES", 16)
    upload = TrackingUpload("notes.txt", 4, chunks=[b"x" * 20, b"SECRET_OVERSIZE"])
    with caplog.at_level(logging.WARNING, logger="opspilot"):
        with pytest.raises(ChatAttachmentError) as exc:
            read_bounded_upload(upload, content_length="32")
    assert exc.value.code == "file_too_large"
    assert upload.read_calls == 0
    assert "SECRET_OVERSIZE" not in caplog.text


def test_download_disposition_strips_header_injection(local_storage):
    user = _user("disp-user")
    stored = store_upload(filename='report\r\n";.txt', data=b"hello file", owner_key="disp-user@domain.com", team_id="1")
    assert stored.original_name == "report.txt"
    assert "\r" not in stored.original_name and '"' not in stored.original_name
    attachment = _attachment(
        local_storage,
        name="notes.txt",
        data=b"alpha",
        mime="text/plain",
        status=ChatAttachment.STATUS_READY,
        owner="disp-user@domain.com",
    )
    attachment.original_name = 'notes\r\nSet-Cookie: injected=1";.txt'
    attachment.save(update_fields=["original_name"])
    request = APIRequestFactory().get("/download")
    force_authenticate(request, user=user)
    request.user = user
    request.COOKIES["current_team"] = "1"
    response = download_chat_attachment(request, attachment.id)
    disposition = response["Content-Disposition"]
    assert "\r" not in disposition
    assert "\n" not in disposition
    assert disposition.count('"') == 2
    assert "Set-Cookie" not in disposition.split("filename=")[0]


def test_embedded_stream_injects_attachment(local_storage, monkeypatch):
    skill = _skill()
    channel = SkillChannel.objects.create(
        skill=skill,
        channel_type=SkillChannelChoices.EMBEDDED_CHAT,
        enabled=True,
        usage_team=[1],
    )
    plain = UserAPISecret.generate_api_secret()
    UserAPISecret.objects.create(
        username="apiuser",
        domain="domain.com",
        team=1,
        api_secret=UserAPISecret.hash_api_secret(plain),
    )
    attachment = _attachment(
        local_storage,
        name="notes.txt",
        data=b"disk is 90 percent",
        mime="text/plain",
        status=ChatAttachment.STATUS_READY,
        owner="apiuser@domain.com",
        parsed="disk is 90 percent",
    )
    captured = {}

    def fake_stream(params, *args, **kwargs):
        captured["params"] = params
        return StreamingHttpResponse(iter([b"ok"]), content_type="text/event-stream")

    monkeypatch.setattr("apps.opspilot.services.skill_channel_chat_service.stream_agui_chat", fake_stream)
    monkeypatch.setattr(
        "apps.opspilot.services.skill_channel_chat_service.capture_caller_identity",
        lambda request, user: {"username": "apiuser", "domain": "domain.com", "team_id": 1},
    )
    request = APIRequestFactory().post(
        "/embedded",
        {"message": "看一下", "attachment_ids": [attachment.id]},
        format="json",
        HTTP_API_AUTHORIZATION=plain,
    )
    response = execute_skill_embedded_chat(request, skill.id, channel.id)
    assert response.status_code == 200
    assert "disk is 90 percent" in captured["params"]["user_message"]
    attachment.refresh_from_db()
    assert attachment.message_id is not None
