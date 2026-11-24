import json
from unittest.mock import Mock

import pytest
from django.core.files.uploadedfile import SimpleUploadedFile
from django.db import IntegrityError, connection
from django.urls import resolve
from django.utils import timezone
from urllib3.exceptions import HTTPError

from apps.itsm.models import ItsmSetting, Ticket, Workflow
from apps.itsm.models.extend import KnowledgeArticle
from apps.itsm.tests.test_review_regressions import request
from apps.itsm.views.extend import resource_item, resources

pytestmark = pytest.mark.django_db
READER = ["knowledge-View"]
EDITOR = [*READER, "knowledge-Add", "knowledge-Edit", "knowledge-Delete"]


def data(response):
    assert response.status_code == 200, response.content
    return json.loads(response.content)["data"]


def test_draft_publish_withdraw_and_permissions():
    initial = {"title": " 系统操作手册 ", "content": "<img src=invalid>\n处理步骤"}
    article = data(resources(request("post", initial, permissions=EDITOR), "knowledge"))
    article_id = article["id"]
    assert article["title"] == "系统操作手册"
    assert article["status"] == "draft"
    assert data(resources(request(permissions=READER), "knowledge"))["count"] == 0
    assert resource_item(request(permissions=READER), "knowledge", article_id).status_code == 404
    assert resource_item(request("put", {"status": "published"}, permissions=READER), "knowledge", article_id).status_code == 403

    published = data(resource_item(request("put", {"status": "published"}, permissions=EDITOR), "knowledge", article_id))
    assert published["status"] == "published"
    listing = data(resources(request(payload={"q": "操作", "status": "published"}, permissions=READER), "knowledge"))
    assert not listing["can_edit"]
    assert listing["count"] == 1
    assert "content" not in listing["items"][0]
    assert data(resource_item(request(permissions=READER), "knowledge", article_id))["content"] == initial["content"]
    assert resource_item(request(permissions=EDITOR, domain="external.test"), "knowledge", article_id).status_code == 404

    withdrawal = data(resource_item(request("put", {"status": "draft"}, permissions=EDITOR), "knowledge", article_id))
    assert withdrawal["status"] == "draft"
    assert data(resources(request(permissions=READER), "knowledge"))["count"] == 0
    assert data(resource_item(request("delete", permissions=EDITOR), "knowledge", article_id)) == {"id": article_id}


def test_validation_keeps_drafts_and_legacy_publications_usable():
    for invalid in ({"title": " "}, {"title": "超" * 201}, {"title": "标题", "content": 3}, {"title": "标题", "status": "published"}):
        assert resources(request("post", invalid, permissions=EDITOR), "knowledge").status_code == 400
    article = data(resources(request("post", {"title": "草稿"}, permissions=EDITOR), "knowledge"))
    assert resource_item(request("put", {"status": "published"}, permissions=EDITOR), "knowledge", article["id"]).status_code == 400
    assert KnowledgeArticle.objects.get(id=article["id"]).status == "draft"
    legacy = KnowledgeArticle.objects.create(title="已同步", content="", status="synced")
    loaded = data(resource_item(request(permissions=READER), "knowledge", legacy.id))
    assert loaded["status"] == "published"
    assert data(resource_item(request("put", {"title": "早期文章"}, permissions=EDITOR), "knowledge", legacy.id))["status"] == "published"
    assert KnowledgeArticle.objects.get(id=legacy.id).status == "synced"


def test_categories_formats_and_ticket_links_follow_permissions():
    workflow = Workflow.objects.create(name="处理流程", key="knowledge-test")
    mine = Ticket.objects.create(title="我的工单", sn="KB001", creator="alice", workflow=workflow)
    private = Ticket.objects.create(title="他人工单", sn="KB002", creator="bob", workflow=workflow)
    external = Ticket.objects.create(title="外部组织工单", sn="KB003", creator="alice", workflow=workflow, domain="external.test")
    editor = [*EDITOR, "ticket-View"]
    payload = {
        "title": "升级指引",
        "category": " 数据库 ",
        "content": "## 步骤\n\n使用 `SELECT` 验证",
        "content_format": "markdown",
        "ticket_ids": [mine.id, mine.id],
    }
    article = data(resources(request("post", payload, username="alice", permissions=editor), "knowledge"))
    article_id = article["id"]
    assert article["category"] == "数据库"
    assert article["content_format"] == "markdown"
    assert article["content"] == payload["content"]
    assert article["tickets"] == [{"id": mine.id, "title": mine.title, "sn": mine.sn}]
    assert article["attachments"] == []
    assert article["can_link_tickets"]
    for unseen in (private, external):
        inaccessible = request("put", {"ticket_ids": [unseen.id]}, username="alice", permissions=editor)
        assert resource_item(inaccessible, "knowledge", article_id).status_code == 403
    denied = request("put", {"ticket_ids": [mine.id]}, username="alice", permissions=EDITOR)
    assert resource_item(denied, "knowledge", article_id).status_code == 403

    updated = request("put", {"content": "<p><strong>操作说明</strong></p>", "content_format": "richtext", "ticket_ids": []}, permissions=EDITOR)
    assert data(resource_item(updated, "knowledge", article_id))["content_format"] == "richtext"
    alice = request(username="alice", permissions=editor)
    assert data(resource_item(alice, "knowledge", article_id))["tickets"] == article["tickets"]
    bob = request("put", {"ticket_ids": [private.id]}, username="bob", permissions=editor)
    assert data(resource_item(bob, "knowledge", article_id))["tickets"] == [{"id": private.id, "title": private.title, "sn": private.sn}]
    assert data(resource_item(alice, "knowledge", article_id))["tickets"] == article["tickets"]
    assert data(resource_item(request(permissions=EDITOR), "knowledge", article_id))["tickets"] == []

    KnowledgeArticle.objects.create(title="本租户其他分类", category="网络", status="published")
    KnowledgeArticle.objects.create(title="外租户文章", category="不可见", status="published", domain="external.test")
    listing = request(payload={"category": "数据库"}, permissions=editor)
    response = data(resources(listing, "knowledge"))
    assert response["count"] == 1
    assert set(response["categories"]) == {"数据库", "网络"}
    assert "content" not in response["items"][0]
    public = data(resources(request(permissions=READER), "knowledge"))
    assert public["categories"] == ["网络"]


