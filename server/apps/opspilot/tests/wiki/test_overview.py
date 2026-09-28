import pytest


def _page(wiki_factory, kb, title, body=""):
    return wiki_factory.page(
        knowledge_base=kb,
        title=title,
        body=body,
    )


@pytest.mark.django_db
def test_overview_aggregates_counts_and_contribution(wiki_factory):
    from apps.opspilot.models import CheckItem, Material
    from apps.opspilot.services.wiki.overview_service import get_overview

    kb = wiki_factory.bootstrapped_knowledge_base(introduction="概览测试库")
    a = _page(wiki_factory, kb, "A")
    b = _page(wiki_factory, kb, "B")
    Material.objects.create(knowledge_base=kb, name="m", material_type="text", status="done")
    CheckItem.objects.create(
        knowledge_base=kb,
        check_type="orphan",
        status="auto_resolved",
        related={
            "pages": [a.id],
            "resolution": {"action": "automatic_maintenance", "operator": "system"},
        },
    )
    CheckItem.objects.create(
        knowledge_base=kb,
        check_type="cannot_merge",
        status="open",
        related={"pages": [b.id]},
    )

    ov = get_overview(kb)
    assert ov["counts"]["pages"] == 2
    assert ov["counts"]["materials"] == 1
    assert ov["counts"]["open_checks"] == 1
    assert ov["contribution"] == {"human": 2}
    assert ov["material_status"] == {"done": 1}
    assert ov["checks_by_type"] == {"cannot_merge": 1}
    assert ov["health"]["open_checks"] == 1


@pytest.mark.django_db
class TestOverviewView:
    def test_overview_endpoint(self, api_client, wiki_factory):
        kb = wiki_factory.bootstrapped_knowledge_base(introduction="概览接口库")
        _page(wiki_factory, kb, "A")
        r = api_client.get(f"/api/v1/opspilot/wiki_mgmt/knowledge_base/{kb.id}/overview/")
        assert r.status_code == 200
        data = r.json()["data"]
        assert data["knowledge_base"]["id"] == kb.id
        assert data["counts"]["pages"] == 1


@pytest.mark.django_db
def test_root_overview_uses_introduction_not_purpose(wiki_factory):
    from apps.opspilot.models import WikiGenerationOverview

    kb = wiki_factory.bootstrapped_knowledge_base(
        introduction="目标与收录范围",
        purpose_md="# 不应出现在概览里的用途",
    )
    _page(wiki_factory, kb, "A")
    kb.refresh_from_db()
    root = WikiGenerationOverview.objects.get(
        generation_id=kb.active_generation_id,
        scope_key="__root__",
    )
    assert "目标与收录范围" in root.deterministic_text
    assert "不应出现在概览里的用途" not in root.deterministic_text
    assert "purpose_md" not in root.deterministic_text
