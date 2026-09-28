"""智能体 IM 渠道附图：URL 改写与按渠道投递。"""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from apps.opspilot.services import skill_channel_im_media as im_media
from apps.opspilot.services.wiki import parsed_media_service


@pytest.fixture(autouse=True)
def _proxy_secret(monkeypatch):
    monkeypatch.setattr(parsed_media_service, "_media_proxy_secret", lambda: b"test-secret")
    monkeypatch.setattr(im_media, "_try_minio_presign", lambda locator: None)


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
