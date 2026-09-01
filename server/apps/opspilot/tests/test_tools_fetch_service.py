"""Fetch 工具：HTTP 失败透传、HTML/文本/JSON/批量抓取。"""
from unittest.mock import patch

import pytest

from apps.opspilot.metis.llm.tools.fetch import fetch as f

pytestmark = pytest.mark.unit


def _ok(content, url="https://example.com", content_type="text/html"):
    return {"success": True, "content": content, "url": url, "content_type": content_type}


def test_fetch_html_extracts_main_and_truncates():
    html = "<html><body><nav>nav</nav><article><p>hello world from the main article body</p></article></body></html>"
    with patch.object(f, "_http_get_impl", return_value=_ok(html)):
        out = f.fetch_html.invoke({"url": "https://example.com", "extract_main": True, "max_length": 20})
    assert out["success"] is True
    assert out["truncated"] is True
    assert len(out["content"]) <= 20
    assert len(out["content"]) == 20
    assert out["content"].startswith("<article>")
    assert "nav" not in out["content"]
    assert out["url"] == "https://example.com"


def test_fetch_html_propagates_http_failure():
    with patch.object(f, "_http_get_impl", return_value={"success": False, "error": "timeout"}):
        out = f.fetch_html.invoke({"url": "https://down.example"})
    assert out["success"] is False
    assert out["error"] == "timeout"


def test_fetch_txt_strips_tags():
    with patch.object(f, "_http_get_impl", return_value=_ok("<p>alpha <b>beta</b></p>")):
        out = f.fetch_txt.invoke({"url": "https://example.com", "max_length": 500})
    assert out["success"] is True
    assert "alpha" in out["content"]
    assert "<p>" not in out["content"]


def test_fetch_markdown_converts_headings():
    with patch.object(f, "_http_get_impl", return_value=_ok("<h1>Title</h1><p>body</p>")):
        out = f.fetch_markdown.invoke({"url": "https://example.com", "max_length": 500})
    assert out["success"] is True
    assert "Title" in out["content"]


def test_fetch_json_parses_and_rejects_invalid():
    with patch.object(f, "_http_get_impl", return_value=_ok('{"a": 1}', content_type="application/json")):
        out = f.fetch_json.invoke({"url": "https://api.example/data"})
    assert out["success"] is True
    assert out["data"] == {"a": 1}

    with patch.object(f, "_http_get_impl", return_value=_ok("not-json", content_type="text/plain")):
        bad = f.fetch_json.invoke({"url": "https://api.example/bad"})
    assert bad["success"] is False
    assert bad["error"] == "响应的Content-Type不是JSON: text/plain"
    assert bad["url"] == "https://example.com"


def test_fetch_batch_counts_success_and_failure():
    def _impl(url, **kwargs):
        if "fail" in url:
            return {"success": False, "error": "gone"}
        if url.endswith(".json"):
            return _ok('{"ok": true}', url=url, content_type="application/json")
        return _ok("<p>hi</p>", url=url)

    with patch.object(f, "_http_get_impl", side_effect=_impl):
        html_batch = f.fetch_batch.invoke({"urls": ["https://a", "https://fail"], "format": "html"})
        json_batch = f.fetch_batch.invoke({"urls": ["https://a.json"], "format": "json"})
    assert html_batch["total"] == 2
    assert html_batch["succeeded"] == 1
    assert html_batch["failed"] == 1
    assert json_batch["succeeded"] == 1
    assert json_batch["results"][0]["data"] == {"ok": True}
