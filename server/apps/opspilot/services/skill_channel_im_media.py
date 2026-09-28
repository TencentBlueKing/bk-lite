"""智能体 IM / 嵌入式渠道的知识库附图处理。

Web/平台同源可渲染相对 `/api/proxy/...`；企微/钉钉/飞书等需要：
1. 公网可抓取的绝对 URL（优先 MinIO 预签名，其次 WEB_BASE_URL + 代理签名）；
2. 部分平台还要把图片上传为临时素材再发 image 消息。
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from urllib.parse import parse_qs, unquote, urlparse

import requests
from django.conf import settings

from apps.core.logger import opspilot_logger as logger
from apps.opspilot.services.wiki.parsed_media_service import _try_minio_presign, build_media_proxy_url, open_media_bytes, verify_media_proxy_request

_MD_IMAGE_RE = re.compile(r"!\[([^\]]*)\]\(([^)]+)\)")
_PROXY_PATH_PREFIX = "/api/proxy/opspilot/wiki_mgmt/media/"
_MAX_IM_IMAGES = 4
_FETCH_TIMEOUT_SECONDS = 15


@dataclass(frozen=True)
class ImImage:
    alt: str
    source_url: str
    public_url: str
    content: bytes
    content_type: str


def web_public_base() -> str:
    return (getattr(settings, "WEB_BASE_URL", "") or "").rstrip("/")


def absolute_media_proxy_url(locator: str) -> str:
    """同源代理 URL；配置了 WEB_BASE_URL 时返回绝对地址，便于嵌入式/外链。"""

    path = build_media_proxy_url(locator)
    base = web_public_base()
    if base and path.startswith("/"):
        return f"{base}{path}"
    return path


def public_media_url(locator: str) -> str:
    """IM 优先 MinIO 预签名绝对 URL；否则退回绝对代理 URL。"""

    locator = (locator or "").lstrip("/")
    if not locator.startswith("wiki/media/"):
        return locator
    signed = _try_minio_presign(locator)
    if signed and signed.startswith(("http://", "https://")):
        return signed
    return absolute_media_proxy_url(locator)


def _locator_from_proxy_url(url: str) -> str | None:
    value = (url or "").strip()
    if not value:
        return None
    if value.startswith("wiki/media/"):
        return value
    # 相对代理路径补 host，便于 urlparse 取 query
    if value.startswith("/api/proxy/"):
        value = "http://local.invalid" + value
    elif "wiki_mgmt/media" in value and "://" not in value:
        value = "http://local.invalid" + (value if value.startswith("/") else f"/{value}")
    parsed = urlparse(value)
    if "wiki_mgmt/media" not in (parsed.path or ""):
        return None
    query = parse_qs(parsed.query or "")
    locator = (query.get("locator") or [None])[0]
    if not locator:
        return None
    locator = unquote(locator)
    if not locator.startswith("wiki/media/"):
        return None
    exp = (query.get("exp") or [None])[0]
    sig = (query.get("sig") or [None])[0]
    if exp and sig and not verify_media_proxy_request(locator, exp, sig):
        logger.info("im media proxy signature stale, fallback to locator open locator=%s", locator)
    return locator


def resolve_public_image_url(url: str) -> str:
    raw = (url or "").strip()
    if not raw:
        return raw
    if raw.startswith("wiki/media/"):
        return public_media_url(raw)
    locator = _locator_from_proxy_url(raw)
    if locator:
        return public_media_url(locator)
    if raw.startswith("/") and web_public_base():
        return f"{web_public_base()}{raw}"
    return raw


def rewrite_markdown_images_for_im(text: str) -> str:
    """把回答中的 Markdown 图片改写成 IM 可抓取的绝对 URL。"""

    body = text or ""

    def repl(match: re.Match) -> str:
        alt = match.group(1) or ""
        url = resolve_public_image_url(match.group(2) or "")
        return f"![{alt}]({url})"

    return _MD_IMAGE_RE.sub(repl, body)


def strip_markdown_images(text: str) -> str:
    body = _MD_IMAGE_RE.sub("", text or "")
    return re.sub(r"\n{3,}", "\n\n", body).strip()


def iter_markdown_images(text: str) -> list[tuple[str, str]]:
    seen = set()
    out = []
    for match in _MD_IMAGE_RE.finditer(text or ""):
        alt = (match.group(1) or "").strip()
        url = (match.group(2) or "").strip()
        if not url or url in seen:
            continue
        seen.add(url)
        out.append((alt, url))
        if len(out) >= _MAX_IM_IMAGES:
            break
    return out


def _load_image_bytes(url: str) -> tuple[bytes, str] | None:
    locator = None
    raw = (url or "").strip()
    if raw.startswith("wiki/media/"):
        locator = raw
    else:
        locator = _locator_from_proxy_url(raw)

    if locator:
        try:
            fp, content_type = open_media_bytes(locator)
        except Exception:
            logger.exception("im media open failed locator=%s", locator)
            return None
        try:
            data = fp.read()
        finally:
            close = getattr(fp, "close", None)
            if callable(close):
                close()
        if not data:
            return None
        return data, content_type or "application/octet-stream"

    public = resolve_public_image_url(raw)
    if not public.startswith(("http://", "https://")):
        return None
    try:
        response = requests.get(public, timeout=_FETCH_TIMEOUT_SECONDS)
        response.raise_for_status()
    except Exception:
        logger.exception("im media http fetch failed")
        return None
    content_type = (response.headers.get("Content-Type") or "application/octet-stream").split(";")[0].strip()
    return response.content, content_type


def collect_im_images(text: str) -> list[ImImage]:
    images: list[ImImage] = []
    for alt, url in iter_markdown_images(text):
        loaded = _load_image_bytes(url)
        if not loaded:
            continue
        content, content_type = loaded
        images.append(
            ImImage(
                alt=alt or "附图",
                source_url=url,
                public_url=resolve_public_image_url(url),
                content=content,
                content_type=content_type,
            )
        )
    return images


def prepare_im_markdown(text: str) -> tuple[str, list[ImImage]]:
    """返回（改写后的 markdown，可上传的图片列表）。"""

    images = collect_im_images(text or "")
    return rewrite_markdown_images_for_im(text or ""), images


def deliver_skill_channel_im_reply(
    *,
    channel_type: str,
    handler,
    reply_text: str,
    sender_id: str,
    config: dict | None,
    webhook_url: str | None = None,
) -> None:
    """按渠道投递文本 + 附图。失败只记日志，不阻断主文本已发送路径由调用方决定。"""

    config = dict(config or {})
    markdown, images = prepare_im_markdown(reply_text or "")
    channel_type = (channel_type or "").strip()

    if channel_type == "dingtalk":
        target = webhook_url or config.get("webhook_url") or ""
        if target and markdown:
            handler.send_message(target, "markdown", {"title": "机器人回复", "text": markdown})
        return

    if channel_type == "feishu":
        text_body = strip_markdown_images(markdown)
        if text_body:
            handler.send_text_reply(text_body, sender_id, config)
        for image in images:
            try:
                handler.send_image_reply(image, sender_id, config)
            except Exception:
                logger.exception("feishu image reply failed channel=%s", getattr(handler, "channel_id", None))
        if not text_body and not images and markdown:
            handler.send_text_reply(markdown, sender_id, config)
        return

    if channel_type in {"enterprise_wechat", "enterprise_wechat_aibot"}:
        text_body = strip_markdown_images(markdown) if images else markdown
        # aibot 仅有 response_url markdown；保留绝对 URL 的 markdown 图语法作尽力展示。
        if channel_type == "enterprise_wechat_aibot":
            handler.send_reply(markdown, sender_id, config)
            return
        if text_body:
            handler.send_reply(text_body, sender_id, config)
        for image in images:
            try:
                handler.send_image_reply(image, sender_id, config)
            except Exception:
                logger.exception("wechat image reply failed channel=%s", getattr(handler, "channel_id", None))
        return

    if channel_type == "wechat_official":
        text_body = strip_markdown_images(markdown) if images else markdown
        if text_body:
            handler.send_reply(text_body, sender_id, config)
        for image in images:
            try:
                handler.send_image_reply(image, sender_id, config)
            except Exception:
                logger.exception("wechat official image reply failed channel=%s", getattr(handler, "channel_id", None))
        return

    # 未知渠道：保持旧行为
    if hasattr(handler, "send_reply"):
        handler.send_reply(markdown or reply_text, sender_id, config)
