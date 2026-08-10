from datetime import timedelta

import pytest


def _record_with_failed_maintenance(title="Retry"):
    from apps.opspilot.models import BuildRecord, WikiKnowledgeBase
    from apps.opspilot.services.wiki.page_service import create_manual_page

    kb = WikiKnowledgeBase.objects.create(name=f"kb-{title}", team=[1])
    page = create_manual_page(kb, "concept", title, "body", created_by="test")
    record = BuildRecord.objects.create(
        knowledge_base=kb,
        trigger="material",
        status="partial",
        stage="done",
        affected_pages=[page.id],
        maintenance={
            "status": "partial",
            "event": "build",
            "affected_page_ids": [page.id],
            "stages": {
                "relations": {"status": "success", "count": 1},
                "page_embedding": {"status": "failed", "error": "old"},
            },
        },
    )
    return kb, page, record


@pytest.mark.django_db
def test_claim_rejects_second_inflight_retry_without_duplicate_cascade(api_client, monkeypatch):
    from apps.opspilot.viewsets import wiki_page_view

    kb, page, record = _record_with_failed_maintenance("ClaimedRetry")
    cascade_calls = []
    second_responses = []

    def blocking_cascade(knowledge_base, affected_page_ids, event, **kwargs):
        cascade_calls.append((knowledge_base.id, list(affected_page_ids), event, kwargs))
        second_responses.append(
            api_client.post(
                f"/api/v1/opspilot/wiki_mgmt/build_record/{record.id}/retry_maintenance/",
                {},
                format="json",
            )
        )
        return {
            "status": "success",
            "event": "maintenance_retry",
            "affected_page_ids": [page.id],
            "stages": {"relations": {"status": "success", "count": 1}},
        }

    monkeypatch.setattr(wiki_page_view, "cascade", blocking_cascade)

    first_response = api_client.post(
        f"/api/v1/opspilot/wiki_mgmt/build_record/{record.id}/retry_maintenance/",
        {},
        format="json",
    )

    assert first_response.status_code == 200, first_response.content
    assert len(second_responses) == 1
    assert second_responses[0].status_code == 409, second_responses[0].content
    assert cascade_calls == [(kb.id, [page.id], "maintenance_retry", {})]
    record.refresh_from_db()
    assert wiki_page_view._MAINTENANCE_RETRY_CLAIM_KEY not in record.inputs


@pytest.mark.django_db
def test_retry_finalization_merges_latest_stage_under_lock(api_client, monkeypatch):
    from apps.opspilot.models import BuildRecord
    from apps.opspilot.viewsets import wiki_page_view

    _, page, record = _record_with_failed_maintenance("LatestMaintenance")

    def cascade_with_concurrent_stage_update(*args, **kwargs):
        latest = BuildRecord.objects.get(pk=record.pk)
        maintenance = dict(latest.maintenance)
        stages = dict(maintenance["stages"])
        stages["relations"] = {"status": "success", "count": 99}
        stages["check_sweep"] = {"status": "success", "count": 7}
        maintenance["stages"] = stages
        maintenance["decision_children"] = [{"id": 101, "status": "success"}]
        BuildRecord.objects.filter(pk=record.pk).update(maintenance=maintenance)
        return {
            "status": "success",
            "event": "maintenance_retry",
            "affected_page_ids": [page.id],
            "stages": {"page_embedding": {"status": "success", "count": 1}},
            "indexed_pages": 1,
        }

    monkeypatch.setattr(wiki_page_view, "cascade", cascade_with_concurrent_stage_update)

    response = api_client.post(
        f"/api/v1/opspilot/wiki_mgmt/build_record/{record.id}/retry_maintenance/",
        {"stages": ["page_embedding"]},
        format="json",
    )

    assert response.status_code == 200, response.content
    record.refresh_from_db()
    assert record.maintenance["stages"]["page_embedding"] == {"status": "success", "count": 1}
    assert record.maintenance["stages"]["relations"] == {"status": "success", "count": 99}
    assert record.maintenance["stages"]["check_sweep"] == {"status": "success", "count": 7}
    assert record.maintenance["decision_children"] == [{"id": 101, "status": "success"}]


