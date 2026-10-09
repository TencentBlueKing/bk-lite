import pytest


def _kb(name="kb"):
    from apps.opspilot.models import WikiKnowledgeBase
    from apps.opspilot.services.wiki.structure_service import bootstrap_knowledge_base

    kb = WikiKnowledgeBase.objects.create(name=name, team=[1], purpose_md="# Purpose", schema_md="# Schema")
    bootstrap_knowledge_base(kb, operator="u")
    kb.refresh_from_db()
    return kb


def _page(kb, title, body):
    from apps.opspilot.services.wiki.page_service import create_manual_page

    return create_manual_page(kb, page_type="concept", title=title, body=body, created_by="u")


def _relate(from_page, to_page, relation_type="reference", weight=1.0):
    from apps.opspilot.models import PageRelation, WikiKnowledgeBase

    kb = WikiKnowledgeBase.objects.select_related("active_generation").get(pk=from_page.knowledge_base_id)
    return PageRelation.objects.create(
        from_page=from_page,
        to_page=to_page,
        relation_type=relation_type,
        weight=weight,
        generation_id=kb.active_generation_id,
    )


@pytest.mark.django_db
def test_build_context_merges_across_kbs_and_numbers_citations():
    from apps.opspilot.services.wiki.wiki_context_service import build_context

    kb1, kb2 = _kb("运维库"), _kb("产品库")
    _page(kb1, "重启服务", "执行 systemctl restart 重启服务")
    _page(kb2, "重启流程", "重启前先摘流量再重启")

    out = build_context([kb1.id, kb2.id], "重启服务", top_k=5)

    assert len(out["citations"]) == 2
    assert out["citations"][0]["n"] == 1
    # 不同知识库的命中都被纳入,且上下文带来源标注
    titles = {c["title"] for c in out["citations"]}
    assert {"重启服务", "重启流程"} <= titles
    assert "知识库:" in out["context"]


@pytest.mark.django_db
def test_build_context_empty_when_no_match():
    from apps.opspilot.services.wiki.wiki_context_service import build_context

    kb = _kb()
    _page(kb, "网络配置", "配置静态路由")
    out = build_context([kb.id], "数据库备份")
    assert out["citations"] == [] and out["context"] == ""


@pytest.mark.django_db
def test_build_context_expands_one_hop_graph_neighbors():
    from apps.opspilot.services.wiki.wiki_context_service import build_context

    kb = _kb()
    seed = _page(kb, "蓝鲸平台", "蓝鲸平台提供统一运维入口")
    related = _page(kb, "作业平台", "作业平台负责批量脚本执行")
    _relate(seed, related, relation_type="reference", weight=2.0)

    out = build_context([kb.id], "统一运维入口", top_k=3, graph_hops=1)

    titles = [item["title"] for item in out["citations"]]
    assert titles == ["蓝鲸平台", "作业平台"]
    assert out["citations"][1]["explanation"]["matched_by"] == ["graph"]
    assert out["citations"][1]["explanation"]["graph_source_title"] == "蓝鲸平台"


def test_select_hits_direct_first_keeps_graph_from_displacing_direct_hits():
    from apps.opspilot.services.wiki.wiki_context_service import _select_hits_direct_first

    hits = [
        {"id": 1, "score": 300, "explanation": {"matched_by": ["keyword"]}},
        {"id": 2, "score": 160, "explanation": {"matched_by": ["generation_index"]}},
        {"id": 3, "score": 225, "explanation": {"matched_by": ["graph"]}},
    ]
    selected = _select_hits_direct_first(hits, 2)
    assert [hit["id"] for hit in selected] == [1, 2]


def test_select_hits_direct_first_fills_remaining_slots_with_graph():
    from apps.opspilot.services.wiki.wiki_context_service import _select_hits_direct_first

    hits = [
        {"id": 1, "score": 80, "explanation": {"matched_by": ["keyword"]}},
        {"id": 3, "score": 60, "explanation": {"matched_by": ["graph"]}},
    ]
    selected = _select_hits_direct_first(hits, 2)
    assert [hit["id"] for hit in selected] == [1, 3]


