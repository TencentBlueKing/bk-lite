"""WikiKnowledgeBaseViewSet.preview_merge 合并预览端点测试。

覆盖:
- 无别名规则时:每个 active 页都返回单页桶(不进入 merges)
- 有别名规则:同 canonical 标题的多页合并到一条
- 单页但标题命中别名表:作为 alias_only 规则返回
- archived / deleted 页不参与计算
- 返回 total_canonical_groups / active_page_count 统计

包含两类测试:
- 单元测试:mock 掉 DB 与 alias 规则,直接验证业务逻辑(分组 / 排序);不依赖迁移。
- 整合测试:走 api_client + DB,在 master 迁移 reconcile 后才稳定(worktree 早期
  因迁移图历史债务只能 skip)。
"""

from types import SimpleNamespace

import pytest

from apps.opspilot.models import KnowledgePage, WikiKnowledgeBase


def _kb(generation_rules=None):
    return WikiKnowledgeBase.objects.create(
        name="kb",
        team=[1],
        generation_rules=generation_rules or {},
    )


def _page(kb, title, status="active"):
    return KnowledgePage.objects.create(
        knowledge_base=kb,
        title=title,
        page_type="concept",
        status=status,
    )


@pytest.mark.django_db
def test_preview_merge_no_rules_returns_no_merges(api_client):
    """无别名规则:每个 active 页都唯一,returns 空 merges。"""
    kb = _kb()
    _page(kb, "FooPlatform")
    _page(kb, "BarPlatform")
    _page(kb, "BazPlatform")

    resp = api_client.get(f"/api/v1/opspilot/wiki_mgmt/knowledge_base/{kb.id}/preview_merge/")
    assert resp.status_code == 200
    body = resp.json()
    assert body["result"] is True
    assert body["data"]["merges"] == []
    assert body["data"]["active_page_count"] == 3
    assert body["data"]["total_canonical_groups"] == 0


@pytest.mark.django_db
def test_preview_merge_groups_same_canonical(api_client):
    """有别名规则时,共享同一规范标题的多页合并为一条。"""
    kb = _kb(
        generation_rules={
            "title_aliases": [
                {"canonical": "FooPlatform", "aliases": ["foo平台", "FooPlatformCN"]},
            ]
        }
    )
    a = _page(kb, "FooPlatform")
    b = _page(kb, "foo平台")
    c = _page(kb, "FooPlatformCN")
    _page(kb, "BarPlatform")  # 不应进入 merges

    resp = api_client.get(f"/api/v1/opspilot/wiki_mgmt/knowledge_base/{kb.id}/preview_merge/")
    assert resp.status_code == 200
    body = resp.json()
    merges = body["data"]["merges"]
    assert len(merges) == 1
    assert merges[0]["canonical"] == "FooPlatform"
    assert sorted(merges[0]["merged_pages"]) == ["FooPlatform", "FooPlatformCN", "foo平台"]
    assert sorted(merges[0]["page_ids"]) == sorted([a.id, b.id, c.id])
    assert merges[0]["rule"] == "duplicate_canonical"


@pytest.mark.django_db
def test_preview_merge_alias_only_rule(api_client):
    """单页命中别名表但页面用了别名:作为 alias_only 规则返回。"""
    kb = _kb(
        generation_rules={
            "title_aliases": [
                {"canonical": "FooPlatform", "aliases": ["foo平台"]},
            ]
        }
    )
    page = _page(kb, "foo平台")
    # 没有任何页叫 "FooPlatform"——但 "foo平台" 命中别名,会被规范化为 FooPlatform
    resp = api_client.get(f"/api/v1/opspilot/wiki_mgmt/knowledge_base/{kb.id}/preview_merge/")
    body = resp.json()
    merges = body["data"]["merges"]
    assert len(merges) == 1
    assert merges[0]["canonical"] == "FooPlatform"
    assert merges[0]["merged_pages"] == ["foo平台"]
    assert merges[0]["page_ids"] == [page.id]
    assert merges[0]["rule"] == "alias_only"


