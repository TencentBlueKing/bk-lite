import pytest


def _kb():
    from apps.opspilot.models import WikiKnowledgeBase

    return WikiKnowledgeBase.objects.create(name="kb", team=[1])


@pytest.mark.django_db
def test_diff_versions_returns_changed_lines():
    from apps.opspilot.services.wiki.page_service import create_manual_page, diff_versions, edit_page

    kb = _kb()
    page = create_manual_page(kb, page_type="concept", title="T", body="line1\nline2", created_by="u")
    v1 = page.current_version
    edit_page(page, body="line1\nline2 changed", updated_by="u")
    page.refresh_from_db()
    v2 = page.current_version

    lines = diff_versions(page, v1.id, v2.id)
    assert any("changed" in ln for ln in lines)
    assert any(ln.startswith("-") for ln in lines) and any(ln.startswith("+") for ln in lines)


@pytest.mark.django_db
def test_diff_versions_missing_raises():
    from apps.opspilot.services.wiki.page_service import create_manual_page, diff_versions

    kb = _kb()
    page = create_manual_page(kb, page_type="concept", title="T", body="x", created_by="u")
    with pytest.raises(ValueError):
        diff_versions(page, page.current_version.id, 999999)


@pytest.mark.django_db
class TestDiffView:
    def test_diff_endpoint(self, api_client):
        from apps.opspilot.services.wiki.page_service import create_manual_page, edit_page

        kb = _kb()
        page = create_manual_page(kb, page_type="concept", title="T", body="a\nb", created_by="u")
        v1 = page.current_version
        edit_page(page, body="a\nB", updated_by="u")
        page.refresh_from_db()
        v2 = page.current_version

        r = api_client.get(f"/api/v1/opspilot/wiki_mgmt/page/{page.id}/diff/?from={v1.id}&to={v2.id}")
        assert r.status_code == 200
        assert any("B" in ln for ln in r.json()["data"]["diff"])