@pytest.mark.django_db
def test_retry_recovers_expired_claim(api_client, monkeypatch):
    from django.utils import timezone

    from apps.opspilot.viewsets import wiki_page_view

    _, page, record = _record_with_failed_maintenance("StaleClaim")
    record.inputs = {
        wiki_page_view._MAINTENANCE_RETRY_CLAIM_KEY: {
            "token": "stale-token",
            "claimed_at": (timezone.now() - wiki_page_view._MAINTENANCE_RETRY_CLAIM_TTL - timedelta(seconds=1)).isoformat(),
        }
    }
    record.save(update_fields=["inputs", "updated_at"])
    calls = []

    def fake_cascade(*args, **kwargs):
        calls.append((args, kwargs))
        return {
            "status": "success",
            "event": "maintenance_retry",
            "affected_page_ids": [page.id],
            "stages": {"relations": {"status": "success", "count": 1}},
        }

    monkeypatch.setattr(wiki_page_view, "cascade", fake_cascade)

    response = api_client.post(
        f"/api/v1/opspilot/wiki_mgmt/build_record/{record.id}/retry_maintenance/",
        {},
        format="json",
    )

    assert response.status_code == 200, response.content
    assert len(calls) == 1
    record.refresh_from_db()
    assert wiki_page_view._MAINTENANCE_RETRY_CLAIM_KEY not in record.inputs


@pytest.mark.django_db
def test_retry_does_not_finalize_after_claim_token_is_replaced(api_client, monkeypatch):
    from django.utils import timezone

    from apps.opspilot.models import BuildRecord
    from apps.opspilot.viewsets import wiki_page_view

    _, page, record = _record_with_failed_maintenance("LostClaim")
    winning_maintenance = {
        **record.maintenance,
        "stages": {"relations": {"status": "success", "count": 77}},
    }

    def replace_claim(*args, **kwargs):
        latest = BuildRecord.objects.get(pk=record.pk)
        inputs = dict(latest.inputs)
        inputs[wiki_page_view._MAINTENANCE_RETRY_CLAIM_KEY] = {
            "token": "replacement-token",
            "claimed_at": timezone.now().isoformat(),
        }
        BuildRecord.objects.filter(pk=record.pk).update(
            inputs=inputs,
            maintenance=winning_maintenance,
        )
        return {
            "status": "success",
            "event": "maintenance_retry",
            "affected_page_ids": [page.id],
            "stages": {"relations": {"status": "success", "count": 1}},
        }

    monkeypatch.setattr(wiki_page_view, "cascade", replace_claim)

    response = api_client.post(
        f"/api/v1/opspilot/wiki_mgmt/build_record/{record.id}/retry_maintenance/",
        {},
        format="json",
    )

    assert response.status_code == 409, response.content
    record.refresh_from_db()
    assert record.maintenance == winning_maintenance
    assert record.inputs[wiki_page_view._MAINTENANCE_RETRY_CLAIM_KEY]["token"] == "replacement-token"


@pytest.mark.django_db
def test_retry_uses_actual_maintenance_scope_and_clears_old_errors(
    api_client,
    monkeypatch,
):
    from apps.opspilot.services.wiki.page_service import create_manual_page
    from apps.opspilot.viewsets import wiki_page_view

    kb, page, record = _record_with_failed_maintenance("ActualScope")
    pending_page = create_manual_page(
        kb,
        "concept",
        "Pending decision",
        "pending",
        created_by="test",
    )
    record.affected_pages = [page.id, pending_page.id]
    record.errors = ["old maintenance error"]
    record.save(update_fields=["affected_pages", "errors", "updated_at"])
    calls = []

    def fake_cascade(knowledge_base, affected_page_ids, event, **kwargs):
        calls.append((knowledge_base.id, list(affected_page_ids), event, kwargs))
        return {
            "status": "success",
            "event": "maintenance_retry",
            "affected_page_ids": [page.id],
            "stages": {
                "relations": {"status": "success", "count": 1},
            },
        }

    monkeypatch.setattr(wiki_page_view, "cascade", fake_cascade)

    response = api_client.post(
        f"/api/v1/opspilot/wiki_mgmt/build_record/{record.id}/retry_maintenance/",
        {},
        format="json",
    )

    assert response.status_code == 200, response.content
    assert calls == [(kb.id, [page.id], "maintenance_retry", {})]
    record.refresh_from_db()
    assert record.affected_pages == [page.id]
    assert record.errors == []
