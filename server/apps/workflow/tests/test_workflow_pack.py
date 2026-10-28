import base64
import copy
import json
import logging
import os
import zipfile
from io import BytesIO

import pytest
from django.contrib.auth import get_user_model
from django.core import signing
from django.core.files.base import ContentFile
from django.core.files.uploadedfile import SimpleUploadedFile
from docx import Document
from rest_framework.test import APIRequestFactory, force_authenticate

from apps.workflow.models import Workflow, WorkflowVersion
from apps.workflow.services.agent_knowledge_inputs import AGENT_KNOWLEDGE_TOKEN_SALT, store_uploaded_agent_knowledge
from apps.workflow.services.definitions import build_blank_canvas_metadata, build_blank_definition
from apps.workflow.services.object_store import ArtifactTooLarge
from apps.workflow.services.report_template_inputs import REPORT_TEMPLATE_TOKEN_SALT, store_uploaded_report_template
from apps.workflow.services.reports import MAX_TEMPLATE_BYTES
from apps.workflow.services.workflow_pack import MAX_UNCOMPRESSED_BYTES, PackRejected, _validate_members, export_workflow_pack, import_workflow_pack
from apps.workflow.views import WorkflowViewSet

SECRET = "SECRET_TOKEN_SHOULD_NOT_LEAK"
BODY = "SENTINEL_TEMPLATE_BODY"


@pytest.fixture
def superuser(db):
    return get_user_model().objects.create(username="workflow-pack-admin", domain="example.com", is_superuser=True)


class MemoryStore:
    def __init__(self):
        self.objects = {}

    def put(self, key, content):
        self.objects[key] = content.read() if hasattr(content, "read") else bytes(content)

    def get(self, key, *, max_bytes=None):
        if key not in self.objects:
            raise FileNotFoundError(key)
        data = self.objects[key]
        if max_bytes is not None and len(data) > max_bytes:
            raise ArtifactTooLarge("too large")
        return data, key.rsplit("/", 1)[-1], len(data)


def _docx(text: str) -> bytes:
    document = Document()
    document.add_paragraph(text)
    buffer = BytesIO()
    document.save(buffer)
    return buffer.getvalue()


def _request(user):
    request = APIRequestFactory().post("/workflows/import/")
    request.COOKIES["current_team"] = "7"
    force_authenticate(request, user=user)
    return request


def _blank(name: str) -> dict:
    return {
        "name": name,
        "description": "",
        "definition": build_blank_definition(),
        "canvas_metadata": build_blank_canvas_metadata(),
        "files": [],
    }


def _zip(entries: list[dict], extra: list[tuple[str, bytes]] | None = None, *, compression=zipfile.ZIP_DEFLATED) -> bytes:
    buffer = BytesIO()
    with zipfile.ZipFile(buffer, "w", compression=compression) as archive:
        manifest = []
        for index, payload in enumerate(entries, start=1):
            filename = f"workflows/{index:04d}.json"
            archive.writestr(filename, json.dumps(payload, ensure_ascii=False).encode("utf-8"))
            manifest.append({"file": filename, "name": payload.get("name") or ""})
        for path, content in extra or []:
            archive.writestr(path, content)
        archive.writestr(
            "manifest.json",
            json.dumps(
                {"format": "bklite.workflow-pack", "schema_version": 1, "workflows": manifest},
                ensure_ascii=False,
            ).encode("utf-8"),
        )
    return buffer.getvalue()


def _import(user, content: bytes, store=None, **kwargs):
    upload = SimpleUploadedFile("workflow-pack.zip", content, content_type="application/zip")
    return import_workflow_pack(
        upload, request=_request(user), team=[7], username=user.username, domain=user.domain, store=store or MemoryStore(), **kwargs
    )


def _task(name: str, reference: str, inputs: dict) -> dict:
    return {"name": name, "taskReferenceName": reference, "type": "SIMPLE", "inputParameters": inputs}


