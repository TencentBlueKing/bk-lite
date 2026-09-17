import pytest


def test_dynamic_snippet_default_window_is_long():
    from apps.opspilot.services.wiki.retrieval_service import _dynamic_snippet

    body = ("前言。" * 200) + "使用 systemctl restart nginx 重启服务。" + ("尾部。" * 200)
    snippet = _dynamic_snippet(body, ["systemctl", "restart"])
    assert "systemctl restart nginx" in snippet
    assert len(snippet) > 300


def test_fallback_answer_includes_title_and_snippet():
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


def test_qa_retrieval_mode_uses_hybrid_when_embed_provider_configured():
    from types import SimpleNamespace

    from apps.opspilot.services.wiki.retrieval_service import _qa_retrieval_mode, default_retrieval_mode

    assert _qa_retrieval_mode(SimpleNamespace(embed_provider_id=3)) == "hybrid"
    assert _qa_retrieval_mode(SimpleNamespace(embed_provider_id=None)) == "keyword"
    assert _qa_retrieval_mode(SimpleNamespace(embed_provider_id=3), "keyword") == "keyword"
    assert _qa_retrieval_mode(SimpleNamespace(embed_provider_id=None), "hybrid") == "hybrid"
    assert default_retrieval_mode(SimpleNamespace(embed_provider_id=3)) == "hybrid"


def _kb():
    from apps.opspilot.tests.wiki.factories import WikiFactory

    return WikiFactory().bootstrapped_knowledge_base()


def _seed(kb):
    from apps.opspilot.models import Material
    from apps.opspilot.services.wiki.page_service import create_manual_page

    create_manual_page(kb, page_type="concept", title="重启服务", body="使用 systemctl restart nginx 重启服务。", created_by="u")
    create_manual_page(kb, page_type="concept", title="磁盘清理", body="清理 /var/log 释放磁盘空间。", created_by="u")
    Material.objects.create(knowledge_base=kb, name="nginx手册", material_type="text", ai_summary="nginx 服务重启与配置说明。")


@pytest.mark.django_db
def test_search_ranks_relevant_pages():
    from apps.opspilot.services.wiki.retrieval_service import search

    kb = _kb()
    _seed(kb)
    results = search(kb, "重启 服务")
    assert results, "should find results"
    assert results[0]["title"] in ("重启服务", "资料摘要: nginx手册")
    titles = [r["title"] for r in results]
    assert "重启服务" in titles


@pytest.mark.django_db
def test_search_hits_body_only_page_and_keeps_title_ahead():
    from apps.opspilot.models import WikiGenerationIndexEntry
    from apps.opspilot.services.wiki.generation_navigation_service import BODY_INDEX_SEP
    from apps.opspilot.services.wiki.page_service import create_manual_page
    from apps.opspilot.services.wiki.retrieval_service import search

    kb = _kb()
    body_page = create_manual_page(
        kb,
        page_type="concept",
        title="办公网络常见问题",
        body="梯子连不上时请改用华为VPN客户端拨号。",
        created_by="u",
    )
    title_page = create_manual_page(
        kb,
        page_type="concept",
        title="嘉为公司用户VPN使用手册",
        body="安装步骤见下文。",
        created_by="u",
    )
    kb.refresh_from_db()
    entry = WikiGenerationIndexEntry.objects.get(generation_id=kb.active_generation_id, page_id=body_page.id)
    assert BODY_INDEX_SEP in entry.search_text
    assert "梯子连不上" in entry.search_text

    body_hits = search(kb, "梯子连不上", top_k=20)
    assert body_hits
    assert any(item["id"] == body_page.id for item in body_hits)

    title_hits = search(kb, "嘉为公司用户VPN使用手册", top_k=20)
    assert title_hits[0]["id"] == title_page.id


@pytest.mark.django_db
def test_search_legacy_index_without_body_marker_still_scores_page_body():
    from apps.opspilot.models import WikiGenerationIndexEntry
    from apps.opspilot.services.wiki.generation_navigation_service import BODY_INDEX_SEP
    from apps.opspilot.services.wiki.page_service import create_manual_page
    from apps.opspilot.services.wiki.retrieval_service import search

    kb = _kb()
    page = create_manual_page(
        kb,
        page_type="concept",
        title="办公网络常见问题",
        body="梯子连不上时请改用华为VPN客户端拨号。",
        created_by="u",
    )
    kb.refresh_from_db()
    entry = WikiGenerationIndexEntry.objects.get(generation_id=kb.active_generation_id, page_id=page.id)
    nav, _sep, _body = entry.search_text.partition(BODY_INDEX_SEP)
    entry.search_text = nav
    entry.save(update_fields=["search_text"])
    hits = search(kb, "梯子连不上", top_k=20)
    assert hits
    assert any(item["id"] == page.id for item in hits)


