import pytest

from apps.opspilot.models import BuildRecord, CheckItem, KnowledgePage, Material
from apps.opspilot.services.wiki.check_service import accept_candidate
from apps.opspilot.services.wiki.page_service import edit_page


def _kb():
    from apps.opspilot.models import WikiKnowledgeBase

    return WikiKnowledgeBase.objects.create(name="kb", team=[1])


def _page(kb, title, body="", page_type="concept"):
    from apps.opspilot.services.wiki.page_service import create_manual_page

    return create_manual_page(kb, page_type=page_type, title=title, body=body, created_by="u")


@pytest.mark.django_db
def test_create_page_endpoint_runs_incremental_maintenance(monkeypatch, api_client):
    from apps.opspilot.models import PageRelation

    kb = _kb()
    target = _page(kb, "Target")

    def fail_full_rebuild(*args, **kwargs):
        raise AssertionError("page create must not run full relation rebuild")

    monkeypatch.setattr("apps.opspilot.services.wiki.cascade_service.rebuild_relations", fail_full_rebuild)

    response = api_client.post(
        "/api/v1/opspilot/wiki_mgmt/page/",
        {
            "knowledge_base": kb.id,
            "page_type": "concept",
            "title": "Source",
            "body": "See [[Target]].",
        },
        format="json",
    )

    assert response.status_code in (200, 201), response.content
    source_id = response.json()["data"]["id"]
    assert PageRelation.objects.filter(from_page_id=source_id, to_page=target, relation_type="reference").exists()


@pytest.mark.django_db
def test_save_answer_page_records_source_conversation():
    from apps.opspilot.services.wiki.page_service import save_answer_page

    kb = _kb()

    page = save_answer_page(
        knowledge_base=kb,
        page_type="concept",
        title="巡检结论",
        body="蓝鲸平台巡检正常。",
        tags=["qa", "巡检"],
        source_conversation_id="conv-1",
        source_message_id="msg-9",
        source_channel="bot",
        created_by="admin",
    )

    assert page.contribution == "mixed"
    assert page.update_method == "qa_answer"
    assert page.current_version.body == "蓝鲸平台巡检正常。"
    assert page.current_version.change_type == "qa_answer"
    assert page.current_version.meta_snapshot == {
        "source": {
            "type": "qa_answer",
            "conversation_id": "conv-1",
            "message_id": "msg-9",
            "channel": "bot",
        }
    }


@pytest.mark.django_db
def test_save_answer_endpoint_runs_incremental_maintenance(monkeypatch, api_client):
    kb = _kb()
    cascades = []

    def fake_cascade(knowledge_base, affected_page_ids=None, event="build", **kwargs):
        cascades.append((knowledge_base.id, affected_page_ids, event))

    monkeypatch.setattr("apps.opspilot.viewsets.wiki_page_view.cascade", fake_cascade)

    response = api_client.post(
        "/api/v1/opspilot/wiki_mgmt/page/save_answer/",
        {
            "knowledge_base": kb.id,
            "page_type": "entity",
            "title": "CMDB",
            "body": "CMDB 是配置平台。",
            "tags": ["qa"],
            "source_conversation_id": "conv-2",
            "source_message_id": "msg-3",
            "source_channel": "qa",
        },
        format="json",
    )

    assert response.status_code == 201, response.content
    data = response.json()["data"]
    assert data["title"] == "CMDB"
    assert data["contribution"] == "mixed"
    assert data["update_method"] == "qa_answer"
    assert cascades == [(kb.id, [data["id"]], "qa_answer_save")]