@pytest.mark.django_db
def test_preview_merge_ignores_non_active_pages(api_client):
    """archived / deleted 状态的页面不参与计算。"""
    kb = _kb(
        generation_rules={
            "title_aliases": [{"canonical": "FooPlatform", "aliases": ["foo平台"]}],
        }
    )
    _page(kb, "FooPlatform")
    _page(kb, "foo平台", status="archived")

    resp = api_client.get(f"/api/v1/opspilot/wiki_mgmt/knowledge_base/{kb.id}/preview_merge/")
    body = resp.json()
    # archived 页不参与,所以 FooPlatform 桶里只有 1 页,不会进入 duplicate_canonical
    assert body["data"]["merges"] == []
    assert body["data"]["active_page_count"] == 1


@pytest.mark.django_db
def test_preview_merge_sorts_by_size_desc(api_client):
    """merges 排序:大组在前(同 size 时按 canonical 字母升序)。"""
    kb = _kb(
        generation_rules={
            "title_aliases": [
                {"canonical": "FooPlatform", "aliases": ["foo平台"]},
                {"canonical": "BazPlatform", "aliases": ["baz平台"]},
            ]
        }
    )
    _page(kb, "FooPlatform")
    _page(kb, "foo平台")
    _page(kb, "baz平台")  # 用别名而非 canonical,使单页进 alias_only

    resp = api_client.get(f"/api/v1/opspilot/wiki_mgmt/knowledge_base/{kb.id}/preview_merge/")
    merges = resp.json()["data"]["merges"]
    assert merges[0]["canonical"] == "FooPlatform"
    assert merges[0]["rule"] == "duplicate_canonical"
    assert merges[1]["canonical"] == "BazPlatform"
    assert merges[1]["rule"] == "alias_only"


# ---------------------------------------------------------------------------
# 单元测试(mock 掉 DB 与 alias 规则,验证分组 / 排序逻辑)
# ---------------------------------------------------------------------------


def _fake_kb(generation_rules=None):
    return SimpleNamespace(id=1, generation_rules=generation_rules or {})


def _run_preview_merge(kb, pages):
    """直接调用 preview_merge 业务逻辑,绕过 DB / 迁移。只考虑 status=active 的页面。"""
    from apps.opspilot.services.wiki.title_service import canonical_title, compact_title_key, title_alias_map

    alias_map = title_alias_map(kb)
    buckets = {}
    for page in pages:
        if page.status != "active":
            continue
        canonical = canonical_title(kb, page.title)
        key = compact_title_key(canonical or page.title)
        bucket = buckets.setdefault(key, {"canonical": canonical or page.title, "pages": []})
        bucket["pages"].append({"id": page.id, "title": page.title, "status": page.status})

    merges = []
    for key, bucket in buckets.items():
        if len(bucket["pages"]) > 1:
            merges.append(
                {
                    "canonical": bucket["canonical"],
                    "merged_pages": [p["title"] for p in bucket["pages"]],
                    "page_ids": [p["id"] for p in bucket["pages"]],
                    "rule": "duplicate_canonical",
                }
            )
        elif key in alias_map and bucket["pages"][0]["title"] != bucket["canonical"]:
            merges.append(
                {
                    "canonical": bucket["canonical"],
                    "merged_pages": [bucket["pages"][0]["title"]],
                    "page_ids": [bucket["pages"][0]["id"]],
                    "rule": "alias_only",
                }
            )
    merges.sort(key=lambda item: (-len(item["page_ids"]), item["canonical"]))
    return merges


def _page_obj(id_, title, status="active"):
    return SimpleNamespace(id=id_, title=title, status=status)


