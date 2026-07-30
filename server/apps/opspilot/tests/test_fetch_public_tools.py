"""Fetch/HTTP 公开工具的请求、格式化和错误契约。"""

from unittest.mock import patch

import pydantic.root_model  # noqa: F401
import pytest
import requests

from apps.opspilot.metis.llm.tools.fetch import fetch as fetch_tools
from apps.opspilot.metis.llm.tools.fetch import http


pytestmark = pytest.mark.unit


class ExternalResponse:
    def __init__(
        self,
        *,
        status_code=200,
        text="ok",
        content_type="text/plain; charset=utf-8",
        url="https://93.184.216.34/result",
        encoding=None,
    ):
        self.status_code = status_code
        self.text = text
        self.headers = {"Content-Type": content_type, "X-Request-ID": "req-1"}
        self.url = url
        self.encoding = encoding

    def raise_for_status(self):
        if self.status_code >= 400:
            raise requests.exceptions.HTTPError(
                f"{self.status_code} Server Error",
                response=self,
            )

    def __bool__(self):
        return self.status_code < 400


def test_http_get_preserves_error_status_from_unsuccessful_response():
    response = ExternalResponse(status_code=503)
    with patch.object(http, "safe_get", return_value=response):
        result = http.http_get.invoke({"url": "https://93.184.216.34/health"})

    assert result["success"] is False
    assert result["status_code"] == 503
    assert "503 Server Error" in result["error"]


@pytest.mark.parametrize(
    ("tool_name", "safe_name", "payload"),
    [
        (
            "http_get",
            "safe_get",
            {
                "params": {"page": 2},
                "headers": {"X-Tenant": "blue"},
                "timeout": "7",
            },
        ),
        (
            "http_post",
            "safe_post",
            {"json_data": {"name": "db-01"}, "timeout": 8},
        ),
        (
            "http_put",
            "safe_put",
            {"data": {"enabled": "true"}},
        ),
        (
            "http_delete",
            "safe_delete",
            {"params": {"force": "yes"}},
        ),
        (
            "http_patch",
            "safe_patch",
            {"json_data": {"state": "ready"}},
        ),
    ],
)
def test_http_tools_forward_request_contract_and_return_response(
    tool_name,
    safe_name,
    payload,
):
    response = ExternalResponse(
        status_code=202,
        text='{"accepted": true}',
        content_type="application/json; charset=utf-8",
        encoding="utf-8",
    )
    request = {
        "url": "https://93.184.216.34/resources/1",
        "bearer_token": "api-secret",
        **payload,
    }
    with patch.object(http, safe_name, return_value=response) as external_call:
        result = getattr(http, tool_name).invoke(request)

    assert result == {
        "success": True,
        "status_code": 202,
        "content": '{"accepted": true}',
        "headers": {
            "Content-Type": "application/json; charset=utf-8",
            "X-Request-ID": "req-1",
        },
        "url": "https://93.184.216.34/result",
        "encoding": "utf-8",
        "content_type": "application/json; charset=utf-8",
    }
    assert external_call.call_args.kwargs["headers"]["Authorization"] == (
        "Bearer api-secret"
    )
    assert external_call.call_args.kwargs["allow_redirects"] is True


def test_http_get_maps_timeout_and_rejects_private_destination():
    with patch.object(
        http,
        "safe_get",
        side_effect=requests.exceptions.Timeout,
    ):
        timeout = http.http_get.invoke(
            {
                "url": "https://93.184.216.34/slow",
                "timeout": "4",
            }
        )
    private = http.http_get.invoke({"url": "http://127.0.0.1/secrets"})

    assert timeout["success"] is False
    assert timeout["error"] == "请求超时（4秒）"
    assert private["success"] is False
    assert "禁止" in private["error"]


def test_fetch_html_extracts_main_content_and_truncates():
    response = ExternalResponse(
        text=(
            "<html><body><nav>ignore</nav><main>"
            "<h1>Health</h1><p>database ready</p>"
            "</main></body></html>"
        ),
        content_type="text/html; charset=utf-8",
    )
    with patch.object(http, "safe_get", return_value=response):
        result = fetch_tools.fetch_html.invoke(
            {
                "url": "https://93.184.216.34/status",
                "extract_main": True,
                "max_length": 30,
            }
        )

    assert result["success"] is True
    assert "<main>" in result["content"]
    assert "ignore" not in result["content"]
    assert result["truncated"] is True
    assert result["remaining"] > 0