@pytest.mark.django_db
def test_save_answer_endpoint_can_create_review_candidate_without_polluting_active_pages(monkeypatch, api_client):
    kb = _kb()
    cascades = []

    def fake_cascade(knowledge_base, affected_page_ids=None, event="build", **kwargs):
        cascades.append((knowledge_base.id, affected_page_ids, event))
        return {"status": "success", "event": event, "affected_page_ids": affected_page_ids or []}

    monkeypatch.setattr("apps.opspilot.viewsets.wiki_page_view.cascade", fake_cascade)
    monkeypatch.setattr("apps.opspilot.services.wiki.check_service.cascade", fake_cascade)

    response = api_client.post(
        "/api/v1/opspilot/wiki_mgmt/page/save_answer/",
        {
            "knowledge_base": kb.id,
            "page_type": "concept",
            "title": "巡检建议",
            "body": "建议补充蓝鲸平台巡检 FAQ。",
            "tags": ["qa"],
            "source_conversation_id": "conv-qa-1",
            "source_message_id": "msg-qa-2",
            "source_channel": "qa",
            "as_candidate": True,
        },
        format="json",
    )

    assert response.status_code == 201, response.content
    data = response.json()["data"]
    assert data["check_type"] == "qa_answer_candidate"
    assert data["status"] == "open"
    assert data["candidate"]["body"] == "建议补充蓝鲸平台巡检 FAQ。"
    assert data["related"]["source"]["conversation_id"] == "conv-qa-1"
    assert cascades == []

    page = KnowledgePage.objects.get(id=data["related"]["pages"][0])
    assert page.status == "pending_review"
    assert page.current_version_id is None
    assert list(KnowledgePage.objects.filter(knowledge_base=kb, status="active").values_list("id", flat=True)) == []

    check = CheckItem.objects.get(id=data["id"])
    candidate = check.candidate_version
    assert candidate.is_current is False
    assert candidate.change_type == "qa_answer_candidate"
    assert candidate.meta_snapshot["source"]["message_id"] == "msg-qa-2"

    accept_candidate(check, operator="admin")

    page.refresh_from_db()
    assert page.status == "active"
    assert page.current_version_id == candidate.id
    assert cascades == [(kb.id, [page.id], "accept")]


@pytest.mark.django_db
def test_rejecting_save_answer_candidate_deletes_pending_shell_page(api_client):
    kb = _kb()

    response = api_client.post(
        "/api/v1/opspilot/wiki_mgmt/page/save_answer/",
        {
            "knowledge_base": kb.id,
            "page_type": "faq",
            "title": "临时回答",
            "body": "这个回答还需要确认。",
            "source_conversation_id": "conv-reject",
            "as_candidate": True,
        },
        format="json",
    )

    assert response.status_code == 201, response.content
    data = response.json()["data"]
    page_id = data["related"]["pages"][0]

    reject = api_client.post(f"/api/v1/opspilot/wiki_mgmt/check_item/{data['id']}/reject/", {}, format="json")

    assert reject.status_code == 200, reject.content
    assert not KnowledgePage.objects.filter(id=page_id).exists()


@pytest.mark.django_db
def test_save_answer_endpoint_requires_source_conversation(api_client):
    kb = _kb()

    response = api_client.post(
        "/api/v1/opspilot/wiki_mgmt/page/save_answer/",
        {
            "knowledge_base": kb.id,
            "page_type": "concept",
            "title": "无来源回答",
            "body": "缺少来源对话。",
            "source_message_id": "msg-1",
        },
        format="json",
    )

    assert response.status_code == 400, response.content
    assert response.json()["message"] == "source_conversation_id 必填"


@pytest.mark.django_db
def test_delete_page_endpoint_cleans_incremental_state(monkeypatch, api_client):
    from apps.opspilot.models import BuildRecord, CheckItem, PageRelation
    from apps.opspilot.services.wiki.relation_service import rebuild_relations

    kb = _kb()
    target = _page(kb, "Target")
    source = _page(kb, "Source", body="See [[Target]].")
    rebuild_relations(kb)
    build = BuildRecord.objects.create(
        knowledge_base=kb,
        trigger="material",
        status="success",
        stage="done",
        affected_pages=[source.id, target.id],
    )
    check = CheckItem.objects.create(
        knowledge_base=kb,
        check_type="conflict",
        status="open",
        related={"pages": [source.id, target.id]},
    )

    def fail_full_rebuild(*args, **kwargs):
        raise AssertionError("page delete must not run full relation rebuild")

    monkeypatch.setattr("apps.opspilot.services.wiki.cascade_service.rebuild_relations", fail_full_rebuild)

    response = api_client.delete(f"/api/v1/opspilot/wiki_mgmt/page/{target.id}/")

    assert response.status_code == 200, response.content
    assert not PageRelation.objects.filter(from_page=source, to_page_id=target.id).exists()
    assert CheckItem.objects.filter(
        knowledge_base=kb,
        check_type="broken_relation",
        related__pages__contains=[source.id],
        status="open",
    ).exists()

    build.refresh_from_db()
    check.refresh_from_db()
    assert build.affected_pages == [source.id]
    assert check.related["pages"] == [source.id]


@pytest.mark.django_db
def test_page_list_can_filter_by_status(api_client):
    kb = _kb()
    active = _page(kb, "Active")
    invalid = _page(kb, "Invalid")
    invalid.status = "source_invalid"
    invalid.save(update_fields=["status"])

    response = api_client.get(f"/api/v1/opspilot/wiki_mgmt/page/?knowledge_base={kb.id}&status=source_invalid")

    assert response.status_code == 200, response.content
    data = response.json()["data"]
    assert data["count"] == 1
    assert [item["id"] for item in data["items"]] == [invalid.id]
    assert active.id not in [item["id"] for item in data["items"]]