@pytest.mark.django_db
def test_pack_roundtrip_restores_files_and_keeps_local_ids(superuser, caplog):
    caplog.set_level(logging.INFO, logger="workflow")
    docx = _docx(BODY)
    other = _docx("其他模板")
    knowledge = "巡检知识正文".encode()
    store = MemoryStore()
    definition = build_blank_definition()
    definition["tasks"] = [
        _task(
            "bklite_notification",
            "notify_node",
            {"notification_type": "EMAIL", "channel_id": 1, "recipients": ["ops@example.com"], "title": "通知", "body": "正文"},
        ),
        _task("bklite_intent_classification", "intent_node", {"model_id": 8, "text": "你好", "intents": ["咨询"]}),
        _task("bklite_memory_read", "read_node", {"memory_space_id": 3, "query": "最近变更"}),
        _task("bklite_memory_write", "write_node", {"memory_space_id": 4, "model_id": 5, "content": "记下"}),
        _task("bklite_agent", "agent_node", {"agent_id": 9, "message": "总结"}),
        _task("bklite_document_render", "report_node", {}),
    ]
    canvas = build_blank_canvas_metadata()
    canvas["node_titles"] = {
        "notify_node": "邮件通知",
        "intent_node": "意图",
        "read_node": "读取记忆",
        "write_node": "写入记忆",
        "agent_node": "助手",
        "report_node": "生成报告",
    }
    source = Workflow.objects.create(name="季度巡检", description="说明", team=[7], definition=definition, canvas_metadata=canvas, is_builtin=True)
    uploaded = store_uploaded_report_template(
        SimpleUploadedFile("季度巡检.docx", docx),
        workflow_id=source.pk,
        workflow_version=0,
        team=7,
        username="workflow-admin",
        domain="example.com",
        store=store,
    )
    old_key = signing.loads(uploaded["token"], salt=REPORT_TEMPLATE_TOKEN_SALT)["object_key"]
    store.put("workflow/templates/frozen/other.docx", ContentFile(other))
    definition = copy.deepcopy(source.definition)
    definition["tasks"][5]["inputParameters"] = {
        "template": uploaded,
        "template_snapshot": {
            "object_key": "workflow/templates/frozen/other.docx",
            "format": "docx",
            "sha256": "b" * 64,
            "size": len(other),
            "filename_prefix": "other",
        },
    }
    uploaded_knowledge = store_uploaded_agent_knowledge(
        SimpleUploadedFile("a.md", knowledge),
        workflow_id=source.pk,
        team=7,
        store=store,
    )
    definition["tasks"][4]["inputParameters"]["knowledge_files"] = [uploaded_knowledge]
    source.definition = definition
    source.save(update_fields=["definition"])
    old_knowledge_token = uploaded_knowledge["token"]

    content, failures = export_workflow_pack(Workflow.objects.all(), [source.pk], store=store)

    assert failures == []
    assert source.pk
    source.refresh_from_db()
    assert source.is_builtin is True
    assert source.definition["tasks"][0]["inputParameters"]["channel_id"] == 1
    with zipfile.ZipFile(BytesIO(content)) as archive:
        packed = json.loads(archive.read("workflows/0001.json"))
        packed_files = {item["field"]: item for item in packed["files"]}
        template_bytes = archive.read(packed_files["template"]["path"])
        knowledge_bytes = archive.read(packed_files["knowledge_files"]["path"])
    assert set(packed) == {"name", "description", "definition", "canvas_metadata", "files"}
    assert "is_builtin" not in packed and "engine_name" not in packed and "id" not in packed and "rebind" not in packed
    assert SECRET.encode() not in content
    assert old_knowledge_token.encode() not in content
    assert packed["definition"]["tasks"][0]["inputParameters"]["channel_id"] == 1
    assert packed["definition"]["tasks"][1]["inputParameters"]["model_id"] == 8
    assert packed["definition"]["tasks"][2]["inputParameters"]["memory_space_id"] == 3
    assert packed["definition"]["tasks"][3]["inputParameters"]["memory_space_id"] == 4
    assert packed["definition"]["tasks"][3]["inputParameters"]["model_id"] == 5
    assert "workflow/templates/" not in json.dumps(packed)
    assert "workflow/knowledge/" not in json.dumps(packed)
    assert packed_files["template"]["task_reference"] == "report_node"
    assert packed_files["knowledge_files"]["task_reference"] == "agent_node"
    assert packed_files["template"]["path"].startswith("files/")
    assert packed_files["knowledge_files"]["path"].startswith("files/")
    assert template_bytes == docx
    assert knowledge_bytes == knowledge
    assert "knowledge_files" not in packed["definition"]["tasks"][4]["inputParameters"]
    assert packed["definition"]["tasks"][4]["inputParameters"]["agent_id"] == 9

    Workflow.objects.filter(pk=source.pk).delete()
    result = _import(superuser, content, store=store)

    assert result["failed"] == []
    created = Workflow.objects.get(pk=result["created"][0]["id"])
    assert created.id != source.pk
    assert created.status == Workflow.Status.DRAFT
    assert created.current_version == 0
    assert created.enabled is False
    assert created.is_builtin is False
    assert created.has_draft is True
    assert created.engine_name.startswith("bklite_workflow_")
    assert created.team == [7]
    assert not WorkflowVersion.objects.filter(workflow=created).exists()
    report = created.definition["tasks"][5]["inputParameters"]["template"]
    assert report["kind"] == "uploaded"
    assert report["name"] == "季度巡检.docx"
    rebound = signing.loads(report["token"], salt=REPORT_TEMPLATE_TOKEN_SALT)
    assert rebound["workflow_id"] == created.pk
    assert rebound["workflow_version"] == 0
    assert rebound["object_key"].startswith("workflow/templates/uploads/7/")
    assert rebound["object_key"] != old_key
    assert store.objects[rebound["object_key"]] == docx
    assert "template_snapshot" not in created.definition["tasks"][5]["inputParameters"]
    assert created.definition["tasks"][0]["inputParameters"]["channel_id"] == 1
    assert created.definition["tasks"][1]["inputParameters"]["model_id"] == 8
    assert created.definition["tasks"][2]["inputParameters"]["memory_space_id"] == 3
    assert created.definition["tasks"][3]["inputParameters"]["memory_space_id"] == 4
    assert created.definition["tasks"][3]["inputParameters"]["model_id"] == 5
    assert created.definition["tasks"][4]["inputParameters"]["agent_id"] == 9
    restored_knowledge = created.definition["tasks"][4]["inputParameters"]["knowledge_files"]
    assert restored_knowledge[0]["name"] == "a.md"
    assert restored_knowledge[0]["token"] != old_knowledge_token
    restored_payload = signing.loads(restored_knowledge[0]["token"], salt=AGENT_KNOWLEDGE_TOKEN_SALT)
    assert restored_payload["workflow_id"] == created.pk
    assert restored_payload["team"] == 7
    assert restored_payload["object_key"].startswith(f"workflow/knowledge/uploads/7/{created.pk}/")
    assert store.objects[restored_payload["object_key"]] == knowledge
    assert SECRET not in json.dumps(created.definition)
    assert old_knowledge_token not in json.dumps(created.definition)
    assert result["rebind"] == []
    messages = [record.getMessage() for record in caplog.records if record.name == "workflow"]
    assert "event=workflow_pack_exported exported=1 failed=0" in messages
    assert "event=workflow_pack_imported created=1 failed=0" in messages
    assert SECRET not in caplog.text
    assert BODY not in caplog.text
    assert "巡检知识正文" not in caplog.text
    exported = next(record for record in caplog.records if record.msg == "event=workflow_pack_exported exported=%s failed=%s")
    assert exported.args == (1, 0)
    assert exported.getMessage() == "event=workflow_pack_exported exported=1 failed=0"


