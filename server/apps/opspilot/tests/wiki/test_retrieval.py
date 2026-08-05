import pytest


def test_dynamic_snippet_default_window_is_long():
    from apps.opspilot.services.wiki.retrieval_service import _dynamic_snippet

    body = ("前言。" * 200) + "使用 systemctl restart nginx 重启服务。" + ("尾部。" * 200)
    snippet = _dynamic_snippet(body, ["systemctl", "restart"])
    assert "systemctl restart nginx" in snippet
    assert len(snippet) > 300


def test_fallback_answer_mentions_no_model():
    from apps.opspilot.services.wiki.retrieval_service import _fallback_answer

    text = _fallback_answer([{"title": "重启服务", "snippet": "systemctl restart nginx"}])
    assert "未使用模型" in text
    assert "重启服务" in text
    assert "systemctl restart nginx" in text


def test_qa_basic_llm_request_carries_protocol_and_vendor():
    from types import SimpleNamespace

    from apps.opspilot.services.wiki.retrieval_service import _qa_basic_llm_request

    llm = SimpleNamespace(
        vendor_id=1,
        vendor=SimpleNamespace(vendor_type="anthropic"),
        protocol_type="anthropic",
        openai_api_base="https://api.anthropic.com",
        openai_api_key="sk-test",
        model_name="claude-test",
    )
    request = _qa_basic_llm_request(llm, "hello", max_output_tokens=128)
    assert request.protocol_type == "anthropic"
    assert request.vendor_type == "anthropic"
    assert request.model == "claude-test"
    assert request.max_output_tokens == 128


def test_qa_max_output_tokens_default_is_4000(monkeypatch):
    from apps.opspilot.services.wiki import wiki_budget_service as budget

    monkeypatch.delenv("WIKI_QA_MAX_OUTPUT_TOKENS", raising=False)
    config = budget.load_wiki_budget_config(force_reload=True)
    assert config.qa_max_output_tokens == 4000


def _seed(kb):
    from apps.opspilot.models import Material
    from apps.opspilot.services.wiki.page_service import create_manual_page

    create_manual_page(kb, page_type="concept", title="重启服务", body="使用 systemctl restart nginx 重启服务。", created_by="u")
    create_manual_page(kb, page_type="concept", title="磁盘清理", body="清理 /var/log 释放磁盘空间。", created_by="u")
    Material.objects.create(knowledge_base=kb, name="nginx手册", material_type="text", ai_summary="nginx 服务重启与配置说明。")


@pytest.mark.django_db
def test_search_ranks_relevant_pages():
    from apps.opspilot.models import WikiKnowledgeBase
    from apps.opspilot.services.wiki.retrieval_service import search

    kb = WikiKnowledgeBase.objects.create(name="kb", team=[1])
    _seed(kb)
    results = search(kb, "重启 服务")
    assert results, "should find results"
    assert results[0]["title"] in ("重启服务", "资料摘要: nginx手册")
    titles = [r["title"] for r in results]
    assert "重启服务" in titles


@pytest.mark.django_db
def test_search_returns_keyword_explanation():
    from apps.opspilot.models import WikiKnowledgeBase
    from apps.opspilot.services.wiki.retrieval_service import search

    kb = WikiKnowledgeBase.objects.create(name="kb", team=[1])
    _seed(kb)

    results = search(kb, "重启 服务")

    assert results
    explanation = results[0]["explanation"]
    assert explanation["matched_by"] == ["keyword"]
    assert explanation["keyword_score"] == results[0]["score"]
    assert "重启" in explanation["matched_terms"]


@pytest.mark.django_db
def test_answer_without_model_falls_back_with_citations():
    from apps.opspilot.models import WikiKnowledgeBase
    from apps.opspilot.services.wiki.retrieval_service import answer

    kb = WikiKnowledgeBase.objects.create(name="kb", team=[1])
    _seed(kb)
    out = answer(kb, "如何重启服务", llm_model_id=None)
    assert out["citations"], "should cite something"
    assert "systemctl" in out["answer"] or "重启" in out["answer"]
    assert out["citations"][0]["explanation"]["matched_by"] == ["keyword"]
    assert out["mode"] == "fallback"
    assert out["warning_code"] == "wiki_answer_fallback"
    assert "未使用模型" in out["answer"]
    assert len(out["contexts"][0]["snippet"]) > 0


@pytest.mark.django_db
def test_answer_with_missing_model_falls_back_with_explanation():
    from apps.opspilot.models import WikiKnowledgeBase
    from apps.opspilot.services.wiki.retrieval_service import answer

    kb = WikiKnowledgeBase.objects.create(name="kb", team=[1])
    _seed(kb)

    out = answer(kb, "如何重启服务", llm_model_id=999999)

    assert out["citations"]
    assert out["citations"][0]["explanation"]["matched_by"] == ["keyword"]
    assert "重启" in out["answer"]
    assert out["mode"] == "fallback"