@pytest.mark.django_db
def test_build_context_respects_token_budget():
    from apps.opspilot.services.wiki.wiki_budget_service import WikiBudgetExceeded
    from apps.opspilot.services.wiki.wiki_context_service import build_context

    kb = _kb()
    _page(kb, "重启主流程", "重启服务 " + "先摘流量再重启 " * 20)
    _page(kb, "重启补充说明", "重启服务 " + "观察指标确认恢复 " * 20)

    with pytest.raises(WikiBudgetExceeded) as exc:
        build_context([kb.id], "重启服务", top_k=5, token_budget=32)

    details = exc.value.details
    assert details["truncated"] is True
    assert details["token_budget"] == 32
    assert details["used_tokens"] <= 32


@pytest.mark.django_db
def test_build_context_uses_derived_knowledge_budget_not_legacy_8k():
    from apps.opspilot.models import LLMModel
    from apps.opspilot.services.wiki.wiki_context_service import build_context

    kb = _kb()
    _page(kb, "重启主流程", "重启服务")
    model = LLMModel.objects.create(name="qa-window", model="gpt-4")

    out = build_context([kb.id], "重启服务", top_k=5, llm_model_id=model.pk, graph_hops=0)

    assert out["budget"]["configured_token_budget"] == 27_900
    assert out["budget"]["effective_token_budget"] == 27_900
    assert out["budget"]["token_budget"] <= 27_900


@pytest.mark.django_db
def test_build_context_requested_budget_cannot_exceed_derived_cap():
    from apps.opspilot.models import LLMModel
    from apps.opspilot.services.wiki.wiki_context_service import build_context

    kb = _kb()
    _page(kb, "重启主流程", "重启服务")
    model = LLMModel.objects.create(name="qa-window-cap", model="gpt-4")

    out = build_context([kb.id], "重启服务", top_k=5, token_budget=999_999, llm_model_id=model.pk, graph_hops=0)

    assert out["budget"]["effective_token_budget"] == 27_900
    assert out["budget"]["token_budget"] <= 27_900


@pytest.mark.django_db
def test_build_context_can_use_hybrid_search_explanations():
    from apps.opspilot.services.wiki.wiki_context_service import build_context

    kb = _kb()
    restart = _page(kb, "重启服务", "使用 systemctl restart 重启")
    semantic_page = _page(kb, "重启流程", "重启前先摘流量再重启")
    restart.current_version.embedding = [0.0, 1.0]
    restart.current_version.save(update_fields=["embedding"])
    semantic_page.current_version.embedding = [1.0, 0.0]
    semantic_page.current_version.save(update_fields=["embedding"])

    out = build_context(
        [kb.id],
        "重启",
        top_k=2,
        retrieval_mode="hybrid",
        embed_fn=lambda texts: [[0.9, 0.1] for _ in texts],
        graph_hops=0,
    )

    assert out["citations"][0]["id"] == semantic_page.id
    explanation = out["citations"][0]["explanation"]
    assert "vector" in explanation["matched_by"]
    assert explanation["fusion"] == "rrf"
    assert explanation["semantic_rank"] == 1


@pytest.mark.django_db
def test_build_context_rejects_chunk_search_on_generation_kb():
    from apps.opspilot.services.wiki.active_generation_query_service import ActiveGenerationReadError
    from apps.opspilot.services.wiki.wiki_context_service import build_context

    kb = _kb()
    _page(kb, "服务操作手册", "# 重启\nsystemctl restart\n# 备份\nbackup db")

    with pytest.raises(ActiveGenerationReadError) as exc:
        build_context(
            [kb.id],
            "重启",
            top_k=2,
            retrieval_mode="chunk",
            graph_hops=0,
        )

    assert exc.value.code == "chunk_retrieval_not_generation_safe"