@pytest.mark.django_db
def test_import_name_conflict_and_missing_template_fail_one_item(superuser):
    Workflow.objects.create(name="已有流程", team=[7], definition=build_blank_definition(), canvas_metadata=build_blank_canvas_metadata())
    missing = _blank("缺模板")
    missing["definition"] = build_blank_definition()
    missing["definition"]["tasks"] = [_task("bklite_document_render", "report_node", {})]
    missing["files"] = [{"task_reference": "report_node", "field": "template", "path": "files/missing.docx", "filename": "missing.docx"}]
    legacy = _blank("旧目录")
    legacy["definition"] = build_blank_definition()
    legacy["definition"]["tasks"] = [_task("bklite_document_render", "report_node", {})]
    legacy["files"] = [{"task_reference": "report_node", "field": "template", "path": "templates/legacy.docx", "filename": "legacy.docx"}]
    stale_knowledge = _blank("旧知识凭证")
    stale_knowledge["definition"] = build_blank_definition()
    stale_knowledge["definition"]["tasks"] = [
        _task(
            "bklite_agent",
            "agent_node",
            {
                "agent_id": 9,
                "message": "总结",
                "knowledge_files": [{"kind": "workflow_agent_knowledge", "name": "a.md", "format": "md", "size": 4, "token": SECRET}],
            },
        )
    ]
    stale = _blank("旧路径")
    stale["definition"] = build_blank_definition()
    stale["definition"]["tasks"] = [
        _task(
            "bklite_document_render",
            "report_node",
            {
                "template_snapshot": {
                    "object_key": "workflow/templates/frozen/old.docx",
                    "format": "docx",
                    "sha256": "a" * 64,
                    "size": 12,
                    "filename_prefix": "old",
                }
            },
        )
    ]
    content = _zip(
        [_blank("已有流程"), _blank("另一条"), missing, stale, legacy, stale_knowledge],
        [("templates/legacy.docx", _docx("旧"))],
    )

    result = _import(superuser, content)

    assert [item["name"] for item in result["created"]] == ["另一条"]
    assert [item["name"] for item in result["failed"]] == ["已有流程", "缺模板", "旧路径", "旧目录", "旧知识凭证"]
    assert result["failed"][0]["reason"] == "同一组织下已存在同名流程"
    assert result["failed"][1]["reason"] == "文档模板缺失"
    assert result["failed"][2]["reason"] == "文档模板缺失"
    assert result["failed"][3]["reason"] == "文档模板路径非法"
    assert result["failed"][4]["reason"] == "上传知识缺失"
    assert SECRET not in json.dumps([item.definition for item in Workflow.objects.all()])
    assert Workflow.objects.filter(name="已有流程").count() == 1
    assert Workflow.objects.get(name="另一条").status == Workflow.Status.DRAFT
    assert Workflow.objects.get(name="另一条").current_version == 0