@pytest.mark.django_db
def test_page_list_default_returns_active_only_and_explicit_filters_include_other_states(api_client):
    kb = _kb()
    active = _page(kb, "Active")
    invalid = _page(kb, "Invalid")
    archived = _page(kb, "Archived")
    invalid.status = "source_invalid"
    invalid.save(update_fields=["status"])
    archived.status = "archived"
    archived.save(update_fields=["status"])

    default_response = api_client.get(f"/api/v1/opspilot/wiki_mgmt/page/?knowledge_base={kb.id}")

    assert default_response.status_code == 200, default_response.content
    default_ids = [item["id"] for item in default_response.json()["data"]["items"]]
    assert active.id in default_ids
    assert invalid.id not in default_ids
    assert archived.id not in default_ids

    invalid_response = api_client.get(f"/api/v1/opspilot/wiki_mgmt/page/?knowledge_base={kb.id}&status=source_invalid")

    assert invalid_response.status_code == 200, invalid_response.content
    invalid_data = invalid_response.json()["data"]
    assert invalid_data["count"] == 1
    assert [item["id"] for item in invalid_data["items"]] == [invalid.id]

    archived_response = api_client.get(f"/api/v1/opspilot/wiki_mgmt/page/?knowledge_base={kb.id}&status=archived")

    assert archived_response.status_code == 200, archived_response.content
    archived_data = archived_response.json()["data"]
    assert archived_data["count"] == 1
    assert [item["id"] for item in archived_data["items"]] == [archived.id]


@pytest.mark.django_db
def test_archived_page_cannot_be_edited_or_version_restored(api_client):
    kb = _kb()
    page = _page(kb, "Archived", body="v1")
    page.status = "archived"
    page.save(update_fields=["status"])
    version_id = page.current_version_id

    update_response = api_client.put(
        f"/api/v1/opspilot/wiki_mgmt/page/{page.id}/",
        {"title": "Changed", "body": "v2"},
        format="json",
    )
    restore_response = api_client.post(
        f"/api/v1/opspilot/wiki_mgmt/page/{page.id}/restore/",
        {"version_id": version_id},
        format="json",
    )

    assert update_response.status_code == 400, update_response.content
    assert restore_response.status_code == 400, restore_response.content
    page.refresh_from_db()
    assert page.status == "archived"
    assert page.title == "Archived"
    assert page.current_version.body == "v1"


@pytest.mark.django_db
def test_archived_page_can_be_restored_to_active(monkeypatch, api_client):
    kb = _kb()
    page = _page(kb, "Archived")
    page.status = "archived"
    page.save(update_fields=["status"])
    cascades = []

    def fake_cascade(knowledge_base, affected_page_ids=None, event="build", **kwargs):
        cascades.append((knowledge_base.id, affected_page_ids, event))

    monkeypatch.setattr("apps.opspilot.viewsets.wiki_page_view.cascade", fake_cascade)

    response = api_client.post(f"/api/v1/opspilot/wiki_mgmt/page/{page.id}/restore_from_archive/")

    assert response.status_code == 200, response.content
    assert response.json()["data"]["status"] == "active"
    page.refresh_from_db()
    assert page.status == "active"
    assert cascades == [(kb.id, [page.id], "page_restore_archive")]


@pytest.mark.django_db
def test_page_list_can_filter_by_title_and_type(api_client):
    kb = _kb()
    concept = _page(kb, "蓝鲸平台介绍", page_type="concept")
    entity = _page(kb, "蓝鲸平台组件", page_type="entity")
    other_entity = _page(kb, "作业平台", page_type="entity")

    response = api_client.get(f"/api/v1/opspilot/wiki_mgmt/page/?knowledge_base={kb.id}&title=蓝鲸&page_type=entity")

    assert response.status_code == 200, response.content
    data = response.json()["data"]
    assert data["count"] == 1
    assert [item["id"] for item in data["items"]] == [entity.id]
    assert concept.id not in [item["id"] for item in data["items"]]
    assert other_entity.id not in [item["id"] for item in data["items"]]