@pytest.mark.parametrize("fields", [{"content_format": "xml"}, {"category": 2}, {"category": "超" * 129}, {"ticket_ids": [True]}, {"ticket_ids": "1"}])
def test_unrecognized_article_metadata_is_rejected(fields):
    article = data(resources(request("post", {"title": "草稿"}, permissions=EDITOR), "knowledge"))
    invalid = request("put", fields, permissions=[*EDITOR, "ticket-View"])
    assert resource_item(invalid, "knowledge", article["id"]).status_code == 400


def test_publish_html_requires_visible_content():
    payload = {"title": "草稿", "content": "<p>&nbsp;<br></p>", "content_format": "richtext"}
    article = data(resources(request("post", payload, permissions=EDITOR), "knowledge"))
    assert resource_item(request("put", {"status": "published"}, permissions=EDITOR), "knowledge", article["id"]).status_code == 400


def test_attachment_routes_apply_article_permissions_and_return_short_lived_download(monkeypatch, settings, django_capture_on_commit_callbacks):
    from apps.itsm.services.attachment import BUCKET

    minio = Mock()
    settings.MINIO_ACCESS_KEY = "test"
    settings.MINIO_SECRET_KEY = "test"
    minio.presigned_get_object.return_value = "https://storage.example.test/private-download"
    monkeypatch.setattr("apps.itsm.views.knowledge.storage_client", lambda: minio)
    monkeypatch.setattr("apps.itsm.services.attachment.storage_client", lambda: minio)
    monkeypatch.setattr("apps.itsm.services.knowledge_attachments.storage_client", lambda: minio)
    article = KnowledgeArticle.objects.create(title="维修知识", content="处理步骤", created_by="alice")
    base_url = f"/api/v1/itsm/api/knowledge/{article.id}/attachments"
    ItsmSetting.objects.create(domain=article.domain, key="basic", value={"attachment_types": "md"})
    add_only = [*READER, "knowledge-Add"]
    upload, upload_args = resolve(f"{base_url}/").func, {"article_id": article.id}
    uploaded = request("post", username="alice", permissions=add_only)
    uploaded.FILES["file"] = SimpleUploadedFile("维修步骤.md", b"# replacement", content_type="text/markdown")
    assert upload(request("post", permissions=READER), **upload_args).status_code == 403
    rejected = request("post", username="alice", permissions=add_only)
    rejected.FILES["file"] = SimpleUploadedFile("维修步骤.txt", b"replacement")
    assert upload(rejected, **upload_args).status_code == 400
    minio.put_object.assert_not_called()
    item = data(upload(uploaded, **upload_args))
    assert item["name"] == "维修步骤.md"
    assert item["size"] == len(b"# replacement")
    assert item["can_delete"]
    assert "object_name" not in item
    assert minio.put_object.call_args.args[0] == BUCKET
    file_key = minio.put_object.call_args.args[1]
    assert file_key.startswith(f"knowledge/{article.id}/")
    assert minio.put_object.call_args.kwargs["content_type"] == "application/octet-stream"
    download = resolve(f"{base_url}/{item['id']}/download/")
    assert download.func(request(permissions=READER), **download.kwargs).status_code == 404
    assert download.func(request(permissions=EDITOR, domain="external.test"), **download.kwargs).status_code == 404
    assert data(download.func(request(username="alice", permissions=add_only), **download.kwargs)) == {"url": minio.presigned_get_object.return_value}

    article.status = "published"
    article.save()
    detail = data(resource_item(request(permissions=READER), "knowledge", article.id))
    assert detail["attachments"] == [{**item, "can_delete": False}]
    assert not detail["can_upload"]
    assert data(download.func(request(permissions=READER), **download.kwargs))["url"] == minio.presigned_get_object.return_value

    delete = resolve(f"{base_url}/{item['id']}/")
    denied = request("delete", username="alice", permissions=add_only)
    assert delete.func(denied, **delete.kwargs).status_code == 403
    with django_capture_on_commit_callbacks(execute=True):
        assert data(delete.func(request("delete", permissions=EDITOR), **delete.kwargs)) == {"deleted": True}
    minio.remove_object.assert_called_once_with(BUCKET, file_key)
    assert download.func(request(permissions=READER), **download.kwargs).status_code == 404


