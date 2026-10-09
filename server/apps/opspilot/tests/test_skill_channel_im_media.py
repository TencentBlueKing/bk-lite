"""智能体 IM 渠道附图：URL 改写与按渠道投递。"""

from __future__ import annotations

import io
import logging
from types import SimpleNamespace
from unittest.mock import MagicMock
from urllib.parse import quote, urlparse

import pytest
import requests

from apps.core.logger import safe_exception_info
from apps.core.utils.ssrf_validator import SSRFError, SSRFValidator
from apps.opspilot.services import skill_channel_im_media as im_media
from apps.opspilot.services.wiki import parsed_media_service

_MINIO_PRESIGN = (
    "http://minio.internal:9000/munchkin-private/wiki/media/obj"
    "?AWSAccessKeyId=AKIA_SENTINEL&Signature=SIG_SENTINEL&Expires=1893456000"
)
_LOCATOR = "wiki/media/1/2/" + ("d" * 64) + ".png"


@pytest.fixture(autouse=True)
def _proxy_secret(monkeypatch):
    monkeypatch.setattr(parsed_media_service, "_media_proxy_secret", lambda: b"test-secret")
    monkeypatch.setattr(im_media, "_try_minio_presign", lambda locator: None, raising=False)


def test_rewrite_markdown_images_uses_absolute_proxy(settings, monkeypatch):
    settings.WEB_BASE_URL = "https://web.example"
    locator = "wiki/media/1/2/" + ("a" * 64) + ".png"
    relative = parsed_media_service.build_media_proxy_url(locator)
    # build_media_proxy_url 在配置 WEB_BASE_URL 时已绝对化
    assert relative.startswith("https://web.example/api/proxy/")

    body = f"见下图\n\n![流程图]({relative})\n\n完"
    out = im_media.rewrite_markdown_images_for_im(body)
    assert "![流程图](https://web.example/api/proxy/" in out


def test_rewrite_relative_proxy_path_with_web_base(settings):
    settings.WEB_BASE_URL = ""
    locator = "wiki/media/1/2/" + ("b" * 64) + ".png"
    relative = parsed_media_service.build_media_proxy_url(locator)
    assert relative.startswith("/api/proxy/")

    settings.WEB_BASE_URL = "https://web.example"
    out = im_media.rewrite_markdown_images_for_im(f"![x]({relative})")
    assert out.startswith("![x](https://web.example/api/proxy/")


def test_build_media_proxy_url_absolute_for_embed(settings):
    """嵌入式跨域依赖 WEB_BASE_URL 产出绝对代理 URL。"""

    settings.WEB_BASE_URL = "https://portal.example"
    locator = "wiki/media/1/2/" + ("e" * 64) + ".png"
    url = parsed_media_service.build_media_proxy_url(locator)
    assert url.startswith("https://portal.example/api/proxy/opspilot/wiki_mgmt/media/")


def test_strip_markdown_images():
    text = "前言\n\n![a](/api/proxy/x)\n\n后记"
    assert im_media.strip_markdown_images(text) == "前言\n\n后记"


def test_deliver_feishu_sends_text_then_images(monkeypatch):
    settings_web = "https://web.example"
    monkeypatch.setattr(im_media, "web_public_base", lambda: settings_web)
    image = im_media.ImImage(
        alt="图",
        source_url="/api/proxy/x",
        public_url="https://web.example/api/proxy/x",
        content=b"png-bytes",
        content_type="image/png",
    )
    monkeypatch.setattr(im_media, "prepare_im_markdown", lambda text: ("正文\n\n![图](https://x)", [image]))

    handler = MagicMock()
    im_media.deliver_skill_channel_im_reply(
        channel_type="feishu",
        handler=handler,
        reply_text="ignored",
        sender_id="ou_1",
        config={"message_id": "om_1"},
    )
    handler.send_text_reply.assert_called_once_with("正文", "ou_1", {"message_id": "om_1"})
    handler.send_image_reply.assert_called_once()
    assert handler.send_image_reply.call_args.args[0] is image


