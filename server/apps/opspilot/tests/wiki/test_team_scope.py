import pytest
from django.core.files.uploadedfile import SimpleUploadedFile


@pytest.fixture
def team_scoped_objects():
    from apps.opspilot.models import BuildRecord, CheckItem, Material, WikiKnowledgeBase
    from apps.opspilot.services.wiki.page_service import create_manual_page

    own_kb = WikiKnowledgeBase.objects.create(name="own", team=[1])
    shared_kb = WikiKnowledgeBase.objects.create(name="shared", team=[1, 2])
    foreign_kb = WikiKnowledgeBase.objects.create(name="foreign", team=[2])
    own_material = Material.objects.create(
        knowledge_base=own_kb,
        name="own-material",
        material_type="text",
        text_content="own",
    )
    foreign_material = Material.objects.create(
        knowledge_base=foreign_kb,
        name="foreign-material",
        material_type="text",
        text_content="foreign",
    )
    own_page = create_manual_page(own_kb, "concept", "Own", "own", created_by="test")
    foreign_page = create_manual_page(foreign_kb, "concept", "Foreign", "foreign", created_by="test")
    archived_foreign_page = create_manual_page(
        foreign_kb,
        "concept",
        "Archived foreign",
        "foreign",
        created_by="test",
    )
    archived_foreign_page.status = "archived"
    archived_foreign_page.save(update_fields=["status", "updated_at"])
    own_build = BuildRecord.objects.create(
        knowledge_base=own_kb,
        trigger="material",
        status="partial",
        stage="done",
        affected_pages=[own_page.id],
        maintenance={
            "status": "partial",
            "event": "build",
            "affected_page_ids": [own_page.id],
            "stages": {"relations": {"status": "failed", "error": "own"}},
        },
    )
    foreign_build = BuildRecord.objects.create(
        knowledge_base=foreign_kb,
        trigger="material",
        status="running",
        stage="queued",
        inputs={"material_id": foreign_material.id},
        affected_pages=[foreign_page.id],
        maintenance={
            "status": "partial",
            "event": "build",
            "affected_page_ids": [foreign_page.id],
            "stages": {"relations": {"status": "failed", "error": "foreign"}},
        },
    )
    own_check = CheckItem.objects.create(
        knowledge_base=own_kb,
        check_type="cannot_merge",
        status="open",
        related={"pages": [own_page.id]},
    )
    foreign_check = CheckItem.objects.create(
        knowledge_base=foreign_kb,
        check_type="cannot_merge",
        status="open",
        related={"pages": [foreign_page.id]},
    )
    return {
        "own_kb": own_kb,
        "shared_kb": shared_kb,
        "foreign_kb": foreign_kb,
        "own_material": own_material,
        "foreign_material": foreign_material,
        "own_page": own_page,
        "foreign_page": foreign_page,
        "archived_foreign_page": archived_foreign_page,
        "own_build": own_build,
        "foreign_build": foreign_build,
        "own_check": own_check,
        "foreign_check": foreign_check,
    }


@pytest.mark.django_db
def test_wiki_lists_and_details_are_limited_to_intersecting_teams(api_client, team_scoped_objects):
    objects = team_scoped_objects
    endpoints = [
        ("knowledge_base", objects["own_kb"].id, objects["foreign_kb"].id),
        ("material", objects["own_material"].id, objects["foreign_material"].id),
        ("page", objects["own_page"].id, objects["foreign_page"].id),
        ("build_record", objects["own_build"].id, objects["foreign_build"].id),
        ("check_item", objects["own_check"].id, objects["foreign_check"].id),
    ]

    for resource, own_id, foreign_id in endpoints:
        listed = api_client.get(f"/api/v1/opspilot/wiki_mgmt/{resource}/")
        retrieved = api_client.get(f"/api/v1/opspilot/wiki_mgmt/{resource}/{foreign_id}/")

        assert listed.status_code == 200, listed.content
        listed_ids = {item["id"] for item in listed.json()["data"]["items"]}
        assert own_id in listed_ids
        assert foreign_id not in listed_ids
        assert retrieved.status_code == 403, retrieved.content

    kb_ids = {item["id"] for item in api_client.get("/api/v1/opspilot/wiki_mgmt/knowledge_base/").json()["data"]["items"]}
    assert objects["shared_kb"].id in kb_ids


@pytest.mark.django_db
def test_check_mutation_actions_reject_cross_team_items(api_client, team_scoped_objects):
    foreign_check = team_scoped_objects["foreign_check"]
    endpoints = [
        ("assign", {"assignee": "intruder"}),
        ("decide", {"action": "keep_current"}),
        ("revoke_rule", {"reason": "intruder"}),
    ]

    for action_name, payload in endpoints:
        response = api_client.post(
            f"/api/v1/opspilot/wiki_mgmt/check_item/{foreign_check.id}/{action_name}/",
            payload,
            format="json",
        )
        assert response.status_code == 403, response.content

    foreign_check.refresh_from_db()
    assert foreign_check.status == "open"
    assert foreign_check.assignee == ""