@pytest.mark.django_db
def test_search_returns_keyword_explanation():
    from apps.opspilot.services.wiki.retrieval_service import search

    kb = _kb()
    _seed(kb)

    results = search(kb, "重启 服务")

    assert results
    explanation = results[0]["explanation"]
    assert explanation["matched_by"] == ["generation_index"]
    assert explanation["keyword_score"] == results[0]["score"]
    assert "重启" in explanation["matched_terms"]


@pytest.mark.django_db
def test_answer_without_model_falls_back_with_citations():
    from apps.opspilot.services.wiki.retrieval_service import answer

    kb = _kb()
    _seed(kb)
    out = answer(kb, "如何重启服务", llm_model_id=None)
    assert out["citations"], "should cite something"
    assert "systemctl" in out["answer"] or "重启" in out["answer"]
    assert out["citations"][0]["explanation"]["matched_by"] == ["generation_index"]
    assert out["mode"] == "fallback"
    assert out["warning_code"] == "wiki_answer_fallback"
    assert "未使用模型" in out["answer"]
    assert len(out["contexts"][0]["snippet"]) > 0


@pytest.mark.django_db
def test_answer_with_missing_model_falls_back_with_explanation():
    from apps.opspilot.services.wiki.retrieval_service import answer

    kb = _kb()
    _seed(kb)

    out = answer(kb, "如何重启服务", llm_model_id=999999)

    assert out["citations"]
    assert out["citations"][0]["explanation"]["matched_by"] == ["generation_index"]
    assert "重启" in out["answer"]
    assert out["mode"] == "fallback"


@pytest.mark.django_db
def test_answer_empty_kb():
    from apps.opspilot.services.wiki.retrieval_service import answer

    kb = _kb()
    out = answer(kb, "anything", llm_model_id=None)
    assert out["citations"] == []
    assert out["mode"] == "empty"


@pytest.mark.django_db
def test_answer_uses_hybrid_when_embed_provider_configured():
    from apps.opspilot.models import EmbedProvider
    from apps.opspilot.services.wiki.page_service import create_manual_page
    from apps.opspilot.services.wiki.retrieval_service import answer

    kb = _kb()
    provider = EmbedProvider.objects.create(name="embed", model="embed-model")
    kb.embed_provider = provider
    kb.save(update_fields=["embed_provider"])
    restart = create_manual_page(
        kb,
        page_type="concept",
        title="重启服务",
        body="使用 systemctl restart nginx 重启服务。",
        created_by="u",
    )
    flow = create_manual_page(
        kb,
        page_type="concept",
        title="重启流程",
        body="重启前先摘流量再重启。",
        created_by="u",
    )
    restart.current_version.embedding = [0.0, 1.0]
    restart.current_version.save(update_fields=["embedding"])
    flow.current_version.embedding = [1.0, 0.0]
    flow.current_version.save(update_fields=["embedding"])

    out = answer(kb, "重启", llm_model_id=None, embed_fn=lambda texts: [[0.9, 0.1] for _ in texts])
    assert out["citations"]
    assert "vector" in (out["citations"][0].get("explanation") or {}).get("matched_by", [])
    assert out["citations"][0]["title"] == "重启流程"


@pytest.mark.django_db
def test_answer_keeps_keyword_when_retrieval_mode_forced():
    from apps.opspilot.models import EmbedProvider
    from apps.opspilot.services.wiki.retrieval_service import answer

    kb = _kb()
    provider = EmbedProvider.objects.create(name="embed", model="embed-model")
    kb.embed_provider = provider
    kb.save(update_fields=["embed_provider"])
    _seed(kb)

    out = answer(
        kb,
        "如何重启服务",
        llm_model_id=None,
        retrieval_mode="keyword",
        embed_fn=lambda texts: pytest.fail("forced keyword should skip embedding"),
    )
    assert out["citations"]
    assert "vector" not in (out["citations"][0].get("explanation") or {}).get("matched_by", [])