def test_deliver_wechat_strips_md_images_and_sends_media(monkeypatch):
    image = im_media.ImImage(
        alt="图",
        source_url="wiki/media/1/2/" + ("c" * 64) + ".png",
        public_url="https://cdn/x",
        content=b"bytes",
        content_type="image/png",
    )
    monkeypatch.setattr(
        im_media,
        "prepare_im_markdown",
        lambda text: ("hello\n\n![图](https://cdn/x)", [image]),
    )
    handler = MagicMock()
    im_media.deliver_skill_channel_im_reply(
        channel_type="enterprise_wechat",
        handler=handler,
        reply_text="ignored",
        sender_id="ZhangSan",
        config={"agent_id": "1"},
    )
    handler.send_reply.assert_called_once_with("hello", "ZhangSan", {"agent_id": "1"})
    handler.send_image_reply.assert_called_once_with(image, "ZhangSan", {"agent_id": "1"})


def test_deliver_dingtalk_keeps_absolute_md_images(monkeypatch):
    monkeypatch.setattr(
        im_media,
        "prepare_im_markdown",
        lambda text: ("见 ![a](https://cdn/a.png)", []),
    )
    handler = MagicMock()
    im_media.deliver_skill_channel_im_reply(
        channel_type="dingtalk",
        handler=handler,
        reply_text="ignored",
        sender_id="u",
        config={},
        webhook_url="https://oapi.dingtalk.com/robot/send?access_token=t",
    )
    handler.send_message.assert_called_once()
    args = handler.send_message.call_args.args
    assert args[1] == "markdown"
    assert "https://cdn/a.png" in args[2]["text"]


def test_collect_im_images_opens_locator(monkeypatch):
    locator = "wiki/media/1/2/" + ("d" * 64) + ".png"
    fp = SimpleNamespace(read=lambda: b"img", close=lambda: None)
    monkeypatch.setattr(im_media, "open_media_bytes", lambda loc: (fp, "image/png"))
    images = im_media.collect_im_images(f"![流程图]({locator})")
    assert len(images) == 1
    assert images[0].content == b"img"
    assert images[0].alt == "流程图"


def _spy_http_fetch(monkeypatch):
    fetched = []

    def spy_get(url, **kwargs):
        fetched.append(url)
        raise RuntimeError("blocked fetch")

    def spy_request(method, url, **kwargs):
        fetched.append(url)
        raise RuntimeError("blocked fetch")

    monkeypatch.setattr(requests, "get", spy_get)
    monkeypatch.setattr(requests, "request", spy_request)
    monkeypatch.setattr("apps.core.utils.safe_requests.requests.request", spy_request)
    monkeypatch.setattr("apps.core.utils.safe_requests.requests.get", spy_get)
    return fetched


def test_collect_rejects_loopback_http_url(monkeypatch):
    fetched = _spy_http_fetch(monkeypatch)
    images = im_media.collect_im_images("![x](http://127.0.0.1/secret.png)")
    assert images == []
    assert fetched == []


def test_collect_rejects_cloud_metadata_http_url(monkeypatch):
    fetched = _spy_http_fetch(monkeypatch)
    images = im_media.collect_im_images("![x](http://169.254.169.254/latest/meta-data/)")
    assert images == []
    assert fetched == []


def test_collect_rejects_redirect_to_private_network(monkeypatch):
    fetched = []

    def validate(url, allowlist=None):
        host = (urlparse(url).hostname or "").lower()
        if host in {"10.1.2.3", "127.0.0.1", "169.254.169.254"}:
            raise SSRFError("blocked")
        if host == "cdn.example":
            return url
        return SSRFValidator.validate.__func__(SSRFValidator, url, allowlist=allowlist)

    def fake_request(method, url, **kwargs):
        fetched.append(url)
        if "10.1.2.3" in url:
            raise AssertionError("must not follow redirect onto intranet")
        resp = requests.Response()
        resp.status_code = 302
        resp.headers["Location"] = "http://10.1.2.3/secret.png"
        resp._content = b""
        resp.raw = io.BytesIO(b"")
        return resp

    monkeypatch.setattr(SSRFValidator, "validate", staticmethod(validate))
    monkeypatch.setattr(requests, "request", fake_request)
    monkeypatch.setattr(requests, "get", fake_request)
    monkeypatch.setattr("apps.core.utils.safe_requests.requests.request", fake_request)

    images = im_media.collect_im_images("![x](https://cdn.example/a.png)")
    assert images == []
    assert not any("10.1.2.3" in url for url in fetched)


