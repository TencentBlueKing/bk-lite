"""智能体 IM / 嵌入式渠道的知识库附图处理。

Web/平台同源可渲染相对 `/api/proxy/...`；企微/钉钉/飞书等需要：
1. 渠道正文中的公网 URL 只用 WEB_BASE_URL + HMAC 媒体代理；
2. worker 取字节优先 open_media_bytes；非 locator 的 HTTP 走 SSRF 校验；
3. 部分平台还要把图片上传为临时素材再发 image 消息。
"""

from __future__ import annotations

import base64
import hashlib
import re
from dataclasses import dataclass
from urllib.parse import parse_qs, unquote, urlparse

from django.conf import settings

from apps.core.logger import opspilot_logger as logger
from apps.core.logger import safe_exception_info, safe_log_value
from apps.core.utils.safe_requests import safe_get
from apps.opspilot.services.wiki.parsed_media_service import build_media_proxy_url, open_media_bytes, verify_media_proxy_request

_MD_IMAGE_RE = re.compile(r"!\[([^\]]*)\]\(([^)]+)\)")
_MAX_IM_IMAGES = 4
_FETCH_TIMEOUT_SECONDS = 15
_MAX_IM_IMAGE_BYTES = 2 * 1024 * 1024
_MAX_WECOM_STREAM_IMAGE_BYTES = 10 * 1024 * 1024
_MAX_WECOM_STREAM_IMAGES = 10
_ALLOWED_IM_CONTENT_TYPES = frozenset({"image/jpeg", "image/png", "image/gif", "image/webp"})
_WECOM_STREAM_IMAGE_TYPES = frozenset({"image/jpeg", "image/png"})
_WECOM_UPLOAD_IMAGE_TYPES = frozenset({"image/jpeg", "image/png", "image/gif"})


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
    """渠道正文只用 WEB_BASE_URL + HMAC 代理 URL，不写入 MinIO 预签名。"""

    locator = (locator or "").lstrip("/")
    if not locator.startswith("wiki/media/"):
        return locator
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
    if not verify_media_proxy_request(locator, exp, sig):
        logger.debug("im media proxy signature rejected locator=%s", locator)
        return None
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


def _response_content_type(response) -> str:
    return (response.headers.get("Content-Type") or "").split(";", 1)[0].strip().lower()


def _read_limited_image_body(response) -> bytes | None:
    length = response.headers.get("Content-Length")
    if length not in (None, ""):
        try:
            if int(length) > _MAX_IM_IMAGE_BYTES:
                return None
        except (TypeError, ValueError):
            return None
    buf = bytearray()
    for chunk in response.iter_content(chunk_size=64 * 1024):
        if not chunk:
            continue
        buf.extend(chunk)
        if len(buf) > _MAX_IM_IMAGE_BYTES:
            return None
    if not buf:
        return None
    return bytes(buf)


def _load_http_image_bytes(url: str) -> tuple[bytes, str] | None:
    response = None
    try:
        response = safe_get(
            url,
            timeout=_FETCH_TIMEOUT_SECONDS,
            stream=True,
            allow_redirects=True,
        )
        if getattr(response, "status_code", None) != 200:
            return None
        content_type = _response_content_type(response)
        if content_type not in _ALLOWED_IM_CONTENT_TYPES:
            return None
        data = _read_limited_image_body(response)
        if not data:
            return None
        return data, content_type
    except Exception as exc:
        logger.warning(
            "im media http fetch failed host=%s error_type=%s failed_stage=%s",
            safe_log_value(urlparse(url).hostname or ""),
            type(exc).__name__,
            "http_fetch",
            exc_info=safe_exception_info(exc),
        )
        return None
    finally:
        close = getattr(response, "close", None) if response is not None else None
        if callable(close):
            close()


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
        except Exception as exc:
            logger.debug(
                "im media open failed locator=%s error_type=%s failed_stage=%s",
                locator,
                type(exc).__name__,
                "open_bytes",
            )
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
    return _load_http_image_bytes(public)


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


def _wecom_stream_image_type(content: bytes, content_type: str) -> str | None:
    """企微流式图片只收 JPG/PNG。外链写进 markdown 会被客户端拦截。"""
    kind = (content_type or "").split(";", 1)[0].strip().lower()
    if kind == "image/jpg":
        kind = "image/jpeg"
    if kind in _WECOM_STREAM_IMAGE_TYPES:
        return kind
    if content.startswith(b"\x89PNG\r\n\x1a\n"):
        return "image/png"
    if content.startswith(b"\xff\xd8\xff"):
        return "image/jpeg"
    return None


