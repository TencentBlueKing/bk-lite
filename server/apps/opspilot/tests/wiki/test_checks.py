import pytest


def _page_with_current(kb, body="v1"):
    from apps.opspilot.services.wiki.page_service import create_manual_page

    return create_manual_page(kb, page_type="concept", title="T", body=body, created_by="u")


@pytest.mark.django_db
def test_candidate_does_not_pollute_current_then_accept():
    from apps.opspilot.models import WikiKnowledgeBase
    from apps.opspilot.services.wiki.check_service import accept_candidate, create_candidate

    kb = WikiKnowledgeBase.objects.create(name="kb", team=[1])
    page = _page_with_current(kb, body="current")
    check = create_candidate(page, body="candidate", reason="conflict", check_type="conflict", created_by="ai")

    page.refresh_from_db()
    assert page.current_version.body == "current"  # 当前有效版本未被污染
    assert check.candidate_version.is_current is False
    assert check.status == "open"

    accept_candidate(check, operator="u")
    page.refresh_from_db()
    check.refresh_from_db()
    assert page.current_version.body == "candidate"
    assert check.status == "resolved"


@pytest.mark.django_db
def test_reject_candidate_keeps_current():
    from apps.opspilot.models import PageVersion, WikiKnowledgeBase
    from apps.opspilot.services.wiki.check_service import create_candidate, reject_candidate

    kb = WikiKnowledgeBase.objects.create(name="kb", team=[1])
    page = _page_with_current(kb, body="current")
    check = create_candidate(page, body="candidate", reason="conflict")
    cand_id = check.candidate_version_id

    reject_candidate(check, operator="u")
    page.refresh_from_db()
    check.refresh_from_db()
    assert page.current_version.body == "current"
    assert check.status == "dismissed"
    assert not PageVersion.objects.filter(id=cand_id).exists()


@pytest.mark.django_db
def test_scan_health_flags_orphan_and_is_idempotent():
    from apps.opspilot.models import CheckItem, WikiKnowledgeBase
    from apps.opspilot.services.wiki.check_service import scan_health

    kb = WikiKnowledgeBase.objects.create(name="kb", team=[1])
    _page_with_current(kb)  # 人工页面,无关系无证据 -> orphan
    created = scan_health(kb)
    assert len(created) == 1
    assert created[0].check_type == "orphan"
    # 幂等:再次扫描不重复创建
    again = scan_health(kb)
    assert again == []
    assert CheckItem.objects.filter(knowledge_base=kb, check_type="orphan").count() == 1


@pytest.mark.django_db
class TestCheckViews:
    def test_list_accept_and_scan_endpoints(self, api_client):
        from apps.opspilot.models import WikiKnowledgeBase
        from apps.opspilot.services.wiki.check_service import create_candidate

        kb = WikiKnowledgeBase.objects.create(name="kb", team=[1])
        page = _page_with_current(kb, body="current")
        check = create_candidate(page, body="cand", reason="conflict")

        lst = api_client.get(f"/api/v1/opspilot/wiki_mgmt/check_item/?knowledge_base={kb.id}")
        assert lst.status_code == 200
        assert any(c["id"] == check.id for c in lst.json()["data"])

        acc = api_client.post(f"/api/v1/opspilot/wiki_mgmt/check_item/{check.id}/accept/", {}, format="json")
        assert acc.status_code == 200
        page.refresh_from_db()
        assert page.current_version.body == "cand"

        scan = api_client.post(f"/api/v1/opspilot/wiki_mgmt/knowledge_base/{kb.id}/scan/", {}, format="json")
        assert scan.status_code == 200
