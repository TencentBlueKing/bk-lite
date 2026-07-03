"""opspilot-core 切片: metis/llm/rerank ReRankManager 真实测试。

唯一外部边界是 safe_post_llm_endpoint（HTTP 调用），mock 它返回真实形态的
rerank API 响应。其余全部是真实逻辑：按 relevance_score 排序、index→doc 映射、
top_k 截断、阈值过滤（threshold/10 标准化）、SSRF 阻断/重试退避/响应格式错误分支。
"""

import pydantic.root_model  # noqa

from unittest.mock import MagicMock, patch

import pytest

from langchain_core.documents import Document

from apps.core.utils.safe_requests import SafeRequestsError
from apps.core.utils.ssrf_validator import SSRFError
from apps.opspilot.metis.llm.rerank.rerank_config import ReRankConfig
from apps.opspilot.metis.llm.rerank.rerank_manager import ReRankManager

pytestmark = pytest.mark.unit

MOD = "apps.opspilot.metis.llm.rerank.rerank_manager"


def _docs(*contents):
    return [Document(page_content=c, metadata={}) for c in contents]


def _resp(results):
    r = MagicMock()
    r.raise_for_status.return_value = None
    r.json.return_value = {"results": results}
    return r


def _cfg(top_k=10, threshold=None, query="q"):
    return ReRankConfig(
        model_base_url="http://rerank.local/v1",
        model_name="bge-rerank",
        api_key="sk-test",
        query=query,
        top_k=top_k,
        threshold=threshold,
    )


class TestEmptyAndConfigPassthrough:
    def test_empty_search_result_returns_same(self):
        assert ReRankManager.rerank_documents_with_config(_cfg(), []) == []

    def test_rerank_documents_builds_config_and_delegates(self):
        docs = _docs("d0", "d1")
        # results 把 index1 排前面
        with patch(f"{MOD}.safe_post_llm_endpoint", return_value=_resp([
            {"index": 1, "relevance_score": 0.9},
            {"index": 0, "relevance_score": 0.2},
        ])) as m:
            out = ReRankManager.rerank_documents(
                "http://rerank.local/v1", "bge", "sk", "myquery", docs, rerank_top_k=10
            )
        # 调用参数契约: data 包含 model/query/documents
        sent_json = m.call_args.kwargs["json"]
        assert sent_json["model"] == "bge"
        assert sent_json["query"] == "myquery"
        assert sent_json["documents"] == ["d0", "d1"]
        # Authorization header 用 api_key
        assert m.call_args.kwargs["headers"]["Authorization"] == "Bearer sk"
        # 按分数排序: d1 在前
        assert [d.page_content for d in out] == ["d1", "d0"]


class TestRemoteRerankLogic:
    def test_sorted_by_score_and_score_written_to_metadata(self):
        docs = _docs("a", "b", "c")
        with patch(f"{MOD}.safe_post_llm_endpoint", return_value=_resp([
            {"index": 0, "relevance_score": 0.1},
            {"index": 2, "relevance_score": 0.95},
            {"index": 1, "relevance_score": 0.5},
        ])):
            out = ReRankManager.rerank_documents_with_config(_cfg(), docs)
        assert [d.page_content for d in out] == ["c", "b", "a"]
        # relevance_score 回写到对应 doc.metadata
        assert out[0].metadata["relevance_score"] == 0.95

    def test_top_k_truncates_after_sort(self):
        docs = _docs("a", "b", "c")
        with patch(f"{MOD}.safe_post_llm_endpoint", return_value=_resp([
            {"index": 0, "relevance_score": 0.1},
            {"index": 1, "relevance_score": 0.9},
            {"index": 2, "relevance_score": 0.5},
        ])):
            out = ReRankManager.rerank_documents_with_config(_cfg(top_k=2), docs)
        assert [d.page_content for d in out] == ["b", "c"]

    def test_invalid_index_skipped(self):
        docs = _docs("a", "b")
        with patch(f"{MOD}.safe_post_llm_endpoint", return_value=_resp([
            {"index": 99, "relevance_score": 0.9},
            {"index": 0, "relevance_score": 0.4},
        ])):
            out = ReRankManager.rerank_documents_with_config(_cfg(), docs)
        # 越界索引被跳过，只剩 index0
        assert [d.page_content for d in out] == ["a"]

    def test_items_missing_required_fields_filtered_out(self):
        docs = _docs("a", "b")
        with patch(f"{MOD}.safe_post_llm_endpoint", return_value=_resp([
            {"index": 0},  # 缺 relevance_score
            {"relevance_score": 0.5},  # 缺 index
            {"index": 1, "relevance_score": 0.7},
        ])):
            out = ReRankManager.rerank_documents_with_config(_cfg(), docs)
        assert [d.page_content for d in out] == ["b"]

    def test_missing_results_key_returns_original(self):
        docs = _docs("a", "b")
        bad = MagicMock()
        bad.raise_for_status.return_value = None
        bad.json.return_value = {"unexpected": []}
        with patch(f"{MOD}.safe_post_llm_endpoint", return_value=bad):
            out = ReRankManager.rerank_documents_with_config(_cfg(), docs)
        assert out == docs