@pytest.mark.django_db
def test_check_generic_mutation_routes_are_disabled(api_client, team_scoped_objects):
    own_check = team_scoped_objects["own_check"]

    responses = [
        api_client.post(
            "/api/v1/opspilot/wiki_mgmt/check_item/",
            {"knowledge_base": team_scoped_objects["own_kb"].id, "check_type": "cannot_merge"},
            format="json",
        ),
        api_client.put(
            f"/api/v1/opspilot/wiki_mgmt/check_item/{own_check.id}/",
            {"status": "resolved"},
            format="json",
        ),
        api_client.patch(
            f"/api/v1/opspilot/wiki_mgmt/check_item/{own_check.id}/",
            {"status": "resolved"},
            format="json",
        ),
        api_client.delete(f"/api/v1/opspilot/wiki_mgmt/check_item/{own_check.id}/"),
    ]

    assert [response.status_code for response in responses] == [405, 405, 405, 405]
    own_check.refresh_from_db()
    assert own_check.status == "open"


@pytest.mark.django_db
def test_check_serializer_does_not_resolve_cross_kb_page_references(api_client, team_scoped_objects):
    own_check = team_scoped_objects["own_check"]
    own_page = team_scoped_objects["own_page"]
    foreign_page = team_scoped_objects["foreign_page"]
    own_check.related = {"pages": [own_page.id, foreign_page.id]}
    own_check.save(update_fields=["related", "updated_at"])

    response = api_client.get(f"/api/v1/opspilot/wiki_mgmt/check_item/{own_check.id}/")

    assert response.status_code == 200, response.content
    related_pages = response.json()["data"]["related_pages"]
    assert [page["id"] for page in related_pages] == [own_page.id]
    assert all(page["title"] != foreign_page.title for page in related_pages)


@pytest.mark.django_db
def test_check_serializer_does_not_resolve_cross_kb_material_references(api_client, team_scoped_objects):
    from apps.opspilot.models import PageVersion

    own_check = team_scoped_objects["own_check"]
    own_page = team_scoped_objects["own_page"]
    foreign_material = team_scoped_objects["foreign_material"]
    candidate = PageVersion.objects.create(
        page=own_page,
        no=2,
        body="candidate",
        change_type="candidate",
        is_current=False,
    )
    own_check.candidate_version = candidate
    own_check.decision_context = {
        "decision_type": "knowledge_conflict",
        "page_identity": {"page_id": own_page.id},
        "incoming": {"material_id": foreign_material.id},
    }
    own_check.save(update_fields=["candidate_version", "decision_context", "updated_at"])

    response = api_client.get(f"/api/v1/opspilot/wiki_mgmt/check_item/{own_check.id}/")

    assert response.status_code == 200, response.content
    new_knowledge = response.json()["data"]["new_knowledge"]
    assert new_knowledge["source_label"] == ""
    assert new_knowledge["source_count"] == 0


@pytest.mark.django_db
def test_check_serializer_does_not_expose_cross_kb_candidate_body(api_client, team_scoped_objects):
    own_check = team_scoped_objects["own_check"]
    foreign_page = team_scoped_objects["foreign_page"]
    own_check.candidate_version = foreign_page.current_version
    own_check.save(update_fields=["candidate_version", "updated_at"])

    response = api_client.get(f"/api/v1/opspilot/wiki_mgmt/check_item/{own_check.id}/")

    assert response.status_code == 200, response.content
    assert response.json()["data"]["candidate"] is None


@pytest.mark.django_db
def test_decide_auto_resolves_cross_kb_candidate_without_modifying_foreign_page(team_scoped_objects):
    from apps.opspilot.services.wiki.check_service import create_candidate, decide_check

    own_material = team_scoped_objects["own_material"]
    own_material.content_hash = "own-v1"
    own_material.save(update_fields=["content_hash", "updated_at"])
    own_check = create_candidate(
        team_scoped_objects["own_page"],
        body="own candidate",
        reason="cross-kb guard",
        check_type="cannot_merge",
        incoming_material=own_material,
    )
    foreign_page = team_scoped_objects["foreign_page"]
    foreign_version_id = foreign_page.current_version_id
    own_check.candidate_version = foreign_page.current_version
    own_check.save(update_fields=["candidate_version", "updated_at"])

    assert decide_check(own_check, action="keep_current", operator="reviewer") is None

    own_check.refresh_from_db()
    foreign_page.refresh_from_db()
    assert own_check.status == "auto_resolved"
    assert own_check.related["resolution"]["reason"] == "decision_context_stale"
    assert foreign_page.current_version_id == foreign_version_id


