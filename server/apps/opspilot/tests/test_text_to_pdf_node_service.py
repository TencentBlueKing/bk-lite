"""TextToPdfNode：空输入拒绝；有文本时生成 PDF 字节流并写入变量管理器。"""
from io import BytesIO

import pytest

from apps.opspilot.utils.chat_flow_utils.nodes.converter.text_to_pdf import TextToPdfNode

pytestmark = pytest.mark.unit


class _Vars:
    def __init__(self):
        self.store = {}

    def set_variable(self, key, value):
        self.store[key] = value


def test_execute_rejects_empty_input():
    node = TextToPdfNode(_Vars())
    result = node.execute(
        "n1",
        {"data": {"config": {"inputParams": "last_message", "outputParams": "last_message"}}},
        {"last_message": ""},
    )
    assert "输入文本为空" in result["last_message"]


def test_execute_builds_pdf_stream_and_metadata():
    vars_ = _Vars()
    node = TextToPdfNode(vars_)
    node.chinese_font_name = "Helvetica"
    result = node.execute(
        "pdf-1",
        {
            "data": {
                "config": {
                    "inputParams": "last_message",
                    "outputParams": "pdf_file",
                    "pdfConfig": {"title": "报告", "fontSize": 11, "fontName": "Helvetica"},
                }
            }
        },
        {"last_message": "第一行\n\n第二行 <tag> & amp"},
    )
    assert isinstance(result["pdf_file"], BytesIO)
    assert result["pdf_file"].getvalue()[:4] == b"%PDF"
    assert result["pdf_metadata"]["title"] == "报告"
    assert result["pdf_metadata"]["variable_name"] == "pdf_file"
    assert result["pdf_metadata"]["content_length"] == len("第一行\n\n第二行 <tag> & amp")
    assert vars_.store["pdf_file"] is result["pdf_file"]
