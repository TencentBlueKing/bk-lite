import pytest


def _kb():
    from apps.opspilot.models import WikiKnowledgeBase

    return WikiKnowledgeBase.objects.create(name="kb", team=[1], schema_md="types: concept")


def _material(kb):
    from apps.opspilot.models import Material

    return Material.objects.create(knowledge_base=kb, name="m", material_type="text", text_content="raw text", ai_summary="raw text")


@pytest.mark.django_db
def test_build_uses_two_step_pipeline(monkeypatch):
    from apps.opspilot.models import KnowledgePage
    from apps.opspilot.services.wiki import build_service

    kb = _kb()
    mat = _material(kb)
    calls = []

    def fake_invoke(llm_model_id, prompt):
        calls.append(prompt)
        if "JSON" in prompt:  # Stage2(生成页面)
            return '{"pages":[{"page_type":"concept","title":"P1","tags":[],"body":"from facts"}]}'
        return "- fact 1\n- fact 2"  # Stage1(抽取要点)

    monkeypatch.setattr(build_service, "_invoke_llm", fake_invoke)
    build = build_service.build_from_material(mat, llm_model_id=123)

    assert build.status == "success"
    assert len(calls) == 2  # 两步:Stage1 + Stage2
    assert any("fact 1" in c for c in calls)  # Stage1 抽取的要点流入 Stage2 提示词
    page = KnowledgePage.objects.get(knowledge_base=kb, title="P1")
    assert page.current_version.body == "from facts"