@pytest.mark.django_db
def test_frozen_rule_snapshot_keeps_decision_content_but_uses_live_rule_state(api_client, team_scoped_objects):
    from django.utils import timezone

    from apps.opspilot.models import WikiDecisionRule

    own_check = team_scoped_objects["own_check"]
    own_check.status = "resolved"
    own_check.related = {
        "rule_snapshot": {
            "id": 0,
            "status": "active",
            "action": "keep_current",
            "match_snapshot": {"frozen": "match"},
            "result_snapshot": {"frozen": "result"},
            "replay_count": 0,
            "last_replayed_at": None,
            "revoked_reason": "",
        }
    }
    own_check.save(update_fields=["status", "related", "updated_at"])
    rule = WikiDecisionRule.objects.create(
        knowledge_base=team_scoped_objects["own_kb"],
        decision_type="knowledge_conflict",
        decision_key="d" * 64,
        action="use_new",
        source_check=own_check,
        status="revoked",
        replay_count=3,
        last_replayed_at=timezone.now(),
        match_snapshot={"live": "match"},
        result_snapshot={"live": "result", "revoked_reason": "source removed"},
    )

    response = api_client.get(f"/api/v1/opspilot/wiki_mgmt/check_item/{own_check.id}/")

    assert response.status_code == 200, response.content
    serialized_rule = response.json()["data"]["decision_rule"]
    assert serialized_rule["id"] == rule.id
    assert serialized_rule["action"] == "keep_current"
    assert serialized_rule["match_snapshot"] == {"frozen": "match"}
    assert serialized_rule["result_snapshot"] == {"frozen": "result"}
    assert serialized_rule["status"] == "revoked"
    assert serialized_rule["replay_count"] == 3
    assert serialized_rule["last_replayed_at"] is not None
    assert serialized_rule["revoked_reason"] == "source removed"


@pytest.mark.django_db
def test_cross_team_creates_and_team_reassignment_are_rejected(api_client, team_scoped_objects, monkeypatch):
    from apps.opspilot.models import KnowledgePage, Material, WikiKnowledgeBase

    objects = team_scoped_objects
    foreign_kb = objects["foreign_kb"]
    own_kb = objects["own_kb"]
    monkeypatch.setattr(
        "apps.opspilot.viewsets.wiki_material_view.ingest_material",
        lambda *args, **kwargs: pytest.fail("foreign material must not be ingested"),
    )
    monkeypatch.setattr(
        "apps.opspilot.viewsets.wiki_page_view.cascade",
        lambda *args, **kwargs: pytest.fail("foreign page must not cascade"),
    )

    kb_create = api_client.post(
        "/api/v1/opspilot/wiki_mgmt/knowledge_base/",
        {"name": "foreign-created", "team": [2]},
        format="json",
    )
    kb_mixed_create = api_client.post(
        "/api/v1/opspilot/wiki_mgmt/knowledge_base/",
        {"name": "mixed-created", "team": [1, 2]},
        format="json",
    )
    kb_reassign = api_client.patch(
        f"/api/v1/opspilot/wiki_mgmt/knowledge_base/{own_kb.id}/",
        {"team": [2]},
        format="json",
    )
    material_create = api_client.post(
        "/api/v1/opspilot/wiki_mgmt/material/",
        {
            "knowledge_base": foreign_kb.id,
            "name": "blocked",
            "material_type": "text",
            "text_content": "blocked",
        },
        format="json",
    )
    material_batch_create = api_client.post(
        "/api/v1/opspilot/wiki_mgmt/material/batch_create/",
        {
            "knowledge_base": foreign_kb.id,
            "files": [SimpleUploadedFile("blocked.md", b"blocked", content_type="text/markdown")],
        },
        format="multipart",
    )
    page_create = api_client.post(
        "/api/v1/opspilot/wiki_mgmt/page/",
        {
            "knowledge_base": foreign_kb.id,
            "page_type": "concept",
            "title": "Blocked",
            "body": "blocked",
        },
        format="json",
    )

    for response in (
        kb_create,
        kb_mixed_create,
        kb_reassign,
        material_create,
        material_batch_create,
        page_create,
    ):
        assert response.status_code == 403, response.content
    assert not WikiKnowledgeBase.objects.filter(name__in=["foreign-created", "mixed-created"]).exists()
    own_kb.refresh_from_db()
    assert own_kb.team == [1]
    assert not Material.objects.filter(knowledge_base=foreign_kb, name="blocked").exists()
    assert not KnowledgePage.objects.filter(knowledge_base=foreign_kb, title="Blocked").exists()