def wecom_stream_image_items(images: list[ImImage]) -> list[dict]:
    """流式结束帧的 msg_item。md5 对原始字节计算，base64 不带 data: 前缀。"""
    items = []
    for image in images:
        content = image.content or b""
        if not content or len(content) > _MAX_WECOM_STREAM_IMAGE_BYTES:
            continue
        if _wecom_stream_image_type(content, image.content_type) is None:
            continue
        items.append(
            {
                "msgtype": "image",
                "image": {
                    "base64": base64.b64encode(content).decode("ascii"),
                    "md5": hashlib.md5(content).hexdigest(),
                },
            }
        )
        if len(items) >= _MAX_WECOM_STREAM_IMAGES:
            break
    return items


FEISHU_IMAGE_FAILED_TEXT = "图片发送失败，请稍后重试"


def feishu_outbound(text: str) -> tuple[str, list[ImImage]]:
    """飞书 text 不渲染 Markdown 图片。正文去掉外链，图片另发 image 消息。"""
    markdown, images = prepare_im_markdown(text or "")
    visible = strip_markdown_images(markdown)
    had_image = bool(_MD_IMAGE_RE.search(text or "") or _MD_IMAGE_RE.search(markdown))
    if not visible:
        visible = "附图" if images or had_image else (markdown or "")
    return visible, images


def _wecom_upload_image_type(content: bytes, content_type: str) -> str | None:
    """长连接图片素材支持 JPG/PNG/GIF。"""
    kind = _wecom_stream_image_type(content, content_type)
    if kind:
        return kind
    if content.startswith((b"GIF87a", b"GIF89a")):
        return "image/gif"
    kind = (content_type or "").split(";", 1)[0].strip().lower()
    if kind in _WECOM_UPLOAD_IMAGE_TYPES:
        return kind
    return None


def wecom_long_connection_outbound(text: str) -> tuple[str, list[tuple[str, bytes]]]:
    """长连接正文去掉图片外链。图片用素材接口另发，流式帧不带 msg_item。"""
    markdown, images = prepare_im_markdown(text or "")
    visible = strip_markdown_images(markdown)
    if not visible:
        had_image = bool(_MD_IMAGE_RE.search(text or "") or _MD_IMAGE_RE.search(markdown))
        visible = "附图" if images or had_image else (markdown or "")
    files: list[tuple[str, bytes]] = []
    extensions = {"image/jpeg": "jpg", "image/png": "png", "image/gif": "gif"}
    for image in images:
        content = image.content or b""
        kind = _wecom_upload_image_type(content, image.content_type)
        if kind is None or len(content) < 5 or len(content) > _MAX_WECOM_STREAM_IMAGE_BYTES:
            continue
        files.append((f"image-{len(files) + 1}.{extensions[kind]}", content))
        if len(files) >= _MAX_WECOM_STREAM_IMAGES:
            break
    return visible, files


def wecom_short_connection_outbound(text: str) -> tuple[str, list[dict]]:
    """短连接正文去掉图片外链，图片改为流式 msg_item。历史仍保留原文。"""
    markdown, images = prepare_im_markdown(text or "")
    items = wecom_stream_image_items(images)
    visible = strip_markdown_images(markdown)
    if not visible:
        had_image = bool(_MD_IMAGE_RE.search(text or "") or _MD_IMAGE_RE.search(markdown))
        visible = "附图" if items or had_image else (markdown or "")
    return visible, items


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
    channel_type = (channel_type or "").strip()

    if channel_type == "feishu":
        visible, feishu_images = feishu_outbound(reply_text or "")
        if visible:
            handler.send_text_reply(visible, sender_id, config)
        image_send_failed = False
        for image in feishu_images:
            try:
                handler.send_image_reply(image, sender_id, config)
            except Exception:
                image_send_failed = True
                logger.exception("feishu image reply failed channel=%s", getattr(handler, "channel_id", None))
        if image_send_failed:
            handler.send_text_reply(FEISHU_IMAGE_FAILED_TEXT, sender_id, config)
        return

    markdown, images = prepare_im_markdown(reply_text or "")

    if channel_type == "dingtalk":
        target = webhook_url or config.get("webhook_url") or ""
        if target and markdown:
            handler.send_message(target, "markdown", {"title": "机器人回复", "text": markdown})
        return

    if channel_type in {"enterprise_wechat", "enterprise_wechat_aibot"}:
        text_body = strip_markdown_images(markdown) if images else markdown
        # 短连接图片走流式 msg_item。这里只发文本，避免 markdown 外链被企微拦截。
        if channel_type == "enterprise_wechat_aibot":
            visible, _items = wecom_short_connection_outbound(reply_text or "")
            handler.send_reply(visible, sender_id, config)
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
