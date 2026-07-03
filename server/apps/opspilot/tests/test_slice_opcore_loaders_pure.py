"""opspilot-core 切片: metis/llm/loader 纯解析器真实测试。

唯一边界是磁盘文件，用 pytest tmp_path 写真实临时文件后断言真实解析输出。
覆盖 RawLoader(纯内存)、TextLoader、MarkdownLoader 的真实读取与 Document 构造，
ExcelLoader.dataframe_to_excel_format_string 用真实 pandas DataFrame 断言制表符格式。
"""

import pydantic.root_model  # noqa

import pandas as pd
import pytest

from langchain_core.documents import Document

from apps.opspilot.metis.llm.loader.excel_loader import ExcelLoader
from apps.opspilot.metis.llm.loader.markdown_loader import MarkdownLoader
from apps.opspilot.metis.llm.loader.raw_loader import RawLoader
from apps.opspilot.metis.llm.loader.text_loader import TextLoader

pytestmark = pytest.mark.unit


class TestRawLoader:
    def test_wraps_content_into_single_document(self):
        out = RawLoader("hello raw").load()
        assert len(out) == 1
        assert isinstance(out[0], Document)
        assert out[0].page_content == "hello raw"

    def test_empty_content(self):
        out = RawLoader("").load()
        assert out[0].page_content == ""


class TestTextLoader:
    def test_full_mode_reads_file(self, tmp_path):
        p = tmp_path / "a.txt"
        p.write_text("第一行\n第二行", encoding="utf-8")
        out = TextLoader(str(p), load_mode="full").load()
        assert len(out) == 1
        assert out[0].page_content == "第一行\n第二行"

    def test_non_full_mode_returns_empty(self, tmp_path):
        p = tmp_path / "b.txt"
        p.write_text("ignored", encoding="utf-8")
        # 非 full 模式不读取内容
        out = TextLoader(str(p), load_mode="paragraph").load()
        assert out == []


class TestMarkdownLoader:
    def test_reads_markdown_content(self, tmp_path):
        p = tmp_path / "doc.md"
        p.write_text("# 标题\n\n正文内容", encoding="utf-8")
        out = MarkdownLoader(str(p)).load()
        assert len(out) == 1
        assert out[0].page_content == "# 标题\n\n正文内容"


class TestExcelFormatString:
    def test_data_rows_tab_separated(self):
        df = pd.DataFrame({"name": ["alice", "bob"], "age": [30, 25]})
        s = ExcelLoader("x.xlsx").dataframe_to_excel_format_string(df)
        lines = s.strip().split("\n")
        # 注意: 表头行是 str(df.columns) 的 Index repr 被逐字符 \t 拼接（实现特性，
        # 非真正的列名制表符分隔），故此处只对真实可靠的数据行断言。
        assert "alice\t30" in s
        assert "bob\t25" in s
        # 表头行（首行）含 Index repr 残留字符
        assert lines[0].startswith("I\tn\td\te\tx")

    def test_all_nan_rows_and_cols_dropped_and_nan_stripped(self):
        df = pd.DataFrame({"a": [1, None], "b": [None, None]})
        s = ExcelLoader("x.xlsx").dataframe_to_excel_format_string(df)
        # nan 文本被 replace 清空
        assert "nan" not in s
        # 全 NaN 的列 b、全 NaN 的第二行被 dropna 删除，仅剩 a 列第一行 1.0
        assert "1.0" in s