@pytest.mark.django_db
def test_oversized_template_fails_one_item_and_uncompressed_limit_rejects_the_pack(superuser):
    assert MAX_UNCOMPRESSED_BYTES == 200 * 1024 * 1024
    huge = _blank("超大模板")
    huge["definition"] = build_blank_definition()
    huge["definition"]["tasks"] = [_task("bklite_document_render", "report_node", {})]
    huge["files"] = [{"task_reference": "report_node", "field": "template", "path": "files/big.docx", "filename": "big.docx"}]
    content = _zip([huge, _blank("小流程")], [("files/big.docx", os.urandom(MAX_TEMPLATE_BYTES + 1))])

    result = _import(superuser, content)

    assert [item["name"] for item in result["created"]] == ["小流程"]
    assert result["failed"] == [{"name": "超大模板", "reason": "文档模板超过 5MB"}]
    assert Workflow.objects.filter(name="超大模板").count() == 0

    info = zipfile.ZipInfo("workflows/0001.json")
    info.file_size = MAX_UNCOMPRESSED_BYTES + 1
    info.compress_size = MAX_UNCOMPRESSED_BYTES + 1
    info.compress_type = zipfile.ZIP_STORED
    with pytest.raises(PackRejected, match="压缩包解压后总大小超过 200MB"):
        _validate_members([info], max_uncompressed_bytes=MAX_UNCOMPRESSED_BYTES)

    before = Workflow.objects.count()
    with pytest.raises(PackRejected, match="压缩包解压后总大小超过 200MB"):
        _import(superuser, _zip([_blank("不该导入")]), max_uncompressed_bytes=10)
    assert Workflow.objects.count() == before


@pytest.mark.django_db
def test_import_accepts_finder_folder_wrapper_and_macos_junk(superuser):
    packed = _zip([_blank("访达压缩")])
    wrapped = BytesIO()
    with zipfile.ZipFile(BytesIO(packed)) as source, zipfile.ZipFile(wrapped, "w") as archive:
        archive.writestr("workflow-pack/.DS_Store", b"finder")
        for info in source.infolist():
            archive.writestr(f"workflow-pack/{info.filename}", source.read(info))
            archive.writestr(f"__MACOSX/workflow-pack/._{info.filename.replace('/', '_')}", b"apple")

    result = _import(superuser, wrapped.getvalue())

    assert result["failed"] == []
    assert [item["name"] for item in result["created"]] == ["访达压缩"]
    created = Workflow.objects.get(name="访达压缩")
    assert created.status == Workflow.Status.DRAFT
    assert created.team == [7]

    escaped = BytesIO()
    with zipfile.ZipFile(escaped, "w") as archive:
        archive.writestr(zipfile.ZipInfo("workflow-pack/../escape.json"), b"{}")
        archive.writestr("workflow-pack/manifest.json", b"{}")
    with pytest.raises(PackRejected, match="压缩包包含非法路径"):
        _import(superuser, escaped.getvalue())