@pytest.mark.django_db
def test_batch_delete_pages_deletes_current_kb_selection_and_cleans_incremental_state(monkeypatch, api_client):
    from apps.opspilot.models import BuildRecord, CheckItem, KnowledgePage, PageRelation
    from apps.opspilot.services.wiki.relation_service import rebuild_relations

    kb = _kb()
    other_kb = _kb()
    source = _page(kb, "Source", body="See [[Invalid One]] and [[Invalid Two]].")
    invalid_one = _page(kb, "Invalid One")
    invalid_two = _page(kb, "Invalid Two")
    other_invalid = _page(other_kb, "Other Invalid")
    for page in [invalid_one, invalid_two, other_invalid]:
        page.status = "source_invalid"
        page.save(update_fields=["status"])
    rebuild_relations(kb)
    build = BuildRecord.objects.create(
        knowledge_base=kb,
        trigger="material_delete",
        status="success",
        stage="done",
        affected_pages=[source.id, invalid_one.id, invalid_two.id],
    )
    check = CheckItem.objects.create(
        knowledge_base=kb,
        check_type="source_invalid",
        status="open",
        related={"pages": [invalid_one.id, invalid_two.id]},
    )

    def fail_full_rebuild(*args, **kwargs):
        raise AssertionError("batch page delete must not run full relation rebuild")

    monkeypatch.setattr("apps.opspilot.services.wiki.cascade_service.rebuild_relations", fail_full_rebuild)

    response = api_client.post(
        "/api/v1/opspilot/wiki_mgmt/page/batch_delete/",
        {"knowledge_base": kb.id, "ids": [invalid_one.id, invalid_two.id, other_invalid.id, 999999]},
        format="json",
    )

    assert response.status_code == 200, response.content
    data = response.json()["data"]
    assert data["deleted"] == 2
    assert data["skipped"] == 2
    assert data["skipped_ids"] == [other_invalid.id, 999999]
    assert not KnowledgePage.objects.filter(id__in=[invalid_one.id, invalid_two.id]).exists()
    assert KnowledgePage.objects.filter(id=other_invalid.id).exists()
    assert not PageRelation.objects.filter(to_page_id__in=[invalid_one.id, invalid_two.id]).exists()

    build.refresh_from_db()
    check.refresh_from_db()
    assert build.affected_pages == [source.id]
    assert check.related["pages"] == []


@pytest.mark.django_db
def test_page_endpoint_retrieve_patch_diff_and_invalid_inputs(api_client):
    kb = _kb()
    page = _page(kb, "Page", body="v1")
    edit_page(page, body="v2", updated_by="tester")
    page.refresh_from_db()
    versions = list(page.page_versions.order_by("no"))

    retrieve = api_client.get(f"/api/v1/opspilot/wiki_mgmt/page/{page.id}/")
    invalid_page = api_client.get(f"/api/v1/opspilot/wiki_mgmt/page/?knowledge_base={kb.id}&page=bad&page_size=bad")
    patch = api_client.patch(f"/api/v1/opspilot/wiki_mgmt/page/{page.id}/", {"title": "Renamed"}, format="json")
    valid_diff = api_client.get(f"/api/v1/opspilot/wiki_mgmt/page/{page.id}/diff/?from={versions[0].id}&to={versions[1].id}")
    missing_diff_params = api_client.get(f"/api/v1/opspilot/wiki_mgmt/page/{page.id}/diff/")
    missing_diff_version = api_client.get(f"/api/v1/opspilot/wiki_mgmt/page/{page.id}/diff/?from=999999&to=999998")
    missing_restore_version = api_client.post(
        f"/api/v1/opspilot/wiki_mgmt/page/{page.id}/restore/",
        {},
        format="json",
    )
    active_restore_archive = api_client.post(f"/api/v1/opspilot/wiki_mgmt/page/{page.id}/restore_from_archive/")

    assert retrieve.status_code == 200, retrieve.content
    assert retrieve.json()["data"]["id"] == page.id
    assert invalid_page.status_code == 200, invalid_page.content
    assert patch.status_code == 200, patch.content
    assert patch.json()["data"]["title"] == "Renamed"
    assert valid_diff.status_code == 200, valid_diff.content
    assert valid_diff.json()["data"]["diff"]
    assert missing_diff_params.status_code == 400, missing_diff_params.content
    assert missing_diff_version.status_code == 404, missing_diff_version.content
    assert missing_restore_version.status_code == 400, missing_restore_version.content
    assert active_restore_archive.status_code == 400, active_restore_archive.content


