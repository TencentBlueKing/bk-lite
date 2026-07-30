from pathlib import Path

import fitz
import pytest

from apps.operation_analysis.services.dashboard_report_renderer import (
    DashboardChromiumRenderer,
    DashboardRenderContractError,
    DashboardRenderRequest,
)


def write_valid_pdf(path: Path) -> None:
    document = fitz.open()
    page = document.new_page()
    page.insert_text((72, 72), "ready")
    document.save(path)
    document.close()
    with path.open("ab") as file_handle:
        file_handle.write(b"\0" * 10_000)


class FakePage:
    def __init__(self, signal, output_path, *, pdf_error=None):
        self.signal = signal
        self.output_path = output_path
        self.pdf_error = pdf_error
        self.binding = None
        self.pdf_calls = 0
        self.pdf_kwargs = None
        self.goto_wait_until = None
        self.listener_registered = False

    async def expose_binding(self, _name, binding):
        self.binding = binding

    async def add_init_script(self, _script):
        self.listener_registered = True

    async def goto(self, _url, *, wait_until, timeout):
        self.goto_wait_until = wait_until
        assert timeout == 120_000
        await self.binding({}, self.signal)

    async def pdf(self, **kwargs):
        self.pdf_calls += 1
        self.pdf_kwargs = kwargs
        if self.pdf_error:
            raise self.pdf_error
        write_valid_pdf(self.output_path)


class FakeRequestContext:
    async def get(self, _url):
        return FakeResponse({"csrfToken": "csrf"})

    async def post(self, url, **_kwargs):
        if url.endswith("/render-token-exchange/"):
            return FakeResponse(
                {
                    "data": {
                        "session_user": {
                            "id": 1,
                            "username": "test",
                            "token": "scoped-session",
                        }
                    }
                }
            )
        return FakeResponse({"url": "http://web.test/render"})


class FakeResponse:
    ok = True
    status = 200

    def __init__(self, payload):
        self.payload = payload

    async def json(self):
        return self.payload


class FakeContext:
    def __init__(self, page):
        self.page = page
        self.request = FakeRequestContext()

    async def new_page(self):
        return self.page


class FakeBrowser:
    def __init__(self, page):
        self.context = FakeContext(page)
        self.closed = False

    async def new_context(self, **kwargs):
        assert kwargs == {
            "viewport": {"width": 1440, "height": 900},
            "color_scheme": "light",
            "locale": "zh-CN",
        }
        return self.context

    async def close(self):
        self.closed = True


class FakeChromium:
    def __init__(self, browser):
        self.browser = browser

    async def launch(self, **_kwargs):
        return self.browser


class FakePlaywright:
    def __init__(self, browser):
        self.chromium = FakeChromium(browser)


class FakePlaywrightManager:
    def __init__(self, browser):
        self.playwright = FakePlaywright(browser)

    async def __aenter__(self):
        return self.playwright

    async def __aexit__(self, *_args):
        return None


def _request(tmp_path, signal):
    output_path = tmp_path / "report.pdf"
    page = FakePage(signal, output_path)
    browser = FakeBrowser(page)
    request = DashboardRenderRequest(
        execution_id=8,
        render_url="http://web.test/ops-analysis/render/execution/8",
        output_path=output_path,
        render_token="one-time-token",
    )
    return request, page, browser


def test_report_ready_is_the_only_pdf_success_signal(tmp_path):
    request, page, browser = _request(
        tmp_path,
        {
            "type": "report-ready",
            "dashboardId": "8",
            "widgets": [
                {"widgetId": "chart-1", "status": "ready"},
                {"widgetId": "empty-1", "status": "empty"},
            ],
        },
    )
    renderer = DashboardChromiumRenderer(
        playwright_factory=lambda: FakePlaywrightManager(browser)
    )

    renderer.render(request)

    assert page.goto_wait_until == "commit"
    assert page.listener_registered is True
    assert page.pdf_calls == 1
    assert page.pdf_kwargs["format"] == "A4"
    assert page.pdf_kwargs["landscape"] is True
    assert page.pdf_kwargs["print_background"] is True
    assert page.pdf_kwargs["prefer_css_page_size"] is False
    assert page.pdf_kwargs["path"] == str(request.output_path) or page.pdf_kwargs[
        "path"
    ].endswith("report.pdf")
    assert request.output_path.is_file()
    assert browser.closed is True


def test_report_failed_prevents_page_pdf(tmp_path):
    request, page, browser = _request(
        tmp_path,
        {
            "type": "report-failed",
            "dashboardId": "8",
            "widgets": [],
            "widgetId": "chart-1",
            "error": "query failed",
        },
    )
    renderer = DashboardChromiumRenderer(
        playwright_factory=lambda: FakePlaywrightManager(browser)
    )

    with pytest.raises(
        DashboardRenderContractError,
        match="widget=chart-1",
    ) as exc_info:
        renderer.render(request)

    assert "query failed" not in str(exc_info.value)
    assert page.pdf_calls == 0
    assert not request.output_path.exists()
    assert browser.closed is True