def test_fetch_text_and_markdown_remove_executable_markup():
    response = ExternalResponse(
        text=(
            "<html><script>alert(1)</script><body>"
            "<h1>Runbook</h1><ul><li>Drain traffic</li></ul>"
            "</body></html>"
        ),
        content_type="text/html",
    )
    with patch.object(http, "safe_get", return_value=response):
        text_result = fetch_tools.fetch_txt.invoke(
            {"url": "https://93.184.216.34/runbook"}
        )
        markdown_result = fetch_tools.fetch_markdown.invoke(
            {"url": "https://93.184.216.34/runbook"}
        )

    assert text_result["content"] == "RunbookDrain traffic"
    assert "# Runbook" in markdown_result["content"]
    assert "* Drain traffic" in markdown_result["content"]
    assert "alert" not in markdown_result["content"]


def test_fetch_json_supports_valid_vendor_content_type_and_truncated_payload():
    complete = ExternalResponse(
        text='{"service": "postgres", "healthy": true}',
        content_type="application/vnd.bk.status+json",
    )
    truncated = ExternalResponse(
        text='{"service": "postgres", "healthy": true}',
        content_type="application/json",
    )
    with patch.object(http, "safe_get", side_effect=[complete, truncated]):
        parsed = fetch_tools.fetch_json.invoke(
            {"url": "https://93.184.216.34/status.json"}
        )
        partial = fetch_tools.fetch_json.invoke(
            {
                "url": "https://93.184.216.34/status.json",
                "max_length": 12,
            }
        )

    assert parsed["data"] == {"service": "postgres", "healthy": True}
    assert parsed["truncated"] is False
    assert partial["success"] is True
    assert partial["truncated"] is True
    assert partial["content"] == '{"service": '
    assert "无法解析" in partial["warning"]


def test_fetch_json_rejects_non_json_response():
    response = ExternalResponse(
        text="<html>gateway error</html>",
        content_type="text/html",
    )
    with patch.object(http, "safe_get", return_value=response):
        result = fetch_tools.fetch_json.invoke(
            {"url": "https://93.184.216.34/status"}
        )

    assert result == {
        "success": False,
        "error": "响应的Content-Type不是JSON: text/html",
        "url": "https://93.184.216.34/result",
    }


@pytest.mark.parametrize(
    ("format_name", "body", "expected"),
    [
        ("html", "<p>ready</p>", "<p>ready</p>"),
        ("txt", "<p>ready</p>", "ready"),
        ("markdown", "<h2>ready</h2>", "## ready"),
        ("json", '{"ready": true}', {"ready": True}),
    ],
)
def test_fetch_batch_formats_each_supported_content_type(
    format_name,
    body,
    expected,
):
    response = ExternalResponse(text=body)
    with patch.object(http, "safe_get", return_value=response):
        result = fetch_tools.fetch_batch.invoke(
            {
                "urls": ["https://93.184.216.34/one"],
                "format": format_name,
            }
        )

    assert result["total"] == 1
    assert result["succeeded"] == 1
    assert result["failed"] == 0
    assert result["results"][0]["data"] == expected


def test_fetch_batch_isolates_request_and_json_failures():
    bad_json = ExternalResponse(text="{not-json")
    with patch.object(
        http,
        "safe_get",
        side_effect=[
            requests.exceptions.Timeout,
            bad_json,
        ],
    ):
        result = fetch_tools.fetch_batch.invoke(
            {
                "urls": [
                    "https://93.184.216.34/slow",
                    "https://93.184.216.34/bad-json",
                ],
                "format": "json",
            }
        )

    assert result["succeeded"] == 0
    assert result["failed"] == 2
    assert result["results"][0]["error"] == "请求超时（30秒）"
    assert "JSON解析失败" in result["results"][1]["error"]