@pytest.mark.django_db
def test_batch_delete_pages_validates_payload(api_client):
    kb = _kb()

    empty_ids = api_client.post(
        "/api/v1/opspilot/wiki_mgmt/page/batch_delete/",
        {"knowledge_base": kb.id, "ids": []},
        format="json",
    )
    invalid_ids = api_client.post(
        "/api/v1/opspilot/wiki_mgmt/page/batch_delete/",
        {"knowledge_base": kb.id, "ids": ["bad"]},
        format="json",
    )
    missing_kb = api_client.post(
        "/api/v1/opspilot/wiki_mgmt/page/batch_delete/",
        {"ids": [1]},
        format="json",
    )
    not_found_kb = api_client.post(
        "/api/v1/opspilot/wiki_mgmt/page/batch_delete/",
        {"knowledge_base": 999999, "ids": [1]},
        format="json",
    )

    assert empty_ids.status_code == 400, empty_ids.content
    assert invalid_ids.status_code == 400, invalid_ids.content
    assert missing_kb.status_code == 400, missing_kb.content
    assert not_found_kb.status_code == 400, not_found_kb.content


@pytest.mark.django_db
def test_build_record_endpoint_list_detail_retry_and_cancel(monkeypatch, api_client):
    kb = _kb()
    other_kb = _kb()
    material = Material.objects.create(knowledge_base=kb, name="source.md", material_type="text", text_content="body")
    running = BuildRecord.objects.create(
        knowledge_base=kb,
        trigger="material",
        status="running",
        stage="generating",
        inputs={"material_id": material.id},
    )
    BuildRecord.objects.create(knowledge_base=kb, trigger="rebuild", status="success", stage="done")
    BuildRecord.objects.create(knowledge_base=other_kb, trigger="material", status="running", stage="generating")
    delayed = []

    def fake_delay(material_id, llm_model_id, operator):
        delayed.append((material_id, llm_model_id, operator))

    monkeypatch.setattr("apps.opspilot.tasks.wiki_build_material_task.delay", fake_delay)

    listed = api_client.get(
        f"/api/v1/opspilot/wiki_mgmt/build_record/?knowledge_base={kb.id}" "&status=running&trigger=material&page=bad&page_size=bad"
    )
    detail = api_client.get(f"/api/v1/opspilot/wiki_mgmt/build_record/{running.id}/")
    retry = api_client.post(f"/api/v1/opspilot/wiki_mgmt/build_record/{running.id}/retry/")
    cancel = api_client.post(f"/api/v1/opspilot/wiki_mgmt/build_record/{running.id}/cancel/")

    assert listed.status_code == 200, listed.content
    data = listed.json()["data"]
    assert data["count"] == 1
    assert [item["id"] for item in data["items"]] == [running.id]
    assert detail.status_code == 200, detail.content
    assert detail.json()["data"]["id"] == running.id
    assert retry.status_code == 200, retry.content
    assert delayed == [(material.id, None, "testuser")]
    material.refresh_from_db()
    assert material.status == "building"
    assert cancel.status_code == 200, cancel.content
    running.refresh_from_db()
    assert running.status == "cancelled"
    assert running.stage == "cancelled"


@pytest.mark.django_db
def test_build_record_list_can_filter_by_maintenance_stage_failure(api_client):
    kb = _kb()
    chunk_failed = BuildRecord.objects.create(
        knowledge_base=kb,
        trigger="material",
        status="partial",
        stage="done",
        maintenance={
            "status": "partial",
            "stages": {
                "page_embedding": {"status": "success", "count": 1},
                "chunk_embedding": {"status": "failed", "error": "chunk provider down"},
            },
        },
    )
    BuildRecord.objects.create(
        knowledge_base=kb,
        trigger="material",
        status="partial",
        stage="done",
        maintenance={
            "status": "partial",
            "stages": {
                "page_embedding": {"status": "failed", "error": "page provider down"},
                "chunk_embedding": {"status": "success", "count": 3},
            },
        },
    )
    BuildRecord.objects.create(
        knowledge_base=kb,
        trigger="material",
        status="success",
        stage="done",
        maintenance={
            "status": "success",
            "stages": {
                "page_embedding": {"status": "success", "count": 1},
                "chunk_embedding": {"status": "success", "count": 3},
            },
        },
    )

    response = api_client.get(
        f"/api/v1/opspilot/wiki_mgmt/build_record/?knowledge_base={kb.id}"
        "&maintenance_status=partial&maintenance_stage=chunk_embedding&maintenance_stage_status=failed"
    )

    assert response.status_code == 200, response.content
    data = response.json()["data"]
    assert data["count"] == 1
    assert [item["id"] for item in data["items"]] == [chunk_failed.id]


@pytest.mark.django_db
def test_build_record_retry_requires_existing_material(api_client):
    kb = _kb()
    record = BuildRecord.objects.create(
        knowledge_base=kb,
        trigger="material",
        status="failed",
        stage="failed",
        inputs={"material_id": 999999},
    )

    response = api_client.post(f"/api/v1/opspilot/wiki_mgmt/build_record/{record.id}/retry/")

    assert response.status_code == 400, response.content