def test_collect_rejects_oversized_http_body(monkeypatch):
    def validate(url, allowlist=None):
        return url

    body = b"x" * (2 * 1024 * 1024 + 8)

    def fake_request(method, url, **kwargs):
        resp = requests.Response()
        resp.status_code = 200
        resp.headers["Content-Type"] = "image/png"
        resp._content = body
        resp.raw = io.BytesIO(body)
        return resp

    monkeypatch.setattr(SSRFValidator, "validate", staticmethod(validate))
    monkeypatch.setattr(requests, "request", fake_request)
    monkeypatch.setattr(requests, "get", fake_request)
    monkeypatch.setattr("apps.core.utils.safe_requests.requests.request", fake_request)

    images = im_media.collect_im_images("![x](https://cdn.example/big.png)")
    assert images == []


def test_rewrite_and_dingtalk_body_omit_minio_presign(settings, monkeypatch):
    settings.WEB_BASE_URL = "https://web.example"
    monkeypatch.setattr(im_media, "_try_minio_presign", lambda locator: _MINIO_PRESIGN)
    monkeypatch.setattr(parsed_media_service, "_try_minio_presign", lambda locator: _MINIO_PRESIGN)
    monkeypatch.setattr(im_media, "collect_im_images", lambda text: [])

    rewritten = im_media.rewrite_markdown_images_for_im(f"见 ![a]({_LOCATOR})")
    assert "minio.internal" not in rewritten
    assert "AWSAccessKeyId" not in rewritten
    assert "Signature=" not in rewritten
    assert rewritten.startswith("见 ![a](https://web.example/api/proxy/")

    handler = MagicMock()
    im_media.deliver_skill_channel_im_reply(
        channel_type="dingtalk",
        handler=handler,
        reply_text=f"见 ![a]({_LOCATOR})",
        sender_id="u",
        config={},
        webhook_url="https://oapi.dingtalk.com/robot/send?access_token=t",
    )
    text = handler.send_message.call_args.args[2]["text"]
    assert "minio.internal" not in text
    assert "AWSAccessKeyId" not in text
    assert "Signature=" not in text
    assert "https://web.example/api/proxy/" in text


def test_deliver_aibot_body_omits_minio_presign(settings, monkeypatch):
    settings.WEB_BASE_URL = "https://web.example"
    monkeypatch.setattr(im_media, "_try_minio_presign", lambda locator: _MINIO_PRESIGN)
    monkeypatch.setattr(parsed_media_service, "_try_minio_presign", lambda locator: _MINIO_PRESIGN)
    monkeypatch.setattr(im_media, "collect_im_images", lambda text: [])

    handler = MagicMock()
    im_media.deliver_skill_channel_im_reply(
        channel_type="enterprise_wechat_aibot",
        handler=handler,
        reply_text=f"见 ![a]({_LOCATOR})",
        sender_id="u",
        config={},
    )
    text = handler.send_reply.call_args.args[0]
    assert "minio.internal" not in text
    assert "AWSAccessKeyId" not in text
    assert "Signature=" not in text
    assert "https://web.example/api/proxy/" in text


def test_deliver_feishu_keeps_proxy_url_when_collect_empty(monkeypatch):
    markdown = "正文\n\n![图](https://web.example/api/proxy/opspilot/wiki_mgmt/media/?locator=wiki&exp=1&sig=ok)"
    monkeypatch.setattr(im_media, "prepare_im_markdown", lambda text: (markdown, []))
    handler = MagicMock()
    im_media.deliver_skill_channel_im_reply(
        channel_type="feishu",
        handler=handler,
        reply_text="ignored",
        sender_id="ou_1",
        config={"message_id": "om_1"},
    )
    handler.send_text_reply.assert_called_once_with(markdown, "ou_1", {"message_id": "om_1"})
    handler.send_image_reply.assert_not_called()


def test_deliver_feishu_falls_back_to_proxy_url_when_send_image_fails(monkeypatch):
    markdown = "正文\n\n![图](https://web.example/api/proxy/opspilot/wiki_mgmt/media/?locator=wiki&exp=1&sig=ok)"
    image = im_media.ImImage(
        alt="图",
        source_url="wiki/media/x",
        public_url="https://web.example/api/proxy/opspilot/wiki_mgmt/media/?locator=wiki&exp=1&sig=ok",
        content=b"png-bytes",
        content_type="image/png",
    )
    monkeypatch.setattr(im_media, "prepare_im_markdown", lambda text: (markdown, [image]))
    handler = MagicMock()
    handler.send_image_reply.side_effect = RuntimeError("upload failed")
    im_media.deliver_skill_channel_im_reply(
        channel_type="feishu",
        handler=handler,
        reply_text="ignored",
        sender_id="ou_1",
        config={"message_id": "om_1"},
    )
    texts = [call.args[0] for call in handler.send_text_reply.call_args_list]
    assert any("https://web.example/api/proxy/" in text for text in texts)
    handler.send_image_reply.assert_called_once()