@pytest.mark.django_db
class TestContextView:
    def test_context_endpoint(self, api_client):
        kb = _kb()
        _page(kb, "重启服务", "systemctl restart")
        r = api_client.post(
            "/api/v1/opspilot/wiki_mgmt/knowledge_base/context/",
            {"kb_ids": [kb.id], "query": "重启服务"},
            format="json",
        )
        assert r.status_code == 200
        assert r.json()["data"]["citations"][0]["title"] == "重启服务"

    def test_context_endpoint_passes_budget_and_graph_options(self, api_client):
        kb = _kb()
        seed = _page(kb, "蓝鲸平台", "蓝鲸平台提供统一运维入口")
        related = _page(kb, "作业平台", "作业平台负责批量脚本执行")
        _relate(seed, related)

        r = api_client.post(
            "/api/v1/opspilot/wiki_mgmt/knowledge_base/context/",
            {"kb_ids": [kb.id], "query": "统一运维入口", "top_k": 3, "graph_hops": 1, "token_budget": 128},
            format="json",
        )

        assert r.status_code == 200
        data = r.json()["data"]
        assert data["budget"]["token_budget"] == 128
        assert [item["title"] for item in data["citations"]] == ["蓝鲸平台", "作业平台"]

    def test_context_endpoint_accepts_retrieval_mode(self, api_client):
        kb = _kb()
        _page(kb, "重启服务", "systemctl restart 重启")

        r = api_client.post(
            "/api/v1/opspilot/wiki_mgmt/knowledge_base/context/",
            {"kb_ids": [kb.id], "query": "重启", "retrieval_mode": "hybrid", "graph_hops": 0},
            format="json",
        )

        assert r.status_code == 200
        data = r.json()["data"]
        assert data["retrieval_mode"] == "hybrid"
        matched_by = data["citations"][0]["explanation"]["matched_by"]
        assert "keyword" in matched_by or "generation_index" in matched_by

    def test_context_endpoint_rejects_chunk_retrieval_mode(self, api_client):
        kb = _kb()
        _page(kb, "服务操作手册", "# 重启\nsystemctl restart")

        r = api_client.post(
            "/api/v1/opspilot/wiki_mgmt/knowledge_base/context/",
            {"kb_ids": [kb.id], "query": "重启", "retrieval_mode": "chunk", "graph_hops": 0},
            format="json",
        )

        assert r.status_code == 422
        body = r.json()
        assert body["result"] is False
        assert body["code"] == "chunk_retrieval_not_generation_safe"


NEAR_IMAGE = "wiki/media/1/9/bbbbbbbbbbbbbbbb.png"
FAR_IMAGE = "wiki/media/1/9/aaaaaaaaaaaaaaaa.png"
PAGE_IMAGE = "wiki/media/1/pages/cccccccccccccccc.png"
FLOW_IMAGE = "wiki/media/1/9/ffffffffffffffff.png"


@pytest.mark.django_db
def test_build_context_includes_page_body_images():
    from apps.opspilot.services.wiki.wiki_context_service import build_context

    kb = _kb()
    _page(kb, "重启服务", f"执行重启\n![步骤]({PAGE_IMAGE})\n完成")

    out = build_context([kb.id], "重启服务", top_k=5, graph_hops=0)

    assert "附图" in out["context"]
    assert PAGE_IMAGE in out["context"] or "![" in out["context"]
    assert out["hits"][0]["images"]


@pytest.mark.django_db
def test_build_context_includes_material_images_in_snippet_window_only():
    from apps.opspilot.models import Material, PageEvidence
    from apps.opspilot.services.wiki.wiki_context_service import build_context

    kb = _kb()
    page = _page(kb, "登录流程", "在登录页输入账号后点击确认")
    material = Material.objects.create(
        knowledge_base=kb,
        name="手册.pdf",
        material_type="text",
        text_content=(f"![远]({FAR_IMAGE})\n" + ("x" * 500) + f"\n在登录页输入账号后点击确认\n![近]({NEAR_IMAGE})\n"),
    )
    PageEvidence.objects.create(page=page, material=material, locator="")

    out = build_context([kb.id], "登录页输入账号", top_k=5, graph_hops=0)

    assert "bbbbbbbbbbbbbbbb" in out["context"]
    assert "aaaaaaaaaaaaaaaa" not in out["context"]