@pytest.mark.django_db
def test_search_snippet_window_covers_long_body():
    from apps.opspilot.services.wiki.page_service import create_manual_page
    from apps.opspilot.services.wiki.retrieval_service import search

    kb = _kb()
    body = ("前言段落。" * 80) + "使用 systemctl restart nginx 重启服务。" + ("尾部说明。" * 80)
    create_manual_page(kb, page_type="concept", title="重启服务", body=body, created_by="u")
    results = search(kb, "systemctl restart")
    assert results
    snippet = results[0]["snippet"]
    assert "systemctl restart nginx" in snippet
    assert len(snippet) > 300


@pytest.mark.django_db
def test_stream_answer_fallback_events():
    from apps.opspilot.services.wiki.retrieval_service import stream_answer

    kb = _kb()
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
    from apps.opspilot.services.wiki.retrieval_service import stream_answer

    kb = _kb()
    _seed(kb)

    class FakeLLM:
        openai_api_base = "http://example.invalid"
        openai_api_key = "k"
        model_name = "fake"

    class FakeQuerySet:
        def get(self, **_kwargs):
            return FakeLLM()

    monkeypatch.setattr(
        "apps.opspilot.services.wiki.retrieval_service.LLMModel.objects.select_related",
        lambda *_args, **_kwargs: FakeQuerySet(),
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
        kb = _kb()
        _seed(kb)
        s = api_client.post(f"/api/v1/opspilot/wiki_mgmt/knowledge_base/{kb.id}/search/", {"query": "重启 服务"}, format="json")
        assert s.status_code == 200, s.content
        assert any("重启" in r["title"] for r in s.json()["data"])

        q = api_client.post(f"/api/v1/opspilot/wiki_mgmt/knowledge_base/{kb.id}/qa/", {"query": "如何重启服务"}, format="json")
        assert q.status_code == 200, q.content
        payload = q.json()["data"]
        assert payload["citations"]
        assert payload["mode"] == "fallback"

    def test_search_endpoint_uses_hybrid_when_embed_configured(self, api_client, monkeypatch):
        from apps.opspilot.models import EmbedProvider
        from apps.opspilot.services.wiki import retrieval_service as retrieval_mod
        from apps.opspilot.services.wiki.page_service import create_manual_page

        kb = _kb()
        provider = EmbedProvider.objects.create(name="embed", model="embed-model")
        kb.embed_provider = provider
        kb.save(update_fields=["embed_provider"])
        restart = create_manual_page(kb, page_type="concept", title="重启服务", body="使用 systemctl restart nginx 重启服务。", created_by="u")
        flow = create_manual_page(kb, page_type="concept", title="重启流程", body="重启前先摘流量再重启。", created_by="u")
        restart.current_version.embedding = [0.0, 1.0]
        restart.current_version.save(update_fields=["embedding"])
        flow.current_version.embedding = [1.0, 0.0]
        flow.current_version.save(update_fields=["embedding"])

        def stub(texts, _provider=None):
            return [[0.9, 0.1] for _ in texts]

        monkeypatch.setattr(retrieval_mod, "embed_texts_cached", stub)
        response = api_client.post(
            f"/api/v1/opspilot/wiki_mgmt/knowledge_base/{kb.id}/search/",
            {"query": "重启"},
            format="json",
        )
        assert response.status_code == 200, response.content
        payload = response.json()["data"]
        assert payload
        assert payload[0]["title"] == "重启流程"
        assert "vector" in (payload[0].get("explanation") or {}).get("matched_by", [])

    def test_qa_stream_endpoint(self, api_client):
        kb = _kb()
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


def test_index_score_prefers_term_coverage_over_repeated_tokens():
    from types import SimpleNamespace

    from apps.opspilot.services.wiki.retrieval_service import _index_score, _tokenize

    query = "服务器分区扩容"
    terms = _tokenize(query)
    n_docs = 20
    df = {term: 1 for term in terms}
    df["服务"] = 18
    df["务器"] = 16
    spam = SimpleNamespace(
        title="IT资源使用与运维管理规范",
        aliases=["服务", "服务器"],
        tags=["服务"],
        headings=["服务"] * 12,
        keywords=["服务"] * 32,
        entities=[],
        summary="服务服务服务",
        page_type="Policy",
        normalized_title="it资源使用与运维管理规范",
        search_text="",
    )
    target = SimpleNamespace(
        title="腾讯云虚拟机手动扩容磁盘",
        aliases=["磁盘扩容", "分区扩大"],
        tags=[],
        headings=["扩容分区"],
        keywords=["分区", "扩容", "数据盘"],
        entities=[],
        summary="数据盘空间不足时扩容分区",
        page_type="How-to",
        normalized_title="腾讯云虚拟机手动扩容磁盘",
        search_text="",
    )
    spam_score, _ = _index_score(spam, terms, query, idf=df, n_docs=n_docs)
    target_score, _ = _index_score(target, terms, query, idf=df, n_docs=n_docs)
    assert target_score > spam_score


def test_index_score_prefers_docs_covering_query_terms():
    from types import SimpleNamespace

    from apps.opspilot.services.wiki.retrieval_service import _index_score, _tokenize

    query = "VPN使用有什么制度要求？"
    terms = _tokenize(query)
    policy = SimpleNamespace(
        title="嘉为公司用户VPN使用管理规范",
        aliases=[],
        tags=["VPN"],
        headings=[],
        keywords=["VPN", "制度"],
        entities=[],
        summary="VPN使用管理制度要求",
        page_type="Policy",
        normalized_title="嘉为公司用户vpn使用管理规范",
    )
    handbook = SimpleNamespace(
        title="嘉为公司用户VPN使用手册",
        aliases=[],
        tags=["VPN"],
        headings=[],
        keywords=["VPN"],
        entities=[],
        summary="VPN客户端安装与使用步骤",
        page_type="User Guide",
        normalized_title="嘉为公司用户vpn使用手册",
    )
    account = SimpleNamespace(
        title="嘉为公司账号安全性使用规范",
        aliases=[],
        tags=["账号"],
        headings=[],
        keywords=["账号", "规范"],
        entities=[],
        summary="账号安全使用规范",
        page_type="Policy",
        normalized_title="嘉为公司账号安全性使用规范",
    )
    policy_score, _ = _index_score(policy, terms, query)
    handbook_score, _ = _index_score(handbook, terms, query)
    account_score, _ = _index_score(account, terms, query)
    assert policy_score > handbook_score
    assert policy_score > account_score


def test_adapt_context_k_exact_title_keeps_one_or_two():
    """Strong exact-title head should shrink to 1-2 contexts, not max_k."""
    from apps.opspilot.services.wiki.retrieval_service import _adapt_context_k

    hits = [
        {
            "id": 1,
            "title": "exact",
            "score": 220,
            "explanation": {"exact_title_or_alias": True, "matched_terms": ["exact"]},
        },
        {
            "id": 2,
            "title": "weak-a",
            "score": 40,
            "explanation": {"exact_title_or_alias": False, "matched_terms": ["a"]},
        },
        {
            "id": 3,
            "title": "weak-b",
            "score": 35,
            "explanation": {"exact_title_or_alias": False, "matched_terms": ["b"]},
        },
        {
            "id": 4,
            "title": "weak-c",
            "score": 30,
            "explanation": {"exact_title_or_alias": False, "matched_terms": ["c"]},
        },
        {
            "id": 5,
            "title": "weak-d",
            "score": 25,
            "explanation": {"exact_title_or_alias": False, "matched_terms": ["d"]},
        },
    ]
    kept = _adapt_context_k(hits, max_k=5)
    assert 1 <= len(kept) <= 2
    assert kept[0]["id"] == 1
    assert [h["id"] for h in kept] == sorted((h["id"] for h in kept), key=lambda i: -{1: 220, 2: 40, 3: 35, 4: 30, 5: 25}[i])


def test_adapt_context_k_flat_scores_keep_up_to_max_k():
    """Similar/strong scores should be allowed to fill max_k."""
    from apps.opspilot.services.wiki.retrieval_service import _adapt_context_k

    hits = [
        {"id": i, "title": f"t{i}", "score": 110 - i, "explanation": {"exact_title_or_alias": False, "matched_terms": ["x", "y"]}}
        for i in range(1, 6)
    ]
    kept = _adapt_context_k(hits, max_k=5)
    assert len(kept) == 5
    assert [h["id"] for h in kept] == [1, 2, 3, 4, 5]


def test_adapt_context_k_strong_top_with_close_second_then_gap():
    """Keep a close second under a strong top, then stop on a large gap."""
    from apps.opspilot.services.wiki.retrieval_service import _adapt_context_k

    hits = [
        {"id": 1, "title": "top", "score": 200, "explanation": {"exact_title_or_alias": True}},
        {"id": 2, "title": "near", "score": 150, "explanation": {"exact_title_or_alias": False, "matched_terms": ["a", "b"]}},
        {"id": 3, "title": "far", "score": 50, "explanation": {"exact_title_or_alias": False, "matched_terms": ["a"]}},
        {"id": 4, "title": "far2", "score": 40, "explanation": {"exact_title_or_alias": False, "matched_terms": ["b"]}},
    ]
    kept = _adapt_context_k(hits, max_k=5)
    assert [h["id"] for h in kept] == [1, 2]


def test_is_relevant_hit_keeps_single_cjk_term_in_title():
    """中文短查询常只有 1 个 matched_term，且 generation index 标题分远低于 100。"""
    from apps.opspilot.services.wiki.retrieval_service import _is_relevant_hit

    hit = {
        "kind": "page",
        "id": 1,
        "title": "重启服务",
        "score": 12,
        "explanation": {
            "matched_by": ["keyword"],
            "matched_terms": ["重启"],
            "exact_title_or_alias": False,
        },
    }
    assert _is_relevant_hit(hit) is True


def test_is_relevant_hit_keeps_single_product_term_in_title():
    from apps.opspilot.services.wiki.retrieval_service import _is_relevant_hit

    hit = {
        "kind": "page",
        "id": 1,
        "title": "嘉为公司用户VPN使用管理规范",
        "score": 12,
        "explanation": {
            "matched_by": ["generation_index"],
            "matched_terms": ["vpn"],
            "exact_title_or_alias": False,
        },
    }
    assert _is_relevant_hit(hit) is True


def test_is_relevant_hit_drops_generic_single_term():
    from apps.opspilot.services.wiki.retrieval_service import _is_relevant_hit

    hit = {
        "kind": "page",
        "id": 1,
        "title": "产品介绍",
        "score": 8,
        "explanation": {
            "matched_by": ["keyword"],
            "matched_terms": ["知识"],
            "exact_title_or_alias": False,
        },
    }
    assert _is_relevant_hit(hit) is False


def test_is_relevant_hit_relative_peak_does_not_keep_generic_only():
    from apps.opspilot.services.wiki.retrieval_service import _is_relevant_hit

    hit = {
        "kind": "page",
        "id": 1,
        "title": "产品介绍",
        "score": 8,
        "explanation": {
            "matched_by": ["keyword"],
            "matched_terms": ["知识"],
            "exact_title_or_alias": False,
        },
    }
    assert _is_relevant_hit(hit, top_score=8) is False


def test_is_relevant_hit_keeps_exact_title_despite_generic_term():
    from apps.opspilot.services.wiki.retrieval_service import _is_relevant_hit

    hit = {
        "kind": "page",
        "id": 1,
        "title": "知识",
        "score": 5,
        "explanation": {
            "matched_by": ["generation_index"],
            "matched_terms": ["知识"],
            "exact_title_or_alias": True,
        },
    }
    assert _is_relevant_hit(hit) is True


def test_is_relevant_hit_keeps_strong_score_without_terms():
    from apps.opspilot.services.wiki.retrieval_service import _is_relevant_hit

    hit = {
        "kind": "page",
        "id": 1,
        "title": "x",
        "score": 120,
        "explanation": {"matched_by": ["keyword"], "matched_terms": []},
    }
    assert _is_relevant_hit(hit) is True


def test_is_relevant_hit_keeps_vector_recall_without_keyword_terms():
    from apps.opspilot.services.wiki.retrieval_service import _is_relevant_hit

    hit = {
        "kind": "page",
        "id": 1,
        "title": "会议室预定失败或按钮灰色处理",
        "score": 0.69,
        "explanation": {
            "matched_by": ["vector"],
            "matched_terms": [],
            "semantic_rank": 1,
            "vector_score": 0.69,
        },
    }
    assert _is_relevant_hit(hit) is True


def test_is_relevant_hit_keeps_graph_without_matched_terms():
    from apps.opspilot.services.wiki.retrieval_service import _is_relevant_hit

    hit = {
        "kind": "page",
        "id": 2,
        "title": "作业平台",
        "score": 9,
        "explanation": {
            "matched_by": ["graph"],
            "graph_hop": 1,
            "graph_source_id": 1,
            "graph_source_title": "蓝鲸平台",
            "relation_type": "reference",
        },
    }
    assert _is_relevant_hit(hit) is True


def test_is_relevant_hit_drops_body_only_weak_single_term():
    from apps.opspilot.services.wiki.retrieval_service import _is_relevant_hit

    hit = {
        "kind": "page",
        "id": 1,
        "title": "磁盘清理",
        "score": 2,
        "explanation": {
            "matched_by": ["keyword"],
            "matched_terms": ["nginx"],
            "exact_title_or_alias": False,
        },
    }
    assert _is_relevant_hit(hit) is False


def test_is_relevant_hit_keeps_body_only_distinctive_term_when_score_meets_weak():
    from apps.opspilot.services.wiki.retrieval_service import _is_relevant_hit

    hit = {
        "kind": "page",
        "id": 1,
        "title": "磁盘清理",
        "score": 64,
        "explanation": {
            "matched_by": ["keyword"],
            "matched_terms": ["nginx"],
            "exact_title_or_alias": False,
        },
    }
    assert _is_relevant_hit(hit) is True


def test_filter_relevant_contexts_keeps_graph_aligned_to_relevant_seed():
    from apps.opspilot.services.wiki.retrieval_service import _filter_relevant_contexts

    generic = {
        "kind": "page",
        "id": 3,
        "title": "产品介绍",
        "score": 8,
        "explanation": {
            "matched_by": ["keyword"],
            "matched_terms": ["知识"],
            "exact_title_or_alias": False,
        },
    }
    seed = {
        "kind": "page",
        "id": 1,
        "title": "蓝鲸平台",
        "score": 36,
        "explanation": {
            "matched_by": ["keyword"],
            "matched_terms": ["蓝鲸"],
            "exact_title_or_alias": False,
        },
    }
    graph = {
        "kind": "page",
        "id": 2,
        "title": "作业平台",
        "score": 27,
        "explanation": {
            "matched_by": ["graph"],
            "graph_hop": 1,
            "graph_source_id": 1,
            "graph_source_title": "蓝鲸平台",
            "relation_type": "reference",
        },
    }
    kept = _filter_relevant_contexts([generic, seed, graph])
    assert [hit["id"] for hit in kept] == [1, 2]


def test_filter_relevant_contexts_drops_graph_from_irrelevant_seed():
    from apps.opspilot.services.wiki.retrieval_service import _filter_relevant_contexts

    weak = {
        "kind": "page",
        "id": 1,
        "title": "产品介绍",
        "score": 8,
        "explanation": {
            "matched_by": ["keyword"],
            "matched_terms": ["知识"],
            "exact_title_or_alias": False,
        },
    }
    graph = {
        "kind": "page",
        "id": 2,
        "title": "邻页",
        "score": 6,
        "explanation": {
            "matched_by": ["graph"],
            "graph_hop": 1,
            "graph_source_id": 1,
            "graph_source_title": "产品介绍",
        },
    }
    assert _filter_relevant_contexts([weak, graph]) == []


def test_filter_relevant_contexts_keeps_second_hop_aligned_to_first_hop():
    from apps.opspilot.services.wiki.retrieval_service import _filter_relevant_contexts

    seed = {
        "kind": "page",
        "id": 1,
        "title": "蓝鲸平台",
        "score": 36,
        "explanation": {
            "matched_by": ["keyword"],
            "matched_terms": ["蓝鲸"],
            "exact_title_or_alias": False,
        },
    }
    hop1 = {
        "kind": "page",
        "id": 2,
        "title": "作业平台",
        "score": 27,
        "explanation": {
            "matched_by": ["graph"],
            "graph_hop": 1,
            "graph_source_id": 1,
            "graph_source_title": "蓝鲸平台",
        },
    }
    hop2 = {
        "kind": "page",
        "id": 3,
        "title": "节点管理",
        "score": 20.25,
        "explanation": {
            "matched_by": ["graph"],
            "graph_hop": 2,
            "graph_source_id": 2,
            "graph_source_title": "作业平台",
        },
    }
    kept = _filter_relevant_contexts([hop2, seed, hop1])
    assert [hit["id"] for hit in kept] == [3, 1, 2]


def test_filter_relevant_contexts_empty_and_none():
    from apps.opspilot.services.wiki.retrieval_service import _filter_relevant_contexts

    assert _filter_relevant_contexts([]) == []
    assert _filter_relevant_contexts(None) == []
