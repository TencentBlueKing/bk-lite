"""OCR、文本转 PDF 与 SSE 响应器的真实转换契约测试。"""

import base64
import io
from types import SimpleNamespace

import pytest
from PIL import Image

from apps.opspilot.metis.ocr import olm_ocr
from apps.opspilot.metis.ocr.olm_ocr import OlmOcr
from apps.opspilot.utils.chat_flow_utils.engine.sse_responder import (
    SSEResponderMixin,
)
from apps.opspilot.utils.chat_flow_utils.nodes.converter import text_to_pdf
from apps.opspilot.utils.chat_flow_utils.nodes.converter.text_to_pdf import (
    TextToPdfNode,
)


pytestmark = pytest.mark.unit


class VariableManager:
    def __init__(self):
        self.values = {}

    def set_variable(self, key, value):
        self.values[key] = value


class Responder(SSEResponderMixin):
    execution_id = "exec-17"
    AGUI_SKIP_TYPES = {"TOOL_CALL_START", "TOOL_CALL_END"}


def _png_bytes(size=(8, 8), mode="RGB"):
    buffer = io.BytesIO()
    color = (10, 20, 30, 120) if mode == "RGBA" else (10, 20, 30)
    Image.new(mode, size, color).save(buffer, format="PNG")
    return buffer.getvalue()


def _ocr_without_network(monkeypatch):
    client = SimpleNamespace()
    monkeypatch.setattr(olm_ocr, "OpenAI", lambda **_kwargs: client)
    monkeypatch.setattr(
        olm_ocr.SSRFValidator, "validate_llm_endpoint", lambda _url: None
    )
    return OlmOcr("https://ocr.example/v1", "key", model="olm")


def test_ocr_initialization_validates_endpoint_and_builds_client(monkeypatch):
    calls = {}
    monkeypatch.setattr(
        olm_ocr.SSRFValidator,
        "validate_llm_endpoint",
        lambda url: calls.update(validated=url),
    )
    monkeypatch.setattr(
        olm_ocr,
        "OpenAI",
        lambda **kwargs: calls.update(client=kwargs) or SimpleNamespace(),
    )

    client = OlmOcr("https://ocr.example/v1", "key", model="olm-custom")
    assert calls == {
        "validated": "https://ocr.example/v1",
        "client": {"base_url": "https://ocr.example/v1", "api_key": "key"},
    }
    assert client.model == "olm-custom"


def test_ocr_small_image_keeps_original_bytes():
    image = _png_bytes()
    assert OlmOcr._compress_image_from_bytes(image, max_size_kb=600) is image


def test_ocr_large_rgba_png_is_compressed_below_limit():
    image = _png_bytes((500, 500), mode="RGBA")
    compressed = OlmOcr._compress_image_from_bytes(image, max_size_kb=1)
    assert compressed.startswith(b"\x89PNG")
    assert len(compressed) <= 1024
    with Image.open(io.BytesIO(compressed)) as decoded:
        assert decoded.mode == "RGBA"


def test_ocr_predict_from_base64_compresses_and_delegates(monkeypatch):
    client = _ocr_without_network(monkeypatch)
    image = _png_bytes()
    captured = {}
    monkeypatch.setattr(
        client,
        "_perform_ocr",
        lambda encoded: captured.update(encoded=encoded) or "recognized",
    )

    assert client.predict_from_base64(base64.b64encode(image).decode()) == "recognized"
    assert base64.b64decode(captured["encoded"]) == image


def test_ocr_predict_reads_real_file_and_delegates(monkeypatch, tmp_path):
    client = _ocr_without_network(monkeypatch)
    image_path = tmp_path / "screen.png"
    image_path.write_bytes(_png_bytes())
    monkeypatch.setattr(client, "_perform_ocr", lambda _encoded: "file text")

    assert client.predict(str(image_path)) == "file text"


@pytest.mark.parametrize(
    ("choices", "expected"),
    [
        ([SimpleNamespace(message=SimpleNamespace(content="recognized"))], "recognized"),
        ([], "无法识别文本"),
    ],
)
def test_ocr_public_result_contract(monkeypatch, choices, expected):
    client = _ocr_without_network(monkeypatch)
    calls = {}
    client.client = SimpleNamespace(
        chat=SimpleNamespace(
            completions=SimpleNamespace(
                create=lambda **kwargs: calls.update(kwargs)
                or SimpleNamespace(choices=choices)
            )
        )
    )

    assert client._perform_ocr("encoded-image") == expected
    assert calls["model"] == "olm"
    assert calls["temperature"] == 0.01
    image_part = calls["messages"][0]["content"][1]
    assert image_part["image_url"]["url"].endswith("encoded-image")


def test_ocr_provider_exception_is_returned_as_actionable_result(monkeypatch):
    client = _ocr_without_network(monkeypatch)

    def reject(**_kwargs):
        raise RuntimeError("provider offline")

    client.client = SimpleNamespace(
        chat=SimpleNamespace(
            completions=SimpleNamespace(create=reject)
        )
    )
    assert client._perform_ocr("encoded") == "请求失败: provider offline"


def test_text_to_pdf_creates_real_pdf_with_escaped_content(monkeypatch):
    monkeypatch.setattr(TextToPdfNode, "_register_fonts", lambda _self: "Helvetica")
    node = TextToPdfNode(VariableManager())

    pdf = node._create_pdf_stream(
        "first <tag> & value\n\nsecond paragraph",
        title="Inspection",
        font_name="Helvetica",
        font_size=10,
    )

    assert pdf.read(5) == b"%PDF-"
    assert pdf.getbuffer().nbytes > 500