@pytest.mark.django_db
def test_abnormal_compression_and_illegal_path_reject_the_whole_pack(superuser, caplog):
    caplog.set_level(logging.WARNING, logger="workflow")
    bomb = BytesIO()
    with zipfile.ZipFile(bomb, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        archive.writestr("bomb.txt", b"A" * 200_000)
        archive.writestr(
            "manifest.json",
            json.dumps(
                {"format": "bklite.workflow-pack", "schema_version": 1, "workflows": [{"file": "workflows/0001.json", "name": "不该导入"}]}
            ).encode(),
        )
        archive.writestr("workflows/0001.json", json.dumps(_blank("不该导入")).encode())
    with pytest.raises(PackRejected, match="压缩包压缩比异常"):
        _import(superuser, bomb.getvalue())
    assert Workflow.objects.count() == 0
    assert "event=workflow_pack_rejected failed_stage=compression error_type=PackRejected" in caplog.text
    assert "AAAA" not in caplog.text

    escaped = BytesIO()
    with zipfile.ZipFile(escaped, "w") as archive:
        archive.writestr(zipfile.ZipInfo("../escape.json"), b"{}")
        archive.writestr(
            "manifest.json",
            json.dumps(
                {"format": "bklite.workflow-pack", "schema_version": 1, "workflows": [{"file": "workflows/0001.json", "name": "不该导入"}]}
            ).encode(),
        )
        archive.writestr("workflows/0001.json", json.dumps(_blank("不该导入")).encode())
    with pytest.raises(PackRejected, match="压缩包包含非法路径"):
        _import(superuser, escaped.getvalue())
    assert Workflow.objects.count() == 0


@pytest.mark.django_db
def test_export_skips_unreadable_template_and_keeps_workflow_without_template(superuser):
    missing = Workflow.objects.create(
        name="模板丢失",
        team=[7],
        definition=build_blank_definition(),
        canvas_metadata=build_blank_canvas_metadata(),
    )
    definition = copy.deepcopy(missing.definition)
    definition["tasks"] = [
        _task(
            "bklite_document_render",
            "report_node",
            {
                "template_snapshot": {
                    "object_key": "workflow/templates/frozen/missing.docx",
                    "format": "docx",
                    "sha256": "a" * 64,
                    "size": 128,
                    "filename_prefix": "missing",
                }
            },
        )
    ]
    missing.definition = definition
    missing.save(update_fields=["definition"])
    empty = _blank("无模板")
    empty["definition"]["tasks"] = [_task("bklite_document_render", "report_node", {"filename_prefix": "report"})]
    ready = Workflow.objects.create(name="无模板", team=[7], definition=empty["definition"], canvas_metadata=empty["canvas_metadata"])

    content, failures = export_workflow_pack(Workflow.objects.all(), [missing.pk, ready.pk, 999], store=MemoryStore())

    assert failures == [
        {"name": "模板丢失", "reason": "文档模板无法读取"},
        {"name": "999", "reason": "流程不存在或无权导出"},
    ]
    missing.refresh_from_db()
    assert missing.definition["tasks"][0]["inputParameters"]["template_snapshot"]["object_key"].endswith("missing.docx")
    with zipfile.ZipFile(BytesIO(content)) as archive:
        packed = json.loads(archive.read("workflows/0001.json"))
        manifest = json.loads(archive.read("manifest.json"))
        names = archive.namelist()
    assert packed["name"] == "无模板"
    assert packed["files"] == []
    assert "template" not in packed["definition"]["tasks"][0]["inputParameters"]
    assert "failures" not in manifest
    assert names == ["workflows/0001.json", "manifest.json"]

    ready.delete()
    result = _import(superuser, content)
    created = Workflow.objects.get(pk=result["created"][0]["id"])
    assert created.definition["tasks"][0]["inputParameters"] == {"filename_prefix": "report"}
    assert created.current_version == 0
    assert created.is_builtin is False


@pytest.mark.django_db
def test_http_export_and_import_create_a_draft(superuser):
    source = Workflow.objects.create(name="接口流程", team=[7], definition=build_blank_definition(), canvas_metadata=build_blank_canvas_metadata())
    export_view = WorkflowViewSet.as_view({"post": "export_pack"})
    exported = export_view(_json_request(superuser, "post", "/workflows/export/", {"ids": [source.pk]}))
    assert exported.status_code == 200
    body = b"".join(exported.streaming_content)
    assert body.startswith(b"PK")
    with zipfile.ZipFile(BytesIO(body)) as archive:
        assert "failures" not in json.loads(archive.read("manifest.json"))
    source.delete()

    upload = SimpleUploadedFile("workflow-pack.zip", body, content_type="application/zip")
    imported = WorkflowViewSet.as_view({"post": "import_pack"})(_form_request(superuser, "/workflows/import/", {"file": upload, "team": "7"}))
    assert imported.status_code == 200
    created = Workflow.objects.get()
    assert imported.data["created"] == [{"name": "接口流程", "id": created.pk}]
    assert created.team == [7]
    assert created.status == Workflow.Status.DRAFT
    assert created.enabled is False
    assert created.is_builtin is False

    missing = export_view(_json_request(superuser, "post", "/workflows/export/", {"ids": [999]}))
    assert missing.status_code == 400
    assert missing.data["data"]["failed"] == [{"name": "999", "reason": "流程不存在或无权导出"}]
    missing.render()
    rendered = json.loads(missing.content)
    assert rendered["result"] is False
    assert rendered["data"]["failed"] == [{"name": "999", "reason": "流程不存在或无权导出"}]

    partial = export_view(_json_request(superuser, "post", "/workflows/export/", {"ids": [created.pk, 999]}))
    assert partial.status_code == 200
    partial.render()
    payload = json.loads(partial.content)
    assert payload["result"] is True
    assert payload["data"]["failed"] == [{"name": "999", "reason": "流程不存在或无权导出"}]
    with zipfile.ZipFile(BytesIO(base64.b64decode(payload["data"]["pack"]))) as archive:
        manifest = json.loads(archive.read("manifest.json"))
        assert archive.namelist() == ["workflows/0001.json", "manifest.json"]
    assert "failures" not in manifest
    assert manifest["workflows"] == [{"file": "workflows/0001.json", "name": "接口流程"}]


@pytest.mark.django_db
def test_import_uses_the_selected_organizations(superuser):
    view = WorkflowViewSet.as_view({"post": "import_pack"})
    selected = view(
        _form_request(
            superuser,
            "/workflows/import/",
            {"file": SimpleUploadedFile("workflow-pack.zip", _zip([_blank("指定组织")]), content_type="application/zip"), "team": ["8", "7"]},
        )
    )
    assert selected.status_code == 200
    created = Workflow.objects.get()
    assert created.team == [7, 8]
    assert selected.data["created"] == [{"name": "指定组织", "id": created.pk}]

    missing_team = view(
        _form_request(
            superuser,
            "/workflows/import/",
            {"file": SimpleUploadedFile("workflow-pack.zip", _zip([_blank("没有组织")]), content_type="application/zip")},
        )
    )
    assert missing_team.status_code == 400
    assert missing_team.data["detail"] == "请选择组织"
    assert Workflow.objects.filter(name="没有组织").count() == 0


@pytest.mark.django_db
def test_import_rejects_an_organization_outside_the_user_groups():
    user = get_user_model().objects.create(username="workflow-import-member", domain="example.com")
    user.group_list = [{"id": 7, "name": "Current"}]
    user.permission = {"workflow": {"workflow-Add"}}
    view = WorkflowViewSet.as_view({"post": "import_pack"})
    response = view(
        _form_request(
            user,
            "/workflows/import/",
            {"file": SimpleUploadedFile("workflow-pack.zip", _zip([_blank("越权组织")]), content_type="application/zip"), "team": "8"},
        )
    )
    assert response.status_code == 403
    assert Workflow.objects.count() == 0


def _json_request(user, method, path, data):
    request = getattr(APIRequestFactory(), method)(path, data, format="json")
    request.COOKIES["current_team"] = "7"
    force_authenticate(request, user=user)
    return request


def _form_request(user, path, data):
    request = APIRequestFactory().post(path, data, format="multipart")
    request.COOKIES["current_team"] = "7"
    force_authenticate(request, user=user)
    return request