@pytest.mark.django_db
def test_build_context_loads_images_from_parsed_markdown_not_text_content(monkeypatch):
    from apps.opspilot.models import Material, MaterialVersion, PageEvidence
    from apps.opspilot.services.wiki import wiki_context_service

    kb = _kb()
    page = _page(kb, "堡垒机规范", "版本记录表\n版本 1.0")
    material = Material.objects.create(
        knowledge_base=kb,
        name="嘉为堡垒机使用管理规范.docx",
        material_type="file",
        text_content="",
    )
    version = MaterialVersion.objects.create(
        material=material,
        content_locator=f"wiki/parsed/{kb.id}/{material.id}/digest.md",
        content_hash="digest",
    )
    material.current_version = version
    material.save(update_fields=["current_version", "updated_at"])
    PageEvidence.objects.create(page=page, material=material, locator="")

    parsed = "版本记录表\n版本 1.0\n" + ("y" * 500) + f"\n9. 堡垒机资源申请流程图:\n![流程图]({FLOW_IMAGE})\n"
    monkeypatch.setattr(
        wiki_context_service,
        "load_parsed_markdown",
        lambda material, for_display=False: parsed,
    )

    out = wiki_context_service.build_context([kb.id], "堡垒机资源申请流程图", top_k=5, graph_hops=0)

    assert "附图" in out["context"]
    assert "ffffffffffffffff" in out["context"]
    assert out["hits"][0]["images"]


@pytest.mark.django_db
def test_build_context_attaches_query_near_material_images_when_snippet_elsewhere():
    from apps.opspilot.models import Material, PageEvidence
    from apps.opspilot.services.wiki.wiki_context_service import build_context

    kb = _kb()
    # 页面正文只有版本表，检索 snippet 落在这里；流程图在来源 md 后半段。
    page = _page(kb, "嘉为堡垒机使用管理规范", "版本记录表\n版本号 V1.0\n修订说明 初稿")
    material = Material.objects.create(
        knowledge_base=kb,
        name="规范.pdf",
        material_type="text",
        text_content=("版本记录表\n版本号 V1.0\n修订说明 初稿\n" + ("z" * 500) + f"\n9. 堡垒机资源申请流程图:\n![申请流程]({FLOW_IMAGE})\n"),
    )
    PageEvidence.objects.create(page=page, material=material, locator="")

    out = build_context([kb.id], "堡垒机资源申请流程图", top_k=5, graph_hops=0)

    assert "附图" in out["context"]
    assert "ffffffffffffffff" in out["context"]


@pytest.mark.django_db
def test_build_context_page_body_images_use_nearby_caption_as_alt():
    from apps.opspilot.services.wiki.wiki_context_service import build_context

    kb = _kb()
    # 正文前半是版本表噪声；流程图在后半段且 Markdown alt 为空。
    body = "版本记录表\n堡垒机 流程\n" + ("表。" * 200) + f"\n## 四、堡垒机管理流程\n9. 堡垒机资源申请流程图:\n![]({FLOW_IMAGE})\n"
    _page(kb, "嘉为堡垒机使用管理规范", body)

    out = build_context([kb.id], "堡垒机资源申请流程", top_k=5, graph_hops=0)

    assert "资源申请流程图" in (out["hits"][0].get("snippet") or "")
    assert out["hits"][0]["images"]
    assert any("堡垒机资源申请流程图" in image for image in out["hits"][0]["images"])
    assert "ffffffffffffffff" in out["context"]
    assert "禁止改写为「无法展示」" in out["context"]
    assert "/api/proxy/opspilot/wiki_mgmt/media/" in out["context"]


def test_wiki_rules_require_emitting_markdown_images():
    from apps.opspilot.services.wiki.wiki_context_service import FORCE_WIKI_RULES, NON_FORCE_WIKI_RULES

    for rules in (FORCE_WIKI_RULES, NON_FORCE_WIKI_RULES):
        assert "原样输出" in rules
        assert "无法直接展示" in rules


def test_truncate_context_line_keeps_images_before_shrinking_snippet_away():
    from apps.opspilot.services.wiki import wiki_context_service as svc

    hit = {
        "title": "规范",
        "kb_name": "kb",
        "snippet": "正文" * 400,
        "images": [f"![流程图](/api/proxy/opspilot/wiki_mgmt/media/?locator={FLOW_IMAGE})"],
        "directory_breadcrumb": [],
        "heading_path": "",
    }
    # 预算只够前缀 + 少量正文 + 附图，不应直接丢掉附图。
    line = svc._truncate_context_line(1, hit, token_budget=180)
    assert "流程图" in line
    assert "附图" in line