class TestThresholdFilter:
    def test_threshold_normalized_by_ten(self):
        # config threshold 受 le=1.0 约束；过滤时再除以 10 标准化。
        # threshold=0.5 -> 标准化阈值 0.05；保留 score>=0.05
        docs = _docs("a", "b")
        with patch(f"{MOD}.safe_post_llm_endpoint", return_value=_resp([
            {"index": 0, "relevance_score": 0.8},
            {"index": 1, "relevance_score": 0.03},
        ])):
            out = ReRankManager.rerank_documents_with_config(_cfg(threshold=0.5), docs)
        # a(0.8>=0.05)保留, b(0.03<0.05)过滤
        assert [d.page_content for d in out] == ["a"]

    def test_filter_by_threshold_uses_score_fallback(self):
        docs = [
            Document(page_content="x", metadata={"_score": 0.9}),
            Document(page_content="y", metadata={"_score": 0.1}),
        ]
        out = ReRankManager._filter_by_threshold(docs, threshold=5.0)
        assert [d.page_content for d in out] == ["x"]

    def test_filter_by_threshold_zero_is_noop(self):
        docs = [Document(page_content="x", metadata={"relevance_score": 0.0})]
        assert ReRankManager._filter_by_threshold(docs, 0) == docs

    def test_filter_empty_docs(self):
        assert ReRankManager._filter_by_threshold([], 5.0) == []


class TestErrorBranches:
    def test_ssrf_blocked_no_retry_returns_original(self):
        docs = _docs("a")
        with patch(f"{MOD}.safe_post_llm_endpoint", side_effect=SSRFError("blocked")) as m:
            out = ReRankManager.rerank_documents_with_config(_cfg(), docs)
        assert out == docs
        # SSRF 不重试，只调一次
        assert m.call_count == 1

    def test_safe_requests_error_retries_then_returns_original(self):
        docs = _docs("a")
        with patch(f"{MOD}.safe_post_llm_endpoint", side_effect=SafeRequestsError("net")) as m, \
                patch(f"{MOD}.time.sleep") as sleep_mock:
            out = ReRankManager.rerank_documents_with_config(_cfg(), docs)
        assert out == docs
        # 重试到上限 MAX_RETRY_ATTEMPTS 次
        assert m.call_count == ReRankManager.MAX_RETRY_ATTEMPTS
        # 失败两次后退避两次（最后一次不退避）
        assert sleep_mock.call_count == ReRankManager.MAX_RETRY_ATTEMPTS - 1

    def test_unexpected_exception_returns_original(self):
        docs = _docs("a")
        with patch(f"{MOD}.safe_post_llm_endpoint", side_effect=RuntimeError("boom")):
            out = ReRankManager.rerank_documents_with_config(_cfg(), docs)
        assert out == docs

    def test_results_items_not_dict_yields_empty(self):
        docs = _docs("a")
        broken = MagicMock()
        broken.raise_for_status.return_value = None
        # results 是字符串：迭代出单字符，"relevance_score" in <char> 全 False，
        # valid_rerank_items 为空 -> 真实返回空列表（非原始结果）
        broken.json.return_value = {"results": "xyz"}
        with patch(f"{MOD}.safe_post_llm_endpoint", return_value=broken):
            out = ReRankManager.rerank_documents_with_config(_cfg(), docs)
        assert out == []
