"""opspilot-core 切片: metis/llm/chunk 文档分块器真实测试。

不 mock 任何东西 —— langchain RecursiveCharacterTextSplitter 是确定性纯函数，
直接对真实 Document 断言分块数量、chunk_id/chunk_number/segment_number 元数据、
重叠行为与分组逻辑。覆盖 BaseChunk.chunk 公共流程 + 各子类 _split_documents。
"""

import pydantic.root_model  # noqa

import pytest

from langchain_core.documents import Document

from apps.opspilot.metis.llm.chunk import (
    BaseChunk,
    FixedSizeChunk,
    FullChunk,
    RecursiveChunk,
)

pytestmark = pytest.mark.unit


def _doc(text, **meta):
    return Document(page_content=text, metadata=meta)


class TestBaseChunkFlow:
    def test_empty_input_returns_empty(self):
        assert FullChunk().chunk([]) == []

    def test_full_chunk_preserves_content_and_adds_metadata(self):
        docs = [_doc("hello", segment_number=0), _doc("world", segment_number=0)]
        result = FullChunk().chunk(docs)
        assert len(result) == 2
        # 全文分块不切割，原文保留
        assert [d.page_content for d in result] == ["hello", "world"]
        # 同一 segment 内 chunk_number 从 0 递增
        assert [d.metadata["chunk_number"] for d in result] == ["0", "1"]
        # 每个块分配唯一 chunk_id
        ids = [d.metadata["chunk_id"] for d in result]
        assert len(set(ids)) == 2
        assert all(d.metadata["segment_number"] == 0 for d in result)

    def test_chunk_number_resets_per_segment_group(self):
        docs = [
            _doc("a", segment_number=1),
            _doc("b", segment_number=2),
            _doc("c", segment_number=1),
        ]
        result = FullChunk().chunk(docs)
        by_seg = {}
        for d in result:
            by_seg.setdefault(d.metadata["segment_number"], []).append(d.metadata["chunk_number"])
        # segment 1 有两个块，编号 0,1；segment 2 一个块，编号 0
        assert sorted(by_seg[1]) == ["0", "1"]
        assert by_seg[2] == ["0"]

    def test_missing_segment_number_defaults_to_zero(self):
        result = FullChunk().chunk([_doc("no-seg")])
        assert result[0].metadata["segment_number"] == 0
        assert result[0].metadata["chunk_number"] == "0"

    def test_base_chunk_is_abstract(self):
        with pytest.raises(TypeError):
            BaseChunk()  # noqa: 抽象类不可实例化


class TestFixedSizeChunk:
    def test_long_text_split_into_multiple_chunks_no_overlap(self):
        text = "x" * 1200
        result = FixedSizeChunk(chunk_size=500).chunk([_doc(text, segment_number=0)])
        # 1200 字符按 500 无重叠切，至少 3 块
        assert len(result) >= 3
        # 无重叠：各块长度不超过 chunk_size
        assert all(len(d.page_content) <= 500 for d in result)
        # 总字符还原（无重叠时拼接等于原文）
        assert "".join(d.page_content for d in result) == text

    def test_short_text_single_chunk(self):
        result = FixedSizeChunk(chunk_size=500).chunk([_doc("short text", segment_number=0)])
        assert len(result) == 1
        assert result[0].page_content == "short text"


class TestRecursiveChunk:
    def test_overlap_produces_more_total_chars_than_source(self):
        text = "A" * 1000
        result = RecursiveChunk(chunk_size=300, chunk_overlap=100).chunk([_doc(text, segment_number=0)])
        assert len(result) >= 2
        # 有重叠时拼接长度应 >= 原文（块间有重复字符）
        total = sum(len(d.page_content) for d in result)
        assert total >= len(text)

    def test_chunk_size_respected(self):
        text = "B" * 900
        result = RecursiveChunk(chunk_size=200, chunk_overlap=0).chunk([_doc(text, segment_number=0)])
        assert all(len(d.page_content) <= 200 for d in result)