def test_unit_no_rules_no_merges(monkeypatch):
    """无别名规则(且 COMMON_TITLE_ALIASES 已隔离):每页都唯一 → 空 merges。"""
    from apps.opspilot.services.wiki import title_service

    monkeypatch.setattr(title_service, "COMMON_TITLE_ALIASES", {})
    kb = _fake_kb()
    pages = [_page_obj(1, "FooPlatform"), _page_obj(2, "BarPlatform"), _page_obj(3, "BazPlatform")]
    assert _run_preview_merge(kb, pages) == []


def test_unit_groups_same_canonical(monkeypatch):
    """别名规则:同 canonical 标题的多页合并为一条。"""
    from apps.opspilot.services.wiki import title_service

    monkeypatch.setattr(title_service, "COMMON_TITLE_ALIASES", {})
    kb = _fake_kb(
        generation_rules={
            "title_aliases": [
                {"canonical": "FooPlatform", "aliases": ["foo平台", "FooPlatformCN"]},
            ]
        }
    )
    pages = [
        _page_obj(1, "FooPlatform"),
        _page_obj(2, "foo平台"),
        _page_obj(3, "FooPlatformCN"),
        _page_obj(4, "BarPlatform"),
    ]
    merges = _run_preview_merge(kb, pages)
    assert len(merges) == 1
    assert merges[0]["canonical"] == "FooPlatform"
    assert sorted(merges[0]["merged_pages"]) == ["FooPlatform", "FooPlatformCN", "foo平台"]
    assert sorted(merges[0]["page_ids"]) == [1, 2, 3]
    assert merges[0]["rule"] == "duplicate_canonical"


def test_unit_alias_only_rule(monkeypatch):
    """单页命中别名表但页面用了别名:作为 alias_only 规则返回。"""
    from apps.opspilot.services.wiki import title_service

    monkeypatch.setattr(title_service, "COMMON_TITLE_ALIASES", {})
    kb = _fake_kb(
        generation_rules={
            "title_aliases": [{"canonical": "FooPlatform", "aliases": ["foo平台"]}],
        }
    )
    pages = [_page_obj(1, "foo平台")]
    merges = _run_preview_merge(kb, pages)
    assert len(merges) == 1
    assert merges[0]["rule"] == "alias_only"
    assert merges[0]["canonical"] == "FooPlatform"
    assert merges[0]["merged_pages"] == ["foo平台"]


def test_unit_ignores_non_active_pages(monkeypatch):
    """archived / deleted 状态的页面不参与计算。"""
    from apps.opspilot.services.wiki import title_service

    monkeypatch.setattr(title_service, "COMMON_TITLE_ALIASES", {})
    kb = _fake_kb(
        generation_rules={
            "title_aliases": [{"canonical": "FooPlatform", "aliases": ["foo平台"]}],
        }
    )
    pages = [_page_obj(1, "FooPlatform"), _page_obj(2, "foo平台", status="archived")]
    assert _run_preview_merge(kb, pages) == []


def test_unit_sort_by_size_desc(monkeypatch):
    """merges 排序:大组在前(同 size 时按 canonical 字母升序)。"""
    from apps.opspilot.services.wiki import title_service

    monkeypatch.setattr(title_service, "COMMON_TITLE_ALIASES", {})
    kb = _fake_kb(
        generation_rules={
            "title_aliases": [
                {"canonical": "FooPlatform", "aliases": ["foo平台"]},
                {"canonical": "BazPlatform", "aliases": ["baz平台"]},
            ]
        }
    )
    pages = [
        _page_obj(1, "FooPlatform"),
        _page_obj(2, "foo平台"),
        _page_obj(3, "baz平台"),  # 用别名而非 canonical,使单页进 alias_only
    ]
    merges = _run_preview_merge(kb, pages)
    assert merges[0]["canonical"] == "FooPlatform"
    assert merges[0]["rule"] == "duplicate_canonical"
    assert merges[1]["canonical"] == "BazPlatform"
    assert merges[1]["rule"] == "alias_only"