@pytest.mark.django_db
def test_answer_empty_kb():
    from apps.opspilot.models import WikiKnowledgeBase
    from apps.opspilot.services.wiki.retrieval_service import answer

    kb = WikiKnowledgeBase.objects.create(name="kb", team=[1])
    out = answer(kb, "anything", llm_model_id=None)
    assert out["citations"] == []
    assert out["mode"] == "empty"


@pytest.mark.django_db
def test_search_snippet_window_covers_long_body():
    from apps.opspilot.models import WikiKnowledgeBase
    from apps.opspilot.services.wiki.page_service import create_manual_page
    from apps.opspilot.services.wiki.retrieval_service import search

    kb = WikiKnowledgeBase.objects.create(name="kb", team=[1])
    body = ("前言段落。" * 80) + "使用 systemctl restart nginx 重启服务。" + ("尾部说明。" * 80)
    create_manual_page(kb, page_type="concept", title="重启服务", body=body, created_by="u")
    results = search(kb, "systemctl restart")
    assert results
    snippet = results[0]["snippet"]
    assert "systemctl restart nginx" in snippet
    assert len(snippet) > 300


@pytest.mark.django_db
def test_stream_answer_fallback_events():
    from apps.opspilot.models import WikiKnowledgeBase
    from apps.opspilot.services.wiki.retrieval_service import stream_answer

    kb = WikiKnowledgeBase.objects.create(name="kb", team=[1])
    _seed(kb)
    events = list(stream_answer(kb, "如何重启服务", llm_model_id=None))
    kinds = [event["event"] for event in events]
    assert kinds[:3] == ["meta", "delta", "done"]
    assert events[0]["mode"] == "fallback"
    assert events[0]["citations"]
    assert "未使用模型" in events[1]["text"]
    assert events[2]["mode"] == "fallback"
    assert events[2]["warning_code"] == "wiki_answer_fallback"


@pytest.mark.django_db
def test_stream_answer_llm_deltas(monkeypatch):
    from apps.opspilot.metis.llm.common.llm_client_factory import LLMClientFactory
    from apps.opspilot.models import WikiKnowledgeBase
    from apps.opspilot.services.wiki.retrieval_service import stream_answer

    kb = WikiKnowledgeBase.objects.create(name="kb", team=[1])
    _seed(kb)

    class FakeLLM:
        openai_api_base = "http://example.invalid"
        openai_api_key = "k"
        model_name = "fake"

    monkeypatch.setattr(
        "apps.opspilot.services.wiki.retrieval_service.LLMModel.objects.get",
        lambda **_kwargs: FakeLLM(),
    )

    def fake_stream(_request, _messages):
        yield "部"
        yield "分回答"
        _request.extra_config = {
            **(_request.extra_config or {}),
            "_isolated_finish_reason": "stop",
            "_isolated_output_truncated": False,
        }

    monkeypatch.setattr(LLMClientFactory, "stream_isolated", fake_stream)

    events = list(stream_answer(kb, "如何重启服务", llm_model_id=1))
    assert events[0]["event"] == "meta"
    assert events[0]["mode"] == "llm"
    deltas = [event["text"] for event in events if event["event"] == "delta"]
    assert deltas == ["部", "分回答"]
    done = events[-1]
    assert done["event"] == "done"
    assert done["answer"] == "部分回答"
    assert done["mode"] == "llm"


@pytest.mark.django_db
class TestRetrievalViews:
    def test_search_and_qa_endpoints(self, api_client):
        from apps.opspilot.models import WikiKnowledgeBase

        kb = WikiKnowledgeBase.objects.create(name="kb", team=[1])
        _seed(kb)
        s = api_client.post(f"/api/v1/opspilot/wiki_mgmt/knowledge_base/{kb.id}/search/", {"query": "重启 服务"}, format="json")
        assert s.status_code == 200, s.content
        assert any("重启" in r["title"] for r in s.json()["data"])

        q = api_client.post(f"/api/v1/opspilot/wiki_mgmt/knowledge_base/{kb.id}/qa/", {"query": "如何重启服务"}, format="json")
        assert q.status_code == 200, q.content
        payload = q.json()["data"]
        assert payload["citations"]
        assert payload["mode"] == "fallback"

    def test_qa_stream_endpoint(self, api_client):
        from apps.opspilot.models import WikiKnowledgeBase

        kb = WikiKnowledgeBase.objects.create(name="kb", team=[1])
        _seed(kb)
        response = api_client.post(
            f"/api/v1/opspilot/wiki_mgmt/knowledge_base/{kb.id}/qa_stream/",
            {"query": "如何重启服务"},
            format="json",
            HTTP_ACCEPT="text/event-stream",
        )
        assert response.status_code == 200, response.content
        assert "text/event-stream" in response["Content-Type"]
        body = b"".join(response.streaming_content).decode("utf-8")
        assert "data: " in body
        assert '"event": "meta"' in body or '"event":"meta"' in body
        assert "fallback" in body
        assert "未使用模型" in body