def test_collect_opens_locator_from_valid_proxy_signature(monkeypatch):
    opened = []

    def open_bytes(locator):
        opened.append(locator)
        return SimpleNamespace(read=lambda: b"img", close=lambda: None), "image/png"

    monkeypatch.setattr(im_media, "open_media_bytes", open_bytes)
    url = parsed_media_service.build_media_proxy_url(_LOCATOR)
    images = im_media.collect_im_images(f"![流程图]({url})")
    assert len(images) == 1
    assert images[0].content == b"img"
    assert opened == [_LOCATOR]


def test_collect_rejects_non_image_http_content_type(monkeypatch):
    def validate(url, allowlist=None):
        return url

    def fake_request(method, url, **kwargs):
        resp = requests.Response()
        resp.status_code = 200
        resp.headers["Content-Type"] = "text/html"
        body = b"<html>not-an-image</html>"
        resp._content = body
        resp.raw = io.BytesIO(body)
        return resp

    monkeypatch.setattr(SSRFValidator, "validate", staticmethod(validate))
    monkeypatch.setattr(requests, "request", fake_request)
    monkeypatch.setattr("apps.core.utils.safe_requests.requests.request", fake_request)

    images = im_media.collect_im_images("![x](https://cdn.example/page.html)")
    assert images == []


def test_collect_rejects_proxy_url_with_missing_signature(monkeypatch):
    opened = []

    def open_bytes(locator):
        opened.append(locator)
        return SimpleNamespace(read=lambda: b"img", close=lambda: None), "image/png"

    monkeypatch.setattr(im_media, "open_media_bytes", open_bytes)
    url = "/api/proxy/opspilot/wiki_mgmt/media/?locator=" + quote(_LOCATOR, safe="")
    images = im_media.collect_im_images(f"![x]({url})")
    assert images == []
    assert opened == []


def test_collect_rejects_proxy_url_with_expired_signature(monkeypatch):
    opened = []

    def open_bytes(locator):
        opened.append(locator)
        return SimpleNamespace(read=lambda: b"img", close=lambda: None), "image/png"

    monkeypatch.setattr(im_media, "open_media_bytes", open_bytes)
    url = parsed_media_service.build_media_proxy_url(_LOCATOR, expires_in=-60)
    images = im_media.collect_im_images(f"![x]({url})")
    assert images == []
    assert opened == []


def test_http_fetch_failure_log_omits_url_secrets(monkeypatch, caplog):
    secret_url = (
        "https://cdn.example/obj?AWSAccessKeyId=AKIA_SENTINEL&Signature=SIG_SENTINEL&sig=SIG_QUERY"
    )

    def validate(url, allowlist=None):
        return url

    def fake_request(method, url, **kwargs):
        raise requests.RequestException(f"failed for {secret_url}")

    monkeypatch.setattr(SSRFValidator, "validate", staticmethod(validate))
    monkeypatch.setattr(requests, "request", fake_request)
    monkeypatch.setattr(requests, "get", fake_request)
    monkeypatch.setattr("apps.core.utils.safe_requests.requests.request", fake_request)

    caplog.set_level(logging.DEBUG, logger="opspilot")
    images = im_media.collect_im_images(f"![x]({secret_url})")
    assert images == []

    formatter = logging.Formatter()
    opspilot_output = []
    for record in caplog.records:
        if record.name != "opspilot":
            continue
        rendered = record.getMessage()
        formatted = formatter.format(record)
        opspilot_output.extend([rendered, formatted, str(record.msg), str(record.args)])
        if record.exc_info:
            opspilot_output.append(formatter.format(record))
            safe_type, safe_error, safe_tb = safe_exception_info(record.exc_info[1])
            opspilot_output.append(str(safe_error))
    blob = "\n".join(opspilot_output)
    assert "AWSAccessKeyId" not in blob
    assert "AKIA_SENTINEL" not in blob
    assert "SIG_SENTINEL" not in blob
    assert "sig=SIG_QUERY" not in blob
    assert "cdn.example" in caplog.text
    assert any(
        record.name == "opspilot" and "error_type=" in (record.msg if isinstance(record.msg, str) else "")
        for record in caplog.records
    )