def test_attachment_storage_failure_rolls_back_metadata(monkeypatch, settings):
    from apps.itsm.views.knowledge import upload_knowledge_attachment

    settings.MINIO_ACCESS_KEY = "test"
    settings.MINIO_SECRET_KEY = "test"
    article = KnowledgeArticle.objects.create(title="维修知识")
    minio = Mock()
    minio.put_object.side_effect = HTTPError("unavailable")
    monkeypatch.setattr("apps.itsm.views.knowledge.storage_client", lambda: minio)
    monkeypatch.setattr("apps.itsm.services.knowledge_attachments.storage_client", lambda: minio)
    uploaded = request("post", permissions=EDITOR)
    uploaded.FILES["file"] = SimpleUploadedFile("维修步骤.md", b"# replacement")
    assert upload_knowledge_attachment(uploaded, article.id).status_code == 502
    assert not article.attachments.exists()


@pytest.mark.django_db(transaction=True)
def test_attachment_upload_compensates_when_metadata_commit_fails(monkeypatch, settings):
    from apps.itsm.models.extend import KnowledgeAttachmentCleanup
    from apps.itsm.views.knowledge import upload_knowledge_attachment

    settings.MINIO_ACCESS_KEY = "test"
    settings.MINIO_SECRET_KEY = "test"
    article = KnowledgeArticle.objects.create(title="维修知识")
    minio = Mock()
    monkeypatch.setattr("apps.itsm.views.knowledge.storage_client", lambda: minio)
    monkeypatch.setattr("apps.itsm.services.knowledge_attachments.storage_client", lambda: minio)
    commit = connection.commit
    failed = False

    def fail_after_put():
        nonlocal failed
        if minio.put_object.called and not failed:
            failed = True
            raise IntegrityError("附件元数据提交失败")
        commit()

    monkeypatch.setattr(connection, "commit", fail_after_put)
    uploaded = request("post", permissions=EDITOR)
    uploaded.FILES["file"] = SimpleUploadedFile("维修步骤.md", b"# replacement")

    with pytest.raises(IntegrityError):
        upload_knowledge_attachment(uploaded, article.id)
    minio.put_object.assert_called_once()
    minio.remove_object.assert_called_once_with(*minio.put_object.call_args.args[:2])
    assert not article.attachments.exists()
    assert not KnowledgeAttachmentCleanup.objects.exists()


def test_article_deletion_retries_failed_object_cleanup(monkeypatch, django_capture_on_commit_callbacks):
    from apps.core.logger import SafeLogException
    from apps.itsm.models.extend import KnowledgeAttachmentCleanup
    from apps.itsm.services.knowledge_attachments import drain_attachment_cleanup

    article = KnowledgeArticle.objects.create(title="维修知识")
    item = article.attachments.create(name="说明.md", object_name="knowledge/retry", size=5)
    error = HTTPError("attachment-private-data-sentinel")
    storage = Mock()
    storage.remove_object.side_effect = [error, None]
    log = Mock()
    monkeypatch.setattr("apps.itsm.services.knowledge_attachments.storage_client", lambda: storage)
    monkeypatch.setattr("apps.itsm.services.knowledge_attachments.logger.warning", log)

    with django_capture_on_commit_callbacks(execute=True):
        assert resource_item(request("delete", permissions=EDITOR), "knowledge", article.pk).status_code == 200
    assert not KnowledgeArticle.objects.filter(pk=article.pk).exists()
    cleanup = KnowledgeAttachmentCleanup.objects.get(object_name=item.object_name)
    args, kwargs = log.call_args
    assert args[1:] == (cleanup.pk, "remove_object", "HTTPError")
    assert "attachment-private-data-sentinel" not in (args[0] % args[1:])
    exception_type, safe_error, traceback = kwargs["exc_info"]
    assert (exception_type, str(safe_error), traceback) == (SafeLogException, "HTTPError", error.__traceback__)
    assert drain_attachment_cleanup() == {"removed": 0}
    KnowledgeAttachmentCleanup.objects.filter(pk=cleanup.pk).update(next_attempt_at=timezone.now())
    assert drain_attachment_cleanup() == {"removed": 1}
    assert drain_attachment_cleanup() == {"removed": 0}
    assert storage.remove_object.call_count == 2