@pytest.mark.django_db
def test_cross_team_irreversible_delete_restore_and_retries_do_not_mutate(
    api_client,
    team_scoped_objects,
    monkeypatch,
):
    objects = team_scoped_objects
    monkeypatch.setattr(
        "apps.opspilot.viewsets.wiki_material_view.handle_material_deletion",
        lambda *args, **kwargs: pytest.fail("foreign material must not be deleted"),
    )
    monkeypatch.setattr(
        "apps.opspilot.viewsets.wiki_page_view.cascade",
        lambda *args, **kwargs: pytest.fail("foreign maintenance must not run"),
    )
    monkeypatch.setattr(
        "apps.opspilot.tasks.wiki_build_material_task.delay",
        lambda *args, **kwargs: pytest.fail("foreign retry must not enqueue"),
    )

    responses = [
        api_client.delete(f"/api/v1/opspilot/wiki_mgmt/knowledge_base/{objects['foreign_kb'].id}/"),
        api_client.delete(f"/api/v1/opspilot/wiki_mgmt/material/{objects['foreign_material'].id}/"),
        api_client.delete(f"/api/v1/opspilot/wiki_mgmt/page/{objects['foreign_page'].id}/"),
        api_client.post(
            f"/api/v1/opspilot/wiki_mgmt/page/{objects['archived_foreign_page'].id}/restore_from_archive/",
            {},
            format="json",
        ),
        api_client.post(
            f"/api/v1/opspilot/wiki_mgmt/build_record/{objects['foreign_build'].id}/retry/",
            {},
            format="json",
        ),
        api_client.post(
            f"/api/v1/opspilot/wiki_mgmt/build_record/{objects['foreign_build'].id}/retry_maintenance/",
            {},
            format="json",
        ),
        api_client.post(
            f"/api/v1/opspilot/wiki_mgmt/build_record/{objects['foreign_build'].id}/cancel/",
            {},
            format="json",
        ),
    ]

    for response in responses:
        assert response.status_code == 403, response.content
    for key in ("foreign_kb", "foreign_material", "foreign_page", "archived_foreign_page"):
        assert type(objects[key]).objects.filter(pk=objects[key].pk).exists()
    objects["archived_foreign_page"].refresh_from_db()
    objects["foreign_build"].refresh_from_db()
    assert objects["archived_foreign_page"].status == "archived"
    assert objects["foreign_build"].status == "running"
    assert objects["foreign_build"].stage == "queued"


@pytest.mark.django_db
def test_mixed_team_batch_ids_fail_closed_before_any_mutation(api_client, team_scoped_objects, monkeypatch):
    objects = team_scoped_objects
    monkeypatch.setattr(
        "apps.opspilot.viewsets.wiki_page_view.cascade",
        lambda *args, **kwargs: pytest.fail("mixed-team batch must not cascade"),
    )

    page_response = api_client.post(
        "/api/v1/opspilot/wiki_mgmt/page/batch_delete/",
        {
            "knowledge_base": objects["own_kb"].id,
            "ids": [objects["own_page"].id, objects["foreign_page"].id],
        },
        format="json",
    )
    build_response = api_client.post(
        "/api/v1/opspilot/wiki_mgmt/build_record/batch_retry_maintenance/",
        {
            "knowledge_base": objects["own_kb"].id,
            "ids": [objects["own_build"].id, objects["foreign_build"].id],
        },
        format="json",
    )

    assert page_response.status_code == 403, page_response.content
    assert build_response.status_code == 403, build_response.content
    assert type(objects["own_page"]).objects.filter(pk=objects["own_page"].pk).exists()
    assert type(objects["foreign_page"]).objects.filter(pk=objects["foreign_page"].pk).exists()
    objects["own_build"].refresh_from_db()
    objects["own_check"].refresh_from_db()
    assert objects["own_build"].status == "partial"
    assert objects["own_check"].status == "open"


@pytest.mark.django_db
def test_superuser_wiki_scope_remains_unrestricted(api_client, authenticated_user, team_scoped_objects):
    authenticated_user.is_superuser = True
    authenticated_user.save(update_fields=["is_superuser"])
    foreign_kb = team_scoped_objects["foreign_kb"]

    listed = api_client.get("/api/v1/opspilot/wiki_mgmt/knowledge_base/")
    retrieved = api_client.get(f"/api/v1/opspilot/wiki_mgmt/knowledge_base/{foreign_kb.id}/")

    assert listed.status_code == 200, listed.content
    assert foreign_kb.id in {item["id"] for item in listed.json()["data"]["items"]}
    assert retrieved.status_code == 200, retrieved.content