def test_text_to_pdf_execute_persists_stream_and_metadata(monkeypatch):
    monkeypatch.setattr(TextToPdfNode, "_register_fonts", lambda _self: "Helvetica")
    variables = VariableManager()
    node = TextToPdfNode(variables)
    config = {
        "data": {
            "config": {
                "inputParams": "answer",
                "outputParams": "report",
                "pdfConfig": {
                    "title": "Health report",
                    "fontSize": 11,
                    "fontName": "Helvetica",
                },
            }
        }
    }

    result = node.execute("pdf-1", config, {"answer": "database healthy"})

    assert result["report"] is variables.values["report"]
    assert result["report"].read(5) == b"%PDF-"
    assert result["pdf_metadata"]["title"] == "Health report"
    assert result["pdf_metadata"]["content_length"] == len("database healthy")
    assert result["pdf_metadata"]["size_bytes"] > 500


def test_text_to_pdf_execute_rejects_empty_input(monkeypatch):
    monkeypatch.setattr(TextToPdfNode, "_register_fonts", lambda _self: "Helvetica")
    result = TextToPdfNode(VariableManager()).execute(
        "pdf-1", {"data": {"config": {}}}, {}
    )
    assert result == {"last_message": "输入文本为空，无法生成PDF"}


def test_text_to_pdf_execute_contains_rendering_failure(monkeypatch):
    monkeypatch.setattr(TextToPdfNode, "_register_fonts", lambda _self: "Helvetica")
    node = TextToPdfNode(VariableManager())
    monkeypatch.setattr(
        node, "_create_pdf_stream", lambda **_kwargs: (_ for _ in ()).throw(ValueError("bad font"))
    )
    result = node.execute(
        "pdf-1", {"data": {"config": {}}}, {"last_message": "answer"}
    )
    assert result == {"last_message": "PDF生成失败: bad font"}


def test_text_to_pdf_font_registration_uses_existing_candidate(monkeypatch):
    registered = []
    monkeypatch.setattr(
        text_to_pdf.os.path,
        "exists",
        lambda path: path.endswith("DejaVuSans.ttf"),
    )
    monkeypatch.setattr(
        text_to_pdf.pdfmetrics,
        "registerFont",
        lambda font: registered.append(font),
    )
    monkeypatch.setattr(text_to_pdf, "TTFont", lambda name, path: (name, path))

    node = TextToPdfNode(VariableManager())
    assert node.chinese_font_name == "DejaVuSans"
    assert registered[0][0] == "DejaVuSans"


def test_text_to_pdf_font_registration_falls_back_after_error(monkeypatch):
    monkeypatch.setattr(text_to_pdf.os.path, "exists", lambda _path: True)
    monkeypatch.setattr(
        text_to_pdf, "TTFont", lambda *_args: (_ for _ in ()).throw(ValueError("bad"))
    )
    assert TextToPdfNode(VariableManager()).chinese_font_name == "Helvetica"


def test_sse_response_exposes_streaming_headers_and_execution_id():
    response = Responder()._create_sse_stream_response(
        lambda: iter(["data: one\n\n", "data: [DONE]\n\n"])
    )
    assert list(response.streaming_content) == [
        b"data: one\n\n",
        b"data: [DONE]\n\n",
    ]
    assert response["Cache-Control"] == "no-cache, no-store, must-revalidate"
    assert response["X-Accel-Buffering"] == "no"
    assert response["X-Execution-ID"] == "exec-17"
    assert response["Transfer-Encoding"] == "chunked"


@pytest.mark.asyncio
async def test_sse_error_response_has_error_and_terminal_frames():
    response = Responder()._create_error_response("model unavailable")
    frames = [
        frame.decode() if isinstance(frame, bytes) else frame
        async for frame in response.streaming_content
    ]
    assert frames == [
        'data: {"result": false, "error": "model unavailable"}\n\n',
        "data: [DONE]\n\n",
    ]
    assert response["Cache-Control"] == "no-cache, no-store, must-revalidate"


def test_sse_final_message_extracts_only_visible_protocol_content():
    responder = Responder()
    content = [
        None,
        {"type": "TOOL_CALL_START", "delta": "hidden"},
        {"type": "CUSTOM", "delta": "hidden"},
        {
            "object": "chat.completion.chunk",
            "choices": [
                None,
                {"delta": None},
                {"delta": {"content": "openai "}},
            ],
        },
        {"type": "TEXT_MESSAGE_CONTENT", "delta": "agui "},
        {"object": "message", "message": "message "},
        {"text": "fallback"},
    ]
    assert responder._extract_final_message(content) == (
        "openai agui message fallback"
    )
    assert responder._extract_final_message([]) == ""


def test_sse_browser_steps_ignore_invalid_events_and_keep_last_evaluation():
    responder = Responder()
    content = [
        None,
        {"type": "CUSTOM", "name": "other", "value": {}},
        {"type": "CUSTOM", "name": "browser_step_progress", "value": "bad"},
        {
            "type": "CUSTOM",
            "name": "browser_step_progress",
            "value": {
                "step_number": 1,
                "next_goal": "open dashboard",
                "evaluation": "page opened",
            },
        },
        {
            "type": "CUSTOM",
            "name": "browser_step_progress",
            "value": {
                "step_number": 2,
                "next_goal": "read status",
                "evaluation": "healthy",
            },
        },
    ]
    assert responder._extract_browser_steps(content) == [
        "步骤1 open dashboard",
        "步骤2 read status",
        "最终结果: healthy",
    ]
    assert responder._extract_browser_steps([]) == []
